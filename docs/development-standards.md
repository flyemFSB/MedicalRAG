# MedicalRAG 开发规范（强制）

> 规范性文档：实现阶段所有 Python/TypeScript 代码必须遵守。来源：`docs/research/python-backend-and-data-stack.md` §14、`docs/research/monorepo-best-practices.md`、`docs/research/agent-and-frontend-stack.md` 的官方结论提炼，以及 ADR 0025/0060。术语约束见 [CONTEXT.md](../CONTEXT.md)（本文件不重复清单，必须引用）。

## 0. 总则

- **术语强制**：任何标识符、注释、文档、UI 文案必须使用 CONTEXT.md 的正名，禁止用 Avoid 词。这是最高优先级约束。
- **最简正确（YAGNI）**：只实现当前需求的最小正确解；不造投机抽象、不为假想需求加层。开发时按根 `AGENTS.md` 的 ponytail 原则执行。
- **依赖方向**：只能从外向内（runtime → application/adapter → domain）；`packages/medical-core` 不依赖任何框架/SDK。
- **生成物**：凡自动生成文件（OpenAPI TS 类型、route tree、codegen 输出）标记 generated，不手改，CI 校验无漂移。

## 1. Python

### 1.1 命名
- 模块/包/函数/变量：`lower_snake_case`；类与异常：`CapWords`；常量：`UPPER_SNAKE_CASE`；私有成员单前导下划线。
- Pydantic/SQLAlchemy 字段用业务统一词汇，不用同义的 `id`/`uuid`/`key` 混称；公共事件字段一旦发布不得改名。
- async 函数不加无意义 `_async` 后缀（是否异步由调用语义决定）；阻塞/异步两版并存时才用清晰后缀或模块边界区分。
- 测试函数以行为命名：`test_<behavior>_<condition>_<expected>`；避免 `test_utils_1`。

### 1.2 注释与 docstring
- 公共 package/模块/类/端口/外部适配器写 docstring，说明职责、输入输出、异常、资源所有权、并发约束。
- 注释解释**为什么**（为何不在事务内调外部 API、为何消息必须幂等、为何用某隔离级别）；不逐行复述代码。
- 对易误用边界（Redis lease、PostgreSQL 状态转换、outbox relay）在端口/handler 附近写出明确不变量与失败语义。
- 迁移文件注释说明数据迁移风险、锁风险、回滚限制；不只写 "auto generated"。
- **禁止**在注释、docstring、日志、fixture 中写真实患者身份信息、访问令牌、外部服务密钥。

### 1.3 类型与依赖
- 所有跨层端口、DTO、事件 envelope、repository 方法写类型标注；避免用 `Any` 隐藏边界不确定性。
- `medical-core` 不 import FastAPI、SQLAlchemy、Redis、Milvus、arq、LangGraph、Aegra；反向依赖走 protocol/port + DI。
- 异常分层：领域层抛领域异常；基础设施层抛可分类 adapter 异常；应用层判定 retryable/non-retryable；API 异常映射只在 FastAPI 边界。
- 日志用模块级 logger，统一携带 `request_id`/`run_id`/`workspace_id`/`job_id`/`event_id`；不输出完整 prompt、文档正文、token、连接字符串。

### 1.4 异步与资源
- `async def` 内所有 I/O 必须可 await 或明确隔离；禁止在事件循环内直接调用同步 HTTP client、阻塞文件扫描、CPU 密集解析（用 `def`/`anyio.to_thread`）。
- 所有连接池、session、consumer、producer、PubSub、background task 必须有创建者、所有者、关闭路径；在 `lifespan`/shutdown 清理。
- 取消异常、超时、进程关闭必须可回收资源；不吞 cancellation 并无限重试。

### 1.5 格式与工具
- `src` layout；类型标注 + 显式返回类型。
- 格式/静态检查由 uv 管：`ruff`（或等价）format + lint；类型 `mypy`/`pyright` 可选。
- 依赖经 `uv.lock` 锁定；CI 用 `uv sync --locked`；禁 `latest`。

## 2. TypeScript / React（前端）

### 2.1 命名与结构
- 组件在 `apps/web/src/components` / `src/features/<feature>/`；通用请求/认证/格式化在 `src/lib/`；路由在 `src/routes`。
- 生成物（OpenAPI 类型、route tree）标记 generated，不手改。
- 组件命名 `PascalCase`；hooks `useXxx`；文件与导出同名。

### 2.2 类型与格式
- TypeScript `strict`；`tsc -b` 为类型门禁（不把 Vite bundling 当类型检查）。
- 根 `tsconfig.base.json` + 根 `eslint.config.mjs`/`prettier.config.mjs`；lint 用 oxlint（或 eslint），格式用 Prettier；不复制漂移配置。
- 内部包依赖用 `workspace:*`；共享版本走 `catalog:`。

### 2.3 数据与状态
- 服务端状态用 TanStack Query（`useSuspenseQuery`/`ensureQueryData`）；不做手写 fetch 缓存。
- `/api` 类型来自 OpenAPI 生成的 TS 类型（ADR 0071）；不手写重复 DTO；运行时不做 /api 响应二次校验。

## 3. 日志与可观测（红线）

- 结构化日志 + 指标 + 健康检查；**不铺自定义 Trace**（无 OTel SDK/Collector/Tempo/Grafana，ADR 0062）。
- 日志用 **loguru**（ADR 0074 优先三方库）；`safe_bind()` 在绑定前校验字段名——禁用字段与未知字段直接抛 `UnsafeLogField`。
- **永不写日志/观测**：raw prompts、文档正文、evidence 文本、患者标识、凭据、cookie、授权头、provider 响应体、隐藏 chain-of-thought。
- 关联字段：`request_id`/`run_id`/`workspace_id`/`job_id`/`event_id`；`run_id` 是业务真相，`langfuse_trace_id` 仅关联。
- Langfuse 只记脱敏元数据且 fail-open；Aegra 是唯一 Langfuse 摄取 owner，应用不初始化 Langfuse client。

## 4. 包边界（ADR 0060/0025）

- Python 导入名用项目限定名（`medicalrag_infra` 而非 `infra`）。
- 禁止 `helpers.py`/`common.py` 垃圾桶；公共代码归属明确领域或适配器模块。
- `apps/*` 互不 import；共享行为经 `medical-core`/`packages/infra`。
- 禁止循环依赖；需要互引类型时上移稳定抽象到契约层。

## 5. 发布与配置

- 配置启动 fail fast；生产用 secrets；超时/pool/retry/backoff/并发度可审计。
- 镜像与包版本锁定（见 [version-baseline.md](version-baseline.md)）；禁 `latest`。
