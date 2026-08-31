# Python 后端与数据栈官方最佳实践调研

> 调研日期：2026-07-26  
> 适用范围：MedicalRAG 的 Python 3.12 后端、异步 API、业务数据库、缓存/协调层、异步任务消息总线。  
> 覆盖技术：Python 3.12、uv、FastAPI、Pydantic v2、SQLAlchemy 2 async、Alembic、PostgreSQL、Redis/redis-py、Apache RocketMQ/Python client。  
> 来源约束：只引用技术项目自身官方文档、Apache 官方文档、Python/PyPA 官方文档及 Apache 官方项目仓库/PyPI 元数据。  
> 本文不是实现代码；“官方事实”记录上游文档明确描述的行为，“本项目设计建议”是结合 MedicalRAG 运行边界推导出的工程方案，二者不混写。

> **计划变更（2026-08-01）：** 本文是历史调研快照，正文保留原始记录供决策追溯，不再作为实现目标。复刻计划已按 [ADR 0063](../adr/0063-arq-replaces-rocketmq-as-the-durable-job-queue.md) 将异步任务消息总线从 Apache RocketMQ 更换为 arq（Redis 支撑的 asyncio 任务队列，配合 PostgreSQL 事务性 Outbox 与失败/重放），并按 [ADR 0064](../adr/0064-uv-manages-python-314-runtime.md) 将 Python 运行时基线从 3.12 提高到 3.14（uv 管理）。正文中与 RocketMQ、Python 3.12 相关的结论均已被上述 ADR 取代。

## 1. 结论摘要

### 1.1 推荐的后端运行形态

本项目的 Python 侧应保持明确的进程职责：

| 进程 | 主要职责 | 不能承担的职责 |
| --- | --- | --- |
| `apps/api` | FastAPI HTTP 入口、认证授权、业务 API、管理 API、配置读取、请求级依赖组合 | 不直接运行 RocketMQ 长驻消费者；不在请求中执行文档摄取、MinerU、Embedding 或 Milvus 建索引 |
| `apps/agent` | Aegra/LangGraph graph 的 Python 业务节点与端口接入 | 不复制 FastAPI 的 HTTP 业务逻辑；不自行创建第二套数据库会话管理 |
| `apps/worker` | RocketMQ 消费、文档摄取、解析、切块、Embedding、Milvus 索引及重试/死信处理 | 不持有浏览器请求上下文；不把长任务塞进 FastAPI 请求生命周期 |
| `apps/evaluation` | 隔离的检索/答案评测 runner，可选使用 RAGAS 和受控 judge provider | 不作为常驻生产服务；不把 RAGAS、judge 凭据或评测数据带入 API、Agent、Worker |
| `packages/medical-core` | 与 FastAPI、Agent、Worker 共享的领域对象、状态机、不变量、策略和端口 | 不放 SQLAlchemy model、FastAPI router、Redis/Milvus/RocketMQ SDK 或外部 HTTP client |
| `packages/infra` | PostgreSQL、Redis、Milvus、RocketMQ、对象存储、外部 API、业务 run/audit repository、OpenTelemetry 和普通结构化观测的具体适配器 | 不反向依赖 API 路由或前端；不把基础设施细节泄露到领域包；不初始化 Langfuse |

这是本项目的设计建议，不是 FastAPI、SQLAlchemy 或 uv 强制要求的唯一结构。其目的在于让 API、Agent 和 Worker 共享同一套医疗业务不变量，同时保留可替换的基础设施边界。

### 1.2 最重要的异步原则

- FastAPI、SQLAlchemy 2 async 和 redis-py asyncio 路径可以使用异步 I/O；阻塞式 SDK、文件系统操作和 CPU 密集工作不得直接阻塞事件循环。[PY3][FA2]
- SQLAlchemy `AsyncSession` 不得在并发任务之间共享；每个并发任务需要独立 session。[SA1]
- redis-py asyncio 客户端必须显式关闭；异步连接池不能依赖析构函数完成清理。[RD2]
- 需要区分两代 Python client：旧的 `rocketmq-client-python` 是基于 C++ 客户端的 ctypes 封装；新的 `rocketmq-python-client` 属于 Apache `rocketmq-clients` 5.x 多语言 gRPC client，使用 Protobuf/gRPC，不再依赖旧的 `librocketmq` 动态库。[RMQ7][RMQ8][RMQ11][RMQ12]

因此，RocketMQ Python client 应只位于 `apps/worker` 的专用进程边界内；不能在 FastAPI 的 async path operation 中直接调用它。若确实需要从异步代码触发消息，应该通过 worker/适配器边界或受控线程隔离，而不是把阻塞调用伪装成异步函数。

### 1.3 关键兼容性结论：应优先使用 Apache 官方 RocketMQ 5.x Python client

此前关于“RocketMQ Python client 尚未确认支持 Python 3.12”的判断只适用于旧的 `rocketmq-client-python` 2.x ctypes client，不能套用于 Apache 当前的 5.x 多语言 client：

1. Apache `rocketmq-clients` 官方仓库说明该项目是 RocketMQ 5.x SDK 集合，遵循 `rocketmq-apis`，基于 Protocol Buffers 和 gRPC；其 feature matrix 将 Python 的 normal、FIFO、delay、transaction、simple consumer 和 push consumer 标记为 Ready。[RMQ11]
2. 官方 Python 包名为 `rocketmq-python-client`，PyPI 当前版本为 `5.1.1`，声明 `Requires-Python >=3.7`，发布 `py3-none-any` wheel，依赖 `grpcio`、`grpcio-tools`、`protobuf` 和 OpenTelemetry 组件，不再要求旧的 `librocketmq`。`Requires-Python >=3.7` 是下限声明，不等于对 Python 3.12 的显式测试报告；`py3-none-any` 只说明该发行版本身没有 CPython/平台专属 wheel，也不能替代对 `grpcio` 等传递依赖和目标 Linux 镜像的运行时验证。[RMQ12][RMQ13]
3. Apache 官方 Python 示例覆盖同步 producer、Future 风格的异步 producer、push consumer、simple consumer 和 transaction producer；新 client 使用 `ClientConfiguration` 的 gRPC endpoint，而不是旧 client 的 NameServer ctypes 接口。[RMQ14]
4. RocketMQ 官方 5.0 文档将 gRPC SDK 的支持范围指向 `rocketmq-clients` 仓库，并明确 gRPC SDK 需要 RocketMQ server `>=5.0`；因此判断 Python 支持时，应以该官方仓库和对应 PyPI 发布物为准，并锁定具体版本。[RMQ1][RMQ11]

**本项目设计建议**：将 `rocketmq-python-client==5.1.1` 作为首选方案，先验证 Python 3.12、`grpcio`/Protobuf、RocketMQ 5.0+ gRPC endpoint、认证/TLS、事务、重试、DLQ、重启和重复投递。旧的 `rocketmq-client-python` 与新的 `rocketmq-python-client` 都使用 `rocketmq` import namespace，不能在同一运行环境中共存；依赖锁中只能保留新 client。[RMQ7][RMQ12]

### 1.4 RocketMQ Python client 的替代方案结论

有替代方案，但优先级不同：

| 方案 | 是否保留 RocketMQ | Python 3.12 的旧 native ABI 风险 | 额外运行时 | 主要前提 | 本项目结论 |
| --- | --- | --- | --- | --- | --- |
| Apache `rocketmq-python-client` 5.1.1 | 是 | 不再依赖旧 `librocketmq`；仍需验证 `grpcio` 等传递依赖 | 无额外桥接进程 | RocketMQ 5.0+、Proxy/gRPC endpoint | 首选 |
| Apache 5.x Go client sidecar | 是 | Python 进程无 RocketMQ native ABI | Go bridge service | 自定义 Python↔Go bridge contract | 首选兜底 |
| Apache 5.x Java client sidecar | 是 | Python 进程无 RocketMQ native ABI | JVM bridge service | Java 8 runtime、Java 11+ build、Proxy/gRPC endpoint | 可行兜底，运维成本高于 Go |
| Apache 5.x Node.js client sidecar | 是 | Python 进程无 RocketMQ native ABI | Node.js bridge service | Node.js 16.19+，官方推荐 >=18.17、Proxy/gRPC endpoint | 可行但不优先 |
| Apache Pulsar Python client | 否 | PyPI 提供 CPython 3.12 wheels | 更换 broker 与部署拓扑 | 重新设计消息语义、重试、DLQ、运维和迁移 | 仅在有意更换 broker 时考虑 |
| 旧 `rocketmq-client-python` 2.x | 部分兼容旧链路 | 仍有 `ctypes`/`librocketmq`/平台 ABI 风险 | 无 | 旧 Remoting/NameServer 链路 | 不采用 |

以上表格中的“首选/兜底/不优先”是本项目设计建议；各 SDK 的协议、语言和运行时前提是 Apache 官方仓库、官方文档或 PyPI 元数据中的事实。[RMQ1][RMQ11][RMQ12][RMQ13][RMQ18][RMQ19][RMQ20][RMQ21][RMQ22]

### 1.5 存储职责建议

