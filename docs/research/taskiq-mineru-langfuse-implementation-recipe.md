# TaskIQ + MinerU + Langfuse 实现配方

> 调研日期：2026-08-04。来源约束：TaskIQ 部分以本地 `.venv` 已安装源码（taskiq 0.12.4 / taskiq-redis 1.2.3，uv.lock 钉版）为准；MinerU 部分联网核实 [mineru.net/apiManage/docs](https://mineru.net/apiManage/docs)；Langfuse 部分联网核实 langfuse.com 官方文档（SDK 未装于 worker venv，版本按基线 4.14.x）。无法联网处标注「训练知识」。
> 性质：实现配方（怎么写），不替代 spec/architecture/ADR。术语遵循 CONTEXT.md 正名。

## 1. TaskIQ（0.12.4，已核对现有 `worker.py`）

### 1.1 Broker 配置（现有代码正确）
```python
from taskiq.middlewares import SmartRetryMiddleware
from taskiq_redis import ListQueueBroker, ListRedisScheduleSource, RedisAsyncResultBackend

_redis_url = "redis://127.0.0.1:6379/0"          # Windows 用 127.0.0.1 避免 ::1 挂起
broker = ListQueueBroker(url=_redis_url, queue_name="medicalrag",
                         max_connection_pool_size=8)      # 至少 workers+1
broker = broker.with_result_backend(RedisAsyncResultBackend(
    redis_url=_redis_url, result_ex_time=3600))          # 默认 keep_results=True 无 TTL，生产须设过期
broker.add_middlewares(SmartRetryMiddleware(
    default_retry_count=3, default_retry_label=True, use_delay_exponent=True,
    max_delay_exponent=60, use_jitter=True,
    schedule_source=ListRedisScheduleSource(url=_redis_url)))  # 真退避必需
```
注意：`RedisAsyncResultBackend` 默认 `PickleSerializer`（非 JSON）。

### 1.2 任务参数：没有 `retries/retry_backoff`，重试走 middleware + labels
- `@broker.task` 只收 `task_name` 与任意 `**labels`，**不收 retry 参数**。重试由 `SimpleRetryMiddleware`/`SmartRetryMiddleware`（含指数退避 `use_delay_exponent`、抖动 `use_jitter`）实现；任务级开关是 labels：`retry_on_error`（默认 False，须显式开）、`max_retries`、`delay`。
- `SmartRetryMiddleware` **不配 `schedule_source` 时 delay 不兑现**（本版本 broker 不消费 `delay` label，退避无效）；配了 `ListRedisScheduleSource` 后经 `schedule_by_time` 延迟投递，**必须有独立 scheduler 进程**。
```python
@broker.task(retry_on_error=True, max_retries=5)
async def run_ingestion_stage(run_id: str, stage: IngestionRunState) -> None: ...
```

### 1.3 启动命令（worker 与 scheduler 是**两个独立进程**）
```bash
taskiq worker medicalrag_worker.worker:broker -w 2 --max-async-tasks 50
taskiq scheduler medicalrag_worker.scheduler:scheduler      # 独立进程，含 cron 分发
```
scheduler 参数：`--update-interval`（默认 60s 拉取 schedule）、`--skip-first-run`、`--tasks-pattern`（默认 `**/tasks.py`）。可嵌入 FastAPI lifespan 时须自行 `await broker.startup()/shutdown()`，生产仍建议独立进程。

### 1.4 cron 调度
`taskiq scheduler` 单独进程 + `ListRedisScheduleSource`（`RedisScheduleSource` 已 deprecated）。动态注册：`await task.schedule_by_cron(source, "*/15 * * * *", *args)`；或声明式 `TaskiqScheduler(broker, sources=[...])` 由 CLI `taskiq scheduler module:obj` 导入（obj 可为实例或工厂函数）。cron 用 `pycron`，每分钟粒度。

### 1.5 稳定 job id / 去重（等价 arq `_job_id`）
`AsyncKicker.with_task_id(task_id)` 设置稳定 `task_id`（默认 `uuid4().hex`，可 `broker.with_id_generator(fn)` 覆盖）。**但 taskiq 无内置去重**——ListQueueBroker 直接 `LPUSH`，同 id 消息照投。去重靠应用侧：Redis `SETNX task_id`（带 TTL）或 PostgreSQL `UNIQUE(ingestion_run_id, stage)` / outbox 唯一约束（ADR 0073 既定方案）。回调去重以 provider `task_id` + `data_id` 为唯一键（ADR 0031）。

## 2. MinerU Cloud API（2026-08-04 联网核实）

- 提交（单文件 URL）：`POST https://mineru.net/api/v4/extract/task`，头 `Authorization: Bearer <token>`，响应 `data.task_id`。核心字段：`url`、`model_version`（`pipeline` 默认 / `vlm` / `MinerU-HTML`）、`is_ocr`（默认 false）、`enable_formula`（默认 true）、`enable_table`（默认 true）、`language`（默认 `ch`）、`data_id`（≤128，`[A-Za-z0-9_.-]`）、`callback`、`seed`、`extra_formats`（`docx`/`html`/`latex`，md+json 恒含）、`page_ranges`（如 `"2,4-6"`）、`no_cache`。
- 本地文件走签名上传：`POST /api/v4/file-urls/batch` → `data.batch_id` + `file_urls[]`，再 `PUT <file_url>` 原始文件体，解析自动开始；`POST /api/v4/extract/task/batch` 为 URL 批（≤50 文件）。
- 轮询：`GET /api/v4/extract/task/{task_id}`（单）或 `GET /api/v4/extract-results/batch/{batch_id}`（批）；`data.state ∈ {waiting-file,pending,running,done,failed,converting}`，done 含 `full_zip_url`。
- **回调**：`callback` + `seed` 一起提交；回调 POST 两参数 `checksum` + `content`（JSON 字符串，等于查询响应的 data）；**`checksum = SHA256(uid + seed + content)`**（uid 来自个人中心）。非 200 时 MinerU 重试最多 5 次后放弃。对账策略：回调先验 checksum → 幂等落库 → 缺失/失败任务走 bounded 退避轮询（ADR 0031）。
- 支持格式：PDF、PNG/JPG/JPEG/JP2/WEBP/GIF/BMP、Doc/Docx、Ppt/PPTx、Xls/Xlsx、HTML（MinerU-HTML 模型）；单文件 ≤200MB / ≤200 页。**`.md`/`.txt` 不在 MinerU 范围**，走确定性文本规范化器（ADR 0032），与应用允许清单（ADR 0030：.docx/.pptx/.xlsx/.pdf/.md/.txt/.png/.jpg/.jpeg）对齐。
- 错误码：鉴权 `A0202` token 错误 / `A0211` 过期；服务（负数）`-60001` 生成上传 URL 失败 · `-60002` 类型识别失败 · `-60005` >200MB · `-60006` >200 页 · `-60007` 模型服务不可用 · `-60009` 队列满 · `-60010` 解析失败 · `-60012` 任务不存在 · `-60018` 日配额耗尽 · `-60019` HTML 配额不足；Agent API `-30001`/`-30002`/`-30003`/`-30004`。
- caveat：当前文档**没有 `v_speed` 参数**（仅 `model_version`）；旧版文档曾出现 `v_speed`，若部署平台支持则视为「训练知识」，以所购 API 版本文档为准。

## 3. Langfuse Python SDK v4（4.14.x，langfuse.com 官方文档）

### 3.1 fail-open
官方语义：「SDK errors are caught and logged, cannot break your application」；客户端基于 OTel 异步导出，队列满丢 span 不阻塞业务。初始化/导出/`flush()` 失败只记脱敏日志与降级指标，不改变 Aegra run 结果（ADR 0059）。

### 3.2 `mask_otel_spans`（官方签名）
```python
from langfuse.types import MaskOtelSpansParams, MaskOtelSpansResult
def mask_otel_spans(*, params: MaskOtelSpansParams) -> MaskOtelSpansResult | None:
    # params.spans: dict[OtelSpanIdentifier, OtelSpanData]（attributes/resource_attributes 只读）
    return MaskOtelSpansResult(span_patches=[
        OtelSpanPatch(delete_attributes=["gen_ai.prompt", ...],
                      set_attributes={"request_id": "safe"})])  # set 在 delete 之后
```
约束：只能改 span attributes（不可改 name/ID/parent/resource/events/links）；在 OTel batch 线程同步执行，须确定性、快速、禁网络/异步 I/O；hook 抛异常或返回非法结果 → **整批丢弃**；单 patch 非法只丢该 span。仅影响本 Langfuse client 的导出，其他 exporter 拿不到未脱敏副本——脱敏须在 exporter 入口前完成。

### 3.3 采样
`LANGFUSE_SAMPLE_RATE` 环境变量或 `Langfuse(sample_rate=0.3)`，取值 `[0,1]`，默认 `1`；**trace 级**采样：trace 被采中则其 observations/scores 全发，否则全不发。`Langfuse.__init__` 另支持 `flush_at=512`、`flush_interval=5`、`environment`（env `LANGFUSE_TRACING_ENVIRONMENT`）、`release`、`tracer_provider`、`span_exporter`、`should_export_span`。

### 3.4 自托管 OTLP（ADR 0062/0072）
```bash
OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:3000/api/public/otel"
OTEL_EXPORTER_OTLP_HEADERS="Authorization=Basic ${AUTH},x-langfuse-ingestion-version=4"
```
仅 OTLP over HTTP（JSON/protobuf，无 gRPC）；**`x-langfuse-ingestion-version: 4` 为必需头**（否则摄取延迟最多 10 分钟）；self-hosted server 需 ≥3.63.0。

### 3.5 测试侧模拟导出（应用不初始化 client，但契约测试可）
官方构造参数 `span_exporter`/`tracer_provider` 就是为注入自定义 exporter 设计：
```python
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
exporter = InMemorySpanExporter()
client = Langfuse(base_url="http://127.0.0.1:3000", span_exporter=exporter,
                  mask_otel_spans=..., should_export_span=...)
# 生成 observation → client.flush() → 断言 exporter.get_finished_spans()
# fail-open：mock exporter.export 抛异常 / base_url 指向不可达地址，断言业务不抛
```
契约断言点：v4 ingestion 头、脱敏后无敏感 attribute、采样完整性、导出失败不抛。测试用合成非医疗数据，不依赖真实 Langfuse（ADR 0059 第 9 条）。

## 来源

- TaskIQ：本地 `.venv/Lib/site-packages/taskiq`（0.12.4，`decor.py`/`abc/broker.py`/`kicker.py`/`middlewares/*_retry_middleware.py`/`scheduler/`/`cli/worker|scheduler`）与 `taskiq_redis`（1.2.3，`redis_broker.py`/`redis_backend.py`/`schedule_source.py`/`list_schedule_source.py`）；官方站点 https://taskiq.ai 。
- MinerU：https://mineru.net/apiManage/docs （2026-08-04）。
- Langfuse：https://langfuse.com/docs/observability/features/masking 、/features/sampling 、/sdk/python 、https://python.reference.langfuse.com/langfuse 、/self-hosting/deployment/docker-compose 、/integrations/native/opentelemetry 。
- 项目对齐：`docs/adr/0031`、`0032`、`0030`、`0059`、`0062`、`0063`、`0072`、`0073`；`apps/worker/src/medicalrag_worker/worker.py`。
