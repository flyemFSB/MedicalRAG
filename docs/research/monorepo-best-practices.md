# MedicalRAG 单仓库 Monorepo 最佳实践调研

> 调研日期：2026-07-26  
> 适用范围：单一 Git monorepo；后端使用 uv、Python 3.12、FastAPI、Aegra、Langfuse；前端使用 Node.js 24 LTS、pnpm、TypeScript、TanStack Start、React、Vite；部署入口为仓库根目录的 `docker-compose.yml`。  
> 来源约束：本文只引用技术项目自身或标准组织维护的官方一手文档。没有使用博客、教程转载、厂商二手文章或社区约定作为事实依据。

> **计划变更（2026-08-01）对账说明**：本文是历史调研快照，正文保留原始记录。除运行时基线（Python 3.14，[ADR 0064](../adr/0064-uv-manages-python-314-runtime.md)）与镜像配置（[ADR 0065](../adr/0065-aliyun-mirrors-for-pnpm-uv-and-apt.md)）外，以下布局级决策已取代正文中对应章节：
> - 前端不再使用 TanStack Start SSR，改为 **Vite SPA + Nginx/Vite 同源代理**（[ADR 0070](../adr/0070-vite-spa-with-nginx-proxy-is-the-frontend-runtime.md)）；正文 §2.5/§3 中 TanStack Start/SSR 相关目录与任务以该 ADR 为准。
> - Worker 不再是 RocketMQ 消费者，改为 **arq worker + PostgreSQL 事务性 Outbox**（[ADR 0063](../adr/0063-arq-replaces-rocketmq-as-the-durable-job-queue.md)）。
> - 契约边界：**OpenAPI 单向生成**（FastAPI → TS 类型，CI drift 门禁；`/api/agent` 例外 = Agent Protocol v2）（[ADR 0071](../adr/0071-openapi-single-source-contract-generation.md)）。
> - `packages/medical-core` 收窄为**领域 seam**，聊天管线编排（LangGraph 图 + Aegra 绑定）归 `apps/agent`（[ADR 0025](../adr/0025-shared-medical-application-package-for-fastapi-and-aegra.md)）。
> - 对象存储钉 MinIO AGPL 最后版（[ADR 0017](../adr/0017-s3-compatible-object-storage-with-minio.md)）。

## 1. 结论摘要

### 1.1 推荐的整体形态

本项目采用：

```text
一个 Git monorepo
├── 一个 uv workspace：管理所有 Python 应用与 Python 包
├── 一个 pnpm workspace：管理 Web 应用与 TypeScript 包
├── 一个 Turborepo 任务图：只编排 pnpm workspace 内的 JS/TS 任务
└── 一个根目录 docker-compose.yml：管理开发、测试、生产拓扑
```

这是“单仓库、双原生 workspace、分语言任务编排”，而不是把 Python 包伪装成 JavaScript workspace 包，也不是让 Turborepo 直接承担 Python 依赖解析。

**官方事实**：uv workspace 使用每个成员自己的 `pyproject.toml`，共享一个 `uv.lock`；pnpm workspace 需要根目录 `pnpm-workspace.yaml`，并通过 workspace 协议管理本地 JavaScript/TypeScript 包；Turborepo 的 monorepo 模型建立在包管理器 workspace、各包 `package.json`、根 `turbo.json` 和包管理器 lockfile 之上。[U1][P1][T1]

**本项目设计结论**：Python 与 TypeScript 保留各自的 lockfile、包元数据和构建工具；在 CI 中用独立的 Python、前端和 Compose 集成测试任务汇合，而不是制造一个跨语言的虚拟依赖图。

### 1.2 推荐的关键边界

- `apps/api`：FastAPI HTTP 入口、认证授权、管理 API、业务 API 和依赖注入组合根。
- `apps/agent`：Aegra/LangGraph graph 定义、节点编排、运行时接入和流式协议适配；不重复实现医疗业务规则。
- `apps/worker`：RocketMQ 消费者和异步摄取/解析/Embedding/索引任务；不承载浏览器请求。
- `apps/evaluation`：隔离的 RAGAS/检索评测 runner；不作为常驻生产服务，也不进入 API、Agent 或 Worker 的生产依赖。
- `packages/medical-core`：跨 FastAPI、Aegra 和 Worker 复用的医疗领域模型、业务规则、应用服务和端口；不放数据库、FastAPI、Aegra 或第三方 SDK 实现。
- `packages/infra`：PostgreSQL、Redis、Milvus、RocketMQ、对象存储、外部 API、业务 run/audit repository、结构化日志、metrics 和 health 的具体适配器；依赖 `medical-core`，不反向依赖应用入口。Aegra 的 graph/LLM Langfuse 集成由 Aegra runtime 自己拥有，`packages/infra` 不包含应用级 Trace provider。
- `packages/contracts`：语言无关的 JSON Schema、事件协议和 API 约定；其 Python 与 TypeScript 产物分别作为对应语言包发布或安装。
- `apps/web`：TanStack Start/React 页面、路由、组件和前端 feature；只通过 HTTP/LangGraph 合同访问服务，不直接接触数据库、Milvus、LLM 或 MinerU。

不创建 `packages/ui`、`packages/testkit`、`packages/config`、`packages/common` 或 `packages/utils`。组件留在 `apps/web`，测试替身留在各 member 的 `tests/`，配置留在各运行时，公共逻辑按领域或适配器归属放置。

### 1.3 `medical-core` 的准确作用

`medical-core` 不是“所有公共代码”目录，也不是 `utils` 大杂烩。它的价值在于让以下进程共享同一套可测试的业务语义：

1. FastAPI 接收请求时使用的意图、会话、知识库、检索和安全规则。
2. Aegra Agent Graph 节点执行时使用的同一套意图解析、查询改写、证据融合和回答约束。
3. RocketMQ Worker 处理文档摄取、任务状态、幂等和索引发布时使用的同一套状态与不变量。

