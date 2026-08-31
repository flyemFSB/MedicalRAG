# MedicalRAG 功能实现配方：官方最新推荐方法

> 调研日期：2026-08-01
> 适用范围：MedicalRAG 复刻计划所选技术栈在实现各功能时的官方推荐写法，偏好性能最佳、最流行的做法。
> 来源约束：优先一手来源（官方文档、官方仓库、PyPI/NPM 元数据）；经浏览器 CDP 联网核实，无法联网处明确标注「训练知识」。本文件是**实现配方**（怎么写），不是选型理由（选什么见 tech-stack-objective-evaluation.md）。
> 文档性质：实现前的研究清单；不替代 `docs/spec.md`、`docs/architecture.md` 或 ADR。
> **2026-08 存储轴取代**：§2.1（Milvus 混合检索）与 §2.5（向量 upsert/重建）已被 [ADR 0075](../adr/0075-qdrant-replaces-milvus-as-the-hybrid-retrieval-engine.md) 取代——唯一检索引擎改为 Qdrant 单容器（dense + fastembed 静态 sparse/BM25 + 内置 RRF k=60），配方见 [qdrant-assistant-ui-implementation-recipe.md](qdrant-assistant-ui-implementation-recipe.md)；Milvus 段保留为历史参考。§1.6/§1.7 的 arq 段由 [ADR 0073](../adr/0073-taskiq-replaces-arq-as-the-durable-job-queue.md) 取代为 TaskIQ，配方见 [taskiq-mineru-langfuse-implementation-recipe.md](taskiq-mineru-langfuse-implementation-recipe.md)。

---

## 1. 后端 / API 实现配方

### 1.1 FastAPI 应用结构（已联网验证）
- 大型应用分层：`main.py` 只建 app + 注册中间件/异常/生命周期 + `include_router`；router 按 feature 拆分（auth/conversations/knowledge/ingestion/admin/health）。
- 生命周期用 **`lifespan=`**（`on_event` 已废弃）；依赖注入用 `Depends` + `Annotated` 组合根；配置用 `pydantic-settings`。
- SSE 用内置 **`fastapi.sse.EventSourceResponse` / `ServerSentEvent`**（FastAPI ≥0.135）：POST SSE、Last-Event-ID 续传、内置 keep-alive 15s、自动 `X-Accel-Buffering: no`。不要手写 `StreamingResponse`。

### 1.2 认证与会话（已联网验证）
- 密码哈希：**`argon2-cffi` 的 `PasswordHasher()`**——默认参数即 RFC 9106 SECOND RECOMMENDED（argon2id，m=64MiB，t=3，p=4）。`ph.check_needs_rehash()` 用于升级。
```python
from argon2 import PasswordHasher
ph = PasswordHasher()
hash = ph.hash("...")                 # $argon2id$v=19$m=65536,t=3,p=4$...
ph.verify(hash, "...")                # 错密码抛 VerifyMismatchError
```
- 会话：计划用 **Redis 服务端会话 + HttpOnly Secure cookie**（starlette 只有签名 cookie 版，无 Redis 版；FastAPI 官方教程主推 Bearer token）。OWASP 要点：会话数据必须存服务端；自造 sid 用 **CSPRNG ≥128bit**（`secrets.token_urlsafe(32)`）；登录后必须重生成 sid 防 session fixation；`Set-Cookie: __Host-SessionID=...; Secure; HttpOnly; SameSite=Strict; Path=/`。

### 1.3 限流（已联网验证）
- Redis 滑动窗口计数；redis-py 8 当前官方用法（`INCREX` 等单命令原子限流自 Redis 8.8+）；超限返回排队/429，配合排队状态事件（用户故事 29）。

### 1.4 SQLAlchemy 2 async（已联网验证）
```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncAttrs
class Base(AsyncAttrs, DeclarativeBase): ...
engine = create_async_engine("postgresql+asyncpg://...")
async_session = async_sessionmaker(engine, expire_on_commit=False)   # 官方推荐
```
- 默认池即 **AsyncAdaptedQueuePool**（pool_size=5 / max_overflow=10 / pool_timeout=30）；pool_pre_ping 建议开启；**每 worker 进程一个 engine**（AsyncEngine 不可跨 event loop 共用）。
- AsyncSession **不可跨并发 task 共享**；避免 lazy load——用 **`selectinload()`**、`AsyncAttrs.awaitable_attrs`、`lazy="raise"`/`raiseload("*")`（async 下隐式 lazy load 直接报 MissingGreenlet）。

