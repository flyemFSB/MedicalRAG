# MedicalRAG 技术栈客观评估与最佳实践核实

> 调研日期：2026-08-01
> 适用范围：MedicalRAG 复刻计划截至 2026-08-01 的全部既定技术栈（后端与数据、AI/RAG/检索/可观测、前端/工具链/部署）。
> 来源约束：优先一手官方文档、官方仓库、PyPI/NPM 官方元数据；通过浏览器 CDP 联网验证（部分结论来自并行子代理的联网核实），无法联网处明确标注「未联网验证（训练知识）」。
> 文档性质：客观评估「当前选型是否最优 + 用法是否符合当前官方最新最佳实践」，目标降低复杂度、提升性能。本文不替代 `docs/spec.md`、`docs/architecture.md` 或现有 ADR；若结论建议回改计划，见第 5 节「处置建议」。

---

## 1. 后端与数据栈

### 1.1 Python 3.14 + uv — ✓ 最佳

- **官方事实（已联网验证）**：当前稳定版 3.14.6（bugfix 阶段，EOL 2030-10，PEP 745）；3.15 仍为 pre-release。生态已就绪：fastapi 0.141.1、redis-py 8.1.0、pymilvus 3.0.1、arq 0.28.0、uvicorn 均声明支持 3.14；pydantic-core 2.47.0、SQLAlchemy 2.0.51（自 2.0.47 起）、hiredis 3.4.0（自 3.3.0 起）、grpcio 1.83.0（自 1.81.0 起）、asyncpg 0.31.0（仅此版）提供 cp314 wheel。uv 官方将 3.10–3.14 列为 Tier 1。
- **最佳实践检查**：建议 `requires-python = ">=3.14"` **去掉 `<3.15` 上界**（官方文档一律下界写法；3.15 数月后发布，写上界会强制二次解依赖）。用 `.python-version` 固定 3.14.x 锁定开发环境。
- **复杂度/性能**：版本下限必须盯紧（asyncpg≥0.31.0、hiredis≥3.3.0、grpcio≥1.81.0、SQLAlchemy≥2.0.47），否则降级源码编译。uv workspace = 根 pyproject + `[tool.uv.workspace]` members，共享单一 uv.lock（入 VCS）；PEP 735 dependency-groups 仅本地开发，发布用 optional-dependencies。
- **待验证**：PyPI 上 "aegra" 是 meta-package（aegra-cli），classifiers 最高仅 3.12、未声明 3.14——若它真进栈需先验证。

### 1.2 FastAPI — ✓ 最佳

- **官方事实（已联网验证）**：0.141.1（2026-07-29），依赖 pydantic≥2.9、starlette≥0.46，支持 3.14。0.135 起内置 SSE：`fastapi.sse.EventSourceResponse` + `ServerSentEvent`，支持 POST SSE、Last-Event-ID 续传、内置 keep-alive 15s 与 `X-Accel-Buffering:no`。
- **最佳实践检查**：计划用法符合官方推荐；3 处升级——① SSE 用内置 `EventSourceResponse`，勿手写 `StreamingResponse`；② 生命周期用 `lifespan=`（`on_event` 已废弃）；③ 同步阻塞 SDK 用 `def`/`anyio.to_thread` 隔离。
- **备选**：Litestar（DI/SSE 齐但生态远弱）、Falcon（无 DI/校验/SSE，需全手写）、裸 Starlette（内置 SSE 需第三方）。均不成立。

### 1.3 SQLAlchemy 2 async + Alembic — ✓ 最佳

- **官方事实（已联网验证）**：2.0.51 提供 cp314 wheel；asyncpg 0.31.0。官方 async 模式：`create_async_engine` + `async_sessionmaker` + `async with` + `expire_on_commit=False`；AsyncSession **不可跨并发 task 共享**；避免 lazy load（selectinload / AsyncAttrs / lazy="raise"）；连接池 AsyncAdaptedQueuePool 默认 5/10/30s。Alembic 1.18.5 用 `alembic init -t async` + `run_sync`；autogenerate 不检测改名/匿名约束，须人工 review。
- **复杂度/性能**：pool_size 提到 10–20、max_overflow 10–30、pool_pre_ping=True；FastAPI 与 arq worker **各自独立 engine**。
- **备选**：SQLModel 无官方 async 路径（0.0.39 Beta）、Tortoise 1.1.7 为 Alpha（迁移走 Aerich）、裸 asyncpg 丢 ORM/迁移。均不成立。

### 1.4 PostgreSQL — ✓ 最佳（建议 PG 18）