| 存储 | 建议承担 | 不应承担 |
| --- | --- | --- |
| PostgreSQL | 用户、workspace、权限、知识库元数据、文档状态、任务状态、审计、反馈、幂等记录和结构化业务事实 | 作为临时缓存；用应用代码单独模拟唯一性/外键约束 |
| Redis | Session、短期缓存、限流计数、短期锁、Pub/Sub 和跨进程协调 | 作为医疗业务唯一事实来源；用普通 TTL key 代替持久化状态机 |
| Milvus | 向量与全文 hybrid 检索及索引 | 本文不展开其专属官方文档；通过明确端口由 `packages/infra` 接入 |
| RocketMQ | 摄取/索引等长任务的持久化异步事件、消费重试和死信 | 代替 PostgreSQL 事务；承诺业务 exactly-once |

### 1.6 事实与建议的阅读约定

- **官方事实**：可以从链接的官方文档、官方源码或 PyPI 官方元数据直接核对。
- **本项目设计建议**：是对 MedicalRAG 的边界、可靠性和可测试性要求的推导，不应误读为上游工具的强制规则。
- **版本 caveat**：说明文档当前版本、兼容性不确定性或升级时必须重新验证的边界。

## 2. 推荐 Python monorepo 目录与职责边界

### 2.1 官方事实

- Python Packaging User Guide 将 `pyproject.toml` 的 `[build-system]`、`[project]` 和 `[tool]` 分别作为构建系统、项目元数据和工具配置的主要位置。[PY7]
- Python Packaging User Guide 说明 `src` layout 把 import package 放在 `src/` 下，需要先安装项目才能运行，可以降低从仓库工作目录误导入未安装源码的风险。[PY8]
- uv workspace 由一个或多个 workspace member 组成；每个 member 有自己的 `pyproject.toml`，workspace 共享一个 lockfile，成员之间的依赖可以 editable 方式安装。[UV1][UV2]
- FastAPI 官方多文件示例使用 Python package、`main.py`、子 package 和多个 `APIRouter`，最后由主应用 `include_router()` 组合。[FA1]

### 2.2 本项目设计建议

建议的 Python 目录如下。目录名称是本项目约定，不是上游框架的硬性要求。

```text
MedicalRAG/
├── pyproject.toml                       # uv workspace coordinator
├── uv.lock                              # Python workspace 唯一锁文件
├── apps/
│   ├── api/
│   │   ├── pyproject.toml
│   │   ├── alembic.ini
│   │   ├── alembic/
│   │   │   ├── env.py
│   │   │   ├── script.py.mako
│   │   │   └── versions/
│   │   ├── src/medicalrag_api/
│   │   │   ├── main.py                   # 创建并组合 FastAPI app
│   │   │   ├── bootstrap.py               # 生命周期与依赖容器
│   │   │   ├── config/                    # Settings 与配置分组
│   │   │   ├── api/
│   │   │   │   ├── dependencies.py
│   │   │   │   ├── exception_handlers.py
│   │   │   │   └── v1/
│   │   │   │       ├── auth/
│   │   │   │       ├── workspaces/
│   │   │   │       ├── knowledge_bases/
│   │   │   │       ├── documents/
│   │   │   │       ├── conversations/
│   │   │   │       └── administration/
│   │   │   └── application/               # API 用例编排，不放 SDK 细节
│   │   └── tests/
│   │       ├── unit/
│   │       ├── integration/
│   │       └── contract/
│   ├── agent/
│   │   ├── pyproject.toml
│   │   ├── src/medicalrag_agent/
│   │   │   ├── graph/
│   │   │   ├── nodes/
│   │   │   ├── runtime/
│   │   │   └── main.py
│   │   └── tests/
│   └── worker/
│       ├── pyproject.toml
│       ├── src/medicalrag_worker/
│       │   ├── main.py
│       │   ├── consumers/
│       │   │   ├── document_ingestion.py
│       │   │   ├── embedding.py
│       │   │   └── indexing.py
│       │   ├── handlers/
│       │   ├── retry_policy.py
│       │   └── runtime/
│       └── tests/
│           ├── unit/
│           ├── integration/
│           └── contract/
├── packages/
│   ├── medical-core/
│   │   ├── pyproject.toml
│   │   ├── src/medical_core/
│   │   │   ├── domain/
│   │   │   │   ├── identity/
│   │   │   │   ├── workspaces/
│   │   │   │   ├── knowledge_bases/
│   │   │   │   ├── documents/
│   │   │   │   ├── ingestion/
│   │   │   │   ├── retrieval/
│   │   │   │   └── conversations/
│   │   │   ├── application/
│   │   │   │   ├── ports/
│   │   │   │   ├── commands/
│   │   │   │   └── services/
│   │   │   └── shared/
│   │   └── tests/
│   │       └── unit/
│   └── infra/
│       ├── pyproject.toml
│       ├── src/medicalrag_infra/
│       │   ├── postgres/
│       │   │   ├── engine.py
│       │   │   ├── session.py
│       │   │   ├── models/
│       │   │   └── repositories/
│       │   ├── redis/
│       │   ├── milvus/
│       │   ├── rocketmq/
│       │   ├── providers/
│       │   │   ├── generation/
│       │   │   ├── embedding/
│       │   │   ├── reranker/
│       │   │   └── mineru/
│       │   └── observability/
│       │       ├── trace_recorder/
│       │       ├── logging/
│       │       └── metrics/
│       └── tests/
│           ├── unit/
│           ├── integration/
│           └── contract/
```

### 2.3 `medical-core` 的具体作用

`medical-core` 不是 `utils` 集合，也不是所有共享代码的垃圾桶。它应保存：

- workspace、文档、知识库、摄取任务、检索请求、会话和权限边界的领域对象与值对象；
- 文档摄取状态机、发布状态、任务重试状态、幂等不变量等纯业务规则；
- 领域服务、策略和端口接口，例如文档仓储、事件发布、检索、外部模型调用的抽象；
- 可以不连接 PostgreSQL、Redis、RocketMQ、Milvus 或 HTTP 服务运行的测试。

它不应保存：

- SQLAlchemy declarative model 或 `AsyncSession`；
- FastAPI `APIRouter`、HTTP exception 或 request object；
- redis-py、RocketMQ、Milvus、MinerU 或外部模型 SDK；
- Aegra server 启动、进程生命周期和 Docker 配置。

**本项目设计建议**：API、Agent 和 Worker 都依赖 `medical-core`；`packages/infra` 实现 `medical-core` 的端口；每个入口应用负责组合依赖。不能把 `infra` 放入 `apps/api`，否则 Agent/Worker 要么反向 import API，要么重复实现适配器，要么增加不必要的内部 HTTP hop。

## 3. Python 3.12

### 3.1 官方事实

- Python 3.12 官方文档包含独立的 3.12 标准库与语言文档；当前页面显示的文档修订版本为 3.12.13。[PY1]
- Python `asyncio` 是用于并发代码的标准库，提供 event loop、Task 和 high-level API；官方文档区分异步 I/O 与会阻塞事件循环的同步调用。[PY3]
- Python `asyncio.to_thread()` 用于把会阻塞事件循环的同步函数放到线程中执行；它适合 I/O-bound 阻塞任务，不能把 CPU 密集工作自动变成高效异步任务。[PY9]
- Python `venv` 文档把虚拟环境视为可删除、可重建的环境，并不建议把它作为需要跨机器复制的持久化资产。[PY4]
- PEP 8 建议 4 个空格缩进、模块级导入分组、明确命名和受控的行长度；PEP 257 规定了 docstring 的约定。[PY5][PY6]

### 3.2 本项目设计建议

- 所有 Python workspace member 统一声明 `>=3.12,<3.13`，Docker、CI、开发机都使用同一 Python 3.12 minor/patch 基线；不要让 API、Agent、Worker 在不同 minor 版本下开发。
- 采用 `src` layout、类型标注和显式返回类型；将异步 I/O 边界限制在 API、PostgreSQL、Redis 和明确支持 async 的外部 client。
- 对同步 SDK 做显式隔离：RocketMQ Python client 运行在 worker 进程，不在 FastAPI 事件循环中直接调用；不能因为函数外层写了 `async def` 就认为内部调用是非阻塞的。
- 虚拟环境和镜像依赖均由 uv lockfile 重建；不把 `.venv` 作为源码交付物，不把运行时状态写回源码树。
- Python 标准库的 `contextlib`、`logging`、`dataclasses`、`enum`、`typing` 和 `asyncio` 用于通用基础能力；只有在确有跨进程/跨服务边界时才引入额外抽象。

### 3.3 版本 caveat

Python 3.12 的标准库行为以 3.12 文档为准；实现阶段应固定 3.12.x patch 版本，并在升级 patch 或基镜像时运行 `grpcio` 等 native extension、SQLAlchemy driver、redis-py 和 RocketMQ 5.x endpoint 的兼容性测试。旧 `rocketmq-client-python` 的 `librocketmq` ABI 只属于明确不采用的旧路线，不应再作为新 client 的默认前提。Python 3.12 的新语法或运行时特性不应未经必要性评估就扩散到共享包，以便未来升级 Python 时降低迁移成本。[PY2]

## 4. uv 与 Python workspace

### 4.1 官方事实

