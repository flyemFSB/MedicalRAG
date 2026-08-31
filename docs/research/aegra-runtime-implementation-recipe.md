# Aegra 运行时实现配方（aegra-api / aegra-cli 0.9.24，端口 2026）

> 调研日期：2026-08-04。范围：Aegra 托管 LangGraph StateGraph、Agent Protocol v2 SSE、自定义 channel、Langfuse 集成、worker 拓扑、Thread↔Conversation 映射。一手来源 = docs.aegra.dev 官方文档 + aegra/aegra 仓库 `main`（0.9.25，本项目钉 0.9.24）源码；无法核实处标注「训练知识」。本文件是实现配方，不替代 ADR/spec。与 [ADR 0058 / 0023 / 0024 / 0025 / 0002 / 0059 / 0062 / 0072](../adr/) 一致。

## 1. aegra.json 完整 schema

解析顺序：`AEGRA_CONFIG` > CWD `aegra.json` > 兼容回退 `langgraph.json`。顶层字段仅 5 个：`dependencies`、`graphs`、`auth`、`http`、`store`（无 server/port 字段）。

```json
{
  "graphs": { "agent": "./src/agent/graph.py:graph" },
  "auth": { "path": "./src/agent/auth.py:auth", "disable_studio_auth": false },
  "http": { "app": "./custom_routes.py:app", "enable_custom_route_auth": true,
            "cors": { "allow_origins": ["https://app.example"], "allow_credentials": true } },
  "dependencies": ["./shared"]
}
```

- `graphs`：graph ID → `./path/file.py:variable`。冒号后变量可为已编译 graph（启动缓存）、0 参 callable、或 factory（`def graph(config: dict, runtime: ServerRuntime)`，per-request 重建）。`context_schema=` 可声明 `Runtime[T]`。
- `auth.path`：接受 `./auth.py:auth`、嵌套相对路径、或 `mypackage.auth:auth`；不配 = no-op 模式（全放行，identity=`anonymous`，无用户隔离）。`disable_studio_auth` 只放开 LangGraph Studio。`AUTH_TYPE` env ∈ `noop|custom`，源码实际以 `auth.path` 为准。

## 2. auth 字段接应用 Redis 会话

签名（源码 `auth_middleware.py` 证实）：

```python
from langgraph_sdk import Auth

@auth.authenticate
async def authenticate(headers: dict) -> dict:
    ...
```

- `headers` 是**完整请求头 dict**（Starlette `conn.headers` 转 dict，**含 Cookie 头**），故可解析 HttpOnly session cookie。
- 返回 dict：`identity`（必填，唯一用户标识）+ 可选 `display_name` / `permissions` / `is_authenticated` + 任意自定义键（如 `workspace_ids`）。抛异常即拒绝（401）。
- 结果注入图执行：`config["configurable"]["langgraph_auth_user"]`，快捷键 `user_id` / `user_display_name`；节点/工具用 `config: RunnableConfig` 或 `InjectedToolArg` 读取。
- **接 Redis 会话的写法**：handler 内从 `headers.get("cookie")` 解析 session token → 复用 `medicalrag_infra.auth.RedisSessionStore.load(token)`（同 Redis，`session:` 前缀）→ 解析 User/Workspace 成员 → 返回 `{"identity": str(user_id), "workspace_ids": [...]}`。Aegra 每请求调用 handler，天然即时生效于新请求（ADR 0024）。aegra.json 里同时指向该 handler 文件（依赖 `packages/infra`）。
- **旁路/透传**：无内置「应用会话直通」；必须写 auth handler。唯一旁路是「不配 auth」= no-op；无路由级 bypass（`disable_studio_auth` 仅 Studio；`enable_custom_route_auth` 管自定义路由）。

## 3. Agent Protocol v2 端点

**`POST /threads/{tid}/commands`**（JSON-RPC 信封，`{id:int, method:str, params:dict}`）。0.9.24 源码只接受 `run.start` 与 `input.respond`（其余报 `unknown_command`；**无 run.cancel/stop**）：

```json
{"id": 1, "method": "run.start", "params": {"assistant_id": "agent",
  "input": {"messages": [{"role": "user", "content": "hi"}]}}}
{"id": 2, "method": "input.respond", "params": {"response": "...", "interrupt_id": "..."}}
// input.respond 批量：{"responses": [{"interrupt_id": "...", "response": "..."}]}
```

