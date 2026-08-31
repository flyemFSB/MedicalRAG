# LangChain、LangGraph、Ragent Agentic RAG 与 TypeScript 6 兼容性研究

## 研究元数据

- 研究日期：2026-07-26。
- 研究范围：Ragent 实际 Agentic RAG 源码；LangChain Python、LangGraph Python 官方文档与官方源码；Agent Protocol/Aegra；assistant-ui LangGraph adapter；TypeScript 6、typescript-eslint、Vite 8、Vitest 4、TanStack Start 的官方 NPM metadata。重点核对“Ragent 是否需要 LangGraph”“Python 运行时与 Python SDK 的边界”以及“前端仅使用必要的 LangGraph JS SDK、采用 TypeScript 6”的约束。
- 文档性质：独立官方文档研究与兼容性判断；本次不修改实现代码，但结论会同步到 spec、architecture 和 ADR。

> **计划变更（2026-08-01）：** 本文是历史调研快照。按 [ADR 0064](../adr/0064-uv-manages-python-314-runtime.md)，Python 运行时基线从 3.12 提高到 3.14；正文中与 Python 3.12 相关的结论已被该 ADR 取代，LangGraph/LangChain 的 3.14 兼容性需在实现前重新验证。
- 证据标记：
  - **官方事实**：由官方文档、官方仓库、官方 NPM/PyPI metadata 直接支持。
  - **代码观察**：由 `D:\yzb\ragent` 当前源码直接观察到。
  - **本项目建议**：结合上述事实与现有 `docs/research/compatibility-openai-and-evaluation.md` 的结论提出的工程建议，不是供应商承诺。

## 结论先行

1. **Ragent 当前不是一个必须使用 LangGraph 的开放式 Agent loop**。它是由 Spring 明确编排的 Agentic RAG pipeline：记忆加载、查询改写/拆分、意图分类、条件短路、多通道检索、MCP 工具调用、重排/上下文组装和 SSE 输出均由应用代码控制。
2. **只从“复刻 Ragent 一次请求行为”的角度看，LangChain Python 加普通 Python 编排足够**：模型、Prompt、结构化输出、工具、Retriever、串并行 runnable 都属于 LangChain Python 或应用层能力；Ragent 源码中没有观察到 LangGraph checkpoint、`interrupt`/resume 或 durable graph execution 契约。
3. **本项目的最终选型是 Python LangGraph + LangChain，而不是 LangChain-only**。原因不是“Agentic RAG”这个标签，而是项目已选定 Aegra/assistant-ui 的 LangGraph thread/run/state/stream 集成边界，并需要把固定 Ragent 流程作为可持久化、可流式、可恢复的 graph 运行。LangChain 官方将 LangChain 定位为 agent framework，将 LangGraph 定位为低层 orchestration framework/runtime；LangChain 的 `create_agent` 虽然建立在 LangGraph 之上，但本项目不应把它作为顶层自由 ReAct 循环。
4. **Aegra 使 Python LangGraph 成为所选服务端实现的直接依赖**：Aegra 官方 API 包依赖 Python `langgraph`、`langgraph-sdk` 和 Postgres checkpoint。该结论来自 Aegra 的实现，不是 Agent Protocol 或 assistant-ui 普遍强制 Python 的结果。
5. **本项目使用官方 v2-native React runtime**。assistant-ui 的 `@assistant-ui/react-langchain@0.0.20` 包装 `@langchain/react@1.0.29` 的 `useStream`；后者固定使用 `@langchain/langgraph-sdk@1.9.28` 的 `ThreadStream` 与内置 SSE transport，调用 Aegra 的 `/state`、`/stream/events`、`/commands`。业务代码不直接调用 `runs.stream`、不实现 SSE parser 或协议桥。Python `langgraph`/`langgraph-sdk`仍留在服务端和 Python 集成测试边界。
6. **TypeScript 6.0.3 与当前 `typescript-eslint` 8.65.0 的 peer metadata 是兼容的**：`typescript-eslint` 要求 `typescript >=4.8.4 <6.1.0`。因此现有兼容性文档中“必须退回 TypeScript 5.9.3”的理由只针对 TypeScript 7.0.2，不适用于 TypeScript 6.0.3。TS 6 仍需通过本项目真实的 Vite/Start 类型检查和插件构建验证。
7. **TypeScript 6.0.3 + Vite 8.1.5 + Vitest 4.1.10 + `@tanstack/react-start` 1.168.32 在 registry 元数据层面没有发现直接 peer/engine 冲突**：Vite 8 接受 Node `^20.19.0 || >=22.12.0`，Vitest 4 接受 Vite 6/7/8，TanStack Start 要求 Node `>=22.12.0`、Vite `>=7.0.0`。这证明依赖元数据兼容候选，不等于 SSR、插件、类型生成和生产构建已经验证。