它应包含领域对象、值对象、状态机、策略、应用服务接口、端口和可脱离基础设施运行的规则测试；它不应包含 SQLAlchemy model、FastAPI `APIRouter`、Milvus client、Redis client、RocketMQ SDK、外部模型 HTTP client 或 Aegra server 启动代码。

**本项目设计结论**：如果没有 `medical-core`，FastAPI、Aegra 和 Worker 很容易分别实现一套“看起来相同但边界不同”的意图、检索和安全逻辑；引入它是为了固定依赖方向、减少行为漂移和提高纯单元测试比例，而不是为了追求更多包。

## 2. 官方文档事实与适用解释

### 2.1 uv workspace 与 Python 包布局

**官方事实**：

- uv workspace 是由一个或多个 workspace member 组成的包集合；每个成员拥有自己的 `pyproject.toml`，workspace 共享一个 lockfile。[U1]
- workspace 通过根 `pyproject.toml` 的 `[tool.uv.workspace]` 配置 `members` 和可选的 `exclude` glob；被匹配的成员必须包含 `pyproject.toml`。[U1]
- workspace 成员可以是应用或库；`uv lock` 作用于整个 workspace，`uv run` 和 `uv sync` 默认针对 workspace root，也可以使用 `--package` 选择具体成员。[U1]
- workspace 内的本地依赖通过 `[tool.uv.sources]` 中的 `workspace = true` 声明；workspace 成员之间的依赖默认以 editable 方式安装。[U1]
- uv 文档明确指出，workspace 适合多个相互关联的包，但不适合成员需要互相冲突的依赖约束或必须拥有完全独立虚拟环境的情况；workspace 还要求整个 workspace 的 `requires-python` 取所有成员约束的交集。[U1]
- uv 项目以 `pyproject.toml` 为项目根识别文件，并维护 `uv.lock` 和项目虚拟环境；项目结构可以使用 `src` layout。[U2]
- `tool.uv.package = false` 可以强制 uv 不构建和安装当前项目本身，但仍可处理依赖；`tool.uv.package = true` 可以强制构建和安装项目。[U4]
- Python Packaging User Guide 将 `pyproject.toml` 的 `[build-system]`、`[project]` 和工具专用的 `[tool]` 表分别定义为构建系统、项目元数据和工具配置的主要位置。[PY2]
- Python Packaging User Guide 说明 `src` layout 将 import package 放入 `src/`；它需要先安装项目才能运行，因此可以减少从仓库工作目录“误导入未安装源码”的问题。[PY1]

**本项目设计结论**：

- 所有 Python 成员统一声明 Python 3.12 兼容范围，例如 `>=3.12,<3.13`；这样符合 uv workspace 的共同 `requires-python` 约束，并避免 Agent、API 与 Worker 的开发环境出现不一致。
- 根 `pyproject.toml` 作为 uv workspace coordinator，设置 `tool.uv.package = false`；真正可运行或可安装的项目放在 `apps/*` 和 `packages/*` 的成员目录中。
- 采用 `src` layout；应用和库均从 `src/<import_package>/` 开始，测试放在成员目录下的 `tests/`，不把源码直接放在仓库根目录。
- 将所有 Python workspace 成员的 `pyproject.toml` 和根 `uv.lock` 纳入代码审查；开发环境使用 uv 的 project/workspace 命令，不手工向 `.venv` 注入依赖。
- 由于 API、Agent 和 Worker 共享 Python 3.12 且目标依赖可以统一协调，本项目采用 uv workspace；如果未来 Aegra 运行时必须使用与应用冲突的依赖范围，再把它拆为独立 uv project，而不是强行破坏 workspace 的一致性。

### 2.2 pnpm workspace 与 TypeScript 包管理

**官方事实**：

- pnpm 对 monorepository 有内置支持；workspace 根目录必须有 `pnpm-workspace.yaml`。[P1]
- `workspace:` 协议会拒绝从 registry 解析非本地包，确保声明的依赖确实来自当前 workspace；普通版本范围可能在本地包不匹配时回退到 registry。[P1]
- `pnpm --filter` 支持按包名、目录、依赖、被依赖者以及 Git 变更范围选择项目。[P2]
- `pnpm -r`/`pnpm recursive` 可以在 workspace 项目中递归运行命令；默认可按拓扑顺序执行，`--workspace-concurrency` 控制并发度，`--parallel` 可完全忽略拓扑顺序并行运行长任务。[P3]
- pnpm 在 CI 中会自动进入 frozen-lockfile 行为；官方 CI 文档还强调应确保 CI 使用与生成 lockfile 的 pnpm major 版本兼容，并只缓存可信任务可写入的 pnpm store/cache。[P4]

**本项目设计结论**：

- `pnpm-workspace.yaml` 只纳入 `apps/web` 和 TypeScript 包，例如 `packages/contracts/typescript`；不把 Python 目录写入 pnpm workspace。
- 所有内部 TypeScript 依赖使用 `workspace:*` 或明确的 `workspace:^`/`workspace:~`，禁止用普通 semver 让本地包静默回退到 registry。
- 每个 TypeScript 包都拥有自己的 `package.json`，直接依赖写在使用它的包中；根 `package.json` 只放 workspace 级工具和便利脚本，不作为所有应用的隐式依赖仓库。
- 前端变更优先使用 `pnpm --filter` 或 Turborepo filter 缩小任务范围；需要确保依赖包先完成构建时使用拓扑任务图，而不是用不可见的脚本顺序。

### 2.3 Turborepo 的适用边界

**官方事实**：

