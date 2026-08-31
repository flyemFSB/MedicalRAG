# Langfuse 最新可观测性集成调研

- 调研日期：2026-07-27
- 适用范围：MedicalRAG 的 Python/FastAPI、后台 worker、LangChain/LangGraph、Aegra 与 Agent Protocol v2。
- 来源约束：只使用 Langfuse、LangChain、LangGraph、FastAPI、Aegra、OpenTelemetry 官方文档、官方仓库源码或官方包索引；没有使用博客、转载或社区文章。
- 文档性质：集成研究与职责建议，不包含业务实现，也不替代 `docs/spec.md`、`docs/architecture.md` 或现有 ADR。

> **计划变更（2026-08-01）：** 本文是历史调研快照。按 [ADR 0063](../adr/0063-arq-replaces-rocketmq-as-the-durable-job-queue.md) 消息总线已从 Apache RocketMQ 更换为 arq，按 [ADR 0064](../adr/0064-uv-manages-python-314-runtime.md) Python 基线已提高到 3.14。正文中与 RocketMQ、Python 3.12 相关的结论已被上述 ADR 取代。

> **本项目最终决策**：Aegra 的官方 Langfuse 集成是唯一的 AI/RAG Trace 路径。FastAPI、Worker 和 domain service 不初始化 Langfuse client，不添加应用级 OpenTelemetry/Collector/Tempo/Grafana，也不创建手动 Trace。它们使用结构化日志、metrics、health checks 和 PostgreSQL 业务 run/audit 记录；PostgreSQL 可保存可选的 `langfuse_trace_id`。本文中 FastAPI/Worker 手动 observation、OpenTelemetry 和 OTLP 内容是官方能力或候选方案调研，不是目标实现路径。

## 结论摘要