- uv workspace 是一个或多个 package 的集合；workspace member 可以是应用或库，每个 member 需要自己的 `pyproject.toml`。[UV1]
- workspace 默认共享一个 lockfile，以保证整个 workspace 的依赖集合一致；member 之间的本地依赖可以以 editable 方式安装。[UV1]
- 根 `pyproject.toml` 可以用 `[tool.uv.workspace]` 的 `members` 和 `exclude` 配置 workspace；所有成员的 `requires-python` 必须存在可满足的交集。[UV1]
- uv 项目以 `pyproject.toml` 为项目元数据入口，旁边维护 `uv.lock` 和项目虚拟环境；uv 文档也明确描述了 `src` layout 的项目结构。[UV2]
- `tool.uv.package = true/false` 可以显式控制当前项目是否构建和安装；这适合区分 workspace coordinator 与真正的应用/库包。[UV3]
- uv 的依赖组、项目依赖和 lock/sync 操作都以 `pyproject.toml` 和 lockfile 为中心；不应把手工修改 `.venv` 当作项目配置。[UV3][UV4]

### 4.2 本项目设计建议

- 根 `pyproject.toml` 只承担 uv workspace coordinator 角色；`apps/api`、`apps/agent`、`apps/worker`、`packages/medical-core`、`packages/infra` 和隔离的 `apps/evaluation` 各自拥有 `pyproject.toml`。
- 根 `uv.lock` 纳入代码审查和 CI；依赖升级必须由 uv 完成并检查 lockfile 变化，不直接使用未锁定的 `pip install` 进入生产镜像。
- 所有 member 的 `requires-python` 先统一到 `>=3.12,<3.13`。RocketMQ client 只由 worker 专属依赖声明；如果直接 Python client 的传递依赖无法在同一 workspace 稳定解析，优先把它隔离为 worker 专属依赖组或切换到 sidecar，并记录原因；不要通过放宽整个 workspace 的 Python 约束掩盖兼容性问题。
- 生产、CI 和本地开发都使用 lockfile 驱动的同步流程；开发依赖与运行依赖分组，但不能让测试依赖偷偷进入生产镜像。
- `medical-core` 保持轻依赖，避免把 SQLAlchemy、redis-py 或 RocketMQ client 拉入所有 Python 进程；基础设施依赖只由 `packages/infra` 或相应应用声明。Ollama 和本地模型服务不进入任何生产依赖组。
- Docker 构建时先复制 `pyproject.toml`、workspace 配置和 `uv.lock`，在依赖层稳定后再复制源码；这利用的是 uv 官方 Docker 指南描述的缓存分层思路，而不是业务代码要求。[UV5]

### 4.3 版本 caveat

uv 文档是随工具演进的滚动文档，CLI 参数和配置键可能比项目代码更快变化。实现阶段必须固定 uv 版本，CI 中同时核对 Python 版本、uv 版本和 `uv.lock`；不能把 `uv` 或依赖声明为 `latest` 并期待生产结果长期可重现。

## 5. FastAPI

### 5.1 官方事实

- FastAPI 官方多文件应用示例使用 package、`main.py`、子 package、`APIRouter` 和 `include_router()` 拆分应用。[FA1]
- FastAPI 支持依赖注入，依赖可以有子依赖；依赖函数也可以通过 `yield` 管理需要释放的资源。[FA1][FA7]
- FastAPI 的现代生命周期入口是 `lifespan`；它把 startup 和 shutdown 资源管理放在同一个异步上下文中。官方文档提示，使用 `lifespan` 时不应再同时使用旧的 startup/shutdown 事件处理器。[FA3]
- FastAPI 的 settings 文档使用 `pydantic-settings` 读取环境变量，并展示用 `lru_cache` 只创建一次 Settings 对象的方式。[FA4]
- FastAPI 测试文档使用 `TestClient`、pytest 的 `test_` 命名约定和 `app.dependency_overrides`；异步测试文档使用 `pytest.mark.anyio` 与 `httpx.AsyncClient`。[FA5][FA6]
- FastAPI 的 async 文档说明：可以 `await` 的库应在 `async def` 中调用；阻塞调用则会影响事件循环，框架对同步 path operation 有线程池处理语义，但这不是任意阻塞链路的性能保证。[FA2]

### 5.2 本项目设计建议

- `main.py` 只做 app 创建、middleware、异常处理、OpenAPI 元数据、生命周期和 router 组合；业务流程放在 application service，领域规则放在 `medical-core`。
- 每个 feature 按 `router`、request/response schema、依赖、权限策略和 application service 分目录；不要按“所有 routers 一个目录、所有 schemas 一个目录”的技术类型大杂烩方式无限扩张。
- 在 `lifespan` 中创建和关闭 AsyncEngine、Redis async client、Milvus client 和外部 API client；RocketMQ producer 不由 HTTP 请求创建，也不在每次请求后销毁。
- 使用 FastAPI dependency provider 注入 session、当前用户、workspace scope 和授权策略；依赖函数只做边界组合，不把完整业务规则塞进 `dependencies.py`。
- API 层只接受和返回 Pydantic DTO；领域异常在 API 边界转换为稳定的 HTTP 错误结构，`medical-core` 不依赖 FastAPI 的 HTTP exception。
- API 只负责快速请求/响应、管理命令和启动异步任务；文档解析、Embedding、Milvus 建索引和长时间外部 API 调用转成 RocketMQ 任务。
- 使用 `TestClient` 覆盖同步边界，使用异步 HTTP 客户端覆盖需要真实 async 生命周期的边界；测试生命周期时使用官方文档要求的 context manager 语义。

### 5.3 版本 caveat

FastAPI 的文档与依赖生态会随 Starlette、Pydantic 和 ASGI 服务器版本变化。实现阶段应锁定 FastAPI/Pydantic/Starlette 的兼容组合，特别回归 `lifespan`、依赖覆盖、异常处理、OpenAPI 生成和异步测试；不要同时混用旧 startup/shutdown 写法和新 lifespan 写法。

## 6. Pydantic v2 与 pydantic-settings

### 6.1 官方事实

- Pydantic v2 的模型验证入口包括 `model_validate()` 和 `model_validate_json()`；模型序列化入口包括 `model_dump()`。[PD1]
- Pydantic 默认可能进行类型转换；官方提供 strict mode 以禁止部分宽松转换。[PD1][PD4]
- Pydantic v2 使用 `field_validator` 和 `model_validator` 进行字段级和模型级校验，支持 before、after、wrap 等模式。[PD3]
- Settings 管理已由独立的 `pydantic-settings` 包提供；`BaseSettings` 可以读取环境变量、`.env` 文件和 secrets directory，并支持嵌套配置与大小写策略。[PD2]
- Pydantic v2 迁移文档列出了 v1 API 到 v2 API 的变化，例如 `dict()`/`parse_obj()` 等旧风格与 `model_dump()`/`model_validate()` 的迁移关系。[PD5]

### 6.2 本项目设计建议

- 将 Pydantic 模型分为三类：HTTP DTO、事件/消息 DTO、Settings DTO。不要把 SQLAlchemy ORM model 直接当作所有边界的 schema。
- 外部输入、事件消息和管理配置使用显式字段；对事件 envelope、workspace id、job id、枚举和版本号使用更严格的类型策略。对需要拒绝未知字段的边界使用 `extra` 策略，但按边界逐一决定，不把所有模型无差别设置为同一模式。
- 使用 `model_validate()`/`model_dump()` 等 v2 API；禁止在新代码中引入 v1 `parse_obj`、`dict`、`Config`、`validator` 风格，除非是迁移兼容层。
- Settings 按子系统拆分：应用、PostgreSQL、Redis、RocketMQ、Milvus、外部 API、观测和安全。敏感字段使用 secrets 或专用 Secret 类型，不在启动日志中输出完整连接 URL、token 或密码。
- 本地可使用 `.env`，生产优先使用容器环境变量或 secrets directory；`.env` 不纳入镜像和版本库。
- Settings 在进程启动阶段一次性解析并验证；请求路径只读取已构造的不可变配置对象，不每次请求重新加载环境变量。
- validator 只承担边界格式、不变量和跨字段约束；数据库唯一性、外键和并发状态转换仍由 PostgreSQL 约束/事务保障，不能只依赖 Pydantic 校验。

### 6.3 版本 caveat

Pydantic v2 的兼容性重点不是“能否导入”，而是 v1 的隐式转换、序列化、字段别名、ORM 对象读取和 validator 语义是否改变。升级 Pydantic 时必须回归 API DTO、事件 DTO、配置加载、OpenAPI schema 和错误结构；`pydantic-settings` 也应单独锁定并测试。

## 7. SQLAlchemy 2 async

### 7.1 官方事实

- SQLAlchemy 2.0 async API 提供 `create_async_engine`、`AsyncEngine`、`AsyncConnection`、`AsyncSession` 和 `async_sessionmaker`。[SA1]
- `AsyncSession` 是有状态的 session，官方明确说明单个 `AsyncSession` 不安全地在并发 task 之间共享；并发任务应各自获取 session。[SA1]
- 官方 async 示例通常使用 `async_sessionmaker`，并推荐在需要提交后继续访问 ORM 对象时考虑 `expire_on_commit=False`，以避免不必要的隐式加载。[SA1]
- 异步 ORM 下的 lazy loading、expired attributes 和 deferred columns 可能触发隐式 I/O；官方提供显式 eager loading、`AsyncAttrs.awaitable_attrs` 和其他方式避免在不允许 await 的属性访问中发生隐式 I/O。[SA1]
- SQLAlchemy 提供 `AsyncConnection.run_sync()`/`AsyncSession.run_sync()` 作为 async 与同步 API 的桥接；Alembic 的 async 环境也使用此机制。[SA1][AL1]
- SQLAlchemy 的 asyncio 连接池使用 asyncio 兼容的队列池；普通 `QueuePool` 不兼容 asyncio DBAPI driver。[SA2]
- 连接池提供 `pool_pre_ping`、`pool_recycle`、`pool_size`、`max_overflow` 和 `dispose()` 等机制；这些参数会影响失效连接探测、连接生命周期和并发上限。[SA2]

