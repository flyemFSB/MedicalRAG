# 版本兼容性、OpenAI-compatible 边界与 RAGAS 迁移决策

## 研究元数据

- 研究日期：2026-07-26。
- 目标：核对已选技术栈的交叉兼容性，确定可锁定的实现基线，明确 OpenAI-compatible 的适用范围，并决定 Ragent 评测能力与 RAGAS 的迁移边界。
- 文档性质：实现前研究与决策依据，不包含应用实现代码。
- 版本口径：版本号来自项目官方文档、官方 GitHub、NPM registry 或 PyPI 官方元数据；“兼容”分为依赖解析/导入兼容、协议/服务兼容和生产就绪三个层级，不能混为一谈。

> **计划变更（2026-08-01）：** 本文是历史调研快照。按 [ADR 0063](../adr/0063-arq-replaces-rocketmq-as-the-durable-job-queue.md)，RocketMQ Python client 5.1.1 已从基线移除，消息总线改为 arq；按 [ADR 0064](../adr/0064-uv-manages-python-314-runtime.md)，Python 基线从 3.12.13 提高到 3.14，需在 3.14 上重新验证依赖解析与导入。正文中的兼容性结论以此为边界解释。

## 结论先行

1. **TypeScript 6.0.3 是当前前端基线**：它落在 `typescript-eslint` 8.65.0 的 `>=4.8.4 <6.1.0` peer 范围内；TypeScript 7.0.2 仍不兼容该 lint 基线。TS 6 仍须通过真实的 TanStack Start SSR、Vite、Vitest 和生产构建验证。
2. **推荐的前端兼容组**：Node.js 24.18.x、pnpm 11.17.x、React 19.2.x、Vite 8.1.x、TanStack Start 1.168.x、TypeScript 6.0.3、ESLint 10.8.x、typescript-eslint 8.65.x、Vitest 4.1.x、Playwright 1.62.x、`@assistant-ui/react-langchain` 0.0.20、`@langchain/react` 1.0.29 与其固定的 `@langchain/langgraph-sdk` 1.9.28。该组合走官方 v2-native `useStreamRuntime`，不直接拼装 Client/Run API。
3. **推荐的 Python 基线可共同解析并导入**：Python 3.12.13、uv 0.11.x、Aegra API/CLI 0.9.24、FastAPI 0.140.0、Pydantic 2.13.4、SQLAlchemy 2.0.51、Alembic 1.18.5、redis-py 8.0.1、PyMilvus 2.6.17、RocketMQ Python client 5.1.1。临时 Python 3.12 环境已经完成依赖解析和关键包导入验证。
4. **Milvus 不采用 3.0-beta 作为首个生产基线**：虽然当前文档和 registry 已出现 Milvus 3.0-beta/SDK 3.0.0，但本项目应先锁定 Milvus 2.6.x 稳定线，例如 `milvusdb/milvus:v2.6.21` + `pymilvus==2.6.17`；3.0 仅作为独立 Spike/升级路线。
5. **RocketMQ 采用新 5.x gRPC Python client，不采用旧 ctypes client**：`rocketmq-python-client==5.1.1` 与 RocketMQ server/proxy 5.5.x 的协议方向兼容；必须以 Proxy/gRPC、事务、重试、DLQ 和重复消费合同测试作为发布门禁。
6. **OpenAI-compatible 只统一生成和 Embedding 的上游协议**：生成优先支持 Responses API，通用供应商默认保留 Chat Completions fallback；Embedding 使用 `/v1/embeddings`。Reranker 与 MinerU 不伪装成 OpenAI API，使用各自的 provider port 和官方接口。
7. **RAGAS 应迁移，但只能作为隔离的离线评测能力**：Ragent 没有嵌入 Python `ragas`，而是提供 `GET /rag/eval` 检索/意图评测契约。MedicalRAG 应在不迁移 MCP 分支字段的前提下保留其可观察检索/意图行为，在独立 `apps/evaluation`/eval profile 中使用 RAGAS；生产 API、Agent、Worker 不依赖 RAGAS。

## 1. 版本兼容矩阵

### 1.1 Python、Agent 与数据访问