- **官方事实（已联网验证）**：PG 18 为当前唯一稳定大版本（18.4，EOL 2030-11）；PG 19 仍 Beta。**PG 18 内置 `uuidv7()`**（PG 17 仅 gen_random_uuid），顺序 UUID 对 B-tree 主键友好。
- **建议**：官方镜像 `postgres:18.4`；UUID 主键可用 PG18 内核 `uuidv7()`（无需 pgcrypto）。Outbox relay 用「轮询（`FOR UPDATE SKIP LOCKED` 批量领取）+ pg_notify 唤醒」混合——notify 可能丢/重复，轮询兜底。

### 1.5 Redis — ✓ 最佳（注意策略）

- **官方事实（已联网验证）**：最新稳定 8.10.0，镜像 `redis:8.10`；redis-py 8.1.0 支持 3.14。eviction 策略实例级；pub/sub 是 at-most-once、fire-and-forget，可靠投递用 Streams；限流推荐滑动窗口计数，8.8+ 有 INCREX 单命令原子限流。
- **复杂度/性能**：单实例 db0 + maxmemory + **noeviction**（arq 队列/会话不能容忍逐出），缓存一律显式 TTL；持久化 AOF everysec + RDB；缓存膨胀后再拆独立缓存实例。redis-py 全局单客户端 `from_url(max_connections=50, decode_responses=True)` + `redis[hiredis]`。
- **许可提示**：Redis 8 许可为 RSALv2/SSPLv1/AGPLv3 三选一（非纯 OSS）。
- **arq 传输**：队列是 Sorted Set（ZADD，score=时间），worker 轮询、**悲观执行**（成功/失败才 ZREM），依赖 Redis 持久化、自身不落盘——这正是需要 AOF 的原因。

### 1.6 arq — ✓ 有条件采用

- **官方事实（已联网验证）**：v0.28.0；README 明示「**maintenance only mode**」，作者确认仅修安全漏洞、不归档；3.14 支持已合入 main。WorkerSettings 关键字段：functions、cron（unique=True 默认防多 worker 重复执行）、retry/max_tries（默认 5）、job_timeout（默认 300s）、keep_result（默认 3600s）、max_jobs、queue_name。`enqueue_job(_job_id=...)` 用 WATCH 原子去重（job/result key 已存在则返回 None），**去重窗口 = keep_result 时长**。
- **备选**：Celery 功能最全但**无 asyncio 池**；Dramatiq 同步执行模型；RQ 最简但无内置调度；pgmq PG 原生队列但无 worker/消费循环、与 Redis 传输不符。对「摄取→分块→嵌入→建索引」arq 最契合，代价是接受维护模式。
- **复杂度/性能**：独立 worker 服务、多进程共享 Redis 横向扩展；任务按阶段拆分、独立 `_job_id` 链式 enqueue；瞬态错误 `raise Retry(defer=ctx['job_try']*N)` 指数退避；**普通异常/超时不自动重试直接判失败，无内建死信**——用 result key 扫描告警或补偿。

### 1.7 事务性 Outbox + arq — ✓ 组合成立

- **官方事实（已联网验证）**：microservices.io 明确 outbox 须与业务**同事务写入**、relay 独立投递、可能重复发布→**消费端必须幂等**；arq 文档明示「Jobs may be called more than once!」，官方建议 DB 事务/幂等键兜底。
- **正确性设计**：outbox 表 `id, aggregate_type, aggregate_id, event_type, payload(JSONB), created_at, processed_at(NULL=待投递)`，部分索引 `(created_at) WHERE processed_at IS NULL`；relay 独立进程轮询为主 + SKIP LOCKED 批量领取 + pg_notify 加速，enqueue 成功（含 None）即标记 processed_at，**勿在业务事务内调 Redis**；幂等 `_job_id=f'outbox:{id}'` + 消费端目标表 `UNIQUE(...)` 兜底；失败闭环覆盖「relay 崩溃重扫重投 / 投递后崩溃未标记重复投递 / 执行失败 Retry 至 max_tries 永久失败需监控 / 进程崩溃队列保留重跑」。

---

## 2. AI/RAG、检索与可观测

### 2.1 Milvus dense + sparse/BM25 混合检索 — ✓ 方案成立（API 需按当前文档校正）