1. **当前 Python 主线是 Langfuse SDK v4。** 截至 2026-07-27，官方 PyPI 的最新版本为 `4.14.1`，要求 Python `>=3.10,<4.0`；新代码使用 `get_client()`、`start_as_current_observation()`、`@observe` 和统一的 observation API。`start_span()`、`start_generation()` 等 v3 写法只应出现在迁移兼容代码中。[官方来源（访问日期：2026-07-27）：PyPI](https://pypi.org/pypi/langfuse/json)、[Python SDK README](https://raw.githubusercontent.com/langfuse/langfuse-python/main/README.md)、[v3 到 v4 迁移](https://langfuse.com/docs/observability/sdk/upgrade-path/python-v3-to-v4.md)
2. **LangChain/LangGraph 官方 `CallbackHandler` 是可用能力，但本项目不启用它。** Aegra 已经为托管的 graph/LLM 调用提供唯一的官方 Langfuse ingestion owner；应用不得再叠加 callback 或第二个 exporter。[官方来源（访问日期：2026-07-27）：Langfuse LangChain 集成](https://langfuse.com/integrations/frameworks/langchain.md)、[Aegra observability](https://docs.aegra.dev/guides/observability.md)
3. **FastAPI 请求和独立 worker 也可以手动补 Langfuse observation，但不是本项目路径。** Langfuse SDK/exporter 仅随 Aegra runtime 配置；API/Worker 使用结构化日志、metrics 和 health checks。[官方来源（访问日期：2026-07-27）：Langfuse instrumentation](https://langfuse.com/docs/observability/sdk/instrumentation.md)、[FastAPI Background Tasks](https://fastapi.tiangolo.com/tutorial/background-tasks/)
4. **OTLP 入口当前是 HTTP，不是 gRPC。** Langfuse native OTLP 使用 `/api/public/otel`，需要 Cloud/self-host 对应 endpoint 和 Basic Auth；发送 v4 数据应设置 `x-langfuse-ingestion-version: 4`，否则官方提示可能延迟约 10 分钟。[官方来源（访问日期：2026-07-27）：Langfuse OpenTelemetry 集成](https://langfuse.com/integrations/native/opentelemetry.md)
5. **Docker Compose 是 self-hosted 的简单 local/VM 路径，不是 HA、水平扩展或备份方案。** SaaS 的 server version 由 Langfuse 管理并持续部署；self-hosted 需要自行升级、备份、管理 secrets 和校验 Server/SDK 兼容矩阵。[官方来源（访问日期：2026-07-27）：Docker Compose 部署](https://langfuse.com/self-hosting/deployment/docker-compose.md)、[版本管理](https://langfuse.com/self-hosting/upgrade/versioning.md)
6. **医疗内容默认按不采集处理。** 在入口关闭 decorator 的 input/output 捕获；需要保留结构时只传脱敏后的 ID、数量、状态和版本。Langfuse 的 masking 只影响 Langfuse exporter，因此必须在 Aegra exporter 入口前完成白名单和脱敏。[官方来源（访问日期：2026-07-27）：Langfuse masking](https://langfuse.com/docs/observability/features/masking.md)、[instrumentation](https://langfuse.com/docs/observability/sdk/instrumentation.md)
7. **Agent Protocol v2 是线程/命令/SSE 传输合同，不是 tracing backend。** Aegra 是唯一的 graph/LLM Langfuse ingestion owner；API、Worker 和 domain service 不创建第二个 Trace 路径。[官方来源（访问日期：2026-07-27）：Aegra observability](https://docs.aegra.dev/guides/observability.md)、[Aegra streaming](https://docs.aegra.dev/guides/streaming.md)、[Aegra 文档索引](https://docs.aegra.dev/llms.txt)

## 事实与建议的边界

本文使用以下标记：

| 标记 | 含义 |
| --- | --- |
| **官方事实** | 上游官方文档、官方仓库源码或官方包索引明确描述的行为。 |
| **本项目建议** | 结合 MedicalRAG 的医疗数据敏感性、Aegra 运行时和 worker 边界推导的工程决策，不是 Langfuse 强制要求。 |
| **版本 caveat** | 版本、默认值或兼容行为可能变化，实施时必须重新锁定依赖并做合同测试。 |

## 1. Python SDK 当前 API

### 1.1 版本与初始化

**官方事实**：截至访问日，`langfuse` PyPI 最新版本为 `4.14.1`，Python 要求为 `>=3.10,<4.0`。官方 SDK v4 基于 OpenTelemetry，使用异步请求，SDK 错误会被捕获并记录，不应破坏应用。Langfuse Cloud 自动满足 SDK 的最低 server 要求；self-hosted 对 Python SDK v3/v4 的最低 server 版本为 `3.63.0`。新 v4 的 `api.observations`、`api.metrics` 等接口需要 Langfuse v4 server；self-hosted v3 必须使用 legacy API。[官方来源（访问日期：2026-07-27）：[PyPI 元数据](https://pypi.org/pypi/langfuse/json)、[SDK overview](https://langfuse.com/docs/observability/sdk/overview.md)、[SDK README](https://raw.githubusercontent.com/langfuse/langfuse-python/main/README.md)]

推荐的进程级初始化是单例客户端：

```python
from langfuse import get_client

langfuse = get_client()
```

客户端从环境变量读取 `LANGFUSE_PUBLIC_KEY`、`LANGFUSE_SECRET_KEY` 和可选的 `LANGFUSE_BASE_URL`。也可以显式构造 `Langfuse(...)`，用于设置 `environment`、`release`、`sample_rate`、`flush_at`、`flush_interval`、`mask_otel_spans`、`should_export_span`、自定义 `tracer_provider` 或 `span_exporter` 等选项。采样和 tracing 开关应放在 client/环境变量层，而不是 LangChain callback 构造器。[官方来源（访问日期：2026-07-27）：[SDK overview](https://langfuse.com/docs/observability/sdk/overview.md)、[Python API reference](https://python.reference.langfuse.com/langfuse.html)、[LangChain integration](https://langfuse.com/integrations/frameworks/langchain.md)]

**本项目建议**：只有 Aegra runtime 初始化 Langfuse client，密钥只从 secret 注入；FastAPI、Worker 和 `packages/infra` 不创建 Langfuse client。把 `environment`、`release` 和 `sample_rate` 固化为 Aegra 部署配置，并为 Cloud 与 self-hosted 使用不同的配置检查。

### 1.2 trace、span、generation 的 v4 写法

**官方事实**：v4 用统一的 `start_observation()` / `start_as_current_observation()` 创建 observation，通过 `as_type` 区分 `span`、`generation`、`embedding`、`agent`、`tool`、`chain`、`retriever`、`evaluator` 和 `guardrail`。在当前推荐模型中，一个根 observation 承载 trace 的入口语义，子 observation 形成层级；`start_as_current_observation()` 会建立当前 OTEL context，手动 `start_observation()` 不会自动改变当前 context，必须显式 `.end()`。[官方来源（访问日期：2026-07-27）：[instrumentation](https://langfuse.com/docs/observability/sdk/instrumentation.md)、[Python API reference](https://python.reference.langfuse.com/langfuse.html)、[v3 到 v4 迁移](https://langfuse.com/docs/observability/sdk/upgrade-path/python-v3-to-v4.md)]

```python
from langfuse import get_client

langfuse = get_client()

with langfuse.start_as_current_observation(
    as_type="span",
    name="process-request",
    input={"request_id": "safe-id"},
) as span:
    with langfuse.start_as_current_observation(
        as_type="generation",
        name="llm-response",
        model="gpt-5.6",
        model_parameters={"temperature": 0},
        input={"prompt_ref": "safe-prompt-id"},
    ) as generation:
        # 只写入已脱敏的结果或摘要。
        generation.update(output={"status": "completed"})

langfuse.flush()
```

`start_as_current_observation()` 的 context manager 会在退出时结束 observation；长生命周期或跨回调边界的手动 observation 使用 `.update(...)` 后显式 `.end()`。可从当前 context 读取 `get_current_trace_id()`、`get_current_observation_id()`；`trace_context={"trace_id": ..., "parent_span_id": ...}` 可把下游 observation 接到已有 trace。[官方来源（访问日期：2026-07-27）：[Python API reference](https://python.reference.langfuse.com/langfuse.html)、[instrumentation](https://langfuse.com/docs/observability/sdk/instrumentation.md)]

### 1.3 event、score 与 metadata

**官方事实**：`create_event(...)` 创建瞬时的 EVENT observation，支持 `trace_context`、`name`、`input`、`output`、`metadata`、`version`、`level` 和 `status_message`；它不是需要 `.end()` 的长 span。`create_score(...)` 支持 `name`、`value`、`trace_id`、`observation_id`、`score_id`、`data_type`、`comment`、`config_id`、`metadata`、`timestamp` 和 `environment`。在已有当前 context 时，也可以使用 `score_current_span(...)` 或 `score_current_trace(...)`。[官方来源（访问日期：2026-07-27）：[Python API reference](https://python.reference.langfuse.com/langfuse.html)、[LangChain integration](https://langfuse.com/integrations/frameworks/langchain.md)]

```python
langfuse.create_event(
    name="retrieval.completed",
    input={"query_ref": "safe-query-id"},
    output={"document_count": 8},
)

langfuse.create_score(
    name="answer_quality",
    value=0.9,
    trace_id=langfuse.get_current_trace_id(),
    data_type="NUMERIC",
)
```

`propagate_attributes(...)` 可传播 `user_id`、`session_id`、`metadata`、`version`、`environment` 和 `trace_name`；`as_baggage=True` 会把值放进 outbound HTTP headers，官方明确警告不要把敏感值放入 baggage。v4 推荐把 trace-level input/output 直接放在根 observation；旧的 `set_trace_io()` / `set_current_trace_io()` 已 deprecated。[官方来源（访问日期：2026-07-27）：[instrumentation](https://langfuse.com/docs/observability/sdk/instrumentation.md)、[Python API reference](https://python.reference.langfuse.com/langfuse.html)]

## 2. LangChain 与 LangGraph

**官方事实**：Langfuse 当前 Python 集成使用：

```python
from langfuse import get_client
from langfuse.langchain import CallbackHandler

langfuse = get_client()
langfuse_handler = CallbackHandler()

result = agent.invoke(
    {"messages": [{"role": "user", "content": "..."}]},
    config={"callbacks": [langfuse_handler]},
)
```

LangGraph 使用相同方式，把 handler 放进 invocation 的 `config`。该 callback 捕获 LangChain 的 LLM、tools、retrievers 等调用；`langfuse_user_id`、`langfuse_session_id`、`langfuse_tags` 可以通过 LangChain metadata 传入，也可以使用 `propagate_attributes()`。[官方来源（访问日期：2026-07-27）：[Langfuse LangChain 集成](https://langfuse.com/integrations/frameworks/langchain.md)、[LangChain callbacks](https://docs.langchain.com/oss/python/langchain/callbacks)、[LangGraph overview](https://docs.langchain.com/oss/python/langgraph/overview)]

**版本 caveat**：当前 import 是 `from langfuse.langchain import CallbackHandler`；旧的 `from langfuse.callback import CallbackHandler` 是旧路径。v4 的 callback handler 不再接受旧的 `sample_rate`、`tracing_enabled` 等构造参数，这些应配置在 Langfuse client 或环境变量中；v3 的 `CallbackHandler(update_trace=...)` 也已移除。[官方来源（访问日期：2026-07-27）：[Langfuse LangChain 集成](https://langfuse.com/integrations/frameworks/langchain.md)、[v3 到 v4 迁移](https://langfuse.com/docs/observability/sdk/upgrade-path/python-v3-to-v4.md)]

**本项目建议**：本项目不在 LangChain/LangGraph 入口注入 `CallbackHandler`。Aegra-hosted graph/LLM 只由 Aegra 官方 Langfuse integration 发送到 Langfuse；API/Worker 不创建 Langfuse observation，也不添加应用级 tracing backend。以下 callback 代码仅用于说明官方能力，不是目标实现：

```python
with langfuse.start_as_current_observation(
    as_type="span",
    name="medicalrag.request",
    input={"request_id": "safe-id"},
) as request_span:
    agent.invoke(input_data, config={"callbacks": [langfuse_handler]})
```

该建议由 Langfuse 的官方 callback 捕获范围和 Aegra 的官方 OTEL instrumentation 叠加推导而来。[官方来源（访问日期：2026-07-27）：[Langfuse LangChain 集成](https://langfuse.com/integrations/frameworks/langchain.md)、[Aegra observability](https://docs.aegra.dev/guides/observability.md)]

## 3. FastAPI 与后台 worker 的手动 tracing

### 3.1 FastAPI 请求（非目标路径）

**官方事实**：Langfuse 提供 context manager、`@observe()` 和 manual `start_observation()` 三种 instrumentation 方式。`@observe()` 自动采集被装饰函数的 input/output、计时和错误，并支持 `as_type="generation"`；可用 `capture_input=False`、`capture_output=False` 或环境变量关闭 I/O 捕获。[官方来源（访问日期：2026-07-27）：[Langfuse instrumentation](https://langfuse.com/docs/observability/sdk/instrumentation.md)]

**本项目决策**：FastAPI 不使用 Langfuse manual observation，也不使用应用级 OpenTelemetry tracing。PostgreSQL 只记录业务 run/audit 状态和可选的 `langfuse_trace_id`；结构化日志、metrics 和 health checks 记录 API 诊断，并遵守同样的脱敏规则。以下代码仅保留为官方 API 研究示例：

```python
from langfuse import get_client

langfuse = get_client()


async def handle_query(request_id: str, question: str) -> dict:
    with langfuse.start_as_current_observation(
        as_type="span",
        name="medicalrag.api.query",
        input={"request_id": request_id, "question_chars": len(question)},
    ) as span:
        result = await run_domain_flow(question)
        span.update(output={"status": "completed"})
        return result
```

上例只展示 observation 边界；实际脱敏必须在把值交给 SDK 前完成，因为 export-stage masking 不是所有 exporter 的全局拦截器。[官方来源（访问日期：2026-07-27）：[Langfuse masking](https://langfuse.com/docs/observability/features/masking.md)、[OpenTelemetry instrumentation](https://opentelemetry.io/docs/languages/python/instrumentation/)]

### 3.2 后台任务与 worker（非目标路径）

**官方事实**：FastAPI 的 `BackgroundTasks` 在响应发送后执行，适合小型任务；FastAPI 官方 caveat 指出，重型计算或需要多进程/多服务器时应考虑 Celery 等更大的工具和消息/任务队列。Langfuse 官方则指出 background work、短生命周期脚本、serverless 和 worker 需要在结束时 `flush()` 或 `shutdown()`。[官方来源（访问日期：2026-07-27）：[FastAPI Background Tasks](https://fastapi.tiangolo.com/tutorial/background-tasks/)、[Langfuse instrumentation](https://langfuse.com/docs/observability/sdk/instrumentation.md)]

**本项目决策**：Worker 不使用 Langfuse manual observation，也不使用应用级 OpenTelemetry tracing。`BackgroundTasks` 只用于不重要且很短的同进程收尾工作；可重试、耗时或需要持久性的 MedicalRAG job 由现有队列 worker 承担，并通过结构化日志、metrics 和 health checks 记录诊断状态，业务状态写入 PostgreSQL。以下 Langfuse 示例不属于目标实现。

```python
def run_worker_job(job_id: str, parent_context: dict | None = None) -> None:
    langfuse = get_client()
    observation = langfuse.start_observation(
        as_type="span",
        name="medicalrag.worker.job",
        input={"job_id": job_id},
        trace_context=parent_context,
    )
    try:
        process_job(job_id)
        observation.update(output={"status": "completed"})
    except Exception:
        # 状态消息只写非敏感错误类别；业务异常仍交给 job 重试/死信策略。
        observation.update(level="ERROR", status_message="worker_job_failed")
        raise
    finally:
        observation.end()
        langfuse.flush()
```

手动 observation 必须显式结束；`flush()` 会等待队列处理，`shutdown()` 会 flush 并等待后台线程退出。正常退出虽有 atexit 处理，但服务 shutdown、worker graceful stop 和强制终止边界仍应显式调用。[官方来源（访问日期：2026-07-27）：[Python API reference](https://python.reference.langfuse.com/langfuse.html)、[Langfuse instrumentation](https://langfuse.com/docs/observability/sdk/instrumentation.md)]

## 4. OpenTelemetry 与 OTLP

### 4.1 Langfuse native OTLP

**官方事实**：Langfuse Cloud OTLP endpoint 为 `https://cloud.langfuse.com/api/public/otel`；self-hosted local 示例为 `http://localhost:3000/api/public/otel`，官方文档标注 self-hosted server `>=3.22.0`。认证使用 `Authorization=Basic ...`；signal-specific traces endpoint 为 `/api/public/otel/v1/traces`。当前支持 OTLP over HTTP 的 JSON 和 protobuf，不支持 gRPC。设置 `x-langfuse-ingestion-version: 4` 才能让 v4 数据实时进入；不设置时官方提示可能延迟最多约 10 分钟。OTLP 是 legacy `POST /api/public/ingestion` 的替代路径。[官方来源（访问日期：2026-07-27）：[Langfuse OpenTelemetry 集成](https://langfuse.com/integrations/native/opentelemetry.md)]

示意配置：

```bash
OTEL_EXPORTER_OTLP_ENDPOINT="https://cloud.langfuse.com/api/public/otel"
OTEL_EXPORTER_OTLP_HEADERS="Authorization=Basic ${AUTH_STRING},x-langfuse-ingestion-version=4"
```

### 4.2 Python OpenTelemetry 手动模型（候选方案，当前不采用）

**官方事实**：OpenTelemetry Python 手动 tracing 的基本模型是配置 `TracerProvider`、`BatchSpanProcessor` 和 exporter，再通过 `trace.set_tracer_provider()`、`trace.get_tracer()`、`tracer.start_as_current_span()` 建立 context；span 可以设置 attributes、添加 event、记录 exception 和设置 status。默认 propagation 使用 W3C Trace Context 与 W3C Baggage。[官方来源（访问日期：2026-07-27）：[OpenTelemetry Python instrumentation](https://opentelemetry.io/docs/languages/python/instrumentation/)、[OTLP specification](https://opentelemetry.io/docs/specs/otlp/)]

**本项目建议**：Aegra 是唯一的 Langfuse provider/exporter owner。FastAPI、Worker 和 `packages/infra` 不创建 Langfuse exporter，也不建立应用级 OpenTelemetry tracing；它们只使用结构化日志、metrics 和 health checks。不得让 Langfuse callback、第二个 Langfuse exporter 和 Aegra instrumentation 同时捕获同一 graph/LLM observation。

### 4.3 版本与兼容注意事项

**官方事实**：Langfuse Python SDK 当前 `pyproject.toml` 要求 `opentelemetry-api>=1.33.1,<2`、`opentelemetry-sdk>=1.33.1,<2` 和 OTLP HTTP exporter `>=1.33.1,<2`；Aegra 当前官方 `pyproject.toml` 为 Python `>=3.12`，要求 `opentelemetry-api/sdk/exporter-otlp>=1.39.1`，并使用 `openinference-instrumentation-langchain>=0.1.58`。因此两者的元数据约束存在 `>=1.39.1,<2` 的交集，但这不是运行时合同的证明，仍需使用 lockfile 和实际启动/导出测试验证 provider、instrumentation scope 与 exporter 行为。[官方来源（访问日期：2026-07-27）：[Langfuse pyproject](https://raw.githubusercontent.com/langfuse/langfuse-python/main/pyproject.toml)、[Aegra pyproject](https://raw.githubusercontent.com/aegra/aegra/main/libs/aegra-api/pyproject.toml)]

**版本 caveat**：Langfuse server 与 SDK 独立版本化；官方 server 版本策略称每个 server major 通常面向当前及前一 SDK major，但 v4 transition 是例外，应查当前 matrix。self-hosted 的新 SDK API 还要满足前述 server minimum；Cloud server 由 Langfuse 管理。[官方来源（访问日期：2026-07-27）：[Langfuse versioning](https://langfuse.com/self-hosting/upgrade/versioning.md)、[SDK overview](https://langfuse.com/docs/observability/sdk/overview.md)]

## 5. self-hosted Docker Compose 与 SaaS 边界

**官方事实**：Langfuse 官方 Docker Compose 是 local/VM 上最简单的 self-hosted 试用/部署路径，需要 Docker、Docker Compose 并替换 compose 中的 secrets。官方明确指出该 setup 缺少 high availability、scaling 和 backup functionality；不支持水平扩展（除非自行增加 load balancer），通常只能垂直扩展。高可用或高吞吐推荐 Kubernetes/Helm。[官方来源（访问日期：2026-07-27）：[Docker Compose deployment](https://langfuse.com/self-hosting/deployment/docker-compose.md)]

**官方事实**：Cloud 持续部署最新 server，server version 由 Langfuse 管理；Cloud 可能领先最新 self-hosted release。self-hosted 需要自行管理升级、数据、备份、secrets、资源和 server/SDK compatibility matrix。[官方来源（访问日期：2026-07-27）：[Langfuse versioning](https://langfuse.com/self-hosting/upgrade/versioning.md)、[Docker Compose deployment](https://langfuse.com/self-hosting/deployment/docker-compose.md)]

**本项目建议**：本地开发或单机验证可使用官方 Compose；生产若有 HA、吞吐、灾备、数据保留或医疗合规要求，不应把 Compose 本身当作满足条件的生产拓扑。SaaS/self-hosted 的选择应由数据出境、保留、运维能力和灾备责任决定，而不是由 SDK 代码决定。

## 6. 脱敏、采样、fail-open、flush 与错误处理

### 6.1 Input/output 脱敏

**官方事实**：`@observe` 默认可以捕获函数 input/output，且支持 `capture_input=False`、`capture_output=False`；环境变量 `LANGFUSE_OBSERVE_DECORATOR_IO_CAPTURE_ENABLED` 也可控制 decorator I/O capture。Python 新项目推荐使用 `mask_otel_spans`，而不是旧 `mask`：它在 export stage 处理 Langfuse SDK 与 third-party instrumentation 导出的 raw OTEL span attributes。[官方来源（访问日期：2026-07-27）：[Langfuse masking](https://langfuse.com/docs/observability/features/masking.md)、[Langfuse instrumentation](https://langfuse.com/docs/observability/sdk/instrumentation.md)]

**官方事实**：`mask_otel_spans` 只能修改 span attributes，不能修改 name、IDs、parent、resource、events 或 links；通常在 OTEL batch processor worker thread 执行，`flush()`/shutdown 时也可能在调用线程执行。hook 必须 deterministic、快速，不能做网络调用、异步 I/O 或长重试。hook 抛异常或返回无效整体结果时，整个 export batch 会被丢弃；单个 patch 无效时只丢对应 span。[官方来源（访问日期：2026-07-27）：[Langfuse masking](https://langfuse.com/docs/observability/features/masking.md)]

**关键边界**：Langfuse `mask_otel_spans` 只保护 Langfuse exporter；若同一 spans 同时被 Aegra 或其他 OTEL exporter 发出，其他 exporter 仍可能拿到未脱敏副本。[官方来源（访问日期：2026-07-27）：[Langfuse masking](https://langfuse.com/docs/observability/features/masking.md)、[Aegra observability](https://docs.aegra.dev/guides/observability.md)]

**本项目建议**：在 Aegra Langfuse exporter 入口之前先做结构化 redaction；默认关闭原始 prompt、医疗问题、检索片段、模型原文 output 和完整 tool arguments。允许保留的字段应限于不可逆或低敏的稳定 ID、长度/count、模型名、版本、耗时、状态和错误类别。API/Worker 的日志和 metrics 也必须执行同等脱敏；不要把 `user_id`、session 内容或 prompt 放入任何跨边界 metadata。[官方来源（访问日期：2026-07-27）：[Langfuse masking](https://langfuse.com/docs/observability/features/masking.md)、[instrumentation](https://langfuse.com/docs/observability/sdk/instrumentation.md)]

### 6.2 Sampling

**官方事实**：`LANGFUSE_SAMPLE_RATE` 或 `Langfuse(sample_rate=...)` 设置 `0..1` 的 trace-level sampling，默认值为 `1`。一个 trace 被采中时，其 observations 和 scores 一并发送；未采中时，整条 trace 的 spans、generations 和 scores 都不发送。[官方来源（访问日期：2026-07-27）：[Langfuse sampling](https://langfuse.com/docs/observability/features/sampling.md)]

**官方事实**：v4 有 smart default span filter，默认保留 Langfuse SDK、GenAI/LLM 和已知 LLM instrumentation scopes；过滤 parent 可能产生 orphaned children。自定义 `should_export_span` 会替换默认过滤器，如果只是扩展默认规则，应组合 `is_default_export_span`；`blocked_instrumentation_scopes` 仍兼容但已 deprecated。[官方来源（访问日期：2026-07-27）：[Langfuse advanced features](https://langfuse.com/docs/observability/sdk/advanced-features.md)、[v3 到 v4 迁移](https://langfuse.com/docs/observability/sdk/upgrade-path/python-v3-to-v4.md)]

**本项目建议**：生产先用 trace-level 采样控制成本，再保留错误、超时、合规审计所需的低敏业务计数；不要误把 sampling 当作脱敏。Aegra 的 trace sampling 与 Langfuse 的 trace sampling 同时启用时，需用合同测试确认 parent/child 是否完整，避免一方留下 orphaned children。

### 6.3 Fail-open、flush、超时和错误

**官方事实**：Langfuse SDK 的官方设计是捕获并记录 SDK errors，不能让 SDK 错误破坏应用；SDK 通过异步请求发送数据。`flush()` 阻塞等待队列处理，`shutdown()` 会 flush 并等待后台线程退出。OpenTelemetry BatchSpanProcessor 使用有界队列/批量导出语义，队列满时可以丢弃 span，exporter 不应无限阻塞，ForceFlush/Shutdown 有超时语义。[官方来源（访问日期：2026-07-27）：[SDK overview](https://langfuse.com/docs/observability/sdk/overview.md)、[Langfuse instrumentation](https://langfuse.com/docs/observability/sdk/instrumentation.md)、[OTEL trace SDK specification](https://opentelemetry.io/docs/specs/otel/trace/sdk/)、[OTEL error handling](https://opentelemetry.io/docs/specs/otel/error-handling/)]

**本项目建议**：Aegra 的 Langfuse 初始化、mask、export、flush 失败只记录非敏感结构化日志/降级指标，不改变 Agent run 的业务结果；API/Worker 的业务流程和 PostgreSQL 业务记录不依赖 Langfuse。禁止在 Aegra 请求路径对远端 Langfuse 做无界同步等待或无限重试；对 graceful shutdown 使用有界 flush/shutdown timeout，允许丢失低优先级 Langfuse observation。

## 7. Aegra、Agent Protocol 与重复 tracing

### 7.1 官方边界

**官方事实**：Aegra 是 self-hosted Agent Protocol server，并通过 OpenTelemetry 向任意 OTLP backend 开放 tracing。其 observability 文档说明 Aegra 使用 OTEL 做 observability，可配置 Langfuse、Phoenix 或 generic OTLP，并可用 `OTEL_TARGETS="LANGFUSE,PHOENIX"` fan-out；Aegra 使用 LangChain OpenInference instrumentation、singleton provider 和多个 `BatchSpanProcessor` exporter，run metadata 会写入 root OTEL span。[官方来源（访问日期：2026-07-27）：[Aegra 文档索引](https://docs.aegra.dev/llms.txt)、[Aegra observability](https://docs.aegra.dev/guides/observability.md)、[Aegra 官方 pyproject](https://raw.githubusercontent.com/aegra/aegra/main/libs/aegra-api/pyproject.toml)]

**官方事实**：Agent Protocol v2 的 streaming 是 thread-scoped SSE 和 commands，典型路径为 `POST /threads/{thread_id}/commands`、`POST /threads/{thread_id}/stream/events`，wire envelope 包含 `type`、`seq`、`event_id`、`method` 和 `params`。这属于 transport/control stream；Aegra 文档明确将自己的 OTEL tracing 与 Agent Protocol streaming API 分开。[官方来源（访问日期：2026-07-27）：[Aegra streaming](https://docs.aegra.dev/guides/streaming.md)、[Aegra observability](https://docs.aegra.dev/guides/observability.md)]

### 7.2 是否重复、如何定职责

**结论**：会重复，但不是 Agent Protocol 与 Langfuse 传输协议重复；只有在 Aegra 已经用 OTEL 捕获同一 graph/LLM invocation 并发送到 Langfuse，同时应用又对该 invocation 添加 `CallbackHandler` 或另一个 Langfuse OTLP exporter 时，才会出现重复 observations/generations。这是根据两套官方 instrumentation/exporter 合同推导的工程判断。[官方来源（访问日期：2026-07-27）：[Langfuse LangChain 集成](https://langfuse.com/integrations/frameworks/langchain.md)、[Aegra observability](https://docs.aegra.dev/guides/observability.md)、[OpenTelemetry Python instrumentation](https://opentelemetry.io/docs/languages/python/instrumentation/)]

推荐的职责矩阵：

| 层 | 唯一职责 |
| --- | --- |
| Agent Protocol v2 | browser 与 Aegra 之间的 thread/run/command/SSE wire contract、重连游标和 HITL 控制。 |
| Aegra 官方 Langfuse integration | Aegra 托管的 graph runtime、LangChain/LangGraph 子调用和 run/thread metadata；唯一导出到 Langfuse 的路径。 |
| Langfuse | AI/RAG Trace 存储、LLM/agent 分析、evaluation 和 score；不是业务状态或 Agent Protocol source of truth。 |
| FastAPI/Worker diagnostics | 使用结构化日志、metrics 和 health checks 记录 request/domain/job；PostgreSQL 只记录业务 run/audit；不初始化 Langfuse，也不重复记录 Aegra 的 prompt、generation 或 tool。 |
| MedicalRAG 业务审计/运行状态 | 继续由应用自己的数据库和业务合同负责；Langfuse observation 不能替代业务 source of truth。 |

这套划分以 Agent Protocol 的 transport 语义、Aegra 的 OTEL ownership 和 Langfuse 的 observability 语义为依据。[官方来源（访问日期：2026-07-27）：[Aegra streaming](https://docs.aegra.dev/guides/streaming.md)、[Aegra observability](https://docs.aegra.dev/guides/observability.md)、[Langfuse SDK overview](https://langfuse.com/docs/observability/sdk/overview.md)]

### 7.3 去重规则

**本项目建议**：

1. Aegra-hosted graph/LLM 只由 Aegra 官方 Langfuse integration 发送到 Langfuse；不添加 `CallbackHandler`、Generic OTLP target 或第二个 Langfuse exporter。
2. FastAPI、Worker 和 domain service 使用结构化日志、metrics 和 health checks；不创建 Langfuse root trace，也不创建应用级 Trace runtime。
3. Aegra 如需内部 exporter fan-out，只启用实现官方 Langfuse integration 所必需的配置；MedicalRAG 不配置第二个观测 backend。
4. Aegra Langfuse、日志和 metrics 各自在出口前执行脱敏；不能假定 Langfuse masking 会改变日志或其他数据副本。

这些是本项目建议，不是 Aegra 或 Langfuse 的强制配置；上线前应做一次真实调用合同测试，断言 trace 数量、parent/child、采样、脱敏和错误路径。[官方来源（访问日期：2026-07-27）：[Langfuse masking](https://langfuse.com/docs/observability/features/masking.md)、[Langfuse instrumentation](https://langfuse.com/docs/observability/sdk/instrumentation.md)、[Aegra observability](https://docs.aegra.dev/guides/observability.md)、[OpenTelemetry context propagation](https://opentelemetry.io/docs/languages/python/instrumentation/)]

## 8. 实施前检查清单

**本项目建议**：

- 锁定 Aegra、Langfuse/OpenInference 版本，并在 Python 3.12 中验证 Aegra 单一 Langfuse ingestion owner 的启动合同；API/Worker 不引入 Langfuse 依赖。
- 在测试环境验证 Cloud 与 self-hosted endpoint、Basic Auth、`x-langfuse-ingestion-version: 4`、HTTP/protobuf 和 flush/shutdown。
- 用合成的非医疗数据验证 input/output 关闭、`mask_otel_spans`、Aegra exporter 脱敏和 sampling 的 observation 完整性。
- 注入 Langfuse DNS、401、429、5xx、mask exception、队列满和 graceful shutdown，确认 Aegra run 按 fail-open 约定运行；另行验证 API/Worker 业务流程和 PostgreSQL 业务记录不受 Langfuse 故障影响。
- 验证 Aegra 已捕获的 graph/LLM 不再叠加 callback 或第二个 exporter；不创建独立 LangChain/LangGraph Langfuse 路径。

上述检查项分别对应 Langfuse SDK/OTEL 的异步导出与错误语义、Aegra 的 exporter ownership 以及 FastAPI/worker 生命周期边界。[官方来源（访问日期：2026-07-27）：[Langfuse SDK overview](https://langfuse.com/docs/observability/sdk/overview.md)、[Langfuse OTLP](https://langfuse.com/integrations/native/opentelemetry.md)、[Aegra observability](https://docs.aegra.dev/guides/observability.md)、[FastAPI Background Tasks](https://fastapi.tiangolo.com/tutorial/background-tasks/)]

## 官方来源清单

以下来源均于 **2026-07-27** 访问；上文每条事实或由事实推导的结论已在对应段落再次给出 URL。

- Langfuse Python SDK README：<https://raw.githubusercontent.com/langfuse/langfuse-python/main/README.md>
- Langfuse Python SDK package metadata：<https://pypi.org/pypi/langfuse/json>
- Langfuse SDK overview：<https://langfuse.com/docs/observability/sdk/overview.md>
- Langfuse Python API reference：<https://python.reference.langfuse.com/langfuse.html>
- Langfuse instrumentation：<https://langfuse.com/docs/observability/sdk/instrumentation.md>
- Langfuse Python v3 到 v4 migration：<https://langfuse.com/docs/observability/sdk/upgrade-path/python-v3-to-v4.md>
- Langfuse LangChain/LangGraph integration：<https://langfuse.com/integrations/frameworks/langchain.md>
- Langfuse masking：<https://langfuse.com/docs/observability/features/masking.md>
- Langfuse sampling：<https://langfuse.com/docs/observability/features/sampling.md>
- Langfuse advanced SDK features：<https://langfuse.com/docs/observability/sdk/advanced-features.md>
- Langfuse native OpenTelemetry/OTLP：<https://langfuse.com/integrations/native/opentelemetry.md>
- Langfuse Docker Compose：<https://langfuse.com/self-hosting/deployment/docker-compose.md>
- Langfuse self-hosting versioning：<https://langfuse.com/self-hosting/upgrade/versioning.md>
- Langfuse SDK `pyproject.toml`：<https://raw.githubusercontent.com/langfuse/langfuse-python/main/pyproject.toml>
- LangChain callbacks：<https://docs.langchain.com/oss/python/langchain/callbacks>
- LangGraph overview：<https://docs.langchain.com/oss/python/langgraph/overview>
- FastAPI Background Tasks：<https://fastapi.tiangolo.com/tutorial/background-tasks/>
- OpenTelemetry Python instrumentation：<https://opentelemetry.io/docs/languages/python/instrumentation/>
- OpenTelemetry OTLP specification：<https://opentelemetry.io/docs/specs/otlp/>
- OpenTelemetry trace SDK specification：<https://opentelemetry.io/docs/specs/otel/trace/sdk/>
- OpenTelemetry error handling：<https://opentelemetry.io/docs/specs/otel/error-handling/>
- Aegra documentation index：<https://docs.aegra.dev/llms.txt>
- Aegra observability：<https://docs.aegra.dev/guides/observability.md>
- Aegra streaming：<https://docs.aegra.dev/guides/streaming.md>
- Aegra API `pyproject.toml`：<https://raw.githubusercontent.com/aegra/aegra/main/libs/aegra-api/pyproject.toml>