| 层 | 推荐锁定基线 | 官方约束/交叉结果 | 状态 |
|---|---|---|---|
| Python | 3.12.13（3.12.x） | Aegra 官方 workspace 要求 Python `>=3.12`；本项目明确使用 3.12 | 可锁定 |
| uv | 0.11.x，实施时锁定具体 patch | uv 本身是工具链，不进入业务运行时；使用 `uv.lock` 和 `uv sync --locked` | 可锁定 |
| Aegra | `aegra-api==0.9.24`、`aegra-cli==0.9.24` | 官方 package 要求 Python `>=3.12`；Aegra API 要求 FastAPI `>=0.110.1`、Pydantic `>=2.11.7`、SQLAlchemy `>=2.0`、Redis `>=5`、LangGraph `>=1.0.3` | 可锁定，但需 Aegra 服务合同测试 |
| FastAPI | 0.140.0 | Python `>=3.10`、Pydantic `>=2.9`、Starlette `>=0.46`；满足 Aegra API 下限 | 可锁定 |
| Pydantic | 2.13.4 | Aegra、FastAPI、pydantic-settings 的约束均兼容 | 可锁定 |
| SQLAlchemy | 2.0.51 | Aegra 要求 `>=2.0`；与 asyncpg 0.31.0、Alembic 1.18.5 兼容 | 可锁定 |
| Alembic | 1.18.5 | 要求 SQLAlchemy `>=1.4.23` | 可锁定 |
| PostgreSQL server | 18.4；不采用 19 beta | Aegra/SQLAlchemy/asyncpg 使用标准 PostgreSQL 协议和驱动；数据库迁移必须在目标版本上验证 | 可锁定，需迁移测试 |
| Redis server | 8.8.x | redis-py 8.0.1 要求 Python `>=3.10`；Aegra 只要求 Redis `>=5` | 可锁定，需会话/PubSub/锁测试 |
| redis-py | `redis[hiredis]==8.0.1` | 与 Aegra `redis[hiredis]>=5` 兼容；应用明确关闭 asyncio client | 可锁定 |
| LangGraph Python | 1.2.9 | Aegra API 仅设 `>=1.0.3`；当前版本与 `langgraph-checkpoint` 4.1.x、SDK 0.4.2 可解出 | 可锁定，需 Aegra runtime 测试 |
| LangGraph Python SDK | 0.4.2 | Aegra API 要求 `>=0.3.5` | 可锁定 |
| Uvicorn | 0.51.0 | Aegra API 要求 `>=0.35.0` | 可锁定 |
| SSE | `sse-starlette==3.4.6` | Aegra API 要求 `>=3.3.4,<4.0.0`；与 Starlette/FastAPI 组合可解出 | 可锁定 |

**交叉验证结果**：以下集合在 Python 3.12、Linux x86_64 目标平台下由 uv 成功解析，且关键包成功导入：

```text
aegra-api==0.9.24
aegra-cli==0.9.24
fastapi==0.140.0
pydantic==2.13.4
sqlalchemy==2.0.51
alembic==1.18.5
redis[hiredis]==8.0.1
asyncpg==0.31.0
pymilvus==2.6.17
rocketmq-python-client==5.1.1
langgraph==1.2.9
langgraph-checkpoint-postgres==3.1.0
langgraph-sdk==0.4.2
uvicorn==0.51.0
sse-starlette==3.4.6
httpx==0.28.1
```

该解析同时选择了 `grpcio==1.83.0`、`grpcio-tools==1.83.0` 和 `protobuf==7.35.1`，并通过了 `pymilvus`、`rocketmq`、`aegra_api`、FastAPI、Redis、SQLAlchemy 和 Pydantic 的导入测试。它证明的是 Python 依赖与 ABI 基线，不证明真实 RocketMQ/Milvus/Aegra 服务端行为。

### 1.2 RocketMQ

| 组件 | 推荐基线 | 结论 |
|---|---|---|
| Server/Proxy | Apache RocketMQ 5.5.0 | 新 gRPC SDK 的官方要求是 server `>=5.0`；5.5.x 满足协议世代要求 |
| Python client | `rocketmq-python-client==5.1.1` | Apache 5.x 多语言 client，基于 gRPC/Protobuf；不使用旧 `rocketmq-client-python` ctypes/librocketmq 路线 |
| 进程边界 | 仅 `apps/worker` 使用 client | Python client 的 producer API 不是 FastAPI 原生 coroutine；避免在请求 event loop 内阻塞发送 |
| 必测项 | Proxy endpoint、认证/TLS、normal/FIFO/delay/transaction、重试、DLQ、重复投递、重启恢复 | 未通过前不能宣称生产兼容 |

