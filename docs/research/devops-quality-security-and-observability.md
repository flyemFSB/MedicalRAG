# MedicalRAG DevOps、质量、安全与可观测性官方资料调研

> 调研日期：2026-07-26  
> 适用范围：MedicalRAG 单仓库；Python 3.12、uv、FastAPI、Aegra；Node.js 24 LTS、pnpm、TypeScript、React、Vite、TanStack Start；PostgreSQL、Redis、Milvus、RocketMQ；外部 LLM、Embedding、Reranker、MinerU API、Langfuse；仓库根目录部署入口为 `docker-compose.yml`。  
> 来源约束：本文只引用技术项目自身维护的官方文档、官方项目仓库或标准组织文档。未使用博客、转载文章、营销材料或社区约定作为官方事实依据。  
> 文档性质：研究与实现前置约束，不包含可直接复制的实现代码，也不替代 `docs/spec.md`、`docs/architecture.md` 或 ADR。

> **计划变更（2026-08-01）：** 本文是历史调研快照。按 [ADR 0063](../adr/0063-arq-replaces-rocketmq-as-the-durable-job-queue.md) 消息总线已从 Apache RocketMQ 更换为 arq，按 [ADR 0064](../adr/0064-uv-manages-python-314-runtime.md) Python 基线已提高到 3.14，并按 [ADR 0065](../adr/0065-aliyun-mirrors-for-pnpm-uv-and-apt.md) 增加 pnpm/uv/apt 阿里云镜像配置。正文中与 RocketMQ、Python 3.12 相关的结论已被上述 ADR 取代。

## 1. 结论摘要

### 1.1 推荐的工程基线

**本项目建议**：

1. 以根目录 `docker-compose.yml` 作为唯一 Compose 入口，使用 `dev`、`test`、`prod` profiles 选择拓扑；不要把 profile 当作权限边界或高可用方案。
2. 所有服务定义轻量、无副作用的 healthcheck；依赖启动使用 `service_healthy`，应用内部仍要具备有界重试和断线恢复。
3. Python 使用 `src` layout、uv lockfile、Ruff、类型检查和 pytest；前端使用 TypeScript `strict`、ESLint flat config、Prettier、Vitest 和 Playwright。
4. 单元测试不访问真实外部 API；FastAPI 组件测试使用 HTTPX 的 ASGI transport，数据库/缓存集成测试使用 Testcontainers，Milvus、RocketMQ、Aegra 多服务合同测试使用 Compose `test` profile。
5. CI 采用“格式/静态检查 → 单元/组件测试 → 合同测试 → Compose 集成测试 → Playwright E2E → 镜像构建 → 发布”的分层门禁；任何来自不可信 fork 的任务不得获得生产密钥、发布权限或可写缓存。
6. 生产可观测性使用 Langfuse 记录 Aegra 的 AI/RAG observations，API/Worker 使用结构化 JSON 日志、metrics 和 health checks；日志、observation 属性和测试产物均禁止包含医疗内容、密码、Cookie、令牌和外部 API 密钥。
7. 身份验证使用本系统自己的服务端会话；密码使用 Argon2id；Cookie 只保存不可推断含义的会话标识，并启用 `Secure`、`HttpOnly`、合适的 `SameSite` 和 CSRF 防护。
8. 容器构建使用锁定的依赖和基础镜像 digest，发布镜像附带 SBOM 与 provenance attestation；生产部署使用不可变 digest，不使用 `latest`。
9. PostgreSQL 是业务数据权威存储，采用 base backup + WAL/PITR；Milvus 索引需要备份或可重建路径；Redis 默认按可恢复缓存/会话处理；RocketMQ 的任务可靠性依赖持久卷、复制、保留策略、重试和死信处理。

### 1.2 必须显式接受的版本事实

**官方事实**：截至本次调研，Python 3.12 已处于 security 阶段，官方生命周期表列出的终止日期为 2028-10；Node.js 24.x 的生命周期和 LTS 状态以官方 release schedule 为准，日期均可能调整。[V1][V2]

**本项目建议**：既然 Python 3.12 和 Node.js 24 是已确认的运行时约束，就在实现阶段锁定它们并建立升级窗口；新依赖必须验证其对这两个运行时的支持。不能因为“仍受支持”就把 Python 3.12 当作拥有完整 bugfix 发布节奏的最新 Python 版本。

## 2. 事实与设计建议的边界

本文使用以下标记：

| 标记 | 含义 |
| --- | --- |
| **官方事实** | 上游官方文档或标准组织明确描述的语义、限制或推荐。 |
| **本项目建议** | 根据 MedicalRAG 已确认的职责、数据敏感性和部署约束推导出的落地方案，不是上游工具强制要求。 |
| **版本 caveat** | 版本、默认值、生命周期或稳定性可能变化，实施前需要再次核对并锁定。 |

如果“官方事实”和“本项目建议”发生冲突，事实用于理解工具边界，建议用于决定本项目的工程约束；改变建议时必须重新评估安全、测试、备份和发布影响。

## 3. 编码与开发规范

### 3.1 Python

**官方事实**：PEP 8 规定 Python 标识符、缩进、导入和代码布局等风格；PEP 257 定义模块、类、函数和方法 docstring 的基本约定。pytest 官方建议新项目使用 `src` layout，并建议使用 `importlib` import mode；pytest 当前文档还提供了 strict 配置，用于启用更严格的配置检查。[PY1][PY2][TST1]

**本项目建议**：

- 每个 uv workspace member 使用 `src/<package_name>/`，测试放在该 member 的 `tests/` 下；禁止依赖仓库工作目录恰好位于 `sys.path` 的隐式导入行为。
- 公共模块、公共类、公共应用服务和跨进程协议适配器使用 docstring；docstring 说明行为、参数、返回值、异常、幂等性和副作用。简单赋值或明显代码不写“复述代码”的注释。
- 命名统一使用 `snake_case` 函数/变量/模块、`PascalCase` 类/协议、`UPPER_SNAKE_CASE` 常量；领域状态、事件类型和错误码使用有限、可枚举的值，不用自由字符串散落在各处。
- 注释重点解释“为什么”：安全限制、外部 API 的反常行为、RocketMQ 的幂等边界、Milvus schema 兼容约束、事务/重试顺序和临时版本 workaround；不要把注释写成逐行翻译。
- Ruff 负责格式和静态规则，类型检查单独作为门禁；格式化器的配置是唯一排版真相，不在不同 member 中复制互相漂移的规则。
- 对 `Any`、裸 `dict`、裸异常捕获、隐式全局状态和动态 import 设立审查门槛；确需使用时写出边界理由和测试覆盖。
- 应用层只依赖领域端口，基础设施实现放在 adapter；禁止 router、Agent graph node 或 RocketMQ consumer 直接把 SQL、Milvus SDK、Redis SDK 或外部 HTTP 调用写进业务流程。

**版本 caveat**：PEP 8 的具体行宽建议与格式化器默认值可能不同；实现阶段只选一套 formatter 配置并在 CI 中检查，不能同时让人工风格、编辑器和 formatter 争夺格式所有权。[PY1][PY2]

### 3.2 TypeScript、React 与前端工具链