### 7.2 本项目设计建议

- 进程级创建一个 AsyncEngine 和一个 `async_sessionmaker`；HTTP 请求、Agent run 节点和 Worker 消费任务各自创建短生命周期 `AsyncSession`。
- 每个业务用例使用明确的 `async with session.begin()` 事务边界；成功时自动提交，异常时回滚。不要把 session 作为全局可变对象传给并发任务。
- repository 使用 SQLAlchemy 2.0 风格的 `select()`、明确的 `await session.execute()` 和显式加载选项；禁止依赖 lazy load 在异步路径中“碰巧工作”。
- `get_session` 这类 FastAPI dependency 负责请求级 session 的获取和关闭；后台任务不得持有已经结束请求的 session。
- 连接池参数以“数据库允许的总连接数”和“服务副本数”反推：所有 API/Agent/Worker 实例的 `pool_size + max_overflow` 总和必须留出 PostgreSQL 管理连接、迁移、运维和其他服务的余量。具体数值必须通过压测与 PostgreSQL 监控确定。
- 开启失效连接探测，设置合理的连接回收时间和连接/查询超时；应用重启或 worker fork 时显式 dispose，避免把旧连接带到不应拥有它的进程。
- 外部 HTTP、MinerU、Embedding、Reranker、Milvus 和 RocketMQ 调用不应长时间占用 PostgreSQL 事务。先在短事务中记录状态，执行外部工作，再用新的短事务写回结果。

### 7.3 版本 caveat

SQLAlchemy 2 async 不是同步 ORM 的简单前缀替换。异步 driver、pool 类型、隐式 I/O、session 并发安全和对象过期行为都会影响正确性。实现阶段应统一使用 2.0 API，禁止混入旧 `Query` 风格；所有升级都要回归连接断开、事务回滚、并发 session、lazy relationship 和服务优雅关闭。

## 8. Alembic

### 8.1 官方事实

- Alembic 官方 cookbook 展示了 async engine 配置、`async_engine_from_config()` 和通过 `connection.run_sync()` 运行迁移逻辑的方式。[AL1]
- Alembic 的 autogenerate 会产生 candidate migration；官方明确要求人工检查、修正和审核，且列出了不能可靠自动检测的变更类型。[AL2]
- Alembic 提供 `revision`、`upgrade`、`downgrade` 等迁移命令，并可使用 `alembic check` 检查模型变化是否产生未提交迁移。[AL3]

### 8.2 本项目设计建议

- PostgreSQL 业务 schema 由一个明确的 Alembic migration owner 管理；建议放在 `apps/api/alembic/`，而不是让每个 worker/包各自创建一套 migration head。
- 所有表、索引、约束、枚举和 JSON 结构变化都通过迁移文件提交；生产禁止依赖 `metadata.create_all()` 作为 schema 发布机制。
- autogenerate 只作为草稿生成器；每个迁移必须人工检查表重建、数据迁移、索引并发性、锁时长、默认值、可空性、外键和回滚影响。
- CI 至少执行一次从空库/基线到 `head` 的升级、`alembic check` 和关键查询 smoke test；测试环境验证需要的 downgrade，但生产是否允许 downgrade 由迁移风险逐项决定。
- 大表变更拆分为“扩展 schema、回填/双写、切换读取、收缩 schema”等阶段，避免单个事务长时间锁住业务表。
- 迁移脚本不调用外部 API、不依赖 Redis/Milvus/RocketMQ 在线状态；迁移应尽量只依赖 PostgreSQL 和明确的本地数据转换。

### 8.3 版本 caveat

Alembic 的 async template 并不意味着迁移脚本本身完全变成 async API；核心迁移操作仍通过 `run_sync` 适配。Alembic autogenerate 也不等于 schema diff 的完整证明，升级 Alembic 或 SQLAlchemy 后必须复查 metadata、命名约定、索引和自定义类型的生成结果。

## 9. PostgreSQL

### 9.1 官方事实

- PostgreSQL 将每条 SQL 语句放在事务中执行；未显式 `BEGIN` 时，单条语句具有隐式 begin/commit，显式事务块使用 `BEGIN`、`COMMIT` 和 `ROLLBACK`。[PG2]
- 事务提供原子性与隔离性；savepoint 可以在事务内部回滚局部工作。[PG2]
- PostgreSQL 提供 Read Committed、Repeatable Read 和 Serializable 等隔离级别；实现应根据并发不变量选择，而不是默认把所有操作提升到最高级别。[PG3]
- Primary key、unique、foreign key 和 check constraint 可以由数据库直接维护唯一性、引用完整性和数据约束。[PG4]
- 索引可以加速查找，但也有写入、存储和维护开销，应有选择地使用。[PG5]
- `max_connections` 直接影响服务器资源分配和同时存在的连接上限；PostgreSQL 还保留超级用户连接槽位。[PG6]
- PostgreSQL 支持 TLS 连接；官方连接配置文档明确说明 `ssl` 配置控制加密连接。[PG6]
- PostgreSQL 提供 `statement_timeout`、`lock_timeout` 和 `idle_in_transaction_session_timeout` 等客户端/会话级超时配置。[PG7]

### 9.2 本项目设计建议

- PostgreSQL 是 MedicalRAG 的业务事实源：身份、workspace、权限、知识库、文档版本、摄取状态、任务状态、审核、反馈和幂等记录都应可在 PostgreSQL 中恢复。
- 使用 primary key、unique、foreign key、check 和必要的 exclusion/partial index 表达不变量；Pydantic 校验只负责请求边界，不能替代并发安全的数据库约束。
- 对“一个业务请求/文档版本/任务阶段只能成功一次”的规则，优先使用唯一约束和事务内状态转换；应用层先查再插入不能单独防止并发竞态。
- 默认采用短事务和明确的 `READ COMMITTED` 语义；只有在可证明的并发异常下才使用显式锁、更高隔离级别或 serializable 重试，并记录其代价。
- 对所有服务设置合理的连接、查询和锁超时；超时值应区分 API 快速查询、后台摄取和迁移，不把无限等待当作可靠性策略。
- 连接池总容量按 PostgreSQL `max_connections` 反推，数据库管理员连接、迁移任务和应急操作必须保留余量。
- 生产使用独立数据库角色和最小权限；传输使用 TLS；备份与恢复演练覆盖 schema、业务数据和必要的审计数据，不只验证“备份文件存在”。
- 索引以真实查询计划、过滤字段、排序、唯一性和写入成本为依据；每一个索引都应有对应查询或约束理由。

### 9.3 版本 caveat

截至调研日，PostgreSQL `current` 官方文档页面显示为 18.4；这不意味着项目必须自动跟随 current。Docker Compose 应固定 PostgreSQL major/minor，升级时分别验证 Alembic、SQLAlchemy driver、扩展、索引行为、备份恢复和查询计划。[PG1][PG10] PostgreSQL minor upgrade、major upgrade 和扩展升级应区分处理，不能只修改镜像标签。

## 10. Redis 与 redis-py

### 10.1 官方事实

- redis-py 提供同步和 asyncio API；asyncio 示例明确要求显式调用 `aclose()`，因为异步对象没有可依赖的析构清理。[RD2]
- redis-py 默认会为 Redis client 创建内部 connection pool；如果自建 pool 并由单个 Redis 实例拥有，可以由 client 负责关闭；如果多个 client 共享 pool，则需要显式管理 pool 生命周期。[RD2]
- redis-py connection 配置包含 `max_connections`、`health_check_interval`、socket timeout/connect timeout、TLS 等选项。[RD3]
- redis-py 提供 `Retry`、backoff 和 `retry_on_error`；官方示例说明可以指定重试次数、backoff 和额外可重试异常。[RD4]
- pipeline 默认可以作为事务批处理，`transaction=False` 可以关闭事务；`WATCH` 用于乐观并发控制，冲突时会抛出 `WatchError`。[RD5]
- 官方文档提醒 PubSub 或 Pipeline 对象不能在多个线程之间安全共享；它们应有明确的使用者和生命周期。[RD5]
- Redis ACL 支持按用户、命令类别和 key pattern 限制权限；Redis 官方 TLS 文档说明可以使用证书、CA 和客户端认证。[RD6]
- Redis RDB 是时间点快照，AOF 记录写操作；两者可以组合，持久性、恢复时间和写入开销不同。[RD6]
- Redis 默认复制是异步的，故障切换时可能丢失尚未复制的数据；复制不能自动等同于强一致持久化。[RD6]

### 10.2 本项目设计建议