RocketMQ server 与 client 的“版本号相同”不是必要条件；关键是 5.x gRPC API、Proxy 和 feature matrix。client 版本必须锁定，不能追踪 `master` 或使用旧包的同名 import namespace。

### 1.3 Milvus、PostgreSQL 与对象存储

| 组件 | 推荐基线 | 结论 |
|---|---|---|
| Milvus server | `milvusdb/milvus:v2.6.21` | 2.6 稳定线，覆盖本项目需要的 dense、sparse/BM25、Hybrid Search |
| Python SDK | `pymilvus==2.6.17` | 与 Milvus 2.6 minor line 对齐；Python 3.12 可安装并导入 |
| Milvus 3.0 | 仅 Spike | 当前官方 release note 标为 `3.0-beta`，SDK 3.0.0；不作为首版生产基线 |
| etcd | Milvus 官方 v2.6.21 compose 中的 `quay.io/coreos/etcd:v3.5.25` | 首次实现优先沿用 Milvus 官方 compose 依赖版本 |
| MinIO | 首次 Milvus 集成优先沿用官方 compose 的 `RELEASE.2024-05-28T17-19-04Z`；共享对象存储升级单独验证 | S3-compatible 不是“任意 MinIO 版本无条件兼容”；应用对象与 Milvus bucket 必须隔离 |

Milvus 3.0-beta 和 PyMilvus 3.0.0 的出现不代表 3.0 已经是本项目最稳妥选择。医疗知识索引需要可回滚、可重建和稳定 schema；在 3.0 GA 与本项目 Hybrid/BM25 Spike 完成前，2.6 稳定线更合适。

### 1.4 Node、React 与前端工具链

| 层 | 推荐锁定基线 | 官方约束/交叉结果 | 状态 |
|---|---|---|---|
| Node.js | 24.18.x LTS | Vite 8 要求 `^20.19.0 || >=22.12.0`；TanStack Start 要求 `>=22.12.0`；pnpm 11 要求 `>=22.13`；Node 24 满足全部约束并有较长支持窗口 | 可锁定 |
| pnpm | 11.17.x | Node `>=22.13`；workspace/frozen lockfile 可用 | 可锁定 |
| React / React DOM | 19.2.8 | assistant-ui 与 TanStack Start 都接受 React 19；react-dom peer 与 React 版本对齐 | 可锁定 |
| Vite | 8.1.5 | Node、React、TanStack Start 组合满足；Vitest 4 接受 Vite 8 | 可锁定 |
| TanStack Start | `@tanstack/react-start==1.168.32` | 依赖/peer 需要 Vite `>=7`、React 18/19、Node `>=22.12`；Vite 8 满足 | 可锁定，但要做 SSR/streaming smoke test |
| TanStack Router | `@tanstack/react-router==1.170.18` | 由当前 Start 版本解析到的兼容线；不要手工漂移 router 内部包 | 可锁定 |
| TypeScript | **6.0.3** | `typescript-eslint==8.65.0` 的 peer 是 `>=4.8.4 <6.1.0`；因此 TypeScript 6.0.3 可进入当前 lint 基线，TypeScript 7.0.2 不能进入 | 可锁定，需真实构建验证 |
| ESLint | 10.8.0 | Node 24 满足官方 engine；flat config | 可锁定 |
| typescript-eslint | 8.65.0 | 与 ESLint 10 和 TypeScript 6.0.3 兼容；不与 TypeScript 7 兼容 | 可锁定 |
| Prettier | 3.9.6 | Node 24 满足 | 可锁定 |
| Vitest | 4.1.10 | peer 接受 Vite 8；Node 24 满足 | 可锁定 |
| Playwright | 1.62.0 | Node `>=20`；与 Node 24 兼容 | 可锁定 |
| assistant-ui | `@assistant-ui/react==0.14.28`、`@assistant-ui/react-langchain==0.0.20` | React 18/19；`useStreamRuntime` 官方包装 `@langchain/react` v1 的 v2-native `useStream`，不实现自定义 runtime/parser | 可锁定 |
| JS LangGraph SDK | `@langchain/langgraph-sdk==1.9.28`（由 `@langchain/react` 固定依赖） | 通过官方 `ThreadStream` 使用 v2 `/state`、`/stream/events`、`/commands`；业务代码不直接调用 legacy `runs.stream` | 可锁定 |