**官方事实**：TypeScript 的 `strict` 选项启用一组更严格的类型检查，并可能随着 TypeScript 版本启用新的严格行为；ESLint 当前文档以 flat config 文件为主要配置模型；Prettier 建议把选项写入配置文件，使 CLI、编辑器和其他集成使用同一套格式规则；Vitest 支持独立测试配置和 monorepo 的 projects；Playwright 官方 CI 文档覆盖浏览器安装、报告和 CI 并行策略。[TS1][TS2][TS3][TS4][TS5]

**本项目建议**：

- 开启 TypeScript `strict`，并额外评估 `noUncheckedIndexedAccess`、`exactOptionalPropertyTypes`、`noImplicitOverride`、`noUnusedLocals` 和 `noUnusedParameters`；最终选项集合在根配置中固定。
- React 组件、hooks、route loader、server function 和 API client 使用明确的输入/输出类型；跨后端、Aegra 流式事件和前端状态的类型从合同源生成或集中维护，不在页面中手写重复结构。
- 禁止用 `any` 绕过后端合同；未知外部数据先进入 `unknown` 边界，再经过 schema 解析或显式缩窄。第三方 API、SSE、LangGraph/Aegra 事件和上传任务状态都视为不可信输入。
- ESLint 使用根级 flat config；Prettier 使用根级配置；包级例外必须说明原因，不能复制一套“差不多”的规则。
- 自动生成的路由树、合同产物和 OpenAPI 类型不得手工修改；源码变更后由生成任务更新，并在 CI 检查生成结果无未提交差异。
- 注释只记录状态机不变量、浏览器兼容性、安全边界和第三方库 workaround；组件名称和测试名称描述用户行为或业务语义，而不是内部实现细节。

### 3.3 依赖、配置和提交规范

**官方事实**：uv 的 CI 集成文档示例使用锁定同步；pnpm 的 CI 文档强调 frozen lockfile、版本兼容和只缓存可信任务可写入的 store/cache；GitHub Actions 安全文档建议最小化 token 权限，并将 action 固定到完整 commit SHA。[UV1][UV2][PN1][GH5]

**本项目建议**：

- CI 使用 `uv sync --locked` 和 `pnpm install --frozen-lockfile` 语义；依赖升级必须同时审查 lockfile、运行时支持、镜像层、漏洞影响和回滚路径。
- 环境变量只承载配置或由 secret 文件读取的引用；不得把密钥默认值写进代码、镜像、测试报告、前端构建产物或日志。
- 提交信息、变更说明和 PR 描述至少说明影响的应用、包、数据库迁移、事件合同、Compose 服务、外部 API 和回滚方式。
- 生成文件、迁移文件、OpenAPI/事件 schema 和 Docker 配置属于合同性变更，不能只按“普通重构”审查。

## 4. Docker Compose、Profiles 与 Healthcheck

### 4.1 Compose 文件与 Profiles

**官方事实**：Compose Specification 的 profiles 用于定义一组激活服务；没有 `profiles` 属性的服务始终启用，带有该属性的服务只有在对应 profile 激活时才参与模型。profile 只改变服务激活，依赖关系仍必须在每个有效 profile 组合下成立。Compose Specification 的顶层 `version` 属性仅为向后兼容，已 obsolete，不用于选择 schema。[D1][D2][D3]

**本项目建议**：

| Profile | 目的 | 约束 |
| --- | --- | --- |
| `dev` | 热重载、调试日志、开发辅助服务 | 使用开发凭据和隔离数据卷，禁止接触生产 secret。 |
| `test` | 集成测试、合同测试、Playwright 所需拓扑 | 使用一次性或独立命名空间/卷；测试结束必须清理或回收。 |
| `prod` | 不可变镜像、Worker、Aegra、观测组件和生产资源限制 | 禁止源码挂载、默认口令和浮动 `latest` 标签。 |

根文件固定为 `docker-compose.yml`。**本项目建议**：不写 obsolete 的顶层 `version`；在 CI 中对所有目标 profile 做模型校验，并检查“启用某 profile 后依赖服务是否仍存在”。Profiles 是配置选择机制，不是租户隔离、网络隔离、权限控制、滚动发布或高可用机制。

### 4.2 Healthcheck 与依赖启动顺序

**官方事实**：Compose 的 `healthcheck` 使用容器内的检查命令判断服务健康；`depends_on` 的长语法可以用 `service_healthy` 等条件控制依赖服务何时满足启动条件；Compose 按依赖顺序创建和删除服务。依赖服务健康只解决 Compose 的依赖启动判断，不等价于完整的应用级故障恢复或持续流量编排。[D3][D4]

**本项目建议**：

- 每个可运行服务定义无副作用、短超时、可重复执行的 healthcheck；检查真实协议或最小应用路径，不使用只判断进程存在的伪健康检查。
- 对 API、Agent、Worker、PostgreSQL、Redis、Milvus、RocketMQ 及观测组件分别定义启动期检查；检查不应触发写入、发送消息、调用外部模型或创建索引。
- 应用对外暴露逻辑上区分 `live` 与 `ready`：`live` 表示进程仍能工作，`ready` 表示必要依赖已就绪。Compose 的单一 healthcheck 选择哪一个要结合启动 gating 和重启策略，不能把“依赖暂时不可用”简单等价为“进程已坏”。
- `depends_on` 只保证启动/停止顺序；API、Agent 和 Worker 仍必须在运行时对 PostgreSQL、Redis、Milvus、RocketMQ 和外部 API 进行有界重试、连接池恢复和降级处理。
- healthcheck 的 `interval`、`timeout`、`start_period`、`retries` 和恢复策略根据服务启动耗时测量确定；不通过无界 `sleep` 掩盖就绪问题。
- 对外健康接口只返回最小状态和版本信息，不暴露连接串、secret、内部异常堆栈或医疗数据；管理员深度诊断走受保护的观测系统。

### 4.3 Compose Secrets、环境变量与构建密钥

**官方事实**：Docker Compose secrets 将 secret 授权给指定服务，并以容器内文件的形式提供；Docker build 文档也提供了 build secrets 机制，以避免把构建凭据写入镜像层。Docker 官方构建最佳实践还建议使用多阶段构建、合理的 build context、锁定基础镜像并避免把不必要的内容带入镜像。[D5][D6][D7]

**本项目建议**：

- 生产数据库密码、Redis/RocketMQ/Milvus 凭据、Cookie signing key、外部 LLM/Embedding/Reranker/MinerU API key、Langfuse credential 和 registry credential 使用 Compose secret 或外部 secret manager；不把它们作为普通环境变量长期暴露。
- 开发环境可使用未提交的 `.env`/secret 文件，但仓库只保留占位模板；模板不得包含可用凭据。
- Dockerfile 不通过 `ARG` 或普通 `ENV` 传递长期 secret；构建期私有包访问使用 build secret，运行时密钥由部署环境注入。
- 应用镜像使用多阶段构建、最小运行时依赖、非 root 用户、明确的工作目录和 `.dockerignore`；不在生产镜像内保留编译缓存、测试数据、源码 secret 或调试工具。

## 5. 测试体系、pytest、HTTPX 与集成测试

### 5.1 pytest 官方事实

**官方事实**：pytest 官方建议新项目采用 `src` layout 和 `importlib` import mode；fixtures 支持不同作用域，`yield` fixture 是推荐的清理方式；自定义 markers 应注册并可用 `strict_markers` 阻止拼写错误；parametrize 用于同一行为的多组输入；pytest 文档还专门说明 flaky tests、测试发现和 CI。[TST1][TST2][TST3][TST4][TST5]