### 1.5 Redis 客户端生命周期（已联网验证）
- 全局单 async client：`redis.from_url(url, max_connections=50, decode_responses=True)` + `redis[hiredis]`；在 `lifespan` 中创建/关闭；不要每个请求新建。

### 1.6 arq 任务队列（已联网验证，v0.28.0）
```python
class WorkerSettings:
    functions = [ingest_document, reconcile_mineru]      # 协程函数列表
    on_startup = startup; on_shutdown = shutdown
    redis_settings = REDIS_SETTINGS
    cron_jobs = [cron(reconcile, hour={9, 12, 18}, minute=12)]
    max_tries = 5; job_timeout = 300; keep_result = 3600; retry_jobs = True
```
- 入队幂等：`await redis.enqueue_job('the_task', url, _job_id='outbox:...')`——同 id 已存在返回 None 不入队，唯一性由 Redis 事务保证（**去重窗口 = keep_result 时长**）。
- 重试：`raise Retry(defer=ctx['job_try'] * 5)` 手动退避（**arq 无内置指数退避**）；超 max_tries 永久失败。
- 启动：官方 CLI `arq demo.WorkerSettings`；嵌入 FastAPI lifespan 用 `handle_signals=False`（`Worker(...).run()` / `await async_run()`；无 `__aenter__`，不支持 `async with`）。生产建议 worker 独立进程。
- 依赖：`redis[hiredis]>=4.2.0,<6`、Redis 服务端 6.2.3+。

### 1.7 事务性 Outbox relay（已联网验证，结合 ADR 0063）
- outbox 表 `(id uuid7, aggregate_type, aggregate_id, event_type, payload jsonb, created_at, processed_at)` + 部分索引 `(created_at) WHERE processed_at IS NULL`；与业务状态**同事务**写入，事务内不碰 Redis。
- relay：`FOR UPDATE SKIP LOCKED` 批量领取 + `pg_notify` 唤醒兜底轮询；enqueue（含 None 去重）成功后标记 `processed_at`；`_job_id=f'outbox:{id}'`。
- 权威参考：microservices.io（Transactional Outbox / Polling Publisher）、Debezium（outbox-event-router）。

### 1.8 健康检查（已联网验证）
- liveness 只答进程存活；readiness 探测 PostgreSQL/Redis/Milvus 等依赖，依赖降级返回 degraded 而非失败；Langfuse fail-open 不进 readiness 门禁。

---

## 2. AI / RAG / 检索实现配方

### 2.1 Milvus 混合检索（已联网验证：milvus-docs HEAD 3.0.x + pymilvus 3.0.1 源码）
```python
from pymilvus import MilvusClient, AnnSearchRequest, RRFRanker, WeightedRanker
client = MilvusClient(uri="http://localhost:19530", token="root:Milvus")
dense_req  = AnnSearchRequest(data=[q_dense], anns_field="dense_vec",
    param={"params": {"ef": 100}}, limit=50, expr='workspace_id in [...]')
sparse_req = AnnSearchRequest(data=[q_text], anns_field="sparse_vec", limit=50)  # 文本直传，BM25 转稀疏
res = client.hybrid_search(collection, reqs=[dense_req, sparse_req],
    ranker=RRFRanker(k=60), limit=20, output_fields=["text","source_id","chunk_id"])
```
- **BM25 Function + 索引**（建库时定义）：`schema.add_function(Function(name="text_bm25", input_field_names=["text"], output_field_names=["sparse_vec"], function_type=FunctionType.BM25))`；稀疏索引 `SPARSE_INVERTED_INDEX, metric_type="BM25", params={"inverted_index_algo":"DAAT_MAXSCORE","bm25_k1":1.2,"bm25_b":0.75}`；dense 用 HNSW/COSINE。
- **ranker 类型 `Union[BaseRanker, Function]`**（3.0 签名）：RRF（默认 k=60，文档推荐 [10,100]）或 `WeightedRanker(0.7, 1.0, norm_score=True)`；服务端重排可下推 `FunctionType.RERANK`（TEI/HF/cohere）。
- 标量授权过滤放每个 `AnnSearchRequest.expr`（官方推荐每路独立）；零结果 → Empty 态。
- 关键避免：`prepare_index`/`load_index` 不存在；`drop_ratio_build` 已弃用（用检索期 `drop_ratio_search`）；ORM `Collection`/`Connections.*` 已 deprecated（用 `MilvusClient`）。