## 1. Ragent 当前 Agentic RAG 的实际源码流程

### 1.1 请求入口与主编排

**代码观察**：`RAGChatController` 暴露 `GET /rag/v3/chat`，接收 `question`、可选 `conversationId` 和 `deepThinking`，返回 SSE；`RAGChatServiceImpl` 负责生成 conversation/task ID、排队、取消句柄和 trace 包装，然后把请求交给 `StreamChatPipeline`。

源码证据：

- `D:\yzb\ragent\bootstrap\src\main\java\com\nageoffer\ai\ragent\rag\controller\RAGChatController.java`
- `D:\yzb\ragent\bootstrap\src\main\java\com\nageoffer\ai\ragent\rag\service\impl\RAGChatServiceImpl.java`
- `D:\yzb\ragent\bootstrap\src\main\java\com\nageoffer\ai\ragent\rag\service\pipeline\StreamChatPipeline.java`

主流程在 `StreamChatPipeline.execute` 中是固定顺序：

```text
loadMemory
  -> rewriteQuery
  -> resolveIntents
  -> ambiguity guidance?  -- yes: emit prompt and stop
  -> system-only?         -- yes: direct LLM response and stop
  -> retrieve
  -> empty retrieval?      -- yes: emit no-document message and stop
  -> streamRagResponse
```

这是应用层的条件流水线，不是由图运行时在外部持久化的 state machine。

### 1.2 查询改写、拆分与意图分类

**代码观察**：`MultiQuestionRewriteService` 先做术语归一化；开启配置时调用 FAST tier LLM，将问题改写并拆分为 `sub_questions`，JSON 解析或模型调用失败时回退到归一化问题。会话模式最多把最近四条 user/assistant 消息带入改写请求。

随后 `IntentResolver` 为每个子问题并行执行意图分类，过滤低于阈值的候选并限制意图数量；总意图超限时先保证每个子问题保留最高分候选，再按分数分配剩余配额。这里的并行、限额和异常降级都是 Java `CompletableFuture` 与业务代码实现的。

源码证据：

- `D:\yzb\ragent\bootstrap\src\main\java\com\nageoffer\ai\ragent\rag\core\rewrite\MultiQuestionRewriteService.java`
- `D:\yzb\ragent\bootstrap\src\main\java\com\nageoffer\ai\ragent\rag\core\intent\IntentResolver.java`

### 1.3 条件分支、检索、MCP 与输出

**代码观察**：

- `IntentGuidanceService` 可因歧义直接向用户输出澄清提示并结束本次请求。
- 如果所有意图都是 `SYSTEM`，则跳过知识库检索，直接按系统 prompt 流式回答。
- 否则 `RetrievalEngine` 对每个子问题拆分 KB intents 与 MCP intents；KB 经过多通道检索，MCP 根据意图执行参数提取和工具调用。
- `MultiChannelRetrievalEngine` 并行调用启用的 search channels，再按 order 执行 post-processors。当前代码包含去重、融合/归因、metadata enrichment、rerank 等后处理扩展点；异常通常记录后跳过单个通道或处理器。
- 检索结果为空时返回固定的“未检索到相关文档”消息；有结果时先发 sources/grounding chunks，再构造 prompt，最后经 `LLMService.streamChat` 发送 SSE。

源码证据：

- `D:\yzb\ragent\bootstrap\src\main\java\com\nageoffer\ai\ragent\rag\core\retrieval\RetrievalEngine.java`
- `D:\yzb\ragent\bootstrap\src\main\java\com\nageoffer\ai\ragent\rag\core\retrieval\MultiChannelRetrievalEngine.java`
- `D:\yzb\ragent\bootstrap\src\main\java\com\nageoffer\ai\ragent\rag\service\pipeline\StreamChatPipeline.java`

因此，Ragent 的“Agentic”体现在 LLM 参与改写、分类、MCP 参数提取和回答，并不意味着它已经采用了 LangGraph 的 durable graph runtime。

### 1.4 评测接口的实际契约