**本项目建议**：

- 每个 Python member 维护独立 `tests/unit`、`tests/component`、`tests/integration`、`tests/contract`；跨进程的 Graph、Worker 和事件顺序测试单独归档。
- fixture 只负责环境准备和清理，不把大量业务断言藏进 fixture；外部服务 fixture 显式标注作用域，避免 session 级共享状态污染测试。
- 所有自定义 marker 在配置中注册，例如 `unit`、`component`、`integration`、`contract`、`e2e`、`slow`、`external_sandbox`；CI 使用严格 marker 检查。
- 参数化用例的 ID 要能表达业务条件，如“空查询”“重复消息”“外部 API 超时”，使失败报告可直接定位。
- 不用无期限重跑插件掩盖不稳定测试。确需临时重跑时必须登记根因、负责人和删除日期；不稳定测试不能作为长期发布依据。

### 5.2 pytest-asyncio、FastAPI 与 HTTPX

**官方事实**：pytest-asyncio 为 pytest collector 提供事件循环作用域；默认测试循环是 function scope，并支持 function/class/module/package/session；其 `strict` 模式要求显式 asyncio 标记和 async fixture，`auto` 模式会自动接管 async 测试。官方文档提示未来版本可能改变未配置 fixture loop scope 的默认值，因此应显式配置。async 测试默认顺序执行，以保持隔离。[ASY1][ASY2]

**本项目建议**：

- 目标运行时全部基于 asyncio 时使用 `asyncio_mode = auto` 以减少样板；若未来引入多个异步测试框架，则改用 `strict` 并要求显式标记。
- 显式设置 test loop scope 和 fixture loop scope，不依赖插件未来默认值；同一模块的相邻测试使用一致的 loop scope，避免“不同 loop 共享异步对象”。
- FastAPI 官方异步测试示例使用 AnyIO + HTTPX 的 `AsyncClient` 和 `ASGITransport`；本项目如果统一采用 pytest-asyncio，保留同样的 HTTPX/ASGI 测试边界，但不要在一个测试套件中无理由混用两套 async plugin。[FA1][HX1]

**官方事实**：HTTPX 的 `Client`/`AsyncClient` 提供连接池和跨请求连接复用，使用后必须关闭；HTTPX 支持显式 timeout、connection limits、ASGI transport、mock transport。HTTPX 的 ASGI transport 不负责触发 ASGI lifespan 事件；FastAPI 官方异步测试文档也明确提醒这一点。[HX1][HX2][HX3][HX4][HX5][FA1]

**本项目建议**：

- 生产外部 API client 使用应用生命周期内可控的共享 `AsyncClient`，设置 connect/read/write/pool 超时和连接上限，关闭时释放连接。
- 只对明确幂等的请求做有限重试；创建任务、扣费、写入、发送事务消息等操作使用幂等键或业务去重，不把 HTTPX 的连接重试当作业务重试。
- 单元/组件测试使用 HTTPX mock transport 或 fake port；测试超时、连接错误、非 2xx、响应 schema 错误、流式中断、重试耗尽和取消传播。
- ASGI 测试需要显式覆盖应用 startup/shutdown/lifespan；不能因为 `ASGITransport` 能发请求，就假定池、观测 SDK、Redis 连接或路由表已经按生产方式初始化。

### 5.3 Testcontainers 与 Compose 集成测试边界

**官方事实**：Testcontainers Python 官方文档将其定位为 functional/integration testing 工具，提供 PostgreSQL 等模块，也支持 generic/custom containers；容器通常通过上下文管理自动清理。其 Docker-in-Docker 文档要求测试容器具有 Docker client 和可用 Docker daemon。[TC1]

**本项目建议**：

| 测试层 | 推荐工具 | 覆盖内容 | 外部 API 策略 |
| --- | --- | --- | --- |
| 单元 | pytest / pytest-asyncio | `medical-core` 领域规则、状态机、意图策略、幂等键、错误映射 | fake port，不联网 |
| 组件 | pytest + HTTPX ASGI transport | FastAPI router、依赖注入、权限、Problem Details、SSE/流式事件适配 | HTTPX mock transport 或专用 fake server |
| 数据集成 | Testcontainers Python | PostgreSQL migration/transaction、Redis TTL/锁/限流、真实驱动行为 | 不调用生产服务 |
| 多服务集成 | `docker-compose.yml` 的 `test` profile | Milvus hybrid 检索、RocketMQ publish/consume/retry/DLQ、Aegra 协议合同、Worker 摄取链路 | 只接测试 endpoint 或受控 stub |
| 合同测试 | schema/OpenAPI/事件协议测试 | FastAPI OpenAPI、Aegra/LangGraph streaming、RocketMQ 事件、前端生成类型 | 固定响应和版本化合同 |
| E2E | Playwright | 登录、会话、聊天流、来源显示、知识库管理、错误态和权限边界 | 使用隔离测试凭据和测试数据 |
| 恢复/韧性 | Compose + 备份还原环境 | 数据库恢复、Milvus 重建、RocketMQ 重放、断线恢复、重复消息 | 不使用真实患者资料 |

**本项目建议**：Testcontainers 适合按测试创建 PostgreSQL/Redis 等单项依赖；Milvus、RocketMQ、Aegra 和 Worker 的跨服务行为依赖网络、卷、启动顺序和多个进程，应优先使用 Compose `test` profile，避免在测试代码中重复拼装生产拓扑。

### 5.4 测试门禁

**本项目建议**：

| 阶段 | 必须通过的门禁 |
| --- | --- |
| 每次提交/PR | Python formatter/lint/type check、TypeScript formatter/lint/type check、快速 unit/component tests、生成文件一致性、Compose 模型校验、secret 扫描。 |
| 合并主分支 | 上述门禁 + API/事件合同 + PostgreSQL/Redis 集成 + 受影响包构建。 |
| 发布候选 | Compose `test` profile + Milvus/RocketMQ/Agent 集成 + Playwright E2E + migration smoke + 镜像构建。 |
| 生产发布 | 发布前测试报告、镜像 digest、SBOM/provenance、环境审批、部署后 health/readiness smoke、回滚 digest 可用。 |
| 定时任务 | 外部 API sandbox smoke、依赖更新验证、备份可用性检查、恢复演练、长时间运行/队列积压和 flaky 测试审计。 |

覆盖率不应单独作为质量证明。**本项目建议**：以“关键领域规则 + 变更代码覆盖 + 关键错误分支 + 合同测试”作为主门禁，建立基线后再设分层阈值；不能用一个全仓库平均百分比掩盖认证、权限、重试、幂等、数据迁移和恢复路径没有测试。

## 6. Langfuse、结构化日志与运行监控

### 6.1 OpenTelemetry 官方事实与当前取舍

**官方事实**：OpenTelemetry 提供 traces、metrics、logs 等信号的 API/SDK、instrumentation、semantic conventions 和 Collector；Python 官方文档覆盖自动/代码 instrumentation 与 exporter。OpenTelemetry Logs 规范定义了日志数据模型和日志与 trace 的关联方式；semantic conventions 为 HTTP、数据库、服务、容器、消息等常见实体提供统一属性。OpenTelemetry 的 tracing SDK 目前规范页标注为 Stable，但不同 signal、SDK、contrib instrumentation 和 semantic convention 的稳定性可能不同。[OT1][OT2][OT3][OT4][OT5][OT6]