### 2.2 LangGraph 受控 RAG 图（已联网验证：langgraph 1.2.10 + checkpoint-postgres 3.1.1）
```python
from langgraph.graph import StateGraph, START, END, MessagesState
from langgraph.prebuilt import ToolNode
workflow = StateGraph(MessagesState)
workflow.add_node("decide", generate_query_or_respond)
workflow.add_node("retrieve", ToolNode([retriever_tool]))
workflow.add_conditional_edges("decide", route_on_tool_calls, {"tools": "retrieve", END: END})
workflow.add_conditional_edges("retrieve", grade_documents)          # 直接返回节点名
workflow.add_edge("rewrite_question", "decide")
graph = workflow.compile()
```
- 容错（langgraph≥1.2）：`add_node(fn, retry_policy=RetryPolicy(max_attempts=3))`、`timeout=TimeoutPolicy(run_timeout=120, idle_timeout=30)`（**仅 async 节点**，同步节点会编译期报错，阻塞 IO 用 `asyncio.to_thread`）；**参数名 `initial_interval`/`backoff_factor`**（`initial_delay`/`exponential_factor` 是旧名，用会抛 TypeError）；补偿 `error_handler=(state, error) -> Command(goto=...)`；`StateGraph.set_node_defaults(...)` 全图默认。
- 生产 checkpoint：**`AsyncPostgresSaver.from_conn_string(DB_URI)` + `await checkpointer.setup()`**（`autocommit=True` + `dict_row`）；`InMemorySaver` 仅单进程调试。

### 2.3 Aegra 运行时（已联网验证：aegra-cli 0.9.24）
- 生产 `aegra up`（官方 compose：pgvector/pg18 + aegra + redis）；**`aegra serve` 不支持 Windows**（psycopg SelectorEventLoop 限制），生产走 Docker/Linux；端口 2026。
- `aegra.json`：`{"graphs":{"agent":"./src/agent/graph.py:graph"},"auth":{"path":"./my_auth.py:auth"}}`；Redis worker：`REDIS_BROKER_ENABLED=true, REDIS_URL=..., WORKER_COUNT=3, N_JOBS_PER_WORKER=10`；checkpoint 走 `DATABASE_URL`（迁移启动自动跑）。
- 应用侧：`from langgraph_sdk import get_client; client = get_client(url=...)`；Agent Protocol v2：`POST /threads/{tid}/commands`（命令信封）+ `POST /threads/{tid}/stream/events`（`channels`, `since` 续传）；`on_disconnect="continue"` 后台续跑。
- OTLP→Langfuse：`OTEL_TARGETS="LANGFUSE"` + `LANGFUSE_BASE_URL/PUBLIC_KEY/SECRET_KEY`（自动 openinference 埋点）。

### 2.4 Langfuse 自托管 + OTLP（已联网验证：Langfuse v4）
- 官方 compose 六服务：**langfuse-worker + langfuse-web + clickhouse + minio + redis + postgres**；无 SQLite 选项；Redis 需 `maxmemory-policy noeviction`。
- OTLP 摄取（唯一推荐路径，旧 `/api/public/ingestion` 弃用）：
```bash
OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:3000/api/public/otel"
OTEL_EXPORTER_OTLP_HEADERS="Authorization=Basic ${AUTH},x-langfuse-ingestion-version=4"
```
- **`x-langfuse-ingestion-version: 4` 是 v4 必需头**（否则最多延迟 10 分钟）；仅 OTLP over HTTP（无 gRPC）。
- 脱敏：`Langfuse(mask_otel_spans=fn)`（export-stage 钩子，旧 `mask=` 已 Legacy；服务端 masking 为 EE）；采样：`LANGFUSE_SAMPLE_RATE`（trace 级全局，无 per-scope）。