**关键修正**：TypeScript 6.0.3 满足当前 `typescript-eslint` 8.65.0 的 `<6.1.0` peer 上限，因此按用户决策锁定 TS 6。TypeScript 7.0.2 仍被该 peer 上限阻断。TS 6 不能仅凭 metadata 宣称生产可用，必须通过 `pnpm install --frozen-lockfile`、`tsc --build`、TanStack Start SSR/生产构建、Vite 构建、Vitest projects 和 assistant-ui + LangGraph SDK direct contract tests。

## 2. 推荐的版本锁定策略

1. 运行时大版本固定：Python 3.12、Node 24、PostgreSQL 18、Redis 8、Milvus 2.6、RocketMQ 5.5。
2. 应用包使用精确版本写入各 member 的 `pyproject.toml`/`package.json`，锁文件由 uv/pnpm 生成并在 CI 使用 locked/frozen 模式。
3. Docker 基础镜像和基础设施镜像使用可追溯 tag，生产发布再固定 digest；禁止 `latest`、`master-*` 和 beta 镜像进入生产。
4. Aegra、Python LangGraph、Python `langgraph-sdk`、TanStack Start、assistant-ui、JS LangGraph SDK 和前端 direct integration 组成升级组；升级其中一个时运行 SSR、Agent Protocol、SSE 重连、取消、assistant-ui rendering 和认证合同测试。
5. Milvus、PyMilvus、schema、dense model、BM25 analyzer、metric 和 rank fusion policy 组成索引升级组；任何字段/模型/Analyzer 改变都创建新的 embedding schema/index version。
6. RocketMQ server、Proxy、Python client 组成消息升级组；消息协议兼容不等于事务/重试/DLQ 语义兼容。

## 3. OpenAI-compatible 的最佳边界

### 3.1 需要统一的能力

#### 生成模型

定义应用自己的 `GenerationProvider`，不让 `medical-core` 依赖 OpenAI SDK 类型。适配器内部使用官方 `AsyncOpenAI` 或等价的受控 HTTP client，并配置供应商的 `base_url`、API key、timeout 和 headers。

- **OpenAI 原生/完整兼容供应商**：优先使用 `/v1/responses`，支持文本/图片输入、工具、结构化输出和流式事件。
- **通用 OpenAI-compatible 供应商**：默认使用 `/v1/chat/completions`，因为多数第三方服务对该契约支持更广；在 provider capability manifest 标记是否支持 Responses、JSON Schema、tool call、vision、streaming 和 cancellation。
- **不能假定所有参数都通用**：`reasoning`、`temperature`、`response_format`、`tools`、`modalities` 等必须按 capability allowlist 发送，unsupported 参数不能静默下发。

上游流事件先被转换成应用自己的 `GenerationStreamEvent`，再由 Aegra/LangGraph graph 转为 Agent Protocol v2 的 messages/content-block/lifecycle 数据。浏览器不直接消费 OpenAI chunk，也不持有 provider key；v2 事件由官方 `useStreamRuntime` 消费。

#### Embedding

定义 `EmbeddingProvider`，优先调用 `/v1/embeddings`。请求必须记录 model、dimension、encoding、batch size、provider version 和 embedding schema version；查询和文档必须使用同一 schema version。不要因为供应商都支持 OpenAI endpoint 就混用不同模型或不同归一化策略。

#### 错误、重试与观测

- 统一解析 HTTP status、provider request id、rate limit、Retry-After、timeout 和可重试错误。
- 非流式请求按 provider policy 做有界重试；流式已经输出 token 后不自动重放生成，避免重复内容。
- 记录 provider/model/capability/latency/token usage/cost metadata，但禁止记录 prompt、医疗上下文、密钥和 Cookie。
- provider adapter 负责 API 语义，model router 负责优先级、能力匹配、健康状态和熔断；不要把供应商选择写入业务 graph 节点。

### 3.2 不应强行 OpenAI-compatible 的能力