**代码观察**：`EvalController` 在 `app.eval.enabled=true` 时暴露 `GET /rag/eval?question=...`，调用链是：

```text
rewriteWithSplit(question, empty history)
  -> intentResolver.resolve
  -> retrievalEngine.retrieve
  -> flatten/deduplicate chunks
  -> resolve chunk -> document business IDs
  -> return retrieval evidence
```

`EvalResponse` 返回 `retrievedDocIds`、`retrievedChunkIds`、`retrievedContexts`、chunk 对应的 document IDs、MCP/KB 分支标志、子问题、top-1 intent leaf IDs 和 latency；它**不返回最终 LLM response**。因此它适合 Recall/Precision、MRR/nDCG、意图 Top-1、分支和延迟评测，不足以单独评估 Faithfulness、Response Relevancy 或答案事实正确性。

源码证据：

- `D:\yzb\ragent\bootstrap\src\main\java\com\nageoffer\ai\ragent\rag\eval\EvalController.java`
- `D:\yzb\ragent\bootstrap\src\main\java\com\nageoffer\ai\ragent\rag\eval\EvalResponse.java`
- `D:\yzb\ragent\bootstrap\src\main\java\com\nageoffer\ai\ragent\rag\eval\EvalProperties.java`
- `D:\yzb\ragent\bootstrap\src\main\resources\application.yaml`（当前配置实际将 `app.eval.enabled` 设为 `true`）

## 2. LangChain 与 LangGraph 的职责边界

### 2.1 Python 官方事实

LangChain Python 官方“Frameworks, runtimes, and harnesses”文档明确区分：

| 层 | 官方职责 | 官方何时使用 |
|---|---|---|
| LangChain Python framework | 模型、工具、结构化内容、agent loop、middleware、provider integrations 等抽象 | 快速构建；需要标准模型/工具/agent loop；应用编排不复杂 |
| LangGraph Python runtime | 低层 orchestration；durable execution、streaming、HITL、persistence、低层控制 | 需要长运行、有状态、失败可恢复、确定性与 agentic 步骤混合、生产部署基础设施 |
| LangChain Python `create_agent` | 高层、可配置的 agent harness；官方说明其 agent 建立在 LangGraph 之上 | 需要标准 agent loop，不想直接维护图 API |

官方还明确说明：LangChain 构建在 LangGraph 之上，但使用 LangChain 不需要直接维护 LangGraph 图 API。这个事实需要区分两层含义：LangChain-only 可以指“只使用 LangChain 的公开高层接口”；它并不意味着 `create_agent` 的内部实现没有 LangGraph。对本项目而言，固定 Ragent pipeline 应显式使用 Python LangGraph `StateGraph`，以便表达阶段状态、条件短路、并行 worker 和服务端运行生命周期。

一手来源：