**本项目建议**：

- OpenTelemetry、Collector、Tempo 和 Grafana 是调研过的成熟候选方案，但当前不进入实现目标；不安装 OTel SDK，不配置 Generic OTLP，不部署 Collector/Tempo/Grafana。
- Aegra 是其托管 graph/LLM 调用的唯一 Langfuse ingestion owner；FastAPI、Worker 和 domain service 不创建 Langfuse client、manual observation 或第二个 exporter。Aegra 的内部 OpenTelemetry 使用属于 runtime 实现细节。[LF1]
- Aegra 使用的 Langfuse Python/server-compatible v4 线采用统一 observation API；其 native OTLP 入口使用 HTTP JSON/protobuf，不是 gRPC，并需要 v4 ingestion header。具体 SDK/server 版本必须锁定并做真实导出合同测试。[LF1]
- Aegra 发往 Langfuse 的数据必须在 exporter 入口前完成脱敏；Langfuse 的 masking 不会改变日志或其他副本。Aegra 的 Langfuse 初始化、导出、flush 和 shutdown 失败按 fail-open 降级处理，不能影响 API/Worker 业务流程。[LF1]
- API/Worker 结构化日志的最小字段包括 `timestamp`、`severity`、`service.name`、`service.version`、`environment`、`request_id`、`run_id`、`event.name`、`operation`、`duration_ms`、`outcome`、`error.type` 和 `error.code`。
- metrics 关注请求量、错误率、延迟、流式断开、Agent run 成功/失败、RocketMQ backlog/retry/DLQ、Worker processing duration、外部 API latency/error/timeout、PostgreSQL pool、Redis memory/eviction、Milvus search latency 和备份年龄。
- 健康检查区分 liveness、readiness 和 dependency degradation；Langfuse 不可用时可以标记 AI/RAG observability degraded，但不能把业务服务标记为错误或阻止状态持久化。

### 6.2 结构化日志

**官方事实**：Python logging cookbook 提供了 `dictConfig`、`LoggerAdapter`、队列处理和 structured logging 的实现方式；RFC 8259 定义 JSON 数据交换格式；OpenTelemetry Logs 规范建议通过现有 logging library 或 OTel log appender 生成带上下文的结构化日志。[PY3][RFC1][OT3]

**本项目建议**：

- 生产日志统一写 stdout/stderr，由运行平台收集；每行一个 JSON event，时间使用 UTC、RFC 3339 格式，字段命名固定。
- 最小公共字段：`timestamp`、`severity`、`service.name`、`service.version`、`environment`、`request_id`、`run_id`、`event.name`、`operation`、`duration_ms`、`outcome`、`error.type`、`error.code`。
- 会话、任务和消息事件可记录经过哈希/脱敏的内部标识，但不能记录原始 session ID、Cookie、Authorization header、密码、API key、模型 token、完整用户问题、上传文档、OCR 文本、检索片段或医疗实体。
- `INFO` 记录业务状态和可操作结果，`WARNING` 记录可恢复降级，`ERROR` 记录需要处理的失败，`DEBUG` 只在开发 profile 启用；禁止用日志级别替代错误分类。
- 日志中的 exception stack 需要关联 trace，但要过滤请求体、响应体、secret 和外部 API 返回中的敏感字段；用户可见错误使用稳定错误码和安全描述。
- 结构化日志 schema、事件名称和敏感字段规则作为可测试合同；日志格式变更需要更新解析器、告警和审计查询。

### 6.3 可观测性安全与告警

**本项目建议**：

- 默认采样成功的长对话 trace，错误、超时、重试耗尽、DLQ、权限拒绝和数据恢复事件提高采样；采样规则不能把医疗内容当作采样 key。
- 控制 metrics label cardinality：禁止以完整用户问题、文档 ID、session ID、外部 URL 或自由文本作为 label；高基数字段留在 trace/log 的受控属性中，仍需脱敏。
- 必须告警：API 5xx/latency/readiness、流式连接异常、Agent run 失败、RocketMQ backlog/retry/DLQ、外部 API 超时/限流/熔断、PostgreSQL 连接池耗尽、Redis eviction/内存、Milvus 检索失败、磁盘耗尽、备份过期、restore drill 失败和证书/secret 即将过期。
- 观测数据本身按敏感数据处理：限制访问角色、保留期限和导出范围；开发/测试禁止使用真实医疗资料。

## 7. 身份验证、密码、Cookie 与 OWASP 基线

### 7.1 Argon2id 与密码存储

**官方事实**：OWASP Password Storage Cheat Sheet 建议密码使用自适应、单向密码哈希而非明文或可逆加密；其当前 Argon2id 最低建议为 memory 19 MiB、iterations 2、parallelism 1。RFC 9106 给出了更高成本的 Argon2id 推荐配置：默认环境首选 2 GiB memory、1 pass、4 lanes；内存受限环境可使用 64 MiB、3 passes、4 lanes。FastAPI 官方安全教程使用 `pwdlib` 的 Argon2 支持作为示例。[SEC1][SEC2][FA2]

**本项目建议**：

- 新用户密码统一存 Argon2id hash；每个密码使用独立随机 salt，数据库只保存哈希字符串及算法参数，不保存明文。
- 以生产硬件校准 work factor；OWASP 最低配置是安全下限，不是 MedicalRAG 的最终运行参数。记录验证延迟和并发资源消耗，避免登录高峰耗尽 CPU/内存。
- 可以使用独立 pepper 增强防护，但 pepper 只能放在 secret manager/Compose secret 中，不能与数据库 hash 放在一起；pepper 丢失必须有轮换和恢复策略。[SEC1]
- 登录成功时可按版本升级旧 hash；比较使用库提供的安全验证函数；密码修改、管理员提权和高风险操作需要重新认证。
- bcrypt 只作为历史兼容方案，不作为新系统默认；密码策略、登录限流、账户恢复、错误消息和审计事件按 OWASP Authentication 指导实现。[SEC7]

### 7.2 服务端会话与安全 Cookie

**官方事实**：OWASP Session Management Cheat Sheet 要求 session ID 只作为客户端标识，业务含义和敏感信息保存在服务端；建议保护 Cookie 的 `Secure`、`HttpOnly`、`SameSite` 属性，并在权限变化后更新 session ID。OWASP CSRF 指南指出，Cookie 属性是纵深防御的一部分，状态变更请求仍需适用的 CSRF 防护；`__Host-` Cookie 前缀可限制 Domain/Path 误配置。FastAPI/Starlette 的 `set_cookie` API 支持 `secure`、`httponly`、`samesite`、`path` 和 `domain` 等属性。[SEC2][SEC3][FA3]

**本项目建议**：

- 采用 Redis 中的服务端 session；浏览器 Cookie 只保存高熵、不可推断用户/角色/医疗信息的 opaque session ID。
- 默认使用 `__Host-` 前缀、`Secure`、`HttpOnly`、`Path=/`、不设置 `Domain`；同站 SPA 优先 `SameSite=Lax` 或更严格策略，跨站场景必须重新评估 `SameSite=None; Secure` 与 CSRF 风险。
- 登录、登出、密码修改、角色/权限变化和风险事件触发 session rotation/revocation；Redis 中保存 idle timeout、absolute timeout、设备/会话审计所需的最小信息。
- 所有改变状态的 POST/PUT/PATCH/DELETE 和流式启动请求都检查 CSRF；不要使用改变状态的 GET。前端不把 session token 放入 localStorage，也不把 Cookie 值写入前端日志。
- Session 相关日志只记录经过 salted hash 的 session 标识或内部关联 ID，禁止记录原始 Cookie。[SEC2]