- **官方事实（已联网验证，Milvus 子代理）**：当前推荐混检 API 是 `client.hybrid_search(collection_name, reqs, ranker=..., limit=..., output_fields=...)`，每个向量场构造一个 `AnnSearchRequest(data, anns_field, param, limit)` 放入 `reqs` 列表。
  - **2.6+/3.0（当前文档）**：新式 Ranker 用 `Function`：`from pymilvus import Function, FunctionType; ranker = Function(name="rrf", input_field_names=[], function_type=FunctionType.RERANK, params={"reranker":"rrf","k":100})`。
  - **2.5（旧式，仍兼容）**：`from pymilvus import RRFRanker`；加权 `WeightedRanker(0.8, 0.2)`。当前 SDK 仍导出 `AnnSearchRequest/RRFRanker/WeightedRanker`。
  - RRF k 默认 60，官方推荐 [10,100]；WeightedRanker 2.6+ 用 `params.weights` 列表、顺序与 reqs 一一对应、`norm_score` 默认 True。
  - **旧 `search(rank=...)` 已移除**；当前只有 `ranker=`。
  - BM25：`Function(function_type=FunctionType.BM25, input_field_names=["text"], output_field_names=["sparse"])` + `SPARSE_INVERTED_INDEX`、`metric_type="BM25"`、`params={"bm25_k1":1.2,"bm25_b":0.75}`，查询直接传文本。
- **对计划的影响**：`docs/architecture.md` 中「Milvus 内置 Weighted/RRF ranker 结合」的表述应更新为当前 `Function/FunctionType` 新式 API；服务端版本决定用旧式类还是新式 Function（2.5 用类、2.6+/3.0 用 Function）。
- 备选（Qdrant/Weaviate/pgvector/Elasticsearch/Vespa）对比结论由 Agent B 最终报告补齐。

### 2.2 Langfuse（唯一 AI/RAG Trace）— ✓ 仍是最优解

- **官方事实（已联网验证）**：最新 4.14.2，`requires_python >=3.10,<4.0`；v3→v4 无破坏性 client 生命周期变化（`Langfuse()` 与全局 `get_client()` 并存，短进程需 flush()/shutdown()），async 用法不变（无 AsyncLangfuse，用 `@observe` + `Langfuse.async_api`）。MIT 核心可免费自托管（数据不出内网），云版可选；官方明示 fail-open（SDK 错误被捕获并记录、不破坏应用，上报为后台队列+批量、全异步）。脱敏主手段 `mask_otel_spans`（export 阶段删改 span 属性，钩子抛错仅丢弃该批），旧 `mask` 参数标 legacy；sampling 用 `LANGFUSE_SAMPLE_RATE`/`sample_rate`；OTLP ingest 端点 `/api/public/otel` 可插自建脱敏代理。
- **自托管依赖（已联网验证）**：PostgreSQL、ClickHouse、Redis/Valkey、S3 兼容存储（默认 MinIO）四项全必需；官方推荐 Docker Compose 单机起步（langfuse-web + langfuse-worker）。2026-01 前后被 ClickHouse 收购，官方承诺保持开源、licensing 无变更计划。
- **竞品（已联网验证）**：LangSmith 自托管仅 Enterprise 付费、非开源，基本出局；Arize Phoenix（ELv2，source-available 非 OSI 开源）单容器可自托管、OTel/OpenInference 生态，是唯一强竞品；OpenLLMetry（Apache-2.0）只是 OTel 插桩 SDK、无存储/UI，非完整后端。
- **LangGraph 集成**：官方 cookbook 确认沿用 Langfuse CallbackHandler 作为 callbacks 传入 graph。**import 路径两来源不一致**：一个子代理实测 `from langfuse.langchain import CallbackHandler`（wheel v4.14.2 无 `langfuse/callback`、无 `langfuse/otel`），另一份报告写 `from langfuse.callback import CallbackHandler`——实现期需按当前 wheel 实测为准。
- **对计划的影响**：计划「Aegra 独占 Langfuse 集成、应用不自行挂 callback」是**有意收敛**而非通用 Langfuse×LangGraph 模式（通用模式是应用侧 callback，见 2.3）。该收敛现在有官方路径支撑：Aegra 原生支持 **OTLP 观测、可导出到任意 OTLP 后端（含 Langfuse 的 `/api/public/otel` 端点）**，因此应用进程无需初始化 Langfuse client，Langfuse callback 的 import 路径问题（`langfuse.langchain` vs `langfuse.callback`）由此变得不重要。

### 2.3 Aegra / LangGraph 运行时 — ✓ 组合成立（已联网验证）