### 2.5 向量 upsert 与重建（已联网验证：pymilvus 3.0.1）
- 批量 `client.upsert(collection, data)`，单请求 <1GB、**分批 ≤256MB/批**；超大用 `LocalBulkWriter + bulk_import`；`create_index(sync=False)` 异步 + `describe_index()` 轮询；`drop_index` 前先 `release_collection`。
- 换 embedding 零停机：① 新增可空向量字段 `add_collection_field(nullable=True)` + 新索引 + 后台回填；② 蓝绿集合 + `create_alias`/`alter_alias` 原子切换。同字段仅一个索引文件，删索引前先 release。

---

## 3. 前端 / 工具链 / 部署实现配方

### 3.1 Vite 8 SPA（已联网验证，v8.2.0）
- Vite 8 默认 **Rolldown**；`@vitejs/plugin-react` 6 用 Oxc 做 React Refresh；React Compiler 显式 opt-in：`react()` + `babel({ presets: [reactCompilerPreset()] })`（`@rolldown/plugin-babel`）。
- `build.rollupOptions`（**不是 rollupOptions**）；默认 target `baseline-widely-available`。
- 脚本：`"build": "tsc -b && vite build"`；lint 用 **oxlint**（模板已取代 eslint）；TS 锁 `~6.0.2`。
- dev 代理：`server.proxy['/api'] = { target: ..., changeOrigin: true, rewrite: ... }`。

### 3.2 TanStack Router + Query（已联网验证）
- Router（v1）：`tanstackRouter({ target:'react', autoCodeSplitting:true })` 插件 + `createRouter({ routeTree })` + `RouterProvider`；`routeTree.gen.ts` 进 lint 忽略。
- **loader→Query 打通用 `queryClient.ensureQueryData(queryOptions)`（而非 `prefetchQuery`）** + `useSuspenseQuery`；QueryClient 放 `createRouter` 的 `context`，`Wrap: QueryClientProvider` 挂载。
- Query v5：`new QueryClient({ defaultOptions: { queries: { staleTime: 60_000, retry: 3, refetchOnWindowFocus: true } } })`；推荐 `useSuspenseQuery`；乐观更新注意 v5 新签名（回调末位 `context`）。

### 3.3 assistant-ui（已联网验证，react 0.15.1 / react-langchain 0.0.22）

> **实现核实（2026-08-02，ADR 0074 优先三方库）：** `@assistant-ui/react` 0.15 是 headless runtime，**不含** `Thread` 组件；`@assistant-ui/react-chat`/`@assistant-ui/sources` 在 registry 不存在；`@assistant-ui/react-ui` 0.2.1 需 0.15.1 没有的 `useThread`/`useAssistantRuntime`（**版本不兼容**）；官方 `Thread` 走 **shadcn 模板**（`npx assistant-ui add`），但 CLI 0.0.108 内嵌 MCP SDK 触发 `zod/v3` 导出 bug（2026-08-02 实测 init 失败）。故用官方 **primitives**（`ThreadPrimitive`/`ComposerPrimitive`/`MessagePrimitive`）组合——官方组件，非手写逻辑；shadcn CLI 修复后再切回官方 `Thread`。
- 官方钩子 `useStreamRuntime`；**`apiUrl` 必须转绝对路径**：`apiUrl: new URL('/api/agent', window.location.href).href`（相对路径会被 LangGraph SDK `new URL()` 抛错）。
- 证据面板官方路：`useLangChainState<Source[]>('sources')` 读 graph state；或官方 shadcn `@assistant-ui/sources` + `<Sources {...part} />`。
- 自研后端 → 官方 `useExternalStoreRuntime`；结构化数据用 data part（`type:"data-*"`）。