| 能力 | 推荐处理 | 原因 |
|---|---|---|
| Reranker | `RerankerProvider` 原生适配器；若供应商有 `/v1/rerank`，也只作为该 provider 的协议，不称为 OpenAI 标准 | OpenAI 官方 OpenAPI 当前包含 Responses、Chat Completions、Embeddings 等，但没有 Rerank endpoint |
| MinerU | 官方 MinerU API client，使用其任务提交、callback、轮询和下载契约 | 解析任务、文件上传 URL、结果 ZIP 和 callback 不是 OpenAI API 语义 |
| Aegra/assistant-ui | LangGraph Server/Agent Protocol 官方适配器 | 这是前端 agent runtime 协议，不应包装成 `/v1/chat/completions` |
| MedicalRAG 对外业务 API | FastAPI domain API + Aegra Agent Protocol | 医疗权限、证据、意图、引用和安全元数据需要领域契约，OpenAI Chat Completion 无法表达完整业务状态 |

### 3.3 是否有必要

**必要，但范围有限。**

- 对生成和 Embedding：必要。它能减少供应商切换、保留外部 API 选择，并复用官方 SDK 的 async、streaming、timeout 和错误模型。
- 对 Reranker/MinerU：不必要且容易误导。各自保留原生 adapter 更稳定。
- 对本系统公开接口：首版不必要。为了兼容 OpenAI 而把医疗 chat、证据、意图、引用和 Aegra stream 压缩成 Chat Completions，会丢失业务语义并制造第二套协议。

因此采用“**应用拥有端口，外部协议拥有适配器**”的方案，而不是让 OpenAI-compatible 成为全系统的领域模型。

## 4. Ragent 评测与 RAGAS 迁移决策

### 4.1 Ragent 实际情况

本地 Ragent 源码显示：

- 评测实现是 Java `EvalController`、`EvalResponse`、`EvalProperties`；没有 Python `ragas` 依赖。
- 实际 Controller 路由是 `GET /rag/eval`，执行 query rewrite、intent resolution 和 retrieval，返回 contexts、Chunk/doc IDs、intent leaf IDs、分支标志和 latency。
- 当前接口不返回最终 `response`，所以不能直接评估 Faithfulness、Response Relevancy、Factual Correctness 等答案指标。
- 注释提到的 `/rag/eval/sync` 和 `EvalRetrievalCaptureAspect` 在当前源码中未找到；迁移时以实际路由/行为为准，不复制失效注释。
- `application.yaml` 当前将 `app.eval.enabled` 配为 `true`，且该开关会影响幂等切面；目标系统必须默认关闭评测路由并隔离评测 profile。

### 4.2 是否迁移 RAGAS

**迁移评测能力，非迁移生产依赖。**

建议新增独立 `apps/evaluation`（独立 uv member/lock 或显式 eval extra），而不是把 `ragas` 放进 `apps/api`、`apps/agent` 或 `apps/worker`。该 runner：

1. 调用内部评测契约并校验 Ragent-parity 字段。
2. 保留 `retrievedContexts` 顺序、Chunk/doc 粒度、intent、branch 和 latency 的旁路记录。
3. 第一阶段只运行无 LLM 的 ID-based Context Precision/Recall、Recall@k、MRR/nDCG、intent Top-1、分支正确性、空召回率、重复率和 P95 latency。
4. 隔离的 answer profile 在获得脱敏 `response`、专家参考答案和证据后，才运行 RAGAS Faithfulness、Context Precision/Recall、Factual Correctness、Response Relevancy、Noise Sensitivity 等诊断指标。
5. 任何 RAGAS 分数都不能替代专家对诊断、处方、剂量、禁忌证、急症升级、拒答和引用完整性的审核。

本次研究核对的 RAGAS 版本是 0.4.3。评测环境必须锁定 RAGAS、judge LLM、embedding、prompt、temperature、数据集、索引、模型和阈值 manifest；RAGAS 的评测 API/实验接口升级时单独回归，不让生产 runtime 随之升级。

### 4.3 推荐 profile

| Profile | 内容 | 是否调用外部 LLM |
|---|---|---:|
| `eval-retrieval` | Ragent-compatible retrieval/intent contract、ID-based 指标、排名指标、延迟/分支检查；合成或批准脱敏数据 | 否 |
| `eval-answer` | 答案回放、证据绑定、RAGAS LLM 指标；隔离 provider、脱敏上下文和专家 reference | 是，受控 |
| `clinical-safety-review` | 规则检查、专家盲审、拒答/剂量/禁忌证/急症升级/时效性样本 | 可选，仅辅助 |

PR 只运行 `eval-retrieval`；nightly/release candidate 才运行受控 `eval-answer`；临床安全发布门禁由专家标签和确定性规则负责，不能由一个 RAGAS 总分负责。