- **结论**：LangGraph `StateGraph` 受控编排 + Aegra 自托管承载，是目前（2026-08）与官方推荐一致且无厂商锁定的组合。Aegra 是活跃维护（push 2026-07-27、1096 stars）、Apache-2.0 的「LangSmith Deployments（原 LangGraph Platform）自托管替代」，原生支持 Agent Protocol v2 流式与 `useStream()`。
- **官方事实（已联网验证）**：
  - **LangGraph 受控 RAG**：`StateGraph` + 条件边仍是官方对「受控 RAG」的推荐（`docs.langchain.com/oss/python/langgraph/agentic-rag` 教程为纯 StateGraph + `ToolNode` + 文档评分循环，无 `create_agent`）；Functional API（`@entrypoint`/`@task`）是官方并列认可的等效替代；`create_agent` 已归 LangChain 侧（快速通道）。→ 佐证计划「根流程不用 `create_agent`」的决策。文档站已整体迁至 docs.langchain.com。
  - **LangGraph Platform → LangSmith Deployment**：运行时叫 Agent Server（assistants/threads/runs + cron；架构 = API servers + queue workers + PostgreSQL + Redis）。自托管 Standalone 可行，但 `langgraph-api`（PyPI v0.11.2）license 为 **Elastic-2.0**（source-available，非 OSI 开源），启动需 `LANGGRAPH_CLOUD_LICENSE_KEY` + beacon 出站校验。
  - **Aegra**（github.com/aegra/aegra，Apache-2.0，FastAPI + PostgreSQL）：同一 `langgraph_sdk.get_client` 代码不变；README 明示「Agent Protocol v2 streaming，thread-scoped SSE + content-block events + 原生 HITL resume，默认启用」；worker 架构（Redis 队列、跨实例 pub/sub）、cron、HITL、PostgreSQL checkpoints、JWT/OAuth/Firebase 认证、**OTLP 观测**。PyPI 包为 `aegra-api` 0.9.24 / `aegra-cli` 0.9.24；`aegra` 是 meta-package（官方不建议装）。
  - **Agent Protocol**：原 AIEF 版协议停在 v1 且已停更；2026 年活跃的是 `github.com/langchain-ai/agent-protocol`（LangGraph 实现其超集）。「Protocol v2」= Agent Server 流式协议：`POST /threads/{id}/commands`（命令信封）+ `POST /threads/{id}/stream/events`（SSE，8 个 channel：values/updates/messages/tools/lifecycle/input/tasks/custom）→ 与计划 ADR 0058 的端点完全一致。
  - **assistant-ui 集成**：`useStream`（`@langchain/react` 1.0.29）仍是官方推荐；官方新推荐 `@assistant-ui/react-langchain`（薄包装 useStream），优于手写 `useExternalStoreRuntime` 桥接。
  - **Resilience 最佳实践**（`docs.langchain.com/oss/python/langgraph/fault-tolerance`）：`add_node(retry_policy=RetryPolicy(max_attempts=3))` 兜 5xx + 指数退避；`TimeoutPolicy` **仅 async 节点支持**（同步节点编译期报错，阻塞 I/O 用 `asyncio.to_thread`）；重试耗尽走 `error_handler(state, error) → Command(goto=...)` 做 Saga 补偿；`StateGraph.set_node_defaults` 全图统一；要求 `langgraph>=1.2`。
- **备选对比**：LangSmith Deployment 云端（厂商锁定、托管）不满足数据主权；Standalone `langgraph-api`（Elastic-2.0 + license key + beacon 出站）许可不合；纯 OSS 库自实现（`thread_id` + `graph.stream` 都在 OSS 库内）可行但需自拼 Thread/Run/流式/认证。**Aegra 以 Apache-2.0 打包上述能力，是降低复杂度与许可风险的最优解。**
- **复杂度/性能建议**：按 agentic-rag 教程建受控图；LLM/检索节点写成 async 以启用 `TimeoutPolicy`；评分用结构化输出二值路由控延迟；流式优先 messages channel 减 token 传输。

---

## 3. 前端、工具链与部署

### 3.1 TanStack Start — ✓ 最优（有 RC 风险）

- **官方事实（已联网验证）**：`@tanstack/react-start` 最新 1.168.34，engines node≥22.12、peer vite≥7 / react≥18||19（Node24/React19/Vite8 全兼容）；官方文档自述「currently in the Release Candidate stage」、非 v1——**唯一硬风险**。SSR 全文档 + streaming Server Functions + 组合式 Middleware + 默认 CSRF；RSC 仅 experimental。
- **最佳实践检查**：计划用 SSR 而非 RSC ✓（RSC 官方自述 experimental）。同源 `/api` 代理：dev 用 Vite `server.proxy`，**prod 用 Nginx 让 `/api` 直连 FastAPI**（SSE 不经 Node，延迟/内存最优）。
- **复杂度建议**：管理后台无 SEO 需求可关 SSR 用 SPA 模式降复杂度；聊天流优先前端同源 fetch 直连后端 SSE。
- **备选**：Next.js（RSC 心智重、倾向 Vercel 锁定）过重；React Router v8 Framework Mode（稳，但 typed streaming 弱，官方迁移页仍 coming soon）；纯 Vite SPA（最简但失 SSR）。

