# MedicalRAG 版本钉版基线

> 规范性文档：实现阶段所有依赖按此钉版；CI 使用 lockfile 的 locked/frozen 模式，禁 `latest`。调研口径 2026-08-01（详见 `docs/research/tech-stack-objective-evaluation.md` 与 `docs/research/implementation-recipes.md`）。实现开始时须按「门禁」逐项验证。

## 1. Python / 后端

| 组件 | 钉版 | 门禁 |
|---|---|---|
| Python | 3.14.x（`.python-version` 锁 minor）| `requires-python >=3.14`（下界）|
| uv | 当前稳定 | Tier 1（3.10–3.14）|
| FastAPI | 0.141.x | 内置 SSE `EventSourceResponse` |
| Pydantic | v2（pydantic-core 2.47.x）| — |
| SQLAlchemy | 2.0.51 | cp314 wheel（≥2.0.47 起）|
| Alembic | 1.19.x | `alembic init -t async` |
| asyncpg | ≥0.31.0 | 仅此版有 cp314 wheel |
| redis-py | 8.1.0 | `redis[hiredis]` |
| hiredis | ≥3.3.0 | 3.4.0 |
| TaskIQ | taskiq 0.12.x + taskiq-redis 1.2.x | redis-py 8.x 兼容；`ListQueueBroker` + `RedisAsyncResultBackend`；重试走 `SmartRetryMiddleware`；去重走 PG 唯一约束/Redis SETNX（ADR 0073）|
| PostgreSQL | 18.4 | 内置 `uuidv7()` |
| Redis | 8.10 | noeviction + AOF；许可 RSALv2/SSPLv1/AGPLv3 |
| pyright | 1.1.411+（dev group）| ADR 0080 类型门禁，basic 起步（根 `[tool.pyright]`）|
| pytest-cov | 7.x（dev group）| `fail_under=80`（基线 82%，ADR 0080）|
| pre-commit | 4.x（dev group）| ruff-check/ruff-format 与 CI 同规则 |

## 2. 检索与存储

| 组件 | 钉版 | 门禁 |
|---|---|---|
| Qdrant | v1.19.x (`qdrant-client>=1.19`) | 单容器部署；Dense + Sparse/BM25 Hybrid Search + RRF；dense 启用 TurboQuant 4-bit 量化（8 倍压缩）；client/server 同步升 1.19（ADR 0081）|
| fastembed | 0.8.x (`fastembed>=0.8.0`) | 静态 `Qdrant/bm25` sparse 模型（官方推荐：无语料库状态，索引/检索对称）|
| PostgreSQL | 18.4-alpine | 内置 `uuidv7()`；内存调优 `shared_buffers=128MB` |
| Redis | 8.10-alpine | noeviction + AOF；许可 RSALv2/SSPLv1/AGPLv3 |
| MinIO | — | **已移除** (Qdrant 单容器部署不需要对象存储) |
| etcd | — | **已移除** (Qdrant 单容器部署不需要元数据服务) |
| 本地对象适配 | fsspec + s3fs + aiofiles | dev/test 用（v1 默认；ObjectStorage 端口后的本地文件系统适配器，ADR 0075）|
| S3 客户端 | minio-py（minio）| 仅在需要 S3 兼容后端时启用；v1 Compose 不预置对象存储 |

## 3. AI / Agent

| 组件 | 钉版 | 门禁 |
|---|---|---|
| Aegra | aegra-api / aegra-cli 0.10.4 | 钉 exact；升级须过 Compose 实测门禁（3.14 兼容，声明 >=3.12）|
| LangGraph | 1.2.x | retry/timeout/error_handler 需 ≥1.2 |
| langchain | 1.3.x | — |
| langgraph-sdk (Py) | 0.4.x | — |
| openai SDK | 3.3.x (`openai>=3.3`) | HTTP 层切换 httpx2（pydantic 维护 fork）；自有 transport 注入必须同源 httpx2（ADR 0081）|
| httpx2 | 2.12.x（infra 直依）| 自有 HTTP 代码统一入口；与传递依赖的 httpx 可共存（对象不可跨包）|
| tiktoken | 0.14.x (`tiktoken>=0.12`) | cl100k_base token 计数（匹配 text-embedding-3 家族；ADR 0077 块预算前置）|
| loguru | 0.7.x | 结构化日志（ADR 0074；development-standards §3 红线）|
| Phoenix (observability) | `arizephoenix/phoenix:15.1.0`（镜像 pin tag）| Postgres 后端（PG≥14，独立库 medicalrag_phoenix）；OTLP HTTP `/v1/traces`；`session.id`=aegra thread_id 深链（ADR 0082）|
| langgraph-checkpoint-postgres | 3.1.x | AsyncPostgresSaver |
| ragas（隔离 eval 环境） | 0.4.3 | 不与主 lock 共存（ragas→instructor→openai<3.0，与项目 openai>=3.3 冲突）；RC 门禁以 `uv run --no-project -p 3.14 --with ragas==0.4.3` 隔离运行（ADR 0080 eval-answer）|