- Redis 定位为 session、缓存、限流、短期 lease、Pub/Sub 和跨进程协调层；PostgreSQL 才是用户、权限、任务状态和审计的事实源。
- 进程级创建异步 Redis client 和 pool，在 FastAPI/Agent/Worker lifespan 中关闭；不要在每个请求中创建新的 pool，也不要把 PubSub 对象放进全局共享业务对象后交给多个并发 task。
- key 命名必须包含环境、workspace/租户边界、业务类型和资源 id，并设置明确 TTL；TTL 是缓存/租约策略，不是业务状态的删除替代品。
- Session、限流、缓存、锁和 Pub/Sub 使用不同的 key namespace；需要不同 ACL 权限或不同超时策略时，使用不同 Redis user 或 client 配置。
- 对 Redis 原子性要求使用单个命令、事务 pipeline、Lua 或 WATCH；不要把“先 GET、再 SET”当成并发安全的状态转换。
- `Retry` 只用于明确可重试的连接/服务暂时性错误；缓存读取可以有限重试，锁获取、计数递增、队列 claim、发布通知等副作用操作必须先证明重复执行安全。
- Pub/Sub 只作为实时通知，不作为唯一可靠事件日志；需要恢复的任务状态写入 PostgreSQL 或 RocketMQ。
- 如果 Redis 只保存可重建缓存，可以选择较轻的持久化策略；如果保存 session、限流窗口或协调状态，应根据丢失容忍度配置 RDB/AOF、备份和故障恢复，并记录“复制异步”的影响。
- 生产启用 ACL/TLS 和最小 key 权限；禁止在日志中输出连接 URL、密码、session token 或完整医疗内容。

### 10.3 版本 caveat

截至调研日，redis-py 官方文档页面显示为 8.0.0；redis-py 与 Redis server 的协议、TLS、ACL、集群/哨兵和 async 生命周期需要一起验证。异步 client 升级时重点回归 `aclose()`、共享 pool、pipeline/WATCH、Pub/Sub 取消订阅、连接断开重连和 retry 行为。[RD1][RD2]

## 11. Apache RocketMQ 与 Python client

### 11.1 Apache 官方事实

- Apache RocketMQ 官方 SDK 概览区分 Remoting 与 gRPC 两套协议：Remoting SDK 与服务端版本演进绑定较强，gRPC SDK 从 5.0 引入，面向更轻量、标准化和可扩展的客户端通信。[RMQ1]
- Apache `rocketmq-clients` 官方多语言仓库说明其 client 遵循 `rocketmq-apis`，使用 Protocol Buffers 和 gRPC 替代 4.x Remoting client；当前仓库 feature matrix 将 Python 和 Node.js 的主要生产/消费能力标记为 Ready。[RMQ11]
- 新的官方 Python client 位于 `rocketmq-clients/python`，包名为 `rocketmq-python-client`；其 `setup.py` 声明 `python_requires >=3.7`，依赖 gRPC、Protobuf 和 OpenTelemetry，不依赖 `librocketmq`。[RMQ12]
- PyPI 官方元数据截至调研日显示 `rocketmq-python-client` 版本为 5.1.1，提供 `py3-none-any` wheel，上传时间为 2026-02-10；该元数据本身不构成 Python 3.12 端到端兼容性证明。[RMQ13]
- 新 Python client 官方示例覆盖 normal producer、Future 风格的 async producer、push consumer、simple consumer 和 transaction producer；producer/consumer 通过 `ClientConfiguration` 连接 gRPC endpoint。[RMQ14]
- RocketMQ 官方 SDK 文档明确：gRPC SDK 只支持 server `>=5.0`，不能直接用于 4.x server；从 Remoting SDK 切换到 gRPC SDK 需要修改代码，因为两套 client API 不兼容。[RMQ1]
- Normal message 官方文档说明，生产发送遇到网络异常或请求超时时可能触发重试；发送端无法判断 broker 是否已经处理了超时请求，因此重发可能产生重复消息，业务逻辑必须能正确处理。[RMQ2][RMQ3]
- 消费重试官方文档说明：消费失败时 broker 会按策略重新投递；达到最大重试次数后进入 dead-letter queue。消费重试用于保护消费完整性，不能替代业务流程控制。[RMQ4]
- 消费 offset 由 RocketMQ 管理，消费者重启后可以依据服务端保存的 offset 继续处理；这并不消除业务副作用重复执行的可能。[RMQ5]
- 集群消费在同一 consumer group 内进行负载均衡；不同 consumer group 可以分别订阅同一消息。[RMQ5]
- RocketMQ transaction message 使用 half message、commit/rollback 和 transaction checker；在 producer 断线或状态未知时，broker 会向 producer 查询本地事务状态。[RMQ6]
- 旧的 Apache `rocketmq-client-python` README/源码仍是 `rocketmq-client-cpp` ctypes wrapper，使用 `send_sync()`、回调消费和 `librocketmq`；旧包与新包的 distribution name 不同，但 import namespace 都是 `rocketmq`。[RMQ7][RMQ8]
- Python client 官方源码显示，`ClientConfiguration` 解析 endpoint 并保存 credentials、namespace 和 request timeout；`Producer` 提供同步 `send()` 与基于 Future 的 `send_async()`，因此它不是 FastAPI 原生 coroutine API。[RMQ15][RMQ16]

### 11.2 本项目设计建议

- RocketMQ 只由 `apps/worker` 使用，负责文档摄取、MinerU 处理、切块、Embedding、Milvus 建索引和运维异步事件；聊天 Thread/Run、Checkpoint 和浏览器流式输出由 Aegra 负责。
- 优先使用 `rocketmq-python-client` 5.x；每个 producer/consumer 在 worker 进程启动时创建，在 graceful shutdown 时显式 shutdown。不要在每条消息或每个 HTTP 请求中初始化 client。
- 新 client 的 public `send()` 仍是同步结果接口，`send_async()` 返回 Future；它不是 FastAPI 原生 coroutine API。worker 内可以使用 Future/回调，但不要在 FastAPI event loop 中直接阻塞调用 `send()`；必要时由异步应用调用隔离线程或继续沿用“API 记录任务、Worker 发布消息”的边界。[RMQ14][RMQ16]
- 新 client 使用 RocketMQ 5.x gRPC endpoint；不要把旧 NameServer 地址直接填入 `ClientConfiguration`。Compose 中应明确启动并暴露与所选 client 对应的 RocketMQ Proxy/gRPC endpoint，端口以实际部署配置为准。[RMQ1][RMQ14][RMQ17]
- 事件 envelope 至少包含稳定的 `event_id`、`event_type`、`schema_version`、`aggregate_id`、`workspace_id`、创建时间、追踪上下文和业务 payload。不要把仅有 RocketMQ message id 当作业务幂等键。
- consumer 只有在 PostgreSQL 状态写入、对象存储/MinerU 结果落盘、Milvus 索引阶段成功且幂等记录提交后，才返回消费成功；可恢复的异常返回 `RECONSUME_LATER`，不可恢复或超过策略的消息进入 DLQ。
- 生产者发送超时必须按“可能已经成功”处理：使用业务 event id/幂等表避免重发造成重复任务，并记录原始 message id、send result 和重试次数。
- 消费处理采用“消息键 + 业务状态机 + PostgreSQL 唯一约束”实现效果上的幂等；Redis SET NX 可以做短期重复抑制或租约，但不能作为最终幂等事实。
- RocketMQ transaction message 只在确实需要“本地 PostgreSQL 状态与消息可见性协调”且新 5.x Python client/broker 兼容性门禁通过时使用。即使使用 transaction message，也不能把它描述为 PostgreSQL、Redis、Milvus 和 RocketMQ 之间的全局 exactly-once 事务。
- 将 client 封装在 `packages/infra` 的小接口中，应用层只看到 `publish()`、`consume()`、`ack/retry` 和事务能力；不要让 `rocketmq` 包名或 gRPC 细节进入 `medical-core`。
- Docker Compose worker 镜像固定 `rocketmq-python-client`、grpcio、protobuf、OpenTelemetry 和 RocketMQ 5.x endpoint 配置；禁止同时安装旧 `rocketmq-client-python`，也禁止从 Git `master` 直接构建未审计版本。

### 11.3 版本 caveat 与发布门禁

旧 ctypes client 的 native ABI 不再是默认路线；新 5.x Python client 仍需要独立 compatibility spike，验证：

1. Python 3.12 环境可以安装并导入 `rocketmq-python-client==5.1.1`，且 `grpcio`/Protobuf wheel 与目标 Linux 镜像兼容；
2. RocketMQ 5.0+ 的 gRPC endpoint、Proxy、认证和 TLS 配置与 `ClientConfiguration` 一致；
3. producer 启动、同步发送、Future 异步发送、超时重试和进程重启后的资源释放正常；
4. PushConsumer/SimpleConsumer 能正确完成消费、ack、invisible duration、重试、DLQ 和 offset 恢复；
5. transaction producer 的 half message、commit/rollback 和 server checker 在选定 broker 版本上可用；
6. 业务幂等层能安全处理发送超时造成的重复消息、消费重投和人工重放。

如果新 5.x client 的传递依赖、endpoint、认证或 broker 兼容性失败，再采用 11.5 节的 Go/Java/Node.js sidecar 方案；不应退回旧 ctypes client，除非明确接受 native ABI 风险。

### 11.4 替代方案的官方事实与边界

- Apache 官方 Go client 说明其实现基于 `rocketmq-apis`、gRPC-go 和 Protocol Buffers。[RMQ18]
- Apache 官方 Java client 说明其 5.x client 采用面向计算/存储分离架构的访问方式，运行时需要 Java 8+、构建需要 Java 11+，并要求部署 NameServer、Broker 和 Proxy。[RMQ19]
- Apache 官方 Node.js client 要求 Node.js 16.19.0 作为最低版本，推荐 Node.js `>=18.17.0`，并同样要求 NameServer、Broker 和 Proxy；官方示例使用 `async/await`，包名为 `rocketmq-client-nodejs`。[RMQ20]
- Apache Pulsar 官方 Python 文档说明 Python client 可创建 producer、consumer 和 reader；PyPI 官方元数据截至调研日提供了 CPython 3.12 的多平台 wheel。[RMQ21][RMQ22]