### 3.4 OpenAPI→TS 代码生成（已联网验证，openapi-typescript 7.13.0）
```bash
npx openapi-typescript schema.yaml -o src/api/schema.d.ts --check   # CI drift 门禁（内置 --check）
```
- v7 内置 `--check`（schema 变更退出码 1）；生成头标记 auto-generated；配 `openapi-fetch`/`openapi-react-query`。备选 orval 8（按 path 生成 react-query hook，无内置 check）。

### 3.5 图表与预览（已联网验证）
- recharts 3.10.1：React 19 官方支持；v3 破坏性变更（`Cell`→`shape`、Tooltip `TooltipContentProps`、`accessibilityLayer` 默认 true）；v3.3+ 可用图表自带 `responsive` 替代 ResponsiveContainer。
- @antv/g6 5.1.1：意图树用 `layout: { type: 'compact-box', direction: 'LR' }`；React 集成 `useEffect` + `useRef` + `() => graph.destroy()`；更完善可用官方封装 **@antv/graphin**。
- 文档预览（ADR 0068 已改选主流库）：PDF 用 **pdfjs-dist**；DOCX 用 **docx-preview**（Apache-2.0，browser=yes）；XLSX 用 **SheetJS xlsx 解析 + @tanstack/react-table 渲染**；**PPTX v1 为 typed unsupported**（无免费客户端渲染器；OnlyOffice Document Server 9.4/AGPL 为 post-v1 服务端选项）。

### 3.6 Docker Compose + Nginx（已联网验证）
- 核心服务**不设 profile**；可选服务 `profiles: [dev]`；`depends_on: { db: { condition: service_healthy, restart: true } }`；healthcheck 含 `start_interval`（需 Compose ≥2.20.2）；prod 用 `-f compose.yaml -f compose.production.yaml` + `docker compose config` 复查。
- Nginx SSE（location 组合为通行做法）：`proxy_pass http://aegra:8000; proxy_http_version 1.1; proxy_set_header Connection ""; proxy_buffering off; proxy_cache off; proxy_read_timeout 3600s;`（配合 `X-Accel-Buffering: no`）。

### 3.7 uv / pnpm / Turborepo（已联网验证）
- uv workspace：根 pyproject `[tool.uv.workspace] members = ["packages/*"]` + `requires-python = ">=3.14"`（下限）+ `.python-version`（`uv python pin`）；成员依赖 `{ workspace = true }`；CI 用 `astral-sh/setup-uv` + `setup-python@v6` 的 `python-version-file`.
- pnpm 11/12：**`allowBuilds: { esbuild: true }`**（v11 起 `onlyBuiltDependencies` 移除）；catalog 集中版本（`"react": "catalog:"`）。
- Turborepo 2.10.8：`turbo.json tasks: { build: { dependsOn: ["^build"], outputs: [...] }, lint: {}, test: { dependsOn: ["^build"] } }`；远程缓存 OIDC 用 `vercel/setup-turborepo-remote-cache-action@v1`。
- CI 四 job：python-quality / frontend-quality / contract-check（= openapi-typescript `--check`）/ compose-integration（`needs: [前三个]`）。

---

## 4. 三分类汇总（跨全部）

**优先采用（官方稳定推荐 + 性能佳）**
- FastAPI：内置 `EventSourceResponse` SSE、`lifespan=`、argon2-cffi 默认参数、Redis 服务端会话（OWASP）。
- SQLAlchemy：`async_sessionmaker(expire_on_commit=False)`、selectinload/AsyncAttrs/lazy="raise"、每进程 engine。
- arq：`WorkerSettings` + `_job_id` 幂等 + `Retry(defer=job_try*5)` + CLI 启动；outbox relay `SKIP LOCKED` + pg_notify。
- Milvus：`MilvusClient.hybrid_search` + `AnnSearchRequest` + RRFRanker(k=60) + BM25 Function + 每路 expr 授权过滤；≤256MB 分批 upsert。
- LangGraph：StateGraph + MessagesState + ToolNode 受控图 + RetryPolicy/TimeoutPolicy(async)/error_handler + `AsyncPostgresSaver`。
- Aegra：`aegra up` + langgraph_sdk + Agent Protocol v2 + OTLP→Langfuse。
- Langfuse：v4 六服务 compose + `/api/public/otel` + `x-langfuse-ingestion-version=4` + `mask_otel_spans`。
- 前端：Vite 8（Rolldown）+ oxlint + `tsc -b && vite build`；TanStack `ensureQueryData` + `useSuspenseQuery`；assistant-ui `useStreamRuntime` + 绝对 `apiUrl`；openapi-typescript 7 `--check`；Compose 核心免 profile + `service_healthy`；Nginx `proxy_buffering off`；pnpm `allowBuilds` + catalog。