## 4. 前端 / 工具链

| 组件 | 钉版 | 门禁 |
|---|---|---|
| Node.js | 24.18.x | Vite8/pnpm12 均满足 |
| pnpm | 12.x（`packageManager` exact 钉 12.1.0） | Rust 重写（2026-08-26 stable）；lockfile 9.0 与 `allowBuilds`/`minimumReleaseAgeExclude` 沿用，未识别 workspace 设置升级为报错；npm `latest` 仍指 11 线，12 走 `next-12`/self-update；CI 用 `pnpm/setup`（action-setup 仅支持 ≤10）；web 镜像经 corepack 取钉版（静态链接，容器无需 libatomic）（ADR 0083）|
| Turborepo | 2.x | 只编排 JS 任务 |
| TypeScript | 7.0.x 原生编译器（`@typescript/native` = `npm:typescript@^7.0.2`，标准 `tsc`）+ `typescript` = `npm:@typescript/typescript6@^6.0.2` 双别名并排（ADR 0084）| 原生 `tsc` 供 build/typecheck；typescript6 供 openapi-typescript 运行时 JS API（TS 7.0 不带 API，7.1 收敛单包）|
| React | 19.2.x | — |
| Vite | 8.x | Rolldown 默认；`build.rolldownOptions` |
| @vitejs/plugin-react | 6.x | Oxc；React Compiler preset |
| assistant-ui | @assistant-ui/react 0.15.x / react-langchain 0.0.22 | `apiUrl` 须绝对 URL |
| @langchain/react | 1.0.29 | — |
| @langchain/langgraph-sdk (JS) | 1.9.28 | — |
| TanStack Router | 1.x | `ensureQueryData` + `useSuspenseQuery` |
| TanStack Query | 5.x | — |
| TanStack Table | 9.x | v9 features 显式声明（`lib/table.ts` 统一 `AppTableFeatures`，仅排序；官方迁移指南）|
| oxlint | 1.79.x | Rust 自解析，不依赖 TS 编译器 API（typescript-eslint 钉版行已移除：幽灵依赖，项目从未安装；ADR 0084）|
| Vitest / Playwright | 4.1.x / 1.62.x | — |
| recharts | 3.10.x | React 19 支持 |
| @antv/g6 | 5.1.x | 意图树编辑器 |
| pdfjs-dist | 6.x | PDF 预览 |
| docx-preview | 0.4.x | DOCX 预览 |
| ~~xlsx (SheetJS CE)~~ | 已移除 | npm 源停更于 0.18.5 且携带已知 CVE（ADR 0080）；XLSX 内嵌预览降级为不支持；恢复须经官方 CDN 源重过供应链审计 |
| openapi-typescript | 7.x | CI drift 门禁 `--check` |

## 5. 部署

| 组件 | 钉版 | 门检 |
|---|---|---|
| Docker Compose | 插件 ≥5.3（`start_interval` 需 ≥2.20.2）| 核心服务免 profile |
| Nginx | `nginx:1.30.4-alpine`（stable line） | 钉 exact tag；`/api`+`/api/agent` 反代；SSE `proxy_buffering off` |
| 镜像 | 全部 pin tag/时 pin digest | 禁 `latest` |
| PostgreSQL | `postgres:18.4-alpine` | Alpine 减小体积 (~50MB) |
| Redis | `redis:8.10-alpine` | Alpine 减小体积 (~6MB) |
| Qdrant | `qdrant/qdrant:v1.19.0` | 与 §2 同步（ADR 0081）|

## 6. 门检（实现开始时逐项验证）

1. cp314 wheels：asyncpg≥0.31.0、hiredis≥3.3.0、grpcio≥1.81.0、SQLAlchemy≥2.0.47 可解析导入。
2. qdrant-client 1.19.x 在 3.14 上实测；dense + sparse/BM25 Hybrid Search + RRF(k=60) + payload 过滤 + TurboQuant 4-bit 量化。
3. TaskIQ 0.12.x + taskiq-redis 1.2.x 与 redis-py 8.x / Redis 8.10 实测（`ListQueueBroker` + 结果 backend；重试中间件与调度器接线）。
4. FastAPI 内置 SSE 在 3.14 生产构建下流式/取消/续传实测。
5. pnpm frozen-lockfile + `allowBuilds`（esbuild）成功安装；`tsc -b && vite build` 通过。
6. openapi-typescript `--check` 作为 contract-check job 生效。
7. 升级策略：lockfile 驱动；升级任一组件须重跑对应合同测试与 Compose `test` profile。