- Turborepo 推荐从 `apps/` 放应用和服务、`packages/` 放库与工具开始；有效 workspace 至少需要包管理器识别的包目录、lockfile、根 `package.json`、根 `turbo.json` 和每个包的 `package.json`。[T1]
- Turborepo 通过每个包 `package.json` 的 scripts 识别任务，在根 `turbo.json` 的 `tasks` 中定义任务和依赖关系。[T2]
- `dependsOn: ["^build"]` 表示先构建依赖包，再构建当前包；不带 `^` 的任务依赖表示同一个包内的任务顺序。[T2]
- `outputs` 告诉 Turborepo 哪些文件和目录可恢复；没有声明输出时，任务日志仍可缓存，但文件产物不会按预期恢复。[T2][T3]
- Turborepo 会根据任务输入生成 fingerprint；lockfile、任务定义、输入文件和配置的变化会影响 cache hit/miss。[T3]
- 环境变量必须通过 `env`、`globalEnv` 或相关 passthrough 配置纳入任务模型，否则可能在不同环境复用错误的缓存结果。[T4]
- Turborepo 官方 CI 文档支持通过 remote cache、`--affected` 和任务图减少 CI 工作量；使用 affected 模式需要足够的 Git 历史，否则可能把所有包误判为变更。[T5]

**本项目设计结论**：

- 使用 Turborepo，但只把它当作 pnpm/TypeScript 任务编排器；它不负责 uv lock、Python 虚拟环境、FastAPI 启动或 RocketMQ 任务。
- `turbo.json` 只注册前端/TypeScript 的 `lint`、`typecheck`、`test:unit`、`build`、`generate` 等确定性任务。
- Python 任务使用 uv 的原生命令，在 CI 中作为独立 job 或显式步骤运行；不要用 Turborepo 伪造 Python package graph。
- 前端应用构建产物、TypeScript 包 `dist/**` 和合同生成产物可以缓存；开发服务器、依赖外部 API 状态的任务、Compose 集成测试和默认 Playwright E2E 不进入可复用缓存。
- remote cache 初期可选；先建立正确的 `inputs`、`outputs` 和环境变量声明，再启用 remote cache。任何包含密钥、医疗数据或外部 API 返回内容的目录都不能作为缓存输出。

### 2.4 FastAPI、应用分层与 Python 服务职责

**官方事实**：FastAPI 的官方“大型应用、多文件”文档使用包目录、`main.py`、依赖模块和多个 `APIRouter`，再由主应用通过 `include_router()` 组合路由；这是一种拆分多文件 HTTP 应用的官方方式。[FA1]

**本项目设计结论**：

- `main.py` 只负责创建 FastAPI app、注册中间件、异常处理、生命周期和 router；不能成为所有业务逻辑的集中点。
- HTTP 层按 feature 拆分 router、request/response DTO、依赖和权限检查；应用服务位于 `application/`，领域规则位于 `medical-core`，具体数据库或外部 API 适配位于 `packages/infra`。`apps/api` 只拥有组合根，不拥有供 Agent/Worker 导入的基础设施实现。
- API 路由不直接调用 SQL、Milvus、Redis 或外部模型 SDK；通过应用服务和端口完成调用，以便 API、Agent 和 Worker 共享行为并可用 fake adapter 测试。
- FastAPI 服务只负责同步请求/响应和管理接口；文档摄取、MinerU、切块、Embedding、Reranker 和 Milvus 索引等长任务由 Worker/ RocketMQ 路径完成。

### 2.5 TanStack Start、React 与 Vite

**官方事实**：

- TanStack Start 官方概览将其定义为基于 TanStack Router 的全栈 React framework，提供 full-document SSR、streaming、server functions、server/API routes、client/server builds 和 Vite/Rsbuild 支持；官方当前文档页面标注其处于 Release Candidate 阶段。[TS1]
- TanStack Start 官方路由文档说明文件路由位于 `src/routes`，根路由必须是 `src/routes/__root.tsx`；路由树文件 `src/routeTree.gen.ts` 是自动生成文件。[TS2]
- Vite 官方文档说明 `index.html` 是应用入口，Vite 以项目 root 解析源码和配置，并明确提到可以解析 monorepo 中 project root 之外的依赖。[V1]
- Vite 官方配置文档说明会在 project root 中查找 `vite.config.*`，支持 TypeScript 配置和 `defineConfig`；官方还提示在 monorepo 中 config bundling 可能遇到问题，可按需使用 module runner。[V2]

**本项目设计结论**：

- `apps/web` 是一个独立的 TanStack Start application package；它拥有自己的 `package.json`、`app.config.ts`、`vite.config.ts`、`tsconfig.json`、`src/`、`public/` 和测试目录。
- `src/routes` 只负责 URL、loader、页面组合和 route-level error boundary；可复用的业务交互放到 `src/features/<feature>/`，通用组件放到 `src/components/`，请求/认证/格式化等放到 `src/lib/`。
- 不手工修改 `routeTree.gen.ts`；它属于生成产物，由 TanStack Start 的开发/构建流程维护。
- TanStack Start 的 server functions/server routes 不承担本项目的第二套业务后端；FastAPI 仍是认证、授权、知识库、检索、模型调用和持久化业务的权威入口。若 Start server loader 需要数据，仍通过版本化 `/api` 合同访问 FastAPI。
- Vite 的 project root 以 `apps/web` 为边界；只在确有 monorepo 解析需要时配置 workspace 目录访问，不把仓库根目录的服务端 secrets 暴露给浏览器构建。

### 2.6 TypeScript、ESLint、Prettier、Vitest 与 Playwright

**官方事实**：