### 11.5 本项目的替代路线建议

1. **默认路线：直接使用 `rocketmq-python-client` 5.1.1。** 它消除了旧 `librocketmq` 动态库与 Python ctypes 的主要 ABI 风险，保留单一 Python worker 和 RocketMQ 5.x 的消息语义。仍必须通过传递依赖、目标镜像、Proxy/gRPC endpoint、认证/TLS 和真实 broker 行为门禁。
2. **第一兜底：Go sidecar。** 将 RocketMQ producer/consumer 放进独立的 Go bridge service，Python worker 只通过项目自定义的内部 HTTP/gRPC contract 发送和接收标准事件 envelope。该 bridge contract 不是 Apache 提供的现成产品能力；它会增加一个进程、部署单元、观测面和协议维护责任，但可以把 RocketMQ client 的语言/runtime 风险从 Python 3.12 进程隔离出去。
3. **第二兜底：Java sidecar。** 当团队已有 Java 运维能力、需要优先采用 Java 生态或对 Java client 的生产验证更充分时使用。它的主要代价是 JVM 镜像、内存、启动时间和 bridge 运维复杂度。
4. **第三选择：Node.js sidecar。** 前端已经使用 Node.js 并不等于消息 bridge 应自动放入前端进程；如采用该路线，应使用独立 Node.js 服务和官方推荐版本，避免把消息消费生命周期耦合到 Vite/TanStack Start 开发或 Web 进程。
5. **只有在决定更换消息系统时才考虑 Pulsar。** Pulsar Python client 对 CPython 3.12 有官方 PyPI wheel，但这不是 RocketMQ client 的替换包；需要重新评估 broker 部署、topic/subscription 语义、重试/DLQ、事务、监控、备份恢复和迁移计划。不能把“有 3.12 wheel”作为切换 broker 的充分理由。

Go、Java、Node.js sidecar 都仍然需要 RocketMQ 5.x 的 Proxy/gRPC endpoint；它们只替代 Python 进程中的 client，不替代 RocketMQ broker 协议或业务幂等设计。以上优先级属于本项目设计建议，语言 client 的能力和运行时前提属于 Apache 官方事实。[RMQ1][RMQ18][RMQ19][RMQ20][RMQ21][RMQ22]

## 12. 跨技术栈的可靠性设计

下面是本项目设计建议；其中的底层语义分别来自 PostgreSQL 事务、Redis 原子操作和 RocketMQ 重试文档，但组合方式不是任何单一官方产品的强制架构。

### 12.1 事务边界

| 边界 | 推荐做法 | 明确不做 |
| --- | --- | --- |
| PostgreSQL | 一个业务状态转换使用一个短 `AsyncSession` 事务；依赖唯一约束、FK、check 和状态条件更新 | 在事务中等待外部 API、MinerU、Milvus 或 RocketMQ 长时间返回 |
| Redis | 单命令、事务 pipeline、WATCH 或 Lua 完成同一 Redis 数据集内的原子转换 | 把 Redis transaction 当作 PostgreSQL + Redis 的分布式事务 |
| RocketMQ | 使用 broker 的消费重试、DLQ；事务消息只解决其支持的本地事务协调场景 | 把 broker ack 当作数据库提交的证明，或承诺跨存储 exactly-once |
| 外部 API | 使用有界 timeout、状态记录和可重入 job；结果落 PostgreSQL/对象存储后再推进状态 | 把外部 API 调用包在数据库锁和长事务内 |

### 12.2 重试分类

- **连接/网络瞬态错误**：可有限次数、指数 backoff、随机抖动重试；每次重试必须重新确认超时预算。
- **唯一约束冲突**：通常是幂等成功或业务冲突，不应无条件重试。
- **事务失败**：必须完整 rollback，再重启整个事务单元；不能在 aborted PostgreSQL transaction 中继续发 SQL。[PG2]
- **超时但结果未知**：按“可能成功”处理，先查业务状态/幂等记录，再决定是否重发；RocketMQ 官方明确警告 producer 重试可能产生重复消息。[RMQ3]
- **不可恢复业务错误**：不做无穷重试，写入失败状态并进入人工处理或 DLQ。
- **Redis 重试**：只把官方 `Retry` 配置用于明确的连接/服务异常；对递增计数、锁、任务 claim 等副作用操作先证明重复执行安全。[RD4]

### 12.3 幂等模型

建议所有异步业务遵循以下状态链：

```text
接收 event_id
    ↓
PostgreSQL 唯一键/状态条件检查
    ↓
已完成：返回幂等成功
处理中：按租约/版本决定等待、重试或接管
未处理：写入处理中并提交
    ↓
执行外部副作用
    ↓
短事务写入完成/失败及结果引用
    ↓
提交消费成功；失败则按策略重试或进入 DLQ
```

这是本项目设计建议。关键约束是：

- `event_id`、文档版本、任务阶段等业务键在 PostgreSQL 中有唯一约束；
- 状态转换带版本号或条件谓词，避免旧重试覆盖新状态；
- 处理结果可重复读取，外部副作用使用幂等 API、稳定对象 key 或阶段记录；
- Redis 只做短期 lease/cache/dedup，租约失效后由 PostgreSQL 状态决定是否可接管；
- RocketMQ message id、offset 和重试次数用于追踪，不单独作为业务唯一性证明。

## 13. 测试与质量门禁

### 13.1 官方事实

- FastAPI 官方使用 `TestClient` 测试 HTTP 应用，使用 `dependency_overrides` 替换依赖；异步测试使用 `pytest.mark.anyio` 与异步 HTTP client。[FA5][FA6]
- Python 标准库提供 `unittest`，`asyncio` 文档和测试工具支持异步任务的测试；Python 3.12 运行时本身不规定项目必须使用哪一个第三方测试框架。[PY3][PY10]
- Alembic 官方提供 `alembic check`，可在 CI 中发现模型变化尚未生成迁移的问题。[AL3]
- RocketMQ 官方消费 API以回调返回消费成功/稍后重试为核心，官方 broker 文档定义了重试和 DLQ 行为；仅 mock 回调不能证明真实 broker 语义。[RMQ4][RMQ8]

### 13.2 本项目设计建议

每个 Python member 单独拥有 `tests/`，但测试层级含义统一：

| 测试层 | 覆盖内容 | 依赖 |
| --- | --- | --- |
| `unit` | `medical-core` 领域规则、状态机、Pydantic DTO、retry 分类、授权策略、纯 application service | 不连接外部服务 |
| `integration` | SQLAlchemy session/事务/约束、Redis pool/TTL/Lua/WATCH、Milvus adapter、外部 API adapter | 测试 Compose 或临时服务 |
| `contract` | FastAPI OpenAPI/错误结构、事件 envelope、RocketMQ producer/consumer adapter、Aegra 接口边界 | 真实协议或官方 client |
| `migration` | Alembic 从基线升级到 head、模型与迁移一致性、关键索引/约束 | 临时 PostgreSQL |
| `failure` | 连接断开、事务回滚、Redis 重连、消息重复、消费异常、DLQ、进程重启 | 真实或高保真基础设施 |
| `e2e` | 登录、workspace 隔离、文档摄取、任务状态、聊天流与管理操作的跨服务路径 | `docker-compose.yml` test profile |

测试规范建议：

- 测试名使用 `test_<behavior>_<condition>_<expected_result>` 或同等清晰命名；测试正文按 Arrange/Act/Assert 组织，这是项目约定，不是某个上游工具的强制格式。
- 不在并发测试中共享 `AsyncSession`、Redis Pipeline 或 PubSub 对象；每个并发参与者拥有自己的资源实例。[SA1][RD5]
- API 测试覆盖正常、认证失败、workspace 越权、Pydantic 错误、依赖不可用、超时和幂等重复请求。
- PostgreSQL 集成测试必须真正执行约束冲突、回滚、并发唯一键、隔离级别/锁等待和迁移，而不是只用 in-memory 数据库替代。
- Redis 集成测试覆盖 TTL、过期、重连、pipeline transaction、WATCH 冲突、Lua 原子性、Pub/Sub 取消订阅和 retry 边界。
- RocketMQ 集成测试覆盖 producer 超时后的重复消息、consumer 返回 `RECONSUME_LATER`、最大重试、DLQ、offset 恢复和事务 checker；测试完成后检查 producer/consumer、gRPC runtime 或 sidecar bridge 是否优雅关闭。
- 外部 API 使用 deterministic fake 或录制的合同响应；不让单元测试依赖真实医疗数据、真实模型答案或不受控的外部网络。
- 质量门槛至少分为提交级 unit/static、PR 级 contract/migration、合并/发布级 Compose integration/failure/e2e；覆盖率不能替代关键失败路径的显式测试。

## 14. 编码、注释、命名和异常规范

### 14.1 官方事实

- PEP 8 给出缩进、导入、空白、命名、注释、异常和代码布局建议；PEP 257 给出 docstring 约定。[PY5][PY6]
- Python 官方 logging 文档提供标准日志层级、logger、handler、formatter 和过滤机制；应用不应使用 `print` 作为生产观测机制。[PY11]