### 3.2 React 19 + TypeScript + Vite — ✓ 基本符合，「TS6」需落实

- **官方事实（已联网验证）**：React latest 19.2.8（React Compiler 已 GA v1.0）；Vite latest 8.2.0（Vite8 起 Rolldown 为唯一打包器，构建快 10–30×，官方 Node≥22.12）；**TypeScript 最新已是 7.0.2**（Go 原生，2026-07-08），**6.0 是最后 JS 版**；typescript-eslint 8.65.0 仅支持 TS<6.1.0、**不支持 TS7**；官方 react-ts 模板默认 `typescript ~6.0.2` + oxlint。
- **最佳实践检查**：计划「TS6」正合生态基线但写法要明确——主包用 alias `typescript@npm:@typescript/typescript6@^6.0.2`，可选加别名 `@typescript/native`（TS7）跑 `npx tsc` 提速 8–12×；**勿主包直升 7.0.2**（eslint peer 冲突）。
- **建议**：`tsc -b && vite build`；dev 由 Oxc 转译；React Compiler 用 reactCompilerPreset 渐进开启后删手写 memo；聊天/表单用 useActionState/useOptimistic。

### 3.3 assistant-ui + @langchain/react（v2-native）— ✓ 当前选择最佳

- **官方事实（已联网验证）**：官方 runtime 指南以 `@assistant-ui/react` 为核心，一等适配器含 LangGraph / **LangChain（包装 @langchain/react 的 useStream）**；`@langchain/react` 1.0.29（peer react^18||19）；`@assistant-ui/react` 0.15.1；新增 `@assistant-ui/react-langchain` 0.0.22（官方新推荐）；**「agent-ui」不存在**（npm 404）。
- **最佳实践检查**：前提是后端讲 **Agent Protocol v2**。若后端是自定义 Python SSE，官方推荐实现该协议两端点（`/threads/:id/commands`、`/stream`）并配现成 `HttpAgentServerAdapter`，否则需自建 runtime。
- **建议**：SSE + fetch override 带鉴权头（WS 不能带自定义头）；HttpAgentServerAdapter 用 useMemo 包裹防断流。

### 3.4 pnpm + Turborepo — ✓ 当前选择最佳

- **官方事实（已联网验证）**：pnpm latest 11.18.0（lockfileVersion 恒 9.0，Node≥22.13）；**pnpm 11 用 `allowBuilds` 取代 v10 的 `onlyBuiltDependencies`**，且 pnpm 10+ 默认不执行依赖 lifecycle scripts——**Vite 的 esbuild 必须加 allowBuilds 白名单**否则 dev/build 失败；Turborepo latest 2.10.8，Vercel Remote Cache 免费。
- **建议**：2 app+2 共享库先用 `pnpm -r --filter`（已内置拓扑排序）跑通即可，turbo 增量价值在 CI 缓存，turbo.json 只留 build/lint/test 三条；内部包用 `workspace:*` + `catalog:` 集中版本；`minimumReleaseAge` 默认 1 天会挡新发布包。

### 3.5 Docker Compose dev/test/prod profiles — ✓ 方向正确，需微调

- **官方事实（已联网验证）**：官方 Tip「**核心服务勿挂 profile**（始终启用）」；`depends_on condition` 仅 `service_started/service_healthy/service_completed_successfully`；healthcheck 含 `start_interval`；顶层 `version` 字段 obsolete；Compose 插件最新 v5.3.1；override 文件 + 生产 `-f compose.production.yaml` 官方推荐，**与 profiles 互补**（profiles 只切服务激活，不能覆盖配置）。
- **微调**：**test profile 拿不到数据库**——Postgres/MinIO 应设为无 profile 核心服务；prod 的端口/镜像/restart 差异走 `-f` override；后端依赖就绪用 `condition: service_healthy`；前端 Node SSR dev 放**宿主机**跑（Vite HMR 容器内差），后端热重载用 Compose Watch sync，node_modules 勿 bind/sync。

### 3.6 MinIO — ✗ 必须调整（社区版进入维护模式）