- TypeScript project references 用于把大型 TypeScript 项目拆成更小的项目；`tsc --build` 与 references 协作以支持更快构建。[TY1]
- TypeScript `strict` 选项启用更严格的类型检查，并可随 TypeScript 版本获得新的严格检查行为。[TY2]
- ESLint 当前官方配置文档以 `eslint.config.js`、`.mjs`、`.cjs` 等 flat config 文件为主，并定义了配置文件查找和组合规则。[ES1]
- Prettier 会从待格式化文件所在位置向上查找配置；配置可以放在专用配置文件或 `package.json` 中。[PR1]
- Vitest 默认会读取 `vite.config.*`，也可以使用单独的 `vitest.config.*`；官方 Test Projects 文档提供了在一个 Vitest 进程中定义多个项目配置的方式，适用于 monorepo，并明确说明旧的 `workspace` 配置已被 `projects` 替代。[VI1][VI2]
- Vitest 官方 coverage 文档支持 V8 和 Istanbul provider，并说明默认使用 V8；未被测试导入的文件需要通过 `coverage.include` 显式纳入报告。[VI3]
- Playwright 官方 CI 文档建议在 CI 中安装浏览器及其系统依赖；为稳定性和可复现性，推荐 CI 使用 `workers: 1`，更大规模并行时再使用 sharding。[PW3]

**本项目设计结论**：

- 根目录统一放 `tsconfig.base.json`、`eslint.config.mjs` 和 Prettier 配置；包可以有最小的本地覆盖，但不能复制出多套互相漂移的规则。
- 开启 TypeScript `strict`；`apps/web` 使用 Vite/TanStack Start 的应用配置，纯 TypeScript 包使用 project references 和 `tsc --build`。不要把 Vite 的 bundling 成功当作类型检查成功。
- Vitest 根配置使用 `test.projects` 指向 `apps/web` 和 `packages/*/typescript` 等前端项目；各项目可按 `unit`、`component`、`browser` 需要定义独立环境。
- Playwright 放在 `apps/web` 的 E2E 测试边界，单独使用 `playwright.config.ts`；它启动或依赖 Compose `test` profile，不与 Vitest 的 unit/component project 混为一个测试入口。
- CI 至少执行格式检查、ESLint、TypeScript 类型检查、Vitest unit/component、API contract 检查和 Playwright E2E；coverage 作为独立质量门槛，覆盖范围以业务核心和边界层为主，不能用单一总百分比替代关键路径测试。

### 2.7 Docker Compose profiles

**官方事实**：

- Compose profiles 用于在同一个 Compose 文件中按环境或用例选择性激活服务；没有 `profiles` 属性的服务默认始终启用，带有 `profiles` 的服务只有在 profile 激活时才会启动。[D1]
- 可以通过 `docker compose --profile <name>` 或 `COMPOSE_PROFILES` 启用 profile，也可以同时启用多个 profile。[D1]
- Docker 官方建议核心服务不要放入 profile，以便它们始终可用；服务之间的依赖不会在所有 profile 组合下自动变得有效，profile 组合必须保持 Compose model 合法。[D1][D2]
- Compose `profiles` 只影响服务激活；其他 top-level 元素不受 profile 影响。[D2]

**本项目设计结论**：

- 用户可见的规范文件名固定为仓库根目录 `docker-compose.yml`；所有文档和 CI 命令显式使用 `-f docker-compose.yml`，避免与 Compose 默认查找的其他文件名产生歧义。
- PostgreSQL、Redis、RocketMQ、Milvus 依赖及其必要的对象存储/元数据服务作为核心基础设施，原则上不依赖环境 profile 才存在。
- `dev` profile 激活热重载、调试工具和开发辅助服务；`test` profile 激活测试 runner、Playwright 所需服务和测试专用配置；`prod` profile 激活生产应用容器、Worker、Aegra server/worker 和生产观测配置。
- profile 不用于偷偷改变同一服务的业务语义；环境变量、镜像标签、资源限制和持久化策略必须明确记录，并通过健康检查、依赖顺序和独立凭据保证环境边界。
- 推荐命令形态：`docker compose -f docker-compose.yml --profile dev up`、`docker compose -f docker-compose.yml --profile test up -d`、`docker compose -f docker-compose.yml --profile prod up -d`。

## 3. 推荐目录布局

以下布局是本项目的设计结论。目录名可在实现阶段微调，但包边界和依赖方向不应随意改变。