### 7.3 OWASP/标准组织安全验证范围

**官方事实**：OWASP ASVS 为应用安全控制测试提供验证标准；OWASP API Security Top 10 2023 将对象级授权、功能级授权、配置错误、注入、资产管理和日志监控等列为 API 风险；OWASP REST、Authentication、File Upload、Logging、Secrets Management Cheat Sheet 提供相应控制建议。RFC 9457 定义 HTTP API 的 Problem Details 表达格式，可用于稳定错误类型和机器可读错误响应。[SEC4][SEC5][SEC6][SEC7][SEC8][SEC9][RFC2]

**本项目建议**：

- 以 ASVS 作为发布前安全检查表，以 API Top 10 作为 API/管理后台专项检查表；安全门禁必须包含认证、对象级授权、功能级授权、租户/知识库隔离、CSRF、输入校验、错误处理、审计和限流。
- API 对外错误使用稳定的错误码和 Problem Details 风格；生产响应不包含 traceback、SQL、外部 provider 原始错误、Prompt 或内部拓扑。
- CORS 使用显式 allowlist；生产只允许 HTTPS；管理接口采用独立权限、审计、限流和更短会话策略。
- 外部 API endpoint 使用配置 allowlist 和 TLS 校验；当前数据源不支持 URL/Feishu 等任意远程地址，可显著减少 SSRF 面，但不能取消对外部 API 出站访问的域名、DNS、超时和证书治理。

### 7.4 文件上传、解析和医疗内容边界

**官方事实**：OWASP File Upload Cheat Sheet 建议限制扩展名和大小、验证文件类型/内容、使用安全文件名和存储位置、限制权限，并根据场景使用恶意内容扫描或 CDR；上传入口还应受到 CSRF 和解析器风险控制。[SEC6]

**本项目建议**：

- 只接受已确认扩展名：`.docx`、`.pptx`、`.xlsx`、`.pdf`、`.md`、`.txt`、`.png`、`.jpg`、`.jpeg`；扩展名、声明 MIME、文件签名和解析结果不一致时拒绝或隔离。
- 限制单文件大小、总任务大小、页数/图片数量、解析时长和外部 MinerU API 响应大小；文件名转为服务端生成的随机标识，不直接拼接到路径或命令。
- 原始文件、MinerU 结果和中间产物不放在可执行目录或 Web 静态目录；解析 Worker 使用最小权限、独立临时目录和明确清理策略。
- 视部署风险增加恶意文件扫描/隔离；“直接流式输出”只适用于已确认的聊天输出策略，不意味着上传内容、解析器和外部 API 请求可以跳过输入边界控制。
- 医疗文档、用户问题、检索证据和模型输出属于敏感数据；测试、日志、trace、截图、Playwright artifact 和 CI artifact 使用合成数据。

## 8. 密钥管理与 CI 工作流

### 8.1 密钥治理

**官方事实**：OWASP Secrets Management Cheat Sheet 建议建立 secret 生命周期、访问控制、轮换、审计和暴露响应；GitHub Actions 官方安全文档明确指出自动 secret redaction 并非对所有变换都可靠，建议最小权限、最小化 `GITHUB_TOKEN`、避免在 workflow 中明文写入 secret。GitHub OIDC 文档支持用短期身份令牌替代长期云凭据。[SEC4][GH5][GH6]

**本项目建议**：

- 每个环境分别管理 PostgreSQL、Redis、Milvus、RocketMQ、Aegra、外部模型 API、MinerU、Langfuse 和 registry 凭据；禁止跨环境复用生产 secret。
- secret 有 owner、用途、创建时间、过期/轮换时间、读取服务和撤销步骤；发现泄露时先撤销/轮换，再清理日志和 artifact，最后复盘来源。
- CI 默认 `contents: read`；只有发布 job 才获得 package write，只有需要 provenance/attestation 的 job 才获得相应 write 权限；OIDC 权限只授予部署/发布 job。
- 不把 secret 放入命令行参数、构建日志、缓存 key、Docker image layer、Turborepo output、Playwright trace 或测试失败快照。
- 生产部署优先使用 OIDC/短期凭据；必须使用长期 API key 时按 provider 的最小权限、来源 IP、额度和轮换能力隔离。

### 8.2 CI 工作流结构

**官方事实**：GitHub Actions workflow syntax 定义 events、jobs、permissions、matrices、artifacts 和 concurrency；Concurrency 可以取消或排队同组运行；dependency caching 和 workflow artifacts 有独立生命周期；GitHub 官方 Docker 发布教程覆盖登录、构建和推送，Docker 官方文档覆盖 build/test、SBOM 和 provenance attestation。[GH1][GH2][GH3][GH4][GH7][D8]

**本项目建议**：

| Workflow | 触发 | 允许的凭据 | 主要门禁/产物 |
| --- | --- | --- | --- |
| `quality` | PR、手工 | 无生产 secret | Python/TS format、lint、type、unit/component、合同、Compose config。 |
| `integration` | PR、主分支、手工 | 仅测试凭据 | Compose `test` profile、真实 PostgreSQL/Redis/Milvus/RocketMQ/Aegra 合同、迁移 smoke。 |
| `e2e` | 主分支、发布候选 | 隔离测试凭据 | Playwright 登录、聊天流、权限、上传、知识库和错误态；保留脱敏报告。 |
| `build` | 主分支、tag | registry 写权限仅限可信 job | 多阶段镜像构建、digest、SBOM、provenance、构建摘要。 |
| `release` | 受保护 tag/环境审批 | OIDC 或短期发布凭据 | 推送不可变镜像、部署 digest、健康 smoke、回滚验证。 |
| `maintenance` | 定时 | sandbox/备份凭据按需 | 外部 API sandbox、依赖更新、备份年龄、恢复演练、flaky 审计。 |

- PR workflow 使用 concurrency 取消同一 PR 的过期运行；发布/灾备 workflow 不随意取消正在执行的恢复或部署任务。
- 第三方 action 固定到完整 commit SHA；优先使用 GitHub、Docker、uv/pnpm 项目提供的官方 action，外部 action 需要安全审查和更新责任人。[GH5]
- 不可信 fork 的 PR 只运行无 secret 的质量任务；不得在其上下文中执行部署、推送镜像、写入共享缓存或调用真实外部 API。
- uv/pnpm/Docker cache 只由可信任务写入；缓存 key 绑定 OS、运行时、工具版本和 lockfile。缓存不能包含 secret、PHI 或外部 API 响应。[UV1][PN1][GH3]
- 测试报告、coverage、Playwright screenshot/trace、image digest、SBOM 和 attestation 作为 artifact 保存，但设置最小保留期，禁止上传真实医疗资料。[GH4]

## 9. 容器构建、发布与回滚