- **官方事实（已联网验证）**：**minio/minio 仓库 README 明示「NO LONGER MAINTAINED」**，开源版最后 RELEASE 2025-10-15；Docker Hub `minio/minio` 已 **ARCHIVED**（最后 tag 2025-09-07）；活跃产品为 **AIStor**（镜像 `quay.io/minio/aistor/minio`，最新 RELEASE.2026-07-24），需 MinIO Software License，Free 仅单节点、过期封禁；docs.min.io 全量重定向 /aistor/。
- **对计划的影响**：`docs/adr/0017`（S3-compatible object storage with MinIO）基于的 MinIO 社区版已停止维护。医疗场景不能长期使用无安全补丁的归档镜像。三选一：AIStor Free（注册单机许可证）/ 钉开源最后版（AGPL，自用无更新）/ **<1TB 单后端直接本地文件系统**（零许可零端口）。此外 Langfuse 自托管默认也依赖 S3 兼容存储（见 2.2），此决策影响面更大。
- **其余最佳实践 ✓**：私有 bucket + presigned（`presigned_get_object`，expires 15–60 分钟）+ 默认拒匿名。

### 3.7 阿里云镜像 — ✓ 方向符合，两处调整

- **官方事实（已联网验证）**：npmmirror 官方 `.npmrc` 写法 `registry=https://registry.npmmirror.com`；tarball 字节级镜像、**integrity 跨源一致**（lockfile 可复用，resolved 域名需重写）；阿里云 PyPI 证书有效、**https 可省 trusted-host**；Ubuntu 24.04+/Debian 12+ 用 deb822（`ubuntu.sources`/保留 Signed-By）；**Docker 镜像加速 2026-06 官方声明已停止同步最新镜像且仅限 ECS**。
- **建议**：npmmirror 与官方 npmjs 双 registry 兜底，生产/CI 加 verdaccio 本地缓存代理防限流；pip/uv 哈希锁可跨源复用；apt 固定 codename（noble/bookworm/trixie 均支持）；**Docker 加速需换 ACR 企业版制品订阅或自建 registry**。

---

## 4. 总体结论

### 确认项（选型成立，符合当前官方最佳实践）
- 后端：Python 3.14 + uv、FastAPI、SQLAlchemy 2 async + Alembic、PostgreSQL（PG 18）、Redis、arq（有条件的 ✓）、事务性 Outbox + arq。
- AI/RAG：Milvus 混合检索（API 按当前 `Function/FunctionType` 校正）、Langfuse（仍最优）、LangGraph `StateGraph` 受控编排 + Aegra 自托管（Apache-2.0、原生 Agent Protocol v2 流式、OTLP 观测，优于 LangSmith Deployment/Standalone 的 Elastic-2.0 许可）。
- 前端/工具链：TanStack Start（接受 RC 风险）、React 19 + Vite 8 + TS6(alias)、assistant-ui + @langchain/react（前提后端讲 Agent Protocol v2）、pnpm 11 + Turborepo 2、Compose profiles（核心服务免 profile + `-f` override 微调）、阿里云镜像（除 Docker 加速）。

### 建议更换/必须调整项
1. **MinIO**：停用归档镜像 → AIStor Free / 钉开源最后版 / 本地文件系统（影响 ADR 0017，且 Langfuse 自托管默认也依赖 S3）。
2. **TypeScript**：「TS 6」落实为 npm alias（TS6 是最后 JS 版，TS7 是当前 Go 原生版）；主包勿直升 TS7（typescript-eslint 不支持）。
3. **Docker 镜像加速**：阿里云已停同步，换 ACR 制品订阅或自建 registry。

### 需进一步验证项
- aegra-api / aegra-cli 对 Python 3.14 的兼容（aegra-api 声明 `>=3.12`，3.14 支持需实测；`aegra` 元包不安装）。
- Aegra 的 OTLP→Langfuse 导出配置，在实现期按当前 Aegra 文档核实。
- arq 对 redis-py 6.x 的依赖上界与 Redis 8.10 长期兼容。

---

## 5. 对计划与 ADR 的处置建议