```text
MedicalRAG/
├── docker-compose.yml                 # 唯一用户可见的 Compose 入口
├── pyproject.toml                     # uv workspace root；不是运行时应用
├── uv.lock                            # 所有 Python workspace 成员共享
├── package.json                       # private root；只放 JS 工具和根脚本
├── pnpm-workspace.yaml                # 只声明 JS/TS workspace 成员
├── pnpm-lock.yaml                     # pnpm workspace lockfile
├── turbo.json                         # 前端/TypeScript 任务图和缓存规则
├── tsconfig.base.json                 # TypeScript 共享基线
├── eslint.config.mjs                 # 根 flat config
├── prettier.config.mjs                # 根格式化配置
├── .node-version                      # Node 24 LTS 运行时约束
├── apps/
│   ├── api/
│   │   ├── pyproject.toml
│   │   ├── src/
│   │   │   └── medicalrag_api/
│   │   │       ├── main.py
│   │   │       ├── api/
│   │   │       │   ├── dependencies.py
│   │   │       │   ├── exception_handlers.py
│   │   │       │   └── v1/
│   │   │       │       ├── router.py
│   │   │       │       ├── auth/
│   │   │       │       │   ├── router.py
│   │   │       │       │   ├── schemas.py
│   │   │       │       │   └── dependencies.py
│   │   │       │       ├── conversations/
│   │   │       │       ├── knowledge/
│   │   │       │       ├── ingestion/
│   │   │       │       ├── admin/
│   │   │       │       └── health/
│   │   │       ├── application/
│   │   │       │   ├── commands/
│   │   │       │   ├── queries/
│   │   │       │   ├── services/
│   │   │       │   └── ports/
│   │   │       ├── bootstrap/
│   │   │       │   ├── container.py
│   │   │       │   └── lifespan.py
│   │   │       └── settings.py
│   │   ├── migrations/
│   │   └── tests/
│   │       ├── unit/
│   │       ├── integration/
│   │       └── contract/
│   ├── agent/
│   │   ├── pyproject.toml
│   │   ├── src/
│   │   │   └── medicalrag_agent/
│   │   │       ├── main.py
│   │   │       ├── graph/
│   │   │       │   ├── builder.py
│   │   │       │   ├── state.py
│   │   │       │   ├── nodes/
│   │   │       │   │   ├── intent/
│   │   │       │   │   ├── rewrite/
│   │   │       │   │   ├── retrieval/
│   │   │       │   │   ├── evidence/
│   │   │       │   │   ├── generation/
│   │   │       │   │   └── safety/
│   │   │       │   └── prompts/
│   │   │       ├── runtime/
│   │   │       │   ├── auth.py
│   │   │       │   ├── config.py
│   │   │       │   └── dependencies.py
│   │   │       └── protocol/
│   │   │           └── langgraph_server.py
│   │   └── tests/
│   │       ├── unit/
│   │       ├── graph/
│   │       └── protocol/
│   ├── worker/
│   │   ├── pyproject.toml
│   │   ├── src/
│   │   │   └── medicalrag_worker/
│   │   │       ├── main.py
│   │   │       ├── consumers/
│   │   │       │   ├── ingestion/
│   │   │       │   ├── extraction/
│   │   │       │   ├── embedding/
│   │   │       │   ├── indexing/
│   │   │       │   └── operations/
│   │   │       ├── handlers/
│   │   │       ├── retry/
│   │   │       └── bootstrap/
│   │   └── tests/
│   │       ├── unit/
│   │       └── integration/
│   ├── evaluation/
│   │   ├── pyproject.toml
│   │   ├── src/medicalrag_evaluation/
│   │   │   ├── datasets/
│   │   │   ├── metrics/
│   │   │   ├── runners/
│   │   │   └── cli.py
│   │   └── tests/
│   │       ├── unit/
│   │       └── contract/
│   └── web/
│       ├── package.json
│       ├── app.config.ts
│       ├── vite.config.ts
│       ├── tsconfig.json
│       ├── vitest.config.ts
│       ├── playwright.config.ts
│       ├── public/
│       ├── src/
│       │   ├── routes/
│       │   │   ├── __root.tsx
│       │   │   ├── login.tsx
│       │   │   ├── _app/
│       │   │   │   ├── route.tsx
│       │   │   │   ├── index.tsx
│       │   │   │   ├── conversations/
│       │   │   │   └── admin/
│       │   ├── routeTree.gen.ts      # generated；禁止手工编辑
│       │   ├── features/
│       │   │   ├── auth/
│       │   │   ├── chat/
│       │   │   ├── conversations/
│       │   │   ├── knowledge/
│       │   │   └── admin/
│       │   ├── components/
│       │   │   ├── layout/
│       │   │   └── ui/
│       │   ├── lib/
│       │   │   ├── api-client/
│       │   │   ├── auth/
│       │   │   ├── assistant/
│       │   │   └── formatting/
│       │   ├── router.tsx
│       │   └── styles/
│       └── tests/
│           ├── unit/
│           ├── component/
│           └── e2e/
├── packages/
│   ├── medical-core/
│   │   ├── pyproject.toml
│   │   ├── src/medical_core/
│   │   │   ├── conversations/
│   │   │   ├── intent/
│   │   │   ├── knowledge/
│   │   │   ├── ingestion/
│   │   │   ├── retrieval/
│   │   │   ├── evidence/
│   │   │   ├── safety/
│   │   │   ├── models/
│   │   │   ├── policies/
│   │   │   └── ports/
│   │   └── tests/
│   │       ├── unit/
│   │       └── property/
│   ├── infra/
│   │   ├── pyproject.toml
│   │   ├── src/medicalrag_infra/
│   │   │   ├── postgres/
│   │   │   ├── redis/
│   │   │   ├── milvus/
│   │   │   ├── rocketmq/
│   │   │   ├── object_storage/
│   │   │   ├── providers/
│   │   │   │   ├── llm/
│   │   │   │   ├── embedding/
│   │   │   │   ├── reranker/
│   │   │   │   └── mineru/
│   │   │   └── observability/
│   │   │       ├── logging/
│   │   │       ├── metrics/
│   │   │       └── health/
│   │   └── tests/
│   │       ├── unit/
│   │       ├── contract/
│   │       └── integration/
│   └── contracts/
│       ├── schemas/
│       │   ├── http/
│       │   ├── events/
│       │   └── agent/
│       ├── python/
│       │   ├── pyproject.toml
│       │   └── src/medicalrag_contracts/
│       └── typescript/
│           ├── package.json
│           ├── tsconfig.json
│           ├── src/
│           └── tests/
├── infra/
│   ├── docker/
│   │   ├── api/
│   │   ├── agent/
│   │   ├── worker/
│   │   └── web/
│   ├── milvus/
│   ├── postgres/
│   ├── redis/
│   └── rocketmq/
├── scripts/
│   ├── ci/
│   ├── dev/
│   └── codegen/
└── docs/
    └── research/
```

### 3.1 根目录文件职责

| 文件 | 职责 | 不应承担的职责 |
| --- | --- | --- |
| `pyproject.toml` | uv workspace root、统一 Python 版本约束和 workspace 成员声明 | FastAPI 业务依赖、运行时入口 |
| `uv.lock` | Python 全 workspace 的确定性解析结果 | 手写依赖版本说明 |
| `package.json` | private root 的 JS 工具、Turborepo 和根级便利命令 | Web 业务依赖的隐式来源 |
| `pnpm-workspace.yaml` | pnpm workspace 成员与 workspace 级 pnpm 配置 | Python 包声明 |
| `pnpm-lock.yaml` | JS/TS 依赖解析结果 | Python 依赖锁定 |
| `turbo.json` | JS/TS 任务图、输入、输出和缓存策略 | Python/Compose 运行时编排 |
| `docker-compose.yml` | 本地、测试、自托管拓扑和 profile | 应用业务逻辑、依赖版本解析 |
| `infra/` | Dockerfile、服务初始化和非业务基础设施配置 | 领域对象和用例 |
| `packages/contracts/schemas` | 跨进程、跨语言的可序列化合同源文件 | 运行时网络调用 |