- [LangChain Python 官方产品分层与选择](https://docs.langchain.com/oss/python/concepts/products)
- [LangChain Python 官方 overview](https://docs.langchain.com/oss/python/langchain/overview)
- [LangChain Python 官方 agents](https://docs.langchain.com/oss/python/langchain/agents)
- [LangChain Python Runnable 参考](https://reference.langchain.com/python/langchain_core/runnables/)
- [LangChain Python RunnableSequence](https://reference.langchain.com/python/langchain_core/runnables/RunnableSequence/)
- [LangChain Python RunnableParallel](https://reference.langchain.com/python/langchain_core/runnables/RunnableParallel/)
- [LangGraph Python 官方 overview](https://docs.langchain.com/oss/python/langgraph/overview)
- [LangGraph Python 官方 workflows and agents](https://docs.langchain.com/oss/python/langgraph/workflows-agents)
- [LangGraph Python Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api)
- [LangGraph Python Functional API](https://docs.langchain.com/oss/python/langgraph/functional-api)

LangGraph Python 官方文档进一步说明：它可以混合 deterministic steps 和 LLM-driven agentic steps；Graph API/Functional API 可以表达条件路由、并行 worker、evaluator-optimizer loop 和 agent/tool loop。Persistence 文档把 checkpointer 定义为 thread 级短期状态，把 store 定义为跨 thread 的长期数据；Interrupts 文档要求 checkpointer 与 `thread_id`，才能在外部输入后恢复。Streaming 文档还提供 graph state、任务、checkpoint、LLM token 和自定义事件等流模式。

一手来源：

- [LangGraph Python persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
- [LangGraph Python interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)
- [LangGraph Python streaming](https://docs.langchain.com/oss/python/langgraph/streaming)
- [LangGraph Python application structure](https://docs.langchain.com/oss/python/langgraph/application-structure)

### 2.2 “仅 LangChain”与“LangGraph + LangChain”的证据化判断

| 判断维度 | 仅 LangChain API surface | LangGraph + LangChain |
|---|---|---|
| 当前 Ragent 的固定 Agentic RAG pipeline | 足够复刻业务行为：改写、结构化解析、意图分类、retriever、工具、prompt、Runnable 串并行 | 更适合作为目标项目运行时：显式状态、条件边、可观测节点和统一流生命周期；不是 Ragent 原实现的必需条件 |
| 多轮记忆 | LangChain 可由应用自行存储历史并注入 prompt | LangGraph checkpointer 提供 thread-scoped state/history，Server 可托管 persistence |
| SSE/token streaming | LangChain model streaming 可提供上游 token；应用自行定义 SSE | LangGraph 提供 graph/event/state/subgraph streaming，Server/SDK 提供统一 run/thread stream |
| 失败恢复/长运行 | 需要应用自行实现任务、重试、状态和恢复 | LangGraph durable execution 与 persistence 是直接匹配的运行时能力 |
| 人工审批/暂停后恢复 | 应用自行保存状态并设计 resume API | `interrupt()` + checkpointer + `thread_id` + `Command(resume)` 是官方直接支持的模式 |
| 分支/循环/并行图 | 可用普通程序控制流实现 | StateGraph/Functional API 将其建模为可观测、可持久化的 graph execution |
| assistant-ui + Aegra | 仅 LangChain 本身不提供 Aegra/Agent Protocol Server 契约 | LangGraph graph + Agent Protocol Server/SDK 是直接匹配的组合 |

**针对 Ragent 的结论**：如果目标只是保持当前 `/rag/v3/chat` 的行为——一次请求内完成改写、意图、检索、结构化槽位处理、回答和 SSE，服务端已有数据库会话记忆、队列和取消机制——没有官方证据表明必须把它改成 LangGraph。LangChain Python 或等价的模型/工具抽象足够；LangGraph 是运行时语义，不是“有检索就必须使用”的标记。Ragent 的 MCP 分支和参数提取不属于 MedicalRAG 目标。

**针对 MedicalRAG 的最终结论**：本项目保留 Aegra、assistant-ui LangGraph adapter、thread/run/checkpoint 和 Agent Protocol 风格 streaming 作为正式契约，因此采用 **Python LangGraph + LangChain**。LangChain Python 负责模型、Prompt、结构化输出、embedding/retriever、reranker/tool/provider integration；Python LangGraph `StateGraph` 负责 graph state、确定性条件分支、子问题 fan-out、checkpoint、interrupt/resume 和 graph streaming。不要使用 `create_agent` 作为顶层实现，因为它提供的是通用 agent loop，而 Ragent 的核心是受控 pipeline。

## 3. LangGraph Server、SDK、Agent Protocol、Aegra 与 assistant-ui 的边界

### 3.1 Agent Protocol 是协议，不是 Python 框架

**官方事实**：`langchain-ai/agent-protocol` README 将 Agent Protocol 定义为 framework-agnostic APIs，用于生产环境服务 LLM agents；核心概念是 runs、threads、store，并包含线程状态、后台 run、取消、等待、流式输出、重连和长期记忆等 endpoint。README 同时明确说 LangGraph Platform 实现的是该协议的 superset，并欢迎其他实现。

一手来源：

- [Agent Protocol 官方仓库 README](https://github.com/langchain-ai/agent-protocol/blob/main/README.md)
- [Agent Protocol OpenAPI JSON](https://langchain-ai.github.io/agent-protocol/openapi.json)
- [Agent Protocol API 文档](https://langchain-ai.github.io/agent-protocol/api.html)

因此 Agent Protocol 本身不规定 Python，也不规定必须使用 LangGraph；它规定的是服务端与客户端之间的资源和运行时契约。

### 3.2 Python LangGraph SDK 是客户端契约层

**官方 metadata**：Python `langgraph-sdk@0.4.2` 的 PyPI metadata 将其定位为官方 LangGraph API client。它负责从 Python 调用 server 的 assistants/threads/runs/state/stream 等 API；它不是图的编排运行时，图运行时仍由 Python `langgraph` 提供。

本项目的边界是：Aegra/agent 服务端使用 Python `langgraph` 与 Python `langgraph-sdk`；前端使用 assistant-ui 官方 `@assistant-ui/react-langchain/useStreamRuntime`，由 `@langchain/react` 内部通过 `@langchain/langgraph-sdk` 的 v2-native `ThreadStream` 连接 Aegra。业务代码不直接实现或拼装 SDK transport。

一手来源：

- [Python LangGraph SDK PyPI metadata](https://pypi.org/pypi/langgraph-sdk/0.4.2/json)
- [LangGraph CLI 官方文档](https://docs.langchain.com/langsmith/cli)

SDK 的存在不等于客户端必须运行 Python；在本项目中只是明确把 SDK 使用面收敛到 Python 服务端与契约测试，浏览器只消费 Aegra 的 HTTP/SSE 契约。

### 3.3 Aegra 的官方集成边界

**官方事实**：Aegra README 将其定位为 self-hosted LangSmith Deployments alternative，使用同一 LangGraph SDK 和 API，并称现有 LangGraph code 可不修改地运行。Aegra API 包 `0.9.24` 的官方 `pyproject.toml`/PyPI metadata 明确依赖：

```text
langgraph>=1.0.3
langgraph-sdk>=0.3.5
langgraph-checkpoint-postgres>=2.0.23
```

Aegra 文档还明确：其 thread 是持久化单位，状态在节点执行后自动保存；streaming 通过 SSE，支持 run-scoped legacy stream 与 Agent Protocol v2 的 thread-scoped stream；官方迁移文档声称 SDK 调用、thread state、streaming、HITL 的使用方式与 LangSmith Deployments 保持一致。

一手来源：

- [Aegra 官方仓库 README](https://github.com/aegra/aegra/blob/main/README.md)
- [Aegra API 官方 pyproject.toml](https://github.com/aegra/aegra/blob/main/libs/aegra-api/pyproject.toml)
- [Aegra API PyPI metadata 0.9.24](https://pypi.org/pypi/aegra-api/0.9.24/json)
- [Aegra threads/state guide](https://docs.aegra.dev/guides/threads-and-state)
- [Aegra streaming guide](https://docs.aegra.dev/guides/streaming)
- [Aegra migration guide](https://docs.aegra.dev/migration)

**边界结论**：

- 选择 Aegra server：Aegra 当前官方实现要求 Python 3.12+，并把 Python LangGraph 作为服务端依赖；此时 Python LangGraph 是 Aegra implementation 的必要条件。
- 选择 Agent Protocol：不因此必需 Python，也不因此必需 LangGraph；任何满足协议的服务端都可以实现 runs/threads/store/streaming 契约。
- 选择 LangGraph Server/Platform：需要提供 LangGraph API/Agent Server 所要求的 graph/server 配置；服务端实现的语言由具体部署产品决定，不应从 Agent Protocol 推导出“必须 Python”。

### 3.4 assistant-ui LangGraph adapter 的真实要求

**官方 package metadata**：`@assistant-ui/react-langchain@0.0.20` 是将 `@langchain/react` `useStream` 包装为 assistant-ui runtime 的 adapter，peer dependency 为：

```text
@langchain/react: ^1.0.2
react: ^18 || ^19
```

**官方仓库 README 与源码**：`@assistant-ui/react-langchain` 将 `@langchain/react` v1 `useStream` 包装为 assistant-ui runtime；`@langchain/react` 官方文档和源码明确将该 hook 定义为 v2-native，并由 `@langchain/langgraph-sdk` `ThreadStream` 调用 `/threads/{id}/stream/events` 与 `/threads/{id}/commands`。旧的 `@assistant-ui/react-langgraph`/`unstable_createLangGraphStream` 只调用 legacy `runs.stream`，不作为本项目路径。

**官方文档**：LangGraph runtime 页面要求 LangGraph API server、React 18/19，以及 graph state 中存在 `messages` key 和 LangChain-like messages；其架构说明 graph state 是 source of truth。

一手来源：

- [assistant-ui LangChain runtime NPM metadata 0.0.20](https://registry.npmjs.org/@assistant-ui%2freact-langchain/0.0.20)
- [assistant-ui LangChain runtime 官方 README](https://github.com/assistant-ui/assistant-ui/blob/main/packages/react-langchain/README.md)
- [assistant-ui LangChain runtime source](https://github.com/assistant-ui/assistant-ui/blob/main/packages/react-langchain/src/useStreamRuntime.ts)
- [assistant-ui LangChain runtime docs](https://www.assistant-ui.com/docs/runtimes/langchain)
- [LangChain React `useStream` 官方文档](https://github.com/langchain-ai/langgraphjs/blob/main/libs/sdk-react/docs/use-stream.md)
- [LangChain React v2 transports](https://github.com/langchain-ai/langgraphjs/blob/main/libs/sdk-react/docs/transports.md)

**边界结论**：assistant-ui 依赖的是 LangGraph/Agent Protocol server contract，而不是 Python import。Aegra 原生提供 v2 的 thread state、command 和 event stream 契约，因此不需要 Aegra 专用 server adapter、协议桥或浏览器 SSE parser。若接入普通 Java/Ragent 的自定义 `/rag/v3/chat` SSE，则不能由该 runtime 自动转换。Aegra 的 Python LangGraph 依赖来自 Aegra 服务端实现，而非 assistant-ui 本身。

## 4. TypeScript 6、typescript-eslint、Vite 8、Vitest 4、TanStack Start

以下判断是截至 2026-07-26 读取官方 NPM registry metadata 的结果；它们是 package metadata 兼容性，不替代本项目的安装、类型检查、SSR、生产构建和浏览器测试。

| 包 | 核对版本 | 官方 metadata | 判断 |
|---|---:|---|---|
| `typescript` | 6.0.3 | `engines.node >=14.17`；registry 同时显示 latest 为 7.0.2，6.0.3 是已发布的 6.x 版本 | 可作为 TS 6 候选；不要把 latest 7.0.2 当作 TS 6 |
| `typescript-eslint` | 8.65.0 | `engines.node ^18.18.0 || ^20.9.0 || >=21.1.0`；peer `typescript >=4.8.4 <6.1.0`；ESLint peer 支持 8/9/10 | 与 TS 6.0.3 peer-compatible；与 TS 7 不兼容 |
| `vite` | 8.1.5 | `engines.node ^20.19.0 || >=22.12.0` | Node 24 满足；自身 metadata 未声明 TypeScript peer 上限 |
| `vitest` | 4.1.10 | `engines.node ^20.0.0 || ^22.0.0 || >=24.0.0`；Vite peer `^6.0.0 || ^7.0.0 || ^8.0.0` | 与 Vite 8.1.5、Node 24 metadata-compatible |
| `@tanstack/react-start` | 1.168.32 | `engines.node >=22.12.0`；peer Vite `>=7.0.0`、React/React DOM 18/19 | 与 Vite 8、Node 24、React 19 metadata-compatible；未声明 TS peer 上限 |

一手来源：

- [TypeScript 6.0.3 NPM metadata](https://registry.npmjs.org/typescript/6.0.3)
- [TypeScript registry dist-tags](https://registry.npmjs.org/typescript)
- [typescript-eslint 8.65.0 metadata](https://registry.npmjs.org/typescript-eslint/8.65.0)
- [Vite 8.1.5 metadata](https://registry.npmjs.org/vite/8.1.5)
- [Vitest 4.1.10 metadata](https://registry.npmjs.org/vitest/4.1.10)
- [TanStack React Start 1.168.32 metadata](https://registry.npmjs.org/@tanstack%2freact-start/1.168.32)

### 4.1 对现有兼容性结论的修正

现有 `docs/research/compatibility-openai-and-evaluation.md` 的判断“TypeScript 7.0.2 与 typescript-eslint 8.65.0 冲突，因此建议 TypeScript 5.9.3”仍对 TS 7 场景成立；但它不能推出“TypeScript 6 不可用”。本次 metadata 核对后的更精确表述是：

> TypeScript 6.0.3 落在 `typescript-eslint@8.65.0` 的 `<6.1.0` peer 范围内；在 Node 24 + Vite 8 + Vitest 4 + TanStack Start 1.168.x 的包元数据层面可作为兼容候选。TypeScript 7.0.2 仍被当前 typescript-eslint peer 上限阻断。

**本项目建议**：将 TS 6.0.3 作为可验证候选基线，而不是直接宣称生产兼容。至少需要真实执行：

- `pnpm install --frozen-lockfile`；
- `tsc --noEmit` 与 strict 类型检查；
- TanStack Start SSR/dev/prod build；
- Vite 8 production build；
- Vitest 4 测试与 coverage/browser 集成；
- 关键 Vite plugin、React/RSC 类型生成和 assistant-ui adapter 的 smoke test。

## 5. 给 MedicalRAG 的选择建议

### 5.1 选择仅 LangChain API surface 的条件

适合以下边界：

- 目标是复刻 Ragent 当前固定 pipeline，而不是开放式长运行 agent；
- thread/history/checkpoint 由应用数据库或服务层自行管理；
- SSE 只需要业务定义的 token/source/grounding 事件；
- 没有跨请求人工审批、暂停后恢复、time travel 或 durable retry 需求；
- 不把 assistant-ui LangGraph adapter/Aegra Agent Protocol 作为正式集成契约。

这条路径的优点是与现有 Ragent 的显式编排更接近，LangGraph 不会被用来替代本来已经清晰的业务 pipeline。

### 5.2 选择 LangGraph + LangChain 的条件

适合以下边界：

- Aegra 是正式运行时；
- assistant-ui 需要 LangGraph thread/run/state/stream contract；
- 需要 durable execution、Postgres checkpoints、后台 run、断线重连和跨实例 stream；
- 需要 `interrupt`/resume 的医疗审核、工具批准、风险升级或人工确认；
- 需要把确定性检索、意图路由、结构化槽位提取、答案生成和 evaluator/retry loop 建模为可观测 graph；
- 需要服务端向 JS/Python SDK 暴露标准 Agent Protocol 数据，而不是只暴露自定义 SSE。

推荐职责分配：

| 组件 | MedicalRAG 中的建议职责 |
|---|---|
| LangChain | Chat model/embedding/tool/provider adapter、prompt、结构化输出、retriever/tool 原语 |
| LangGraph | graph state、节点/边、分支/循环、checkpoint、interrupt/resume、streaming 生命周期 |
| Aegra | self-hosted Agent Protocol/threads/runs/stream server、Postgres persistence、认证/worker/SSE 基础设施 |
| assistant-ui | React UI runtime；消费 LangGraph/Aegra server contract，不负责定义医疗领域证据模型 |
| MedicalRAG domain API | 权限、证据、引用、临床安全、审计和领域错误契约；不压缩成 OpenAI Chat Completions |

### 5.3 最终判断

**不是“Agentic RAG ⇒ 必须 Python LangGraph”。** Ragent 的一次请求流程用 LangChain API surface 就能复刻；它的 Agentic 特征来自 LLM 参与改写、意图判断、结构化槽位处理和回答，而不是来自某个图运行时。MedicalRAG 不迁移 MCP 工具参数提取。

但当前 MedicalRAG 的已确认产品边界包含 Aegra、assistant-ui 官方 LangGraph adapter、Thread/Run、checkpoint、可恢复流和独立 agent runtime。因此本项目最终采用 **Python LangGraph + LangChain**：LangGraph 负责运行时图和状态，LangChain 负责节点内部的模型/工具/结构化输出/检索原语。

更准确的因果关系是：

```text
Agentic RAG 的模型/工具/检索原语
    -> LangChain 足够

需要 durable graph runtime / checkpoint / interrupt / graph streaming
    -> LangGraph 合适

需要 Aegra 官方 server
    -> Aegra 服务端当前要求 Python LangGraph

需要 assistant-ui LangGraph adapter
    -> 需要 LangGraph API/Agent Protocol 契约；不单独要求 Python
```

对当前项目的明确执行结论是：使用 Python LangGraph Graph API（`StateGraph`），不要使用 LangChain `create_agent` 作为顶层；前端使用 `@assistant-ui/react-langchain` 的官方 `useStreamRuntime`，由 `@langchain/react` 与 `@langchain/langgraph-sdk` 的 v2-native ThreadStream 连接 Aegra。这样既保持 Ragent 的受控流程，又满足 Aegra Agent Protocol v2 契约，不需要自定义 runtime、SSE parser、事件桥或 Aegra adapter。

## 6. 最终实现边界

推荐图：

```text
START
  -> load_memory
  -> rewrite_and_split
  -> resolve_intents
  -> route
       | clarification -> END
       | system_answer -> END
       `-> fan_out_subquestions (Send)
             -> hybrid_retrieve
             -> rerank_and_fuse
             -> ground_and_build_sources
             -> generate_stream
             -> persist_trace
             -> END
```

- `StateGraph` 的 state 至少包含 `messages`、conversation/thread identifiers、subquestions、intent decisions、evidence、safety outcome、business run/Langfuse correlation metadata 和 terminal status；所有 reducer 都必须有明确的追加/覆盖语义。
- Ragent 的 ambiguity、system-only、empty-retrieval 和 prohibited-request 分支建模为显式条件边，不交给一个自由循环的 agent 自行决定。
- `Send` 只用于有界的子问题并行；候选合并、去重、外部 reranker、Evidence Fusion 和证据上限仍由应用策略控制。
- Milvus Hybrid Retrieval、外部 Reranker、MinerU 和 OpenAI-compatible model provider 通过应用-owned ports/adapters 接入；不为了使用 LangChain 而把领域权限、证据或安全策略塞进通用 retriever/agent abstraction。
- `apps/agent` 使用 Python `langgraph` 和 `langgraph-sdk`；`apps/web` 在单一 integration 模块中使用 `@assistant-ui/react-langchain/useStreamRuntime`，由 `@langchain/react` 内部使用 JS LangGraph SDK v2 transport。业务组件不得直接依赖 SDK。

## 一手来源索引

### LangChain/LangGraph

- [LangChain Python products and runtimes](https://docs.langchain.com/oss/python/concepts/products)
- [LangChain Python overview](https://docs.langchain.com/oss/python/langchain/overview)
- [LangChain Python agents](https://docs.langchain.com/oss/python/langchain/agents)
- [LangGraph Python overview](https://docs.langchain.com/oss/python/langgraph/overview)
- [LangGraph Python Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api)
- [LangGraph Python Functional API](https://docs.langchain.com/oss/python/langgraph/functional-api)
- [LangGraph Python workflows and agents](https://docs.langchain.com/oss/python/langgraph/workflows-agents)
- [LangGraph Python persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
- [LangGraph Python interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)
- [LangGraph Python streaming](https://docs.langchain.com/oss/python/langgraph/streaming)
- [LangChain Python Runnable 参考](https://reference.langchain.com/python/langchain_core/runnables/)
- [LangChain Python RunnableSequence](https://reference.langchain.com/python/langchain_core/runnables/RunnableSequence/)
- [LangChain Python RunnableParallel](https://reference.langchain.com/python/langchain_core/runnables/RunnableParallel/)
- [LangGraph CLI / server commands](https://docs.langchain.com/langsmith/cli)
- [LangGraph Python SDK metadata](https://pypi.org/pypi/langgraph-sdk/0.4.2/json)

### Agent Protocol、Aegra、assistant-ui

- [Agent Protocol official repository](https://github.com/langchain-ai/agent-protocol)
- [Agent Protocol OpenAPI spec](https://langchain-ai.github.io/agent-protocol/openapi.json)
- [Aegra official repository](https://github.com/aegra/aegra)
- [Aegra API pyproject.toml](https://github.com/aegra/aegra/blob/main/libs/aegra-api/pyproject.toml)
- [Aegra API PyPI metadata](https://pypi.org/pypi/aegra-api/0.9.24/json)
- [Aegra threads/state guide](https://docs.aegra.dev/guides/threads-and-state)
- [Aegra streaming guide](https://docs.aegra.dev/guides/streaming)
- [Aegra migration guide](https://docs.aegra.dev/migration)
- [assistant-ui LangChain runtime NPM metadata](https://registry.npmjs.org/@assistant-ui%2freact-langchain/0.0.20)
- [assistant-ui LangChain runtime README](https://github.com/assistant-ui/assistant-ui/blob/main/packages/react-langchain/README.md)
- [assistant-ui LangChain runtime docs](https://www.assistant-ui.com/docs/runtimes/langchain)
- [LangChain React v2-native `useStream`](https://github.com/langchain-ai/langgraphjs/blob/main/libs/sdk-react/docs/use-stream.md)

### TypeScript toolchain metadata

- [TypeScript 6.0.3](https://registry.npmjs.org/typescript/6.0.3)
- [TypeScript registry](https://registry.npmjs.org/typescript)
- [typescript-eslint 8.65.0](https://registry.npmjs.org/typescript-eslint/8.65.0)
- [Vite 8.1.5](https://registry.npmjs.org/vite/8.1.5)
- [Vitest 4.1.10](https://registry.npmjs.org/vitest/4.1.10)
- [TanStack React Start 1.168.32](https://registry.npmjs.org/@tanstack%2freact-start/1.168.32)