## 5. 实现前仍必须完成的门禁

虽然版本依赖与 RAGAS 边界已经可以决策，但以下事项在实现阶段必须是硬门禁：

1. `pnpm install --frozen-lockfile`、TanStack Start SSR build、Vite production build、TypeScript 6.0.3 strict check、Vitest 和 Playwright smoke test。
2. Aegra 0.9.24 与 Postgres 18/Redis 8 的 thread/run/checkpoint、认证、SSE 重连、取消和多实例合同测试。
3. RocketMQ 5.5.0 Broker/Proxy 与 Python 5.1.1 的事务消息、重试、DLQ、重复投递和 graceful shutdown 测试。
4. Milvus 2.6.21 + PyMilvus 2.6.17 的 BM25 Full Text Search、dense+sparse Hybrid、filter、RRF/Weighted ranker、load/release 和 schema migration 测试。
5. OpenAI-compatible provider capability matrix：Responses、Chat Completions、Embedding、JSON Schema、vision、tool call、streaming、cancellation 和 provider error normalization。
6. RAGAS 只在独立 eval member 中锁定与升级；禁止生产依赖树隐式引入 `ragas`、judge model 或外部评测凭据。

## 官方/一手来源

### 版本与运行时

- [Node.js release index](https://nodejs.org/dist/index.json)
- [Vite package metadata](https://registry.npmjs.org/vite)
- [TanStack React Start package metadata](https://registry.npmjs.org/@tanstack%2freact-start)
- [TypeScript package metadata](https://registry.npmjs.org/typescript)
- [typescript-eslint package metadata](https://registry.npmjs.org/typescript-eslint)
- [Vitest package metadata](https://registry.npmjs.org/vitest)
- [Playwright package metadata](https://registry.npmjs.org/@playwright%2ftest)
- [assistant-ui LangChain runtime metadata](https://registry.npmjs.org/@assistant-ui%2freact-langchain)
- [LangChain React package metadata](https://registry.npmjs.org/@langchain%2freact)
- [Aegra official docs](https://docs.aegra.dev/llms.txt)
- [Aegra official repository workspace](https://github.com/aegra/aegra/blob/main/pyproject.toml)
- [Aegra API PyPI metadata](https://pypi.org/pypi/aegra-api/0.9.24/json)
- [FastAPI PyPI metadata](https://pypi.org/pypi/fastapi/0.140.0/json)
- [PyMilvus 2.6.17 metadata](https://pypi.org/pypi/pymilvus/2.6.17/json)
- [RocketMQ Python client metadata](https://pypi.org/pypi/rocketmq-python-client/5.1.1/json)
- [Milvus 2.6.21 official standalone compose](https://raw.githubusercontent.com/milvus-io/milvus/v2.6.21/deployments/docker/standalone/docker-compose.yml)
- [Milvus Hybrid Search](https://milvus.io/docs/multi-vector-search.md)
- [Milvus Full Text Search/BM25](https://milvus.io/docs/full-text-search.md)
- [Apache RocketMQ SDK overview](https://rocketmq.apache.org/docs/sdk/01overview)
- [Apache RocketMQ official Docker tags](https://hub.docker.com/r/apache/rocketmq/tags)

### OpenAI-compatible

- [OpenAI official OpenAPI specification](https://github.com/openai/openai-openapi/blob/master/openapi.yaml)
- [OpenAI Python SDK official README](https://github.com/openai/openai-python/blob/v2.48.0/README.md)

### Ragent 与 RAGAS

- Ragent `EvalController.java`: `D:\yzb\ragent\bootstrap\src\main\java\com\nageoffer\ai\ragent\rag\eval\EvalController.java`
- Ragent `EvalResponse.java`: `D:\yzb\ragent\bootstrap\src\main\java\com\nageoffer\ai\ragent\rag\eval\EvalResponse.java`
- Ragent `EvalProperties.java`: `D:\yzb\ragent\bootstrap\src\main\java\com\nageoffer\ai\ragent\rag\eval\EvalProperties.java`
- [RAGAS 评测迁移研究](ragas-migration-and-ragent-evaluation.md)
- [RAGAS official metrics](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/)
- [RAGAS v0.4.3 source](https://github.com/vibrantlabsai/ragas/tree/v0.4.3)