## 4. 包边界与依赖方向

### 4.1 依赖图

```text
apps/web
  └── packages/contracts/typescript

apps/api ───────┐
apps/agent ─────┼──> packages/infra ───> packages/medical-core
apps/worker ────┘             │
                              ├── PostgreSQL
                              ├── Redis
                              ├── Milvus
                              ├── RocketMQ
                              └── 外部 LLM/Embedding/Reranker/MinerU API

packages/contracts/python <── packages/contracts/schemas
packages/contracts/typescript <── packages/contracts/schemas
```

### 4.2 强制规则

1. 依赖只能从外向内：delivery/runtime → application/adapter → domain；`medical-core` 不依赖入口应用。
2. `apps/api`、`apps/agent`、`apps/worker` 不互相 import；需要共享行为时依赖 `medical-core` 或 `packages/infra`。
3. `packages/infra` 可以依赖 `medical-core` 的端口和模型，但不能把具体 SDK 类型泄露进核心领域接口。
4. Router、Agent Graph node 和 RocketMQ consumer 都是薄适配层；编排可以不同，业务不变量必须来自同一个核心服务/策略。
5. `apps/web` 只能依赖 TypeScript 合同包和前端库；禁止在浏览器包中引入 Python、数据库、Milvus、Redis、RocketMQ 或模型 SDK。
6. `packages/contracts/schemas` 是跨语言源；Python 和 TypeScript 生成物必须标记为 generated，禁止分别手工维护两套相同 DTO。
7. 每个包声明自己的直接依赖；不得依赖根 `node_modules` 的偶然提升，也不得依赖另一个 Python 成员的传递安装结果。
8. JavaScript/TypeScript 内部包使用 `workspace:` 协议；Python 内部包使用 uv 的 `tool.uv.sources` + `workspace = true`。[P1][U1]
9. 不允许循环依赖；如果两个模块互相需要类型，应将稳定的抽象或合同上移到更低层，而不是增加反向 import。
10. `medical-core` 不允许出现名为 `helpers.py`、`common.py` 的无边界垃圾桶；公共代码必须归属到明确的领域模块或端口模块。
11. `packages/infra` 不是 `apps/api` 的子模块：API、Agent、Worker 各自构造依赖容器，只声明当前进程需要的适配器。
12. `infra/`（仓库根部署目录）与 `packages/infra/`（Python 适配器包）是两个不同职责的目录，不得交叉导入业务代码。

## 5. 任务编排方案

### 5.1 本地开发命令分层

#### Python

```text
uv lock                                  # 更新整个 Python workspace 的锁
uv sync --all-packages                   # 同步本地完整开发环境
uv run --package medicalrag-api ...      # 运行 API 成员命令
uv run --package medicalrag-agent ...    # 运行 Agent 成员命令
uv run --package medicalrag-worker ...   # 运行 Worker 成员命令
```

这里的具体命令参数以实现时使用的 uv 版本官方 CLI 为准；原则是始终通过 uv project/workspace 接口执行，不直接修改 `.venv`。[U1][U2]

#### JavaScript/TypeScript

```text
pnpm install --frozen-lockfile
pnpm --filter @medicalrag/web dev
pnpm --filter @medicalrag/web typecheck
pnpm --filter @medicalrag/web test:unit
pnpm turbo run lint typecheck test:unit build
```

`pnpm --filter` 负责局部选择；Turborepo 负责已注册任务的依赖图、并行和缓存。pnpm 的递归命令可作为简单 workspace 操作，但不能替代明确的 Turborepo 任务依赖。[P2][P3][T2]

#### Compose

```text
docker compose -f docker-compose.yml --profile dev up
docker compose -f docker-compose.yml --profile test up -d
docker compose -f docker-compose.yml --profile prod up -d
```

Compose 只负责服务拓扑和生命周期；应用代码中的迁移、健康探测和业务初始化仍由对应应用或明确的初始化任务负责。[D1][D2]

### 5.2 Turborepo 任务图建议

建议为 TypeScript workspace 注册以下任务：

| 任务 | 依赖关系 | 产物/缓存建议 |
| --- | --- | --- |
| `generate` | 依赖合同源或 OpenAPI 输入 | 缓存生成文件；声明 `generated/**` |
| `lint` | 无构建依赖 | 通常只缓存日志，不恢复源码文件 |
| `typecheck` | 对依赖包使用 `^typecheck` 或 `^build` | 无文件产物，缓存结果和日志 |
| `test:unit` | 通常依赖 `^build` 或合同生成 | 可缓存确定性报告；不要缓存外部服务响应 |
| `build` | `^build` | 声明 `dist/**`、TanStack Start 产物目录 |
| `e2e` | 不纳入默认 `turbo run` | 由 Compose test profile + Playwright 独立运行 |
| `dev` | 不缓存、不进入 CI 质量门槛 | 长驻进程 |

依赖包构建完成后再构建应用使用 `dependsOn: ["^build"]`；同一包内的生成、类型检查和构建顺序使用无 `^` 的任务依赖。每个任务的输出必须准确声明，不能为了提高命中率把整个仓库或包含 secrets 的目录加入 `outputs`。[T2][T3]

### 5.3 Python 与前端任务在 CI 中的汇合方式

推荐 CI 拆成以下 job，而不是强行让一个工具包办全部语言：