1. **ADR 0064（Python 3.14）**：`requires-python` 建议改为 `>=3.14`（去掉 `<3.15` 上界），用 `.python-version` 锁 3.14.x。
2. **ADR 0017（MinIO）**：因社区版停维，需重估对象存储选型（AIStor Free / 钉最后版 / 本地文件系统），并联动 Langfuse 自托管的 S3 依赖。
3. **ADR 0066（UUIDv7）**：PG 18 内置 `uuidv7()`，应用层生成与 PG 内核生成可互为备选；建议在 ADR 中注明 PG 18 原生能力。
4. **arq 维护模式**：接受 + 准备 Dramatiq/TaskIQ 迁移预案（团队在意长期演进时）。
5. **Milvus 混合检索**：`architecture.md` 与 `spec.md` 中「内置 Weighted/RRF ranker」表述更新为当前 `Function/FunctionType` API；服务端版本决定类/Function。
6. **FastAPI**：SSE 用内置 `EventSourceResponse`；生命周期用 `lifespan=`；同步阻塞 SDK 隔离到 `def`/`to_thread`。
7. **Compose**：核心服务（Postgres/MinIO 等）不挂 profile；test profile 依赖无 profile 的数据库；prod 差异走 `-f` override。
8. **Redis**：镜像 8.10；noeviction + AOF everysec + 缓存显式 TTL；注意许可 RSALv2/SSPLv1/AGPLv3。
9. **pnpm**：`allowBuilds` 白名单放行 esbuild 等；`catalog:` 集中版本；Node SSR dev 放宿主机。
10. **Aegra / LangGraph（保持选型）**：Aegra 为 Apache-2.0，优于 LangSmith Deployment 云端或 Standalone `langgraph-api`（Elastic-2.0 + `LANGGRAPH_CLOUD_LICENSE_KEY` + beacon 出站）；LangGraph 受控图按官方 agentic-rag 教程编排，LLM/检索节点写成 async 以启用 `TimeoutPolicy`，`retry_policy` 兜 5xx。
11. **Agent Protocol 术语**：计划中「Agent Protocol v2」即 `langchain-ai/agent-protocol` 的流式协议（`POST /threads/{id}/commands` + `/stream/events`）；建议在文档中注明，避免与已停更的 AIEF 版 v1 混淆。

---

## 来源