### 14.2 本项目设计建议

#### 命名

- 模块、包、函数、变量：`lower_snake_case`；类和异常：`CapWords`；常量：`UPPER_SNAKE_CASE`；私有成员使用单前导下划线。
- Pydantic/SQLAlchemy 字段使用业务统一词汇，不用同一含义的 `id`、`uuid`、`key` 混称；公共事件字段命名一旦发布不得随意改名。
- async 函数不额外添加无意义的 `_async` 后缀；是否异步由调用语义决定。阻塞版本和异步版本同时存在时，才使用清晰的后缀或模块边界区分。
- 测试函数以行为命名，避免 `test_utils_1` 这类不能说明失败含义的名称。

#### 注释与 docstring

- 公共 package、模块、类、端口和外部适配器写 docstring，说明职责、输入输出、异常、资源所有权和并发约束。
- 注释解释“为什么”——例如为什么不在事务内调用外部 API、为什么某个消息必须幂等、为什么使用某个隔离级别；不要逐行复述代码。
- 对 RocketMQ、Redis lease、PostgreSQL 状态转换等易误用边界，在端口或 handler 附近写出明确的不变量和失败语义。
- 不在注释、docstring、日志和测试 fixture 中写真实患者身份信息、访问令牌或外部服务密钥。
- 迁移文件的注释应说明数据迁移风险、锁风险和回滚限制；不能只写“auto generated”。

#### 类型与依赖

- 所有跨层端口、DTO、事件 envelope 和 repository 方法写类型标注；避免用 `Any` 隐藏边界不确定性。
- `medical-core` 不 import FastAPI、SQLAlchemy、Redis、RocketMQ 或 Milvus；反向依赖通过 protocol/port 和依赖注入完成。
- API 异常映射放在 FastAPI 边界；领域层抛出领域异常，基础设施层抛出可分类的 adapter 异常，应用层决定 retryable/non-retryable。
- 日志使用模块级 logger，统一携带 request id、trace id、workspace id、job id 和 event id；避免输出完整 prompt、文档正文、token 和连接字符串。

#### 异步与资源

- `async def` 中所有 I/O 都必须可 await 或明确隔离；禁止在事件循环中直接调用同步 RocketMQ、同步 HTTP client、阻塞文件扫描或 CPU 密集解析。
- 所有连接池、session、consumer、producer、PubSub 和 background task 都必须有创建者、所有者和关闭路径；在 lifespan/shutdown 中完成清理。
- 取消异常、超时和进程关闭必须保持资源可回收；不要吞掉 cancellation 并无限重试。

## 15. 生产配置与运维规范

### 15.1 官方事实

- FastAPI 官方生命周期文档提供 startup/shutdown 资源管理的 lifespan 入口。[FA3]
- SQLAlchemy 官方提供连接池失效检测、回收和 dispose 机制。[SA2]
- PostgreSQL 官方文档提供连接上限、TLS、查询/锁/空闲事务超时、备份和监控相关配置。[PG6][PG7][PG8][PG9]
- redis-py/Redis 官方文档提供异步关闭、连接池、ACL、TLS、持久化和复制语义。[RD2][RD3][RD6]
- RocketMQ 官方文档定义 producer send retry、consumer retry、offset、DLQ 和 transaction checker；这些状态需要进入运维指标和告警。[RMQ3][RMQ4][RMQ5][RMQ6]

### 15.2 本项目设计建议

#### 配置

- 配置在启动时 fail fast：缺少数据库 URL、Redis 凭据、RocketMQ 5.x Proxy/gRPC endpoint、认证信息或外部 API key 时进程明确失败，不以空字符串继续运行；若采用 sidecar，则由 bridge 进程单独校验其 RocketMQ endpoint 配置。
- 配置按环境注入，生产使用 secrets；所有连接 timeout、pool size、retry 次数、backoff、DLQ topic、最大消息大小和任务并发度都必须可审计。
- 不使用 `latest` 镜像或未锁定包版本；Compose、Python lockfile、`rocketmq-python-client` 及其传递依赖，或 sidecar 的 Go/Java/Node.js runtime 与 client 版本，以及 PostgreSQL/Redis/RocketMQ image tag 一起进入发布记录。

#### 生命周期与健康检查

- liveness 只回答进程是否还能工作；readiness 检查当前进程需要的 PostgreSQL、Redis、RocketMQ client/broker 和必要外部依赖，不把一次慢的下游请求拖成无限等待。
- 关闭顺序建议为：停止接收新请求/新消息，等待当前 handler 在上限内完成，提交/回滚数据库事务，停止 producer/consumer，关闭 Redis client 和 SQLAlchemy engine。
- 监控 SQLAlchemy pool checkout wait、连接失效、长事务、锁等待、迁移耗时；Redis command latency、连接错误、retry、内存/eviction、Pub/Sub 断开；RocketMQ send error、consumer retry、DLQ、lag、reconsume times，以及 Python gRPC runtime 或 sidecar bridge 的崩溃/重启。
- 日志必须关联 `event_id`/`job_id`/`message_id`，但不记录敏感正文；错误分类要能区分 retryable、permanent、duplicate 和 operator action required。

#### 数据恢复

- PostgreSQL 备份必须配合定期恢复演练，验证恢复后的 Alembic head、约束、索引和关键业务查询。
- Redis 若只保存缓存，可接受重建；若保存 session 或协调状态，必须明确 RDB/AOF、复制异步和 failover 丢失窗口，并测试应用在丢失/重连后的行为。
- RocketMQ DLQ 需要有查看、人工修复、重放和幂等校验流程；重放不能直接绕过业务状态机。

## 16. 版本与依赖治理清单

截至 2026-07-26 的官方页面观察：

| 技术 | 官方页面观察 | 治理建议 |
| --- | --- | --- |
| Python | 3.12 文档页面显示 3.12.13 | 固定 Python 3.12.x；升级 patch 后重跑 native/driver 测试 |
| uv | 官方文档为滚动文档，workspace/config 语义持续演进 | 固定 uv 版本，提交 `uv.lock`，CI 以 lockfile 驱动 |
| FastAPI | 官方文档为滚动文档，依赖 Starlette/Pydantic | 锁定 FastAPI、Starlette、Pydantic 兼容组合 |
| Pydantic | 使用 v2 文档和 v2 API | 锁定 `pydantic` 与 `pydantic-settings`，禁止新代码回到 v1 API |
| SQLAlchemy | 使用 2.0 async 文档 | 锁定 SQLAlchemy 2.0.x 与 async driver，回归隐式 I/O/事务/池 |
| Alembic | 当前页面显示 1.18.5 文档 | Alembic 与 SQLAlchemy 同步升级，执行 `alembic check` 与迁移回归 |
| PostgreSQL | `current` 页面显示 PostgreSQL 18.4；官方版本策略区分 major 与 minor 支持周期 | Compose 固定 major/minor，升级前验证扩展、迁移、备份恢复 |
| redis-py | 官方文档显示 8.0.0 | 锁定 client/server 组合，回归 async close、pool、retry、Pub/Sub |
| RocketMQ server | 官方 SDK 文档说明 gRPC SDK 需要 server `>=5.0`；官方 Quick Start 以 5.3.2 示例部署 Broker 与 Proxy | 固定 server/Proxy 版本，明确 gRPC endpoint、认证/TLS、重试和 DLQ 配置 |
| RocketMQ Python client | `rocketmq-python-client` PyPI 稳定版为 5.1.1，声明 `Requires-Python >=3.7` 并提供 `py3-none-any` wheel；旧 `rocketmq-client-python` 2.0.0 仍是 ctypes/native 路线 | 首选新 5.x client；将 Python 3.12、`grpcio`/Protobuf、Broker/Proxy 和真实消息语义验证设为发布门禁；失败时切换 Go/Java/Node.js sidecar |
| RocketMQ client sidecar | Apache 官方提供 5.x Go、Java、Node.js client；均不等于官方 bridge service | 仅在 Python client 门禁失败或有明确运行时治理理由时采用；bridge contract、部署和观测由本项目负责 |
| Apache Pulsar Python client | Apache 官方 Python 文档提供 producer/consumer/reader 能力；PyPI 提供 CPython 3.12 wheels | 只有在明确接受 broker、语义、运维和迁移变化时评估，不作为 RocketMQ client 的直接替代 |

所有升级都应同时检查：依赖解析、Docker 镜像、启动/关闭、迁移、API schema、事件 schema、连接池、重试/幂等和数据恢复。不要把“能安装”作为“能生产运行”的证明。

## 17. 官方一手来源

访问日期均为 2026-07-26。

### Python、PyPA 与编码规范