1. `python-quality`：安装 Python 3.12 和 uv，执行 `uv sync --locked`，再按成员运行格式、静态检查、单元测试和合同测试。
2. `frontend-quality`：安装 Node 24 LTS 与固定 pnpm，执行 frozen-lockfile install，再运行 `turbo run lint typecheck test:unit`。
3. `contract-check`：从 `packages/contracts/schemas` 或 FastAPI OpenAPI 输入生成 Python/TypeScript 产物，检查生成结果无未提交差异。
4. `compose-integration`：使用 `docker-compose.yml` 的 `test` profile 启动 PostgreSQL、Redis、RocketMQ、Milvus 和应用依赖，执行 API/Worker/Agent 合同测试。
5. `web-e2e`：在测试拓扑可用后运行 Playwright；CI 默认 `workers: 1`，只有硬件、隔离和测试数据足够稳定时才增加 shard。[PW3]
6. `image-build`：按服务构建 API、Agent、Worker 和 Web 镜像，使用 lockfile 驱动依赖层缓存。

## 6. 缓存与 CI 建议

### 6.1 依赖缓存

**uv**

- 使用官方 `astral-sh/setup-uv` action 或等价官方安装方式，并启用 uv cache；官方示例使用 `uv.lock` 作为缓存 key 的核心输入。[U5]
- CI 以操作系统、Python 版本、uv 版本和 `uv.lock` 共同形成缓存边界；lockfile 变化必须导致依赖缓存重新验证。
- CI 结束前可执行官方推荐的 `uv cache prune --ci`，控制缓存体积。[U5]

**pnpm**

- 缓存 pnpm store，而不是把未经校验的完整 `node_modules` 当作跨任务真相；缓存 key 至少包含操作系统、Node/pnpm major 和 `pnpm-lock.yaml`。[P4]
- 只让可信 job 写入并恢复 pnpm store/cache；不让不可信 PR 任务把可执行内容写入后供可信 job 使用。[P4]
- CI 明确使用与 lockfile 生成版本兼容的 pnpm major，并执行 frozen-lockfile 安装。[P4]

**Docker**

- uv 官方 Docker 指南推荐使用 BuildKit cache mount，并将依赖文件与源代码分层复制，以便源代码变化时复用依赖层。[U6]
- workspace Docker build 在只复制锁文件和 pyproject 时要遵循 uv 官方 workspace 构建建议；最终镜像使用 locked/frozen 的确定性同步，不在镜像内自由解析版本。[U6]

### 6.2 Turborepo 缓存

- 先正确声明 `inputs`、`outputs`、`dependsOn` 和环境变量，再启用 local/remote cache。[T2][T3][T4]
- `build`、`generate`、确定性的 `typecheck` 和 unit test 可以缓存；依赖外部 API、数据库状态、真实 RocketMQ、真实 MinerU 或真实模型响应的任务默认不缓存。
- `VITE_*`、API base URL、构建模式等影响 Web 产物的环境变量必须纳入任务 hash；密钥只通过 CI secret 注入，不能写进 task output 或日志。[T4]
- remote cache 凭据 `TURBO_TOKEN`、`TURBO_TEAM` 只在可信 CI job 注入；不将其传给来自不可信 fork 的 job。[T5]

### 6.3 变更影响范围

- TypeScript：使用 Turborepo `--affected` 或 pnpm `--filter` 选择变更包及其依赖/被依赖者；CI checkout 必须保留足够 Git 历史。[P2][T5]
- Python：uv 负责依赖和 workspace 一致性，不自动替代代码影响分析；初期对所有 Python 核心包运行质量检查，成熟后再按 `apps/*`、`packages/*` 路径做 job 过滤。
- 合同：任何 `packages/contracts/schemas` 变化都视为 API、事件和前端生成物的全局影响，不能只运行修改文件所在目录的测试。
- Compose：`docker-compose.yml`、Dockerfile、infra 初始化脚本或服务版本变化都触发集成测试与镜像构建；不能因为应用源码未改就跳过基础设施合同检查。

## 7. 测试布局与质量门槛

### 7.1 Python

每个 Python member 单独拥有 `tests/`，至少区分：

- `unit/`：medical-core 规则、状态机、策略、纯应用服务和 fake port。
- `integration/`：PostgreSQL、Redis、Milvus、RocketMQ 和外部 API adapter 的合同/集成行为。
- `contract/`：FastAPI OpenAPI、事件 schema、Aegra/LangGraph Server 兼容边界。
- `graph/`：Agent Graph 的节点连接、路由和失败传播；节点内部规则仍由 core unit tests 覆盖。

### 7.2 TypeScript

- 根 Vitest 配置使用 `test.projects`；每个 package 或应用可以有自己的配置和环境，避免将浏览器测试、Node 测试和 UI 测试混在一个隐式默认环境中。[VI2]
- `apps/web` 的 unit/component 测试覆盖 feature、路由 loader、表单状态、错误态和 assistant-ui 适配边界；不要直接测试第三方库内部实现。
- coverage 配置明确 `include`，确保未被某个测试偶然 import 的关键模块不会从报告中消失。[VI3]
- Playwright 只覆盖真实用户路径和跨服务合同：登录、会话、聊天流、来源查看、反馈、知识库管理和关键错误态；不要用 E2E 替代大量 unit tests。

### 7.3 质量门槛的分层

```text
每次提交：格式检查 + ESLint + TypeScript strict/typecheck + Python 静态检查 + 快速 unit tests
Pull Request：上述检查 + contract tests + 受影响前端包构建
合并/发布：Compose test profile + API/Worker/Agent integration + Playwright E2E + 镜像构建
```

这是本项目的执行策略，不是某个工具官方强制的唯一流程；工具官方事实仅约束其配置和运行语义。[TY1][ES1][VI1][PW3]

## 8. 版本与配置治理