**官方事实**：Docker 构建最佳实践覆盖多阶段构建、缓存、`.dockerignore`、基础镜像和非必要内容；Docker 官方 GitHub Actions 文档支持为镜像生成 SBOM 和 provenance attestations；GitHub 官方 Docker 发布文档使用 Docker 的登录、metadata 和 build/push actions。[D7][D8][GH7]

**本项目建议**：

- API、Agent、Worker、Web 分别拥有职责清晰的镜像构建目标；依赖安装只由 lockfile 驱动，运行镜像不在启动时联网解析依赖。
- 基础镜像使用受支持的 major/minor，并在生产构建中固定 digest；应用镜像同时生成不可变 commit tag、可读 release tag 和最终 digest。
- 发布流程“构建一次、晋级多个环境”：测试通过的同一 digest 才能进入 staging/production，不在每个环境重新构建不同内容。
- 生产 Compose 配置只引用 digest 或受控不可变版本，不引用 `latest`；保留上一版本 digest 和数据库迁移回滚/前滚策略。
- 发布前检查镜像内没有 `.env`、secret、测试数据、源码缓存和调试端口；运行时使用非 root、最小网络暴露、最小 Linux capability 和只读文件系统能力（若组件兼容）。
- SBOM 记录 Python/Node 依赖和 OS 包；provenance 记录源 commit、构建 workflow、构建器和输入。发现高风险依赖时，先阻断晋级，再决定升级、豁免或回滚。
- 回滚不是只切换镜像：必须确认数据库 schema 向后兼容、RocketMQ event schema、Milvus collection schema、Aegra protocol 和前端合同仍能被旧版本读取。

## 10. 备份、恢复与灾难恢复

### 10.1 官方事实

**PostgreSQL**：官方备份章节覆盖逻辑备份、文件系统级备份和 continuous archiving；PITR 依赖 base backup 与 WAL 归档。官方高可用文档指出，归档恢复可以用于灾难恢复，warm standby/streaming replication 可用于高可用。[PG1][PG2][PG3]

**Redis**：官方文档区分 RDB 快照、AOF 写入日志、两者组合和无持久化；RDB 适合备份/灾难恢复，复制用于高可用，但复制本身不等于独立备份。[RD1][RD2]

**Milvus**：官方部署文档说明 Milvus 使用对象存储保存日志/索引文件，并支持外部 S3；Milvus 官方 `zilliztech/milvus-backup` 项目提供 Milvus backup/restore 工具。[MV1][MV2]

**RocketMQ**：官方 5.0 部署文档明确指出单节点单副本存在高风险，不建议用于在线环境；自动故障转移文档要求 controller 采用三副本或更多以满足 Raft majority；消息存储、保留、消费 offset、消费重试和死信均有独立官方语义。[RM1][RM2][RM3][RM4][RM5][RM6]

**灾备治理**：NIST SP 800-34 Rev.1 将 contingency planning、恢复优先级、灾难恢复计划和演练作为系统连续性的一部分，而不是只做一次数据复制。[NIST1]

### 10.2 本项目的数据权威性建议

| 数据 | 建议的权威来源 | 恢复策略 |
| --- | --- | --- |
| 用户、权限、知识库、文档元数据、任务状态、审计、配置 | PostgreSQL | base backup + WAL/PITR；恢复后执行迁移和一致性检查。 |
| 原始上传文件、MinerU 解析结果、版本化 chunk manifest | 独立持久对象存储或受保护的文件卷 | 独立备份、校验和、保留策略；不要只依赖 Milvus。 |
| Milvus dense/sparse collection、索引和实体 | Milvus + 对象存储 | 使用官方 backup/restore 或从 canonical artifact/chunk manifest 重建；重建路径必须实际演练。 |
| Redis session、缓存、限流和短期协调状态 | Redis | 明确哪些可丢失；缓存可重建，session 丢失时允许重新登录；若需要连续会话再启用持久化/备份。 |
| RocketMQ 未完成摄取任务、重试和 DLQ | RocketMQ broker 持久化/复制 + PostgreSQL 任务状态 | 保留足够重放窗口，消费者幂等，恢复后从 offset/DLQ 或任务状态安全重放。 |
| Aegra Thread/Run/Checkpoint | 由 Aegra 实际使用的官方 checkpoint backend | 实现前必须确认 backend、导出方式、版本兼容和恢复顺序；不能假设它自动包含在 PostgreSQL 备份中。 |

### 10.3 推荐的备份与恢复控制

**本项目建议**：

- PostgreSQL 至少同时具备周期性 base backup、连续 WAL 归档、加密异地副本、备份年龄监控和隔离环境恢复测试；逻辑 dump 作为迁移/局部恢复工具，不单独承担 PITR。
- Redis 若只存缓存、限流和可重新建立的 session，可把它视为可恢复状态；若业务要求会话连续性，则明确 RDB/AOF、fsync、备份保留和重建后的 session 安全影响。
- Milvus 备份与原始文件/manifest 备份必须分开验证；只有向量库而没有原始数据，无法可靠重建；只有原始数据而没有索引备份，则需要验证全量重建时间是否满足 RTO。
- RocketMQ 生产部署不得使用单节点单副本作为“灾备”；Compose 单主机拓扑适合开发/测试或低可用要求环境，生产高可用需要跨节点/主机的复制和控制器设计，或使用受支持的托管部署。
- Docker volume 的打包/复制不能替代 PostgreSQL、Redis、Milvus 和 RocketMQ 的一致性备份协议；数据库文件必须使用数据库官方备份方法或已验证的冷备窗口。
- 每次恢复都执行：备份完整性/校验 → 恢复 PostgreSQL → 恢复文件/对象存储 → 恢复 Milvus 或重建 → 恢复 RocketMQ/重放任务 → 启动 API/Agent/Worker → health/readiness → 关键业务 smoke → 审计与告警验证。
- 定期演练至少覆盖误删、数据库损坏、单服务不可用、RocketMQ backlog、Milvus 索引损坏、外部 API 长时间不可用和 secret 泄露后的轮换；演练结果记录真实耗时、数据缺口和改进项。

### 10.4 建议的初始 RPO/RTO（待确认）

以下是设计起点，不是官方指标，也不是已经批准的业务 SLA：

| 组件 | 初始 RPO 建议 | 初始 RTO 建议 | 说明 |
| --- | ---: | ---: | --- |
| PostgreSQL 业务数据 | ≤ 15 分钟 | ≤ 1 小时 | 依赖 WAL 归档、异地存储和可用恢复环境。 |
| 原始文档/manifest | ≤ 24 小时 | ≤ 4 小时 | 若业务要求更低 RPO，应改用持续复制对象存储。 |
| Milvus | ≤ 24 小时或可接受重建窗口 | ≤ 4 小时 | 由备份恢复或从 canonical data 重建的实测时间决定。 |
| Redis session/cache | 可丢失或 ≤ 24 小时 | ≤ 30 分钟 | 缓存重建；session 丢失应安全地要求重新登录。 |
| RocketMQ 任务 | ≤ 15 分钟 | ≤ 1 小时 | 依赖复制、保留期、offset/DLQ 和消费者幂等。 |

实现前应由业务确认 RPO/RTO；如果测量结果达不到目标，应调整拓扑、备份频率、保留策略或接受正式的服务降级，而不是把未验证的数字写成承诺。

## 11. 版本、默认值与兼容性 caveat