- `run.start`：`assistant_id`（必填）、`input`、`config`、`metadata`、`multitaskStrategy`（`reject|rollback|interrupt|enqueue`）、`interrupt_before/after`。线程 `interrupted` 时带 `input` → 自动转为 `{"resume": input}`。
- `input.respond`：`response` + 可选 `interrupt_id`（`[0-9a-f]{32}`）或批量 `responses`。
- 响应：`{"type":"success","id":1,"result":{"run_id":"..."}}`。客户端自铸 thread_id，`run.start` 不存在即建。

**`POST /threads/{tid}/stream/events`**：body `{"channels": ["messages","values","lifecycle","tools","input","custom","custom:<name>"], "namespaces"?, "depth"?, "since"?}`。**无 `on_disconnect` 字段**（0.9.24 model 确认）。SSE frame：`id: <seq>`，`data: {"type":"event","seq":n,"event_id":"...:n","method":"<channel>","params":{"data":…,"namespace":[]}}`。messages channel 为 content-block 事件：`message-start → content-block-delta → message-finish`；lifecycle：`started/completed/failed/interrupted`。

- **since 续传**：断线后重连带 `since=<last_seq>`，服务端只发 `seq>since`；`event_id` 幂等去重。v2 下 run 由 worker 后台执行，**SSE 断开不中止 run**；`on_disconnect=continue` 是 legacy `runs.stream` 参数，v2 不需要（运行本身继续）。
- **取消**：v2 命令不支持 stop；用 legacy `client.runs.cancel(thread_id, run_id)` 或 `POST /threads/{tid}/runs/{run_id}/cancel`。
- 门禁：v2 端点需 `FF_V2_EVENT_STREAMING` 未关 + langgraph 版本能发原生 v3 事件，否则 503。

## 4. 自定义 channel / state 结构化数据（evidence/sources/safety/slots）

**官方主路 = 放 state 字段，走 `values` channel**：把结构化数据声明为图 state 键（`TypedDict` + `Annotated[list[T], operator.add]` 累加），节点返回更新。前端 `@assistant-ui/react-langchain` 的 `useLangChainState<T>('sources')` 就是读 `stream.values[key]`（源码确认）；服务端 `get_state()["values"]["sources"]` 同源可读。UI 可见、可持久化。

**`custom` channel（`StreamWriter`）只用于瞬态流式**：节点 `from langgraph.config import get_stream_writer; get_stream_writer()({"type":"progress",...})`（async <3.11 用 `writer: StreamWriter` 参数）。JS 投影为 `thread.extensions.<name>`（`custom:<name>`），**不可**被 `useLangGraphState` 读取、不进 checkpoint。

结论：evidence/safety/slots 用 state 字段；StreamWriter 仅做进度/瞬态事件。

## 5. Langfuse 集成（OTEL）

```bash
OTEL_TARGETS="LANGFUSE"
LANGFUSE_BASE_URL=https://cloud.langfuse.com   # 或 http://localhost:3000（自托管）
LANGFUSE_PUBLIC_KEY=pk-lf-...   LANGFUSE_SECRET_KEY=sk-lf-...
```

- 源码确认（`observability/targets/langfuse.py`）：Aegra 建 `OTLPSpanExporter` → `{BASE}/api/public/otel/v1/traces`，`Authorization: Basic base64(pk:sk)` + **自动带 `x-langfuse-ingestion-version: 4`**（Langfuse v4 必需，否则摄取延迟达 10 分钟；仅 HTTP，无 gRPC）。
- fail-open：导出失败只降级观测，绝不影响 Agent run / 业务持久化（ADR 0059/0062）；`LANGFUSE_*` 缺失则该 target 静默不启。
- 采样/元数据：`ENABLE_PROMETHEUS_METRICS`、run 顶层 `metadata`（≤32 键，`langfuse.trace.metadata.<key>`）。
- **mask_otel_spans 注意（源码核实）**：Aegra 0.9.24 observability 代码**无任何 mask/redaction 钩子**（`grep mask` 仅命中无关文件）。`mask_otel_spans` 是 **Langfuse Python SDK 4.14.x 客户端选项**，只有自建 `Langfuse(mask_otel_spans=…)` 客户端才生效 = 第二个 exporter，违反 ADR 0059「Aegra 为唯一摄取方」。因此实际脱敏必须在**应用层**保证敏感内容不进入 span 属性（openinference 自动捕获 LangGraph 步骤与 LLM 输入/输出）。**此与 ADR 0072「经 mask_otel_spans 脱敏」措辞有出入，需新 ADR 定夺**。
- SDK 钩子签名（若未来走自建客户端，训练知识 + Langfuse 官方文档）：

