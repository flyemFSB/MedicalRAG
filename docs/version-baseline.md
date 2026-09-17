# MedicalRAG 版本钉版基线

> 规范性文档：实现阶段所有依赖按此钉版；CI 使用 lockfile 的 locked/frozen 模式，禁 `latest`。实现开始时须按「门禁」逐项验证。调研底稿在本地 `_archive/docs/research/`（不进 GitHub）。

## 1. Python / 后端

| 组件 | 钉版 | 门禁 |
|---|---|---|
| Python | 3.12.x（`.python-version` 锁 minor）| `requires-python >=3.12`（下界）；业务 ID 用 `medicalrag_core.ids.uuid7`（ADR 0064 修订）|
| uv | ≥0.12.10（`[tool.uv] required-version` 强制；CI setup-uv 钉同一版本） | Tier 1（3.10–3.14）；Dockerfile 走 cache mount |
| FastAPI | 0.141.x | 内置 SSE `EventSourceResponse` |
| Pydantic | v2（≥2.13.5）| — |
| SQLAlchemy | ≥2.0.52 | async engine + `async_sessionmaker` |
| Alembic | ≥1.19 | `alembic init -t async` |
| asyncpg | ≥0.31.0 | 项目持久化 PG 驱动 |
| redis-py | 8.1.x | `redis[hiredis]`；worker 侧仅作心跳键（健康检查），消息传输已迁移 RabbitMQ（ADR 0086） |
| hiredis | ≥3.3.0 | — |
| RabbitMQ | server `rabbitmq:4.3-management-alpine`；client `taskiq-aio-pika>=0.6`（aio-pika 10） | 持久化发布 + 持久化 quorum 队列（ADR 0086）；healthcheck `rabbitmq-diagnostics -q ping`；镜像 pin tag |
| TaskIQ | taskiq ≥0.12 + taskiq-aio-pika ≥0.6 | 传输层为 RabbitMQ（ADR 0086）：`AioPikaBroker`（qos=10 prefetch、持久化发布、quorum 任务队列、内置死信 `taskiq.dead_letter`、`taskiq.delay` 延迟队列承接重试 delay）；重试必须给任务显式 `retry_on_error=True` 标签（`SmartRetryMiddleware.default_retry_label` 默认 False）；重试耗尽由 `IngestionFailureMiddleware` 置 Run 为 FAILED；去重走 PG 唯一约束 |
| PostgreSQL | 18.4 | 内置 `uuidv7()` |
| Redis | 8.10 | noeviction + AOF；许可 RSALv2/SSPLv1/AGPLv3 |
| pyright | ≥1.1.413（dev group）| 类型门禁 basic 起步（根 `[tool.pyright]`）|
| pytest-cov | ≥7.x（dev group）| 总量覆盖率地板 `fail_under=75`（ADR 0088）；口径 = 行 + 分支（`[tool.coverage.run] branch = true`）|
| diff-cover | ≥10.x（dev group）| 变更行覆盖率门禁（ADR 0088），经 `scripts/ci/check_patch_coverage.py` 调用 |
| pre-commit | ≥4.x（dev group）| ruff-check/ruff-format 与 CI 同规则 |

## 2. 检索与存储

| 组件 | 钉版 | 门禁 |
|---|---|---|
| Qdrant | client `qdrant-client>=1.19`；server `qdrant/qdrant:v1.19.1` | 单容器；Dense + Sparse/BM25 Hybrid Search + RRF(k=61 ≡ 论文 1/(rank+60))；dense 启用 TurboQuant 4-bit（`memory=PINNED`）；payload 索引必须覆盖 workspace_id / document_id / is_eligible；client/server 同步升 |
| fastembed | ≥0.8.0 | 静态 `Qdrant/bm25` sparse；中文经 `retrieval/sparse.py` 做 CJK bigram 预处理 + `disable_stemmer=True`（索引端/查询端必须共用同一函数，禁用英文词干与停用词）|
| PostgreSQL | 18.4-alpine | 内置 `uuidv7()`；`shared_buffers=128MB` |
| Redis | 8.10-alpine | noeviction + AOF |
| MinIO / etcd | — | **已移除**（Qdrant 单容器不需要）|
| 本地对象适配 | **stdlib** `pathlib` + `asyncio.to_thread`（`LocalObjectStorage`） | **不引入** fsspec/s3fs/aiofiles/minio；有真实 S3 需求再评估 |

## 3. AI / Agent

| 组件 | 钉版 | 门禁 |
|---|---|---|
| Aegra | aegra-cli **==0.10.4** | exact pin；升级须过 Compose 实测门禁 |
| LangGraph | ≥1.2.x | retry/timeout/error_handler 需 ≥1.2 |
| openai SDK | ≥3.11 | HTTP 层 httpx2；自有 transport 注入必须同源 httpx2 |
| httpx2 | ≥2.12（infra 直依）| 与传递依赖的 `httpx` 可共存（对象不可跨包）|
| tiktoken | ≥0.14 | cl100k_base token 计数 |
| loguru | ≥0.7.3 | 结构化日志 |
| prometheus_client | ≥0.22 | `/metrics` 官方渲染；禁止手写 OpenMetrics 文本 |
| Phoenix | `arizephoenix/phoenix:15.1.0` | Postgres 后端；OTLP `/v1/traces` |
| langgraph-checkpoint-postgres | 3.1.x | AsyncPostgresSaver（Aegra 传递）|
| ragas（隔离 eval） | 0.4.3 | 不与主 lock 共存；`uv run --no-project -p 3.12 --with ragas==0.4.3 …` |