| 组件 | 官方资料观察 | 实施注意 |
| --- | --- | --- |
| Python 3.12 | Python 官方生命周期表显示 security 阶段，EOL 2028-10。 | 保持既定 3.12 约束时，升级依赖要检查是否仍提供 3.12 wheel；规划 3.13/更高版本迁移窗口。 |
| Node.js 24 | Node 官方 release schedule 的 LTS 状态和生命周期以实现时复核为准。 | 固定 Node 24.x 具体版本；pnpm 官方当前文档示例可能使用更新的 Node major，不应直接照抄升级。 |
| uv / pnpm | 官方 CI 文档强调锁定同步、版本兼容和 cache 边界。 | 固定工具版本；lockfile 变更必须触发完整依赖与镜像验证。 |
| pytest / pytest-asyncio | pytest strict 能力、pytest-asyncio loop scope 默认值和 mode 语义会随版本演进。 | 显式设置 import mode、strict markers、asyncio mode 和 loop scopes，不依赖未来默认值。 |
| Docker Compose | Compose Spec 顶层 `version` 已 obsolete；profiles 不是高可用/安全边界。 | 使用当前 Compose CLI/Spec，省略 obsolete version，测试所有 profile 组合。 |
| OpenTelemetry | 官方规范页当前显示 OTel 1.59.0、semantic conventions 1.43.0；不同 signal/contrib 稳定性可能不同。 | 作为未来复杂微服务场景的候选，不进入当前依赖或 Compose 拓扑；重新引入前需要独立 ADR。 |
| Grafana Tempo | 官方文档支持 OTLP、对象存储、monolithic 与 microservices 部署模式；MinIO 可作为 S3-compatible 存储，但单机 Compose 不等于 HA。 | 当前不部署；只有跨服务 SLO 和基础设施 Trace 需求出现后重新评估。 |
| Jaeger v2 | 官方当前文档为 2.20；all-in-one memory 适合开发，生产持久化需要独立 storage backend；Collector/query 在外部存储下可扩展。 | 当前不部署；作为未来分布式 Trace 的替代候选，不与 Tempo 并行。 |
| Langfuse | Python SDK v4（研究快照 4.14.1）基于 OTEL；官方 native OTLP 当前为 HTTP JSON/protobuf，self-hosted Compose 不提供 HA/备份。 | 仅 Aegra graph/LLM 接入；API/Worker 使用结构化日志、metrics 和 health checks；默认不导出 prompt、文档文本或模型原文。 |
| PostgreSQL | PostgreSQL 官方 current 文档已进入 18；19 在本次调研日期仍为 development/beta 线。 | 生产使用受支持稳定 major，不能因为 current 文档更新就使用 beta；备份工具版本与 server major 一起验证。 |
| Milvus | 官方文档同时展示多个版本线，且对象存储、元存储和 backup 工具影响恢复方式。 | 固定 Milvus/server/client/backup 兼容组合，真实演练 hybrid schema、备份和重建。 |
| RocketMQ | 本次官方部署/行为文档以 5.0 为主，同时保留 4.x 文档。 | 固定 server、broker/Proxy、controller 和 Python client 的兼容矩阵；重试、offset、DLQ 和事务消息按目标版本测试。 |
| TanStack Start | 已有研究资料显示官方文档仍需关注 release candidate/版本演进。 | 锁定具体版本；升级时回归 SSR、streaming、route generation 和 assistant-ui/LangGraph adapter 合同。 |
| 外部模型/API | provider 的模型名、Embedding 维度、Reranker schema、MinerU API 版本和限流策略可变。 | 记录 provider/model/api version 与 schema version；禁止使用未审查的 `latest` endpoint，建立 sandbox smoke 和降级策略。 |

## 12. 实现前必须补齐的验证项

以下项目不是本调研文档替开发团队做出的隐式决定，而是进入实现前需要有明确答案的工程问题：

1. Aegra checkpoint 的官方 backend、备份/恢复接口、版本兼容和与 PostgreSQL/RocketMQ 的恢复顺序。
2. 生产观测边界（Langfuse Cloud 或 self-hosted、日志/指标/Langfuse observation 保留期、访问角色和跨境/外部传输边界）。
3. 原始文档和 MinerU 结果的 canonical object storage、加密、生命周期和恢复目标。
4. Milvus 运行模式、对象存储/元存储部署方式、backup 工具版本和全量重建实测时间。
5. RocketMQ 生产是否跨主机部署多副本/controller；如果坚持单 Compose 主机，必须正式记录可接受的可用性和数据丢失风险。
6. PostgreSQL WAL 归档目的地、加密、保留策略、恢复演练频率和 RPO/RTO 批准值。
7. GitHub Actions 的受保护环境、OIDC provider、registry、action SHA 更新责任人和 release approval。
8. 外部 LLM/Embedding/Reranker/MinerU 的数据保留、训练使用、区域、限流、错误语义和 sandbox endpoint；这些不应通过日志或测试偷偷暴露医疗数据。

## 13. 官方一手来源

所有链接均为官方文档、官方项目页面或标准组织文档；访问日期为 2026-07-26；Langfuse 专项资料访问日期为 2026-07-27。

### Docker / Compose