**可选（按需）**
- Milvus 服务端 RERANK Function（需 TEI 等额外资源）；`WeightedRanker`（有明确权重偏好时）。
- orval（想要按 path 生成 react-query hook）；recharts `responsive`；@antv/graphin（G6 封装）；`set_node_defaults`。
- Aegra cron + run metadata 上链；Langfuse 客户端采样。

**避免（弃用/不存在/报错）**
- 手写 SSE `StreamingResponse`；FastAPI `on_event`；Milvus `prepare_index`/`load_index`/`drop_ratio_build`/ORM `Collection`；LangGraph 旧参数名 `initial_delay`/`exponential_factor`、同步节点配 `timeout`、`InMemorySaver` 上生产；Langfuse SQLite/旧 `/api/public/ingestion`/`mask=`；`@js-preview/pptx`（不存在）；`rolldown-vite` 预览包、`build.rollupOptions`、`prefetchQuery` 于 loader、assistant-ui 相对 `apiUrl`、pnpm `onlyBuiltDependencies`；Aegra `aegra serve` on Windows。

---

## 5. 对实现阶段的关键提示

1. **assistant-ui `apiUrl` 必须是绝对 URL**（`new URL('/api/agent', location.href).href`）。
2. **openapi-typescript 7 的 `--check`** 直接承担 CI drift 门禁（ADR 0071 的实现载体）。
3. **PPTX 预览 v1 不支持**——ADR 0068 已改为 pdfjs-dist + docx-preview + SheetJS/TanStack Table，pptx 返回 typed unsupported；OnlyOffice Document Server（AGPL）作为 post-v1 服务端选项。
4. **Langfuse v4 必须带 `x-langfuse-ingestion-version: 4`**，否则摄取延迟可达 10 分钟。
5. **Milvus ranker API 以 3.0 的 `Union[BaseRanker, Function]` 为准**（RRFRanker 类仍在，Function RERANK 可下推服务端）。
6. **`aegra serve` 不支持 Windows**——开发需 Docker/Linux，或接受该限制。
7. **arq 无内置指数退避与内置 DLQ**——退避手写 `Retry(defer=...)`，失败闭环走 PostgreSQL 失败/重放面（ADR 0063）。

## 来源

- 后端：fastapi.tiangolo.com（server-sent-events、lifespan、bigger-applications、security）、argon2-cffi.readthedocs.io、starlette.io/middleware、docs.sqlalchemy.org/en/20（asyncio/pooling/relationships）、redis.readthedocs.io、arq-docs.helpmanual.io、github.com/samuelcolvin/arq、microservices.io（transactional-outbox/polling-publisher）、debezium.io、OWASP Session Management Cheat Sheet。
- AI/RAG：github.com/milvus-io/milvus-docs（multi-vector-search、bm25-function、rrf/weighted/tei-ranker、upsert-entities、manage-aliases）、github.com/milvus-io/pymilvus（milvus_client.py、orm/schema.py）、docs.langchain.com/oss/python/langgraph（agentic-rag、fault-tolerance、checkpointers、graph-api）、github.com/langchain-ai/langgraph、docs.aegra.dev（deployment、streaming、worker-architecture、observability）、langfuse.com/self-hosting 与 /integrations/native/opentelemetry。
- 前端/工具链：vite.dev/blog/announcing-vite8 与 /config、tanstack.com（router、query）、assistant-ui.com/docs/runtimes、openapi-ts.dev、recharts.github.io、g6.antv.antgroup.com、github.com/501351981/vue-office（js-preview）、docs.docker.com/compose（profiles、startup-order、multiple-compose-files）、nginx.org（proxy_module）、docs.astral.sh/uv、pnpm.io、turborepo.dev。