### 后端与数据栈
- [Python 3.14 Downloads](https://www.python.org/downloads/) · [Python Versions](https://devguide.python.org/versions/) · [uv 文档](https://docs.astral.sh/uv/)（config/workspaces/dependencies/python-versions）
- [FastAPI — Bigger Applications](https://fastapi.tiangolo.com/tutorial/bigger-applications/) · [Server-Sent Events](https://fastapi.tiangolo.com/advanced/server-sent-events/) · [Async](https://fastapi.tiangolo.com/async/) · [Events](https://fastapi.tiangolo.com/advanced/events/)
- [SQLAlchemy — Asyncio](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html) · [Engine/Pooling](https://docs.sqlalchemy.org/en/20/core/pooling.html) · [Alembic — Async Cookbook](https://alembic.sqlalchemy.org/en/latest/cookbook.html) · [Alembic — Autogenerate](https://alembic.sqlalchemy.org/en/latest/autogenerate.html)
- [PostgreSQL — Versioning](https://www.postgresql.org/support/versioning/) · [PG18 UUID functions](https://www.postgresql.org/docs/18/functions-uuid.html) · [PostgreSQL — NOTIFY](https://www.postgresql.org/docs/current/sql-notify.html)
- [Redis — Rate Limiting](https://redis.io/docs/latest/operate/oss_and_stack/management/security/rate-limiting/) · [Redis — Persistence](https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/) · [Redis — Streams](https://redis.io/docs/latest/data-types/streams/)
- [arq 官方文档](https://arq-docs.helpmanual.io/) · [arq GitHub](https://github.com/samuelcolvin/arq)（含 issue #510、pyproject.toml）· [PyPI arq](https://pypi.org/project/arq/)
- [Celery](https://docs.celeryq.dev/) · [Dramatiq](https://dramatiq.io/) · [python-rq](https://python-rq.org/) · [pgmq](https://github.com/tembo-io/pgmq) · [graphile-worker](https://github.com/graphile/worker)
- [microservices.io — Transactional Outbox](https://microservices.io/patterns/data/transactional-outbox.html) · [Polling Publisher](https://microservices.io/patterns/data/polling-publisher.html) · [Debezium — Outbox Event Router](https://debezium.io/)

### AI/RAG、检索与可观测
- [Milvus — Multi-Vector Search](https://milvus.io/docs/zh/multi-vector-search.md) · [RRF Ranker](https://milvus.io/docs/zh/rrf-ranker.md) · [Weighted Ranker](https://milvus.io/docs/zh/weighted-ranker.md) · [BM25 Function](https://milvus.io/docs/zh/bm25-function.md) · [Milvus 2.5 文档](https://milvus.io/docs/zh/v2.5.x/multi-vector-search.md) · [pymilvus hybrid_search 示例](https://github.com/milvus-io/pymilvus/blob/master/examples/hybrid_search.py)
- [Langfuse — LangChain/LangGraph 集成](https://langfuse.com/integrations/frameworks/langchain) · [LangGraph cookbook](https://langfuse.com/guides/cookbook/integration_langgraph) · [Langfuse — OpenTelemetry](https://langfuse.com/integrations/native/opentelemetry) · [Langfuse — Self-hosting](https://langfuse.com/self-hosting) · [Langfuse — Queuing/Batching](https://langfuse.com/docs/observability/features/queuing-batching) · [Langfuse — Masking](https://langfuse.com/docs/observability/features/masking) · [Langfuse — Sampling](https://langfuse.com/docs/observability/features/sampling) · [Langfuse — License](https://github.com/langfuse/langfuse/blob/main/LICENSE) · [PyPI langfuse](https://pypi.org/project/langfuse/) · [LangSmith — Self-hosting](https://docs.langchain.com/langsmith/platform-setup) · [Arize Phoenix](https://github.com/Arize-ai/phoenix) · [OpenLLMetry](https://github.com/traceloop/openllmetry)
- [Aegra 官网](https://www.aegra.dev/) · [Aegra 文档](https://docs.aegra.dev/introduction) · [Aegra GitHub](https://github.com/aegra/aegra) · [PyPI aegra-api](https://pypi.org/project/aegra-api/)
- [LangGraph — Agentic RAG 教程](https://docs.langchain.com/oss/python/langgraph/agentic-rag) · [Functional API](https://docs.langchain.com/oss/python/langgraph/functional-api) · [Fault Tolerance](https://docs.langchain.com/oss/python/langgraph/fault-tolerance)
- [LangSmith Agent Server](https://docs.langchain.com/langsmith/agent-server) · [Deploy Standalone Server](https://docs.langchain.com/langsmith/deploy-standalone-server) · [Local Server](https://docs.langchain.com/oss/python/langgraph/local-server)
- [langchain-ai/agent-protocol](https://github.com/langchain-ai/agent-protocol) · [Protocol v2 Command](https://docs.langchain.com/langsmith/agent-server-api/streaming/protocol-v2-command) · [Protocol v2 SSE](https://docs.langchain.com/langsmith/agent-server-api/streaming/protocol-v2-event-stream-sse)
- [assistant-ui — LangChain runtime](https://www.assistant-ui.com/docs/runtimes/langchain) · [LangChain — assistant-ui 集成](https://docs.langchain.com/oss/javascript/langchain/frontend/integrations/assistant-ui)

### 前端、工具链与部署
- [TanStack Start 文档](https://tanstack.com/start/latest/docs/framework/react/overview) · [Server Functions](https://tanstack.com/start/latest/docs/framework/react/guide/server-functions)
- [TypeScript 7.0 发布](https://devblogs.microsoft.com/typescript/announcing-typescript-7-0/) · [Vite 文档](https://vite.dev/guide/features) · [React Compiler](https://react.dev/learn/react-compiler)
- [assistant-ui — Pick a Runtime](https://www.assistant-ui.com/docs/runtimes/pick-a-runtime) · [@langchain/react 传输](https://github.com/langchain-ai/langgraphjs/blob/main/libs/sdk-react/docs/transports.md)
- [pnpm](https://pnpm.io/)（recursive/catalogs/workspaces/settings）· [Turborepo 文档](https://turborepo.dev/docs) · [Turborepo — Vite 指南](https://turborepo.dev/docs/guides/frameworks/vite) · [pnpm 10/11 发布说明](https://github.com/pnpm/pnpm/releases)
- [Docker Compose — Profiles](https://docs.docker.com/compose/how-tos/profiles/) · [Startup Order](https://docs.docker.com/compose/how-tos/startup-order/) · [Production](https://docs.docker.com/compose/how-tos/production/)
- [MinIO GitHub](https://github.com/minio/minio) · [MinIO Docker Hub tags](https://hub.docker.com/r/minio/minio/tags) · [AIStor 文档](https://docs.min.io/aistor/operations/licenses/)
- [npmmirror](https://npmmirror.com/) · [阿里云 PyPI 镜像](https://developer.aliyun.com/mirror/pypi) · [阿里云 Ubuntu 镜像](https://developer.aliyun.com/mirror/ubuntu) · [阿里云 ACR 加速说明](https://help.aliyun.com/zh/acr/user-guide/accelerate-the-pulls-of-docker-official-images)