1. Node.js 24 LTS 是本项目运行时约束；Node 官方 release 页面是生命周期核对来源，实施时应再次确认 24.x 的维护窗口。[N1]
2. pnpm、uv、TypeScript、TanStack Start、React、Vite、ESLint、Prettier、Vitest 和 Playwright 均应在实现阶段固定精确版本或受控 major 范围，不使用 `latest` 作为生产构建输入。
3. 根目录保留 `uv.lock` 与 `pnpm-lock.yaml`；依赖升级必须在同一个变更中说明影响的应用、包、镜像和 CI 缓存。
4. TanStack Start 官方当前文档仍标注 Release Candidate；因此应锁定具体版本并在升级时执行路由生成、SSR、streaming、assistant-ui LangGraph adapter 和 Playwright 回归。[TS1]
5. `docker-compose.yml` 中的服务镜像、健康检查、网络、卷和 profile 名称属于部署合同；修改它们必须有 Compose test profile 验证。
6. 根级配置只定义跨包一致的基线；任何包级例外必须有明确原因，不能复制配置文件后悄悄分叉。

## 9. 官方事实与本项目结论的边界

本文中的“官方事实”是对链接文档当前表述的归纳，例如 uv 的 workspace/lockfile 语义、pnpm 的 `workspace:` 协议、Turborepo 的任务缓存模型、TanStack Start 的路由目录、Vite 的 root、Vitest 的 `projects` 和 Docker Compose profiles。

本文中的“本项目设计结论”是结合 MedicalRAG 已确认的运行时职责推导出的工程方案，例如：

- `medical-core` 与 `packages/infra` 的拆分，以及不把 `infra` 并入 `apps/api`；
- 删除没有独立 seam 价值的 `packages/ui`、`packages/testkit`、`packages/config`、`packages/common` 和 `packages/utils`；
- `apps/api`、`apps/agent`、`apps/worker`、`apps/web` 的服务边界；
- Turborepo 只编排 JS/TS；
- Aegra、RocketMQ、FastAPI 的进程职责；
- profile 的 dev/test/prod 分组；
- 哪些测试和任务允许缓存；
- 目录中的具体 feature 名称。

这些设计结论不是上游工具的强制要求，但应作为本项目实现阶段的默认架构；如需改变，应通过架构决策记录说明新的依赖方向、部署影响、测试影响和迁移成本。

## 10. 官方一手来源

所有链接均为官方文档或官方项目页面；访问日期为 2026-07-26。

### uv / Python packaging

- [U1] [uv — Using workspaces](https://docs.astral.sh/uv/concepts/projects/workspaces/)
- [U2] [uv — Project structure and files](https://docs.astral.sh/uv/concepts/projects/layout/)
- [U3] [uv — Managing dependencies](https://docs.astral.sh/uv/concepts/projects/dependencies/)
- [U4] [uv — Configuring projects](https://docs.astral.sh/uv/concepts/projects/config/)
- [U5] [uv — Using uv in GitHub Actions](https://docs.astral.sh/uv/guides/integration/github/)
- [U6] [uv — Using uv in Docker](https://docs.astral.sh/uv/guides/integration/docker/)
- [PY1] [Python Packaging User Guide — src layout vs flat layout](https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/)
- [PY2] [Python Packaging User Guide — Writing your pyproject.toml](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/)

### pnpm / Turborepo

- [P1] [pnpm — Workspace](https://pnpm.io/workspaces)
- [P2] [pnpm — Filtering](https://pnpm.io/filtering)
- [P3] [pnpm — pnpm recursive](https://pnpm.io/cli/recursive)
- [P4] [pnpm — Continuous Integration](https://pnpm.io/continuous-integration)
- [T1] [Turborepo — Structuring a repository](https://turborepo.com/docs/crafting-your-repository/structuring-a-repository)
- [T2] [Turborepo — Configuring tasks](https://turborepo.com/docs/crafting-your-repository/configuring-tasks)
- [T3] [Turborepo — Caching](https://turborepo.com/docs/crafting-your-repository/caching)
- [T4] [Turborepo — Using environment variables](https://turborepo.com/docs/crafting-your-repository/using-environment-variables)
- [T5] [Turborepo — Constructing CI](https://turborepo.com/docs/crafting-your-repository/constructing-ci)

### FastAPI / TanStack Start / Vite

- [FA1] [FastAPI — Bigger Applications: Multiple Files](https://fastapi.tiangolo.com/tutorial/bigger-applications/)
- [TS1] [TanStack Start — Overview](https://tanstack.com/start/latest/docs/framework/react/overview)
- [TS2] [TanStack Start — Routing](https://tanstack.com/start/latest/docs/framework/react/guide/routing)
- [V1] [Vite — Getting Started](https://vite.dev/guide/)
- [V2] [Vite — Configuring Vite](https://vite.dev/config/)

### TypeScript / ESLint / Prettier / Vitest / Playwright

- [TY1] [TypeScript — Project References](https://www.typescriptlang.org/docs/handbook/project-references.html)
- [TY2] [TypeScript — `strict` TSConfig option](https://www.typescriptlang.org/tsconfig/strict.html)
- [ES1] [ESLint — Configuration Files](https://eslint.org/docs/latest/use/configure/configuration-files)
- [PR1] [Prettier — Configuration File](https://prettier.io/docs/configuration)
- [VI1] [Vitest — Getting Started](https://vitest.dev/guide/)
- [VI2] [Vitest — Test Projects](https://vitest.dev/guide/projects)
- [VI3] [Vitest — Coverage](https://vitest.dev/guide/coverage)
- [PW3] [Playwright — Continuous Integration](https://playwright.dev/docs/ci)

### Node.js / Docker Compose

- [N1] [Node.js — Releases](https://nodejs.org/en/about/previous-releases)
- [D1] [Docker Docs — Using profiles with Compose](https://docs.docker.com/compose/how-tos/profiles/)
- [D2] [Docker Docs — Compose file reference: Profiles](https://docs.docker.com/reference/compose-file/profiles/)