- [PY1] [Python 3.12 Documentation](https://docs.python.org/3.12/)
- [PY2] [What’s New In Python 3.12](https://docs.python.org/3.12/whatsnew/3.12.html)
- [PY3] [Python 3.12 `asyncio`](https://docs.python.org/3.12/library/asyncio.html)
- [PY4] [Python 3.12 `venv`](https://docs.python.org/3.12/library/venv.html)
- [PY5] [PEP 8 — Style Guide for Python Code](https://peps.python.org/pep-0008/)
- [PY6] [PEP 257 — Docstring Conventions](https://peps.python.org/pep-0257/)
- [PY7] [PyPA — Writing your `pyproject.toml`](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/)
- [PY8] [PyPA — `src` layout vs flat layout](https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/)
- [PY9] [Python 3.12 — `asyncio.to_thread`](https://docs.python.org/3.12/library/asyncio-task.html#asyncio.to_thread)
- [PY10] [Python 3.12 `unittest`](https://docs.python.org/3.12/library/unittest.html)
- [PY11] [Python 3.12 `logging`](https://docs.python.org/3.12/library/logging.html)

### uv

- [UV1] [uv — Using workspaces](https://docs.astral.sh/uv/concepts/projects/workspaces/)
- [UV2] [uv — Structure and files](https://docs.astral.sh/uv/concepts/projects/layout/)
- [UV3] [uv — Configuring projects](https://docs.astral.sh/uv/concepts/projects/config/)
- [UV4] [uv — Managing dependencies](https://docs.astral.sh/uv/concepts/projects/dependencies/)
- [UV5] [uv — Using uv in Docker](https://docs.astral.sh/uv/guides/integration/docker/)

### FastAPI

- [FA1] [FastAPI — Bigger Applications: Multiple Files](https://fastapi.tiangolo.com/tutorial/bigger-applications/)
- [FA2] [FastAPI — Concurrency and async/await](https://fastapi.tiangolo.com/async/)
- [FA3] [FastAPI — Lifespan Events](https://fastapi.tiangolo.com/advanced/events/)
- [FA4] [FastAPI — Settings and Environment Variables](https://fastapi.tiangolo.com/advanced/settings/)
- [FA5] [FastAPI — Testing](https://fastapi.tiangolo.com/tutorial/testing/)
- [FA6] [FastAPI — Async Tests](https://fastapi.tiangolo.com/advanced/async-tests/)
- [FA7] [FastAPI — Dependencies with `yield`](https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-with-yield/)

### Pydantic v2

- [PD1] [Pydantic — Models](https://docs.pydantic.dev/latest/concepts/models/)
- [PD2] [Pydantic Settings — Settings Management](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
- [PD3] [Pydantic — Validators](https://docs.pydantic.dev/latest/concepts/validators/)
- [PD4] [Pydantic — Strict Mode](https://docs.pydantic.dev/latest/concepts/strict_mode/)
- [PD5] [Pydantic — Migration Guide](https://docs.pydantic.dev/latest/migration/)

### SQLAlchemy 2 与 Alembic

- [SA1] [SQLAlchemy 2.0 — Asynchronous I/O](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
- [SA2] [SQLAlchemy 2.0 — Connection Pooling](https://docs.sqlalchemy.org/en/20/core/pooling.html)
- [AL1] [Alembic — Using asyncio with Alembic](https://alembic.sqlalchemy.org/en/latest/cookbook.html#using-asyncio-with-alembic)
- [AL2] [Alembic — Auto Generating Migrations](https://alembic.sqlalchemy.org/en/latest/autogenerate.html)
- [AL3] [Alembic — Tutorial and command reference](https://alembic.sqlalchemy.org/en/latest/tutorial.html)

### PostgreSQL

- [PG1] [PostgreSQL — Current Documentation](https://www.postgresql.org/docs/current/)
- [PG2] [PostgreSQL — Transactions](https://www.postgresql.org/docs/current/tutorial-transactions.html)
- [PG3] [PostgreSQL — Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html)
- [PG4] [PostgreSQL — Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html)
- [PG5] [PostgreSQL — Indexes](https://www.postgresql.org/docs/current/indexes.html)
- [PG6] [PostgreSQL — Connections and Authentication](https://www.postgresql.org/docs/current/runtime-config-connection.html)
- [PG7] [PostgreSQL — Client Connection Defaults](https://www.postgresql.org/docs/current/runtime-config-client.html)
- [PG8] [PostgreSQL — Backup and Restore](https://www.postgresql.org/docs/current/backup.html)
- [PG9] [PostgreSQL — Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring.html)
- [PG10] [PostgreSQL — Versioning Policy](https://www.postgresql.org/support/versioning/)

### Redis 与 redis-py

- [RD1] [redis-py 8.0.0 Documentation](https://redis.readthedocs.io/en/stable/)
- [RD2] [redis-py — Asyncio Examples](https://redis.readthedocs.io/en/stable/examples/asyncio_examples.html)
- [RD3] [redis-py — Connecting to Redis](https://redis.readthedocs.io/en/stable/connections.html)
- [RD4] [redis-py — Retry Helpers](https://redis.readthedocs.io/en/stable/retry.html)
- [RD5] [redis-py — Advanced Features: Pipelines, Transactions and Pub/Sub](https://redis.readthedocs.io/en/stable/advanced_features.html)
- [RD6] [Redis — ACL](https://redis.io/docs/latest/operate/oss_and_stack/management/security/acl/)、[TLS](https://redis.io/docs/latest/operate/oss_and_stack/management/security/encryption/)、[Persistence](https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/)、[Replication](https://redis.io/docs/latest/operate/oss_and_stack/management/replication/)

### Apache RocketMQ 与官方 Python client

- [RMQ1] [Apache RocketMQ — Client SDK Overview](https://rocketmq.apache.org/docs/sdk/01overview)
- [RMQ2] [Apache RocketMQ — Normal Message](https://rocketmq.apache.org/docs/featureBehavior/01normalmessage)
- [RMQ3] [Apache RocketMQ — Sending Retry and Throttling Policy](https://rocketmq.apache.org/docs/featureBehavior/05sendretrypolicy)
- [RMQ4] [Apache RocketMQ — Consumption Retry](https://rocketmq.apache.org/docs/featureBehavior/10consumerretrypolicy)
- [RMQ5] [Apache RocketMQ — Consumer Progress and Load Balancing](https://rocketmq.apache.org/docs/featureBehavior/09consumerprogress)、[Consumer Load Balance](https://rocketmq.apache.org/docs/featureBehavior/08consumerloadbalance)
- [RMQ6] [Apache RocketMQ — Transaction Message](https://rocketmq.apache.org/docs/featureBehavior/04transactionmessage)
- [RMQ7] [Apache `rocketmq-client-python` README](https://github.com/apache/rocketmq-client-python/blob/master/README.md)
- [RMQ8] [Apache `rocketmq-client-python` official source — `rocketmq/client.py` and `rocketmq/ffi.py`](https://github.com/apache/rocketmq-client-python/tree/master/rocketmq)
- [RMQ9] [PyPI official metadata — `rocketmq-client-python`](https://pypi.org/project/rocketmq-client-python/)
- [RMQ10] [Apache `rocketmq-client-python` official `setup.py`](https://github.com/apache/rocketmq-client-python/blob/master/setup.py)
- [RMQ11] [Apache `rocketmq-clients` — RocketMQ 5.x client collection, gRPC/Protobuf architecture and feature matrix](https://github.com/apache/rocketmq-clients/blob/master/README.md)
- [RMQ12] [Apache `rocketmq-clients` — official Python client `setup.py`](https://github.com/apache/rocketmq-clients/blob/master/python/setup.py)
- [RMQ13] [PyPI official metadata — `rocketmq-python-client`](https://pypi.org/project/rocketmq-python-client/)
- [RMQ14] [Apache `rocketmq-clients` — official Python examples](https://github.com/apache/rocketmq-clients/tree/master/python/example)
- [RMQ15] [Apache `rocketmq-clients` — Python `ClientConfiguration`](https://github.com/apache/rocketmq-clients/blob/master/python/rocketmq/v5/client/client_configuration.py)
- [RMQ16] [Apache `rocketmq-clients` — Python `Producer`](https://github.com/apache/rocketmq-clients/blob/master/python/rocketmq/v5/producer/producer.py)
- [RMQ17] [Apache RocketMQ — Quick Start, Broker and Proxy deployment](https://rocketmq.apache.org/docs/quickStart/01quickstart/)
- [RMQ18] [Apache `rocketmq-clients` — official Go client](https://github.com/apache/rocketmq-clients/blob/master/golang/README.md)
- [RMQ19] [Apache `rocketmq-clients` — official Java client](https://github.com/apache/rocketmq-clients/blob/master/java/README.md)
- [RMQ20] [Apache `rocketmq-clients` — official Node.js client](https://github.com/apache/rocketmq-clients/blob/master/nodejs/README.md)
- [RMQ21] [Apache Pulsar — official Python client documentation](https://pulsar.apache.org/docs/next/client-libraries-python/)
- [RMQ22] [PyPI official metadata — `pulsar-client`](https://pypi.org/project/pulsar-client/)

## 18. 研究结论边界

本文没有修改项目实现、`docs/spec.md`、`docs/architecture.md`、任何 ADR 或 Wayfinder 票据。本文仅提供官方资料归纳与本项目后续实现时应采用的工程建议。

关于 RocketMQ，当前结论分为两层：旧 `rocketmq-client-python` 的 `librocketmq`/ctypes native ABI 风险仍然存在，但它不是本项目推荐路线；首选的 `rocketmq-python-client` 5.1.1 已转为官方 5.x gRPC/Protobuf client，但 Python 3.12、`grpcio`/Protobuf、目标镜像、Proxy/gRPC endpoint 和 broker 消息语义仍须在实现前通过 compatibility spike。若该门禁失败，使用官方 Go/Java/Node.js client 实现独立 sidecar，并把 Python↔sidecar contract 作为本项目自己的可测试边界。Pulsar 仅是有意更换 broker 时的迁移候选，不是无缝替换。