```python
from langfuse import Langfuse
from langfuse.types import MaskOtelSpansParams, MaskOtelSpansResult, OtelSpanPatch

def mask_otel_spans(*, params: MaskOtelSpansParams) -> MaskOtelSpansResult | None:
    patches = {i: OtelSpanPatch(delete_attributes=("gen_ai.prompt.0.content",),
                                set_attributes={"masking.applied": True})
               for i, s in params.spans.items() if s.instrumentation_scope_name == "openai"}
    return MaskOtelSpansResult(span_patches=patches)
```

## 6. worker / 部署拓扑

- 三模式：`aegra dev`（Docker PG + host 热重载，无 Redis，in-process asyncio 任务）；`aegra up`（PG+Redis+app 全 Docker，app 容器内跑 `aegra serve` + `REDIS_BROKER_ENABLED=true`）；`aegra serve`（裸 uvicorn，自带 PG/Redis，PaaS/K8s）。
- **Redis broker 模式**（`REDIS_BROKER_ENABLED=true`）：run 经 Redis job queue（BLPOP）→ 并发 asyncio worker；`WORKER_COUNT=3`（每实例 worker 循环）× `N_JOBS_PER_WORKER=10`（每循环并发）= 单实例 30 并发；PostgreSQL lease + 心跳 10s + reaper 15s 崩溃恢复；SSE 事件经 Redis pub/sub → Broker 转发。
- **checkpoint**：`DATABASE_URL` 驱动，Aegra 内部用 langgraph-checkpoint-postgres（`AsyncPostgresSaver`）per-request 注入；**应用 graph 不要自配 checkpointer**（Aegra 拥有该 seam，ADR 0025）。迁移启动自动跑；多副本设 `RUN_MIGRATIONS_ON_STARTUP=false` + `aegra db upgrade`。健康检查：`/health` `/ready` `/live` `/info`。
- **Windows dev**：官方文档未明写 OS 限制，但项目已实测 `aegra serve` 在 Windows 不可用（psycopg/SelectorEventLoop，见 implementation-recipes §5.6）。dev 走 Docker：复用根 `docker-compose.yml` `agent` 服务（port 2026，`--profile dev`，依赖 pg/redis/qdrant `service_healthy`），或在 WSL2/Docker Desktop Linux 容器内 `aegra dev/serve`；合同测试走 Compose `test` profile。

## 7. Thread ↔ 业务 Conversation 映射

```python
from langgraph_sdk import get_client
client = get_client(url="http://aegra:2026")   # 服务端/合同测试用；浏览器走 /api/agent

thread = await client.threads.create(
    thread_id=str(conversation_id),          # 业务键直接作 thread_id（uuidv7 字符合法）
    if_exists="do_nothing",                  # 幂等；已存在不报错
    metadata={"workspace_id": ...},
)
state = await client.threads.get_state(thread_id)       # state["values"]/["interrupts"]/["checkpoint"]
await client.threads.update_state(thread_id, values=..., as_node="agent")
history = await client.threads.get_history(thread_id)
```

- 映射推荐：以 `Conversation.id`（uuidv7，ADR 0066）作 `thread_id` 幂等创建；或首跑后把 `aegra_thread_id` 持久化进 conversation 行（ADR 0002 双持有）。`assistant_id` 直接用 graph_id（`"agent"`，Aegra 启动即建默认 assistant）。
- 隔离：auth 开启后线程自动按 `identity` 归属；Workspace 授权在应用层/authorization handler 校验（客户端传的 workspace 仅路由提示）。

## 来源

- docs.aegra.dev：`/reference/configuration`、`/reference/environment-variables`、`/guides/authentication`、`/guides/streaming`、`/guides/threads-and-state`、`/guides/human-in-the-loop`、`/guides/observability`、`/guides/deployment`、`/getting-started`、`/llms.txt`。
- github.com/aegra/aegra（main=0.9.25）：`libs/aegra-api/src/aegra_api/api/event_streaming.py`、`models/event_streaming.py`、`services/event_streaming/commands.py`、`core/auth_middleware.py`、`observability/targets/langfuse.py`、`observability/span_enrichment.py`、`services/langgraph_service.py`、`docs/guides/worker-architecture.mdx`、`libs/aegra-api/pyproject.toml`。
- langfuse.com：`/integrations/native/opentelemetry.md`、`/docs/observability/features/masking.md`（mask_otel_spans 签名）。
- github.com/assistant-ui/assistant-ui：`packages/react-langchain/src/hooks.ts`（`useLangChainState` 读 `stream.values[key]`）。
- docs.langchain.com/oss/python/langgraph/streaming（`get_stream_writer` / `StreamWriter` / v2 StreamPart）。