- [D1] [Compose Specification — Profiles](https://compose-spec.github.io/compose-spec/15-profiles.html)
- [D2] [Compose Specification — Services / depends_on / healthcheck](https://compose-spec.github.io/compose-spec/05-services.html)
- [D3] [Docker Docs — Control startup and shutdown order in Compose](https://docs.docker.com/compose/how-tos/startup-order/)
- [D4] [Docker Docs — Define services in Docker Compose](https://docs.docker.com/reference/compose-file/services/)
- [D5] [Docker Docs — Manage secrets securely in Docker Compose](https://docs.docker.com/compose/how-tos/use-secrets/)
- [D6] [Docker Docs — Build secrets](https://docs.docker.com/build/building/secrets/)
- [D7] [Docker Docs — Building best practices](https://docs.docker.com/build/building/best-practices/)
- [D8] [Docker Docs — Add SBOM and provenance attestations with GitHub Actions](https://docs.docker.com/build/ci/github-actions/attestations/)
- [D9] [Docker Docs — Volumes: back up, restore, or migrate data volumes](https://docs.docker.com/engine/storage/volumes/)
- [D10] [Compose Specification — Version and name](https://compose-spec.github.io/compose-spec/04-version-and-name.html)

### Python、pytest、HTTPX、FastAPI、Testcontainers

- [PY1] [PEP 8 — Style Guide for Python Code](https://peps.python.org/pep-0008/)
- [PY2] [PEP 257 — Docstring Conventions](https://peps.python.org/pep-0257/)
- [PY3] [Python Logging Cookbook](https://docs.python.org/3/howto/logging-cookbook.html)
- [TST1] [pytest — Good Integration Practices](https://docs.pytest.org/en/stable/explanation/goodpractices.html)
- [TST2] [pytest — How to use fixtures](https://docs.pytest.org/en/stable/how-to/fixtures.html)
- [TST3] [pytest — How to mark test functions](https://docs.pytest.org/en/stable/how-to/mark.html)
- [TST4] [pytest — How to parametrize](https://docs.pytest.org/en/stable/how-to/parametrize.html)
- [TST5] [pytest — Flaky tests](https://docs.pytest.org/en/stable/explanation/flaky.html)
- [ASY1] [pytest-asyncio — Concepts](https://pytest-asyncio.readthedocs.io/en/latest/concepts.html)
- [ASY2] [pytest-asyncio — Configuration](https://pytest-asyncio.readthedocs.io/en/latest/reference/configuration.html)
- [HX1] [HTTPX — Clients](https://www.python-httpx.org/advanced/clients/)
- [HX2] [HTTPX — Async support](https://www.python-httpx.org/async/)
- [HX3] [HTTPX — Transports](https://www.python-httpx.org/advanced/transports/)
- [HX4] [HTTPX — Timeouts](https://www.python-httpx.org/advanced/timeouts/)
- [HX5] [HTTPX — Resource limits](https://www.python-httpx.org/advanced/resource-limits/)
- [FA1] [FastAPI — Async Tests](https://fastapi.tiangolo.com/advanced/async-tests/)
- [FA2] [FastAPI — OAuth2 with password hashing](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/)
- [FA3] [FastAPI — Response.set_cookie](https://fastapi.tiangolo.com/reference/response/)
- [TC1] [Testcontainers Python — Official documentation](https://testcontainers-python.readthedocs.io/en/latest/)

### OpenTelemetry、JSON 与版本生命周期

- [OT1] [OpenTelemetry — Python](https://opentelemetry.io/docs/languages/python/)
- [OT2] [OpenTelemetry — Instrumentation](https://opentelemetry.io/docs/languages/python/instrumentation/)
- [OT3] [OpenTelemetry — Logging specification](https://opentelemetry.io/docs/specs/otel/logs/)
- [OT4] [OpenTelemetry — Semantic conventions](https://opentelemetry.io/docs/specs/semconv/)
- [OT5] [OpenTelemetry — Versioning and stability](https://opentelemetry.io/docs/specs/otel/versioning-and-stability/)
- [OT6] [OpenTelemetry — Collector](https://opentelemetry.io/docs/collector/)
- [OT7] [Jaeger — Architecture](https://www.jaegertracing.io/docs/latest/architecture/)
- [OT8] [Jaeger — Storage Backends](https://www.jaegertracing.io/docs/latest/storage/)
- [OT9] [Grafana Tempo — Setup](https://grafana.com/docs/tempo/latest/setup/)
- [OT10] [Grafana Tempo — Configuration](https://grafana.com/docs/tempo/latest/configuration/)
- [LF1] [Langfuse observability integration research](langfuse-observability.md)
- [RFC1] [RFC 8259 — The JavaScript Object Notation (JSON) Data Interchange Format](https://www.rfc-editor.org/rfc/rfc8259)
- [RFC2] [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457)
- [V1] [Python Developer’s Guide — Status of Python versions](https://devguide.python.org/versions/)
- [V2] [Node.js — Releases](https://nodejs.org/en/about/previous-releases)
- [V3] [Node.js Release Working Group — Release schedule](https://github.com/nodejs/release#release-schedule)

### OWASP、IETF 与 NIST

- [SEC1] [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
- [SEC2] [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
- [SEC3] [OWASP Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
- [SEC4] [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
- [SEC5] [OWASP Application Security Verification Standard](https://owasp.org/www-project-application-security-verification-standard/)
- [SEC6] [OWASP File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html)
- [SEC7] [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [SEC8] [OWASP REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html)
- [SEC9] [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [SEC10] [OWASP API Security Top 10](https://owasp.org/API-Security/editions/2023/en/0x00-header/)
- [SEC11] [RFC 9106 — Argon2](https://www.rfc-editor.org/rfc/rfc9106)
- [SEC12] [NIST SP 800-63B — Authentication and Lifecycle Management](https://csrc.nist.gov/pubs/sp/800/63/b/upd1/final)
- [NIST1] [NIST SP 800-34 Rev. 1 — Contingency Planning Guide](https://csrc.nist.gov/pubs/sp/800/34/r1/final)

### GitHub Actions、uv、pnpm 与前端质量工具

- [GH1] [GitHub Actions — Workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax)
- [GH2] [GitHub Actions — Concurrency](https://docs.github.com/en/actions/concepts/workflows-and-actions/concurrency)
- [GH3] [GitHub Actions — Dependency caching reference](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching)
- [GH4] [GitHub Actions — Workflow artifacts](https://docs.github.com/en/actions/concepts/workflows-and-actions/workflow-artifacts)
- [GH5] [GitHub Actions — Secure use reference](https://docs.github.com/en/actions/reference/security/secure-use)
- [GH6] [GitHub Actions — OpenID Connect](https://docs.github.com/en/actions/concepts/security/openid-connect)
- [GH7] [GitHub Actions — Publishing Docker images](https://docs.github.com/en/actions/tutorials/publish-packages/publish-docker-images)
- [UV1] [uv — Using uv in GitHub Actions](https://docs.astral.sh/uv/guides/integration/github/)
- [UV2] [uv — Locking and syncing](https://docs.astral.sh/uv/concepts/projects/sync/)
- [PN1] [pnpm — Continuous Integration](https://pnpm.io/continuous-integration)
- [TS1] [TypeScript — `strict` TSConfig option](https://www.typescriptlang.org/tsconfig/strict.html)
- [TS2] [ESLint — Configuration Files](https://eslint.org/docs/latest/use/configure/configuration-files)
- [TS3] [Prettier — Options and configuration](https://prettier.io/docs/options)
- [TS4] [Vitest — Getting Started](https://vitest.dev/guide/)
- [TS5] [Playwright — Continuous Integration](https://playwright.dev/docs/ci)

### PostgreSQL、Redis、Milvus 与 RocketMQ

- [PG1] [PostgreSQL — Backup and Restore](https://www.postgresql.org/docs/current/backup.html)
- [PG2] [PostgreSQL — Continuous Archiving and PITR](https://www.postgresql.org/docs/current/continuous-archiving.html)
- [PG3] [PostgreSQL — Log-Shipping Standby Servers](https://www.postgresql.org/docs/current/warm-standby.html)
- [RD1] [Redis — Persistence](https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/)
- [RD2] [Redis — Replication](https://redis.io/docs/latest/operate/oss_and_stack/management/replication/)
- [MV1] [Milvus — Configure object storage with Docker Compose or Helm](https://milvus.io/docs/deploy_s3.md)
- [MV2] [Milvus Backup — Official project repository](https://github.com/zilliztech/milvus-backup)
- [RM1] [RocketMQ — Deployment Method](https://rocketmq.apache.org/docs/deploymentOperations/01deploy)
- [RM2] [RocketMQ — Master-Slave Automatic Failover Mode](https://rocketmq.apache.org/docs/deploymentOperations/03autofailover)
- [RM3] [RocketMQ — Transaction Message](https://rocketmq.apache.org/docs/featureBehavior/04transactionmessage)
- [RM4] [RocketMQ — Sending Retry and Throttling Policy](https://rocketmq.apache.org/docs/featureBehavior/05sendretrypolicy)
- [RM5] [RocketMQ — Consumption Retry](https://rocketmq.apache.org/docs/featureBehavior/10consumerretrypolicy)
- [RM6] [RocketMQ — Message Storage and Cleanup](https://rocketmq.apache.org/docs/featureBehavior/11messagestorepolicy)
- [RM7] [RocketMQ — Metrics](https://rocketmq.apache.org/docs/observability/01metrics)