## 4. 前端 / 工具链

| 组件 | 钉版 | 门禁 |
|---|---|---|
| Node.js | 24.18.x | Vite8/pnpm12 |
| pnpm | 12.x（`packageManager` 钉 12.1.0） | CI 用 `pnpm/setup`；web 镜像 corepack 取钉版；任务编排走 pnpm 原生脚本（无第三方编排器，ADR 0055） |
| TypeScript | `@typescript/native`（=typescript **7.0.2**，标准 `tsc`）+ `typescript`→typescript6（openapi-typescript 运行时 API） | **不采用** 7.1 dev/`next`；待 7.1 GA 且 openapi-typescript 兼容后再收敛单包 |
| React | 19.3.x（react + react-dom 成对） | — |
| Vite | 8.x | Rolldown 默认 |
| @vitejs/plugin-react | 6.x | Oxc |
| assistant-ui | @assistant-ui/react 0.15.x + **@assistant-ui/react-langgraph** 0.14.x | 官方 LangGraph 桥；`apiUrl` 须绝对 URL |
| @langchain/langgraph-sdk (JS) | 1.10.x | ChatScreen 直连 Client + react-langgraph peer |
| TanStack Router / Query / Table | Router 1.x / Query 5.x / Table 9.x | queryOptions + useSuspenseQuery；Table v9 features |
| Base UI | @base-ui/react 1.x | 唯一 headless 直依（vendored shadcn 组件）|
| oxlint | ≥1.82 | JS/TS lint（Rust 自解析；无 typescript-eslint）|
| oxfmt | ≥0.67 | JS/TS 格式化（`oxfmt` / `oxfmt --check`；Prettier 兼容工作流）|
| Vitest / Playwright | Vitest 4.x（5.x 另行排期）/ Playwright 1.63.x | — |
| 运营台图表 | **无 recharts / 无 G6** | Dashboard 用 KPI 卡片；意图树自绘折叠树（ADR 0067 superseded）|
| pdfjs-dist | 6.x | PDF 预览（动态 import）|
| docx-preview | 0.4.x | DOCX 预览（动态 import）|
| xlsx (SheetJS) | **已移除** | npm 源停更 + CVE；XLSX 预览不支持 |
| openapi-typescript | 7.x | CI drift 门禁 `--check` |

## 5. 部署

| 组件 | 钉版 | 门禁 |
|---|---|---|
| Docker Compose | 插件 ≥5.3（`start_interval` 需 ≥2.20.2）| 核心服务免 profile |
| Nginx | `nginx:1.30.4-alpine` | `/api`+`/api/agent` 反代；SSE `proxy_buffering off` |
| 镜像 | 全部 pin tag | 禁 `latest` |
| PostgreSQL | `postgres:18.4-alpine` | — |
| Redis | `redis:8.10-alpine` | — |
| Qdrant | `qdrant/qdrant:v1.19.1` | 与 §2 同步 |

## 6. 门禁（升级后逐项验证）

1. `uv lock --locked` / `uv sync --locked --all-packages` 可解析导入（CI 强制 locked，禁自动改锁）。
2. qdrant client/server 1.19.x：Hybrid Search + RRF(k=61) + payload 过滤 + TurboQuant 4-bit。
3. TaskIQ 0.12.x + taskiq-aio-pika 0.6.x：`AioPikaBroker`（qos prefetch + 持久化 quorum 队列 + 死信/延迟队列，ADR 0086）+ `SmartRetryMiddleware` + 任务级 `retry_on_error` 标签。
4. FastAPI 内置 SSE 流式/取消/续传（端点必须是生成器 + `response_class=EventSourceResponse`，否则旁路 keep-alive 与 SSE 响应头）。
5. pnpm frozen-lockfile；`tsc -b && vite build` 通过；`oxfmt --check` 与 `oxlint` 通过。
6. openapi-typescript `--check` 生效。
7. `uv run python scripts/ci/check_package_boundaries.py` 通过。
8. `alembic upgrade head && alembic check` 无 schema 漂移（由 `apps/api/tests/test_migration.py` 在单元级强制）。
9. `uv run python scripts/ci/check_patch_coverage.py --base origin/main` 可运行（变更行覆盖率门禁，ADR 0088；覆盖率报告缺改动文件时必须失败而非静默放行）；其判定逻辑的回归测试为 `uv run pytest scripts/ci/tests`。
10. 升级任一组件须重跑对应合同测试与 Compose `test` profile。
