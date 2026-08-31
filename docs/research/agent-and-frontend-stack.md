# Agent 与前端技术栈官方文档研究

- 研究日期：2026-07-27
- 研究范围：Aegra、LangGraph Server / SDK / Agent Protocol v2、assistant-ui LangChain React runtime、TanStack Start、React、Vite、Node.js、pnpm、TypeScript、ESLint、Prettier、Vitest、Playwright。
- 研究目的：为 MedicalRAG 的 agent 与前端实现提供只基于一手官方资料的技术边界、集成方式、编码规范和测试建议。
- 研究约束：本文只引用项目官方文档、官方 API 参考和官方源代码仓库；不修改实现代码、规格文档、架构文档、ADR 或 Wayfinder 票据。

> **计划变更（2026-08-01）：** 本文是历史调研快照。按 [ADR 0064](../adr/0064-uv-manages-python-314-runtime.md)，Aegra 的 Python 运行时基线从 3.12 提高到 3.14（uv 管理）；正文中“Python 3.12+”等表述应读作“Python 3.14”。

本文中每节都把内容分成两类：

- **官方事实**：可以直接在列出的官方资料中核对的行为、API、限制或版本信息。
- **本项目设计建议**：结合本项目已经确定的系统边界做出的选择，不把它表述成上游项目的要求。

## 1. 研究口径与总体结论

### 官方事实

- Aegra 将自己定位为自托管的 Agent Protocol server，用于运行 LangGraph agents，并提供持久化、流式输出和认证；它声明兼容 LangGraph SDK/API。
- LangGraph 官方服务文档把运行时资源抽象为 assistants、threads 和 runs：assistant 表示运行配置，thread 保存状态，run 表示一次执行。
- assistant-ui 的 LangGraph runtime 直接建立在 ExternalStoreRuntime 之上，要求 graph state 包含 messages，并把 graph state 作为消息展示的事实来源。
- TanStack Start 是建立在 TanStack Router 之上的全栈 React 框架，提供全文档 SSR、streaming、server functions、server routes、客户端/服务端构建和端到端类型安全。
- Vite 由开发服务器和生产构建两部分组成；当前官方文档说明生产构建使用 Rolldown。
- pnpm 原生支持 workspace/monorepo；workspace 必须有根目录的 pnpm-workspace.yaml。

### 本项目设计建议

本项目采用下列边界：

| 边界 | 负责内容 | 不负责内容 |
| --- | --- | --- |
| apps/web | TanStack Start、React、assistant-ui、浏览器路由、SSR 外壳、同源代理，以及官方 v2 runtime 的配置集成 | 直接持有 Aegra 密钥、直接访问数据库、实现第二套 agent runtime 或业务流协议 |
| Aegra 服务 | Agent graph、assistant、thread、run、checkpoint、恢复和 Agent Protocol/SSE | 业务领域 API、前端组件、Milvus 检索实现 |
| FastAPI 业务服务 | 系统身份、授权、业务 API、领域数据和管理接口 | 复制 Aegra 的 thread/run/checkpoint 运行时 |
| packages/contracts | 浏览器和服务端之间需要共享的 JSON-safe 类型/协议契约 | 数据库连接、Node-only/服务端密钥、React 状态 |
| apps/agent、apps/api | Python 运行时，使用 uv 管理 | 不纳入 pnpm 的 JavaScript 依赖图 |

本项目不创建 `packages/ui`。只有一个 Web 应用时，共享组件包没有第二个消费者；组件与可访问性约束直接放在 `apps/web/src/components` 和对应 feature 中。

建议的请求方向是：

浏览器 React UI → TanStack Start 同源 server route/代理 → Aegra Agent Protocol v2；业务资料和身份操作则通过 FastAPI 业务 API。Aegra 与 LangGraph-compatible runtime 在服务端契约层面可以配合，不需要 Aegra 专用 server adapter；但本项目选择 v2-native 的 `@assistant-ui/react-langchain`，不使用依赖 legacy `runs.stream` 的 `@assistant-ui/react-langgraph` helper。浏览器不直接连接 Aegra 的内部地址，也不解析自定义的业务 SSE wire format；官方 JS SDK 只在受控 agent integration 模块中使用。

## 2. Aegra

### 官方事实

- Aegra 官方文档将其定义为开源、自托管的 Agent Protocol server，用于运行 LangGraph agents；官方文档同时说明现有 graph code、LangGraph client libraries 和兼容的前端可以复用。
- Quickstart 文档要求 Python 3.12+，推荐使用 uv，并提供 Aegra CLI 开发启动方式。
- 默认配置文件是 aegra.json。配置解析顺序是：
  1. AEGRA_CONFIG 环境变量指定的路径；
  2. 当前工作目录下的 aegra.json；
  3. 作为兼容回退的 langgraph.json。
- graphs 配置支持已编译的静态 graph、启动时调用的零参数 factory，以及按请求接收 config 或 ServerRuntime 的 factory。
- ServerRuntime 可以提供请求/用户上下文、store 和资源生命周期；factory graph 可以按用户或请求构建不同的 graph 拓扑，异步 factory 以及返回异步上下文管理器的 factory 也在官方配置参考中列出。
- 未配置 auth 时，Aegra 运行在 no-auth 模式，官方文档描述为允许所有请求；配置 auth 后可以接入 JWT、OAuth、Firebase 或自定义认证处理器，并进行资源级访问控制。
- Aegra 可以通过 http.app 挂载自定义 FastAPI 应用，也可以在配置中设置 CORS 和自定义路由认证开关。
- Aegra 把 thread 作为持久化单位。官方 threads and state 文档覆盖 thread 创建、状态读取、checkpoint 历史、按 checkpoint 读取状态、更新状态和删除 thread；启用认证后，thread 默认按认证用户隔离。
- 官方 streaming 文档说明 Aegra 使用 Server-Sent Events；支持 values、updates、messages、messages-tuple、custom、events 和 debug 等 stream mode，并支持 background run、取消、断线恢复以及 Redis broker 下的多实例 SSE。
- Aegra 的普通 run stream 端点支持 Last-Event-ID 重连；后台运行可以先创建 run，再查询状态、等待完成或重新打开 stream。默认断开连接会取消 run，也可以请求断开后继续运行。
- Aegra 当前发布版本（研究时点为 `aegra-api 0.9.24`）同时提供 legacy `POST /threads/{thread_id}/runs/stream` 和 Agent Protocol v2 的 thread-scoped stream。Aegra v2 文档明确说明最新 LangGraph JS/Python SDK 与 React/Vue `useStream()` 使用 v2 端点；因此本项目采用 v2 主路径，不使用 legacy runs stream。
- 当前 JS SDK 的 `ThreadState` 类型以 `tasks[].interrupts` 表达待处理 interrupt；assistant-ui quickstart 也从 `state.tasks[0]?.interrupts` 加载它。Aegra 概念文档同时展示了顶层 `interrupts` 的概念字段，目标版本必须通过契约测试确认实际响应形状。
- Aegra 的 Agent Protocol v2 文档定义了 POST /threads/{thread_id}/commands 和 POST /threads/{thread_id}/stream/events。command 用于 run.start、input.respond 等操作；event stream 通过 channels 和 since 过滤/恢复，事件 envelope 包含 seq、event_id、method、params.data 和 namespace。
- Aegra 当前 Agent Protocol v2 文档明确说明 WebSocket transport 以及 agent.getTree、state.fork、subscription.* 等能力尚未实现。不能把 LangGraph 官方协议页面上的全部端点自动假定为 Aegra 已支持。
- Aegra feature support 文档将语义搜索描述为基于 pgvector 的能力；这只是 Aegra 自带 semantic store 的实现，不等于本项目必须使用 pgvector。
- Aegra 官方 feature matrix 将 Agent Protocol-compatible frontend 标记为 Supported，同时将若干其他协议/扩展能力列为 Coming soon 或 Not yet planned。

### 本项目设计建议

- Aegra 作为独立运行时服务部署。前端、FastAPI 和 Aegra 之间以 HTTP/Agent Protocol 边界集成，不把 Aegra graph 代码嵌入 TanStack Start。
- 生产配置优先使用 aegra.json；只有为兼容旧工具或迁移时才依赖 langgraph.json 回退。Aegra 配置中的 graph 映射、auth、HTTP 和运行参数由 agent 服务自己拥有。
- 只使用本系统既有的身份验证体系：浏览器继续使用系统会话/身份上下文，Start 的服务端代理将必要的身份信息传递给 Aegra 的自定义 auth handler。不要启用 Aegra 的 no-auth 作为生产默认，也不要让浏览器暴露 Aegra API key。
- 业务 FastAPI 与 Aegra 可以在部署拓扑上同属一个 compose 环境，但职责保持分离。Aegra 的 custom FastAPI app 能力不应被用来把所有领域 API 搬入 Aegra。
- Aegra 只承担 agent 的 thread/run/checkpoint 和执行流；本项目的 Milvus hybrid retrieval 仍由业务/检索服务负责，不采用 Aegra pgvector semantic store 作为 Milvus 的替代。
- 首版前端使用 assistant-ui 官方 `@assistant-ui/react-langchain` runtime；它封装 `@langchain/react` v1 `useStream` 与 `@langchain/langgraph-sdk` ThreadStream 的 v2 transport。Aegra v2 的 `GET /state`、`POST /stream/events`、`POST /commands` 由官方 transport 直接消费，前端不重写协议。
- 如果需要多实例 SSE、断线恢复和跨实例取消，生产配置应同时验证 PostgreSQL、Redis broker、worker 和反向代理的超时/缓冲策略；开发模式不应被视为高可用行为的证明。

### 版本与兼容性 caveat

- Aegra 与 LangSmith Deployment/Agent Server 不是同一个产品。Aegra 的“兼容 LangGraph SDK/API”应通过实际使用的 Aegra 版本和契约测试确认，不能只依据 LangChain 托管服务文档推断。
- Aegra 文档的 feature matrix 会随版本变化；升级前必须重新核对普通 LangGraph API、Agent Protocol v2、认证、SSE 恢复和多实例行为。
- Aegra 普通 run stream 的 Last-Event-ID 机制与 Protocol v2 POST event stream 的 since 机制并不等价；适配器必须使用它所支持的那条 API 路径。

### 官方来源

- [Aegra 文档索引](https://docs.aegra.dev/llms.txt)
- [Aegra Quickstart](https://docs.aegra.dev/quickstart)
- [Aegra Configuration](https://docs.aegra.dev/reference/configuration)
- [Aegra Threads and state](https://docs.aegra.dev/guides/threads-and-state)
- [Aegra Streaming](https://docs.aegra.dev/guides/streaming)
- [Aegra Authentication](https://docs.aegra.dev/guides/authentication)
- [Aegra Worker architecture](https://docs.aegra.dev/guides/worker-architecture)
- [Aegra High availability](https://docs.aegra.dev/guides/high-availability)
- [Aegra Feature support](https://docs.aegra.dev/feature-support)
- [Aegra 官方 GitHub 仓库](https://github.com/aegra/aegra)

## 3. LangGraph Server、SDK 与 Agent Protocol

### 官方事实

- LangGraph 是 LangChain 官方文档中的低层 agent orchestration runtime，核心能力包括持久化、durable execution、streaming、human-in-the-loop、memory 和 subgraphs。
- LangChain 当前官方 Agent Server 文档把可部署 agent 的核心对象描述为 assistants、threads 和 runs。Agent Server 还覆盖状态、流式、人工介入、并发输入和认证/授权。
- 官方 SDK 参考仍使用以下包名：
  - Python：langgraph_sdk；
  - JavaScript/TypeScript：@langchain/langgraph-sdk。
- 官方 streaming API 支持完整状态快照、节点更新、LLM messages/messages-tuple、自定义数据、事件和 debug 等模式；thread streaming 支持在断线后用最后事件位置恢复。
- JavaScript SDK 的 v2 示例使用 thread-scoped `threads.stream()`/`ThreadStream`；Python SDK 提供对应的 thread streaming 能力。legacy `runs.stream` 仍存在，但不是本项目浏览器主路径。
- `@assistant-ui/react-langgraph` 的 `unstable_createLangGraphStream` 明确调用 `Client.runs.stream`，因此它不满足本项目的 Agent Protocol v2 主路径要求。
- `@assistant-ui/react-langchain@0.0.20` 的 `useStreamRuntime` 官方包装 `@langchain/react@1.0.29` 的 v2-native `useStream`，并直接提供 assistant-ui runtime、消息转换、工具调用、interrupt、取消和线程生命周期接入；应用仍可能提供可选的远程线程列表适配器和 Conversation↔thread_id 映射，但不实现 runtime 或协议解析。
- LangGraph/Agent Server 的认证文档明确区分 authentication 与 authorization：authenticate handler 负责确认身份，resource/action authorization handler 决定用户能访问哪些资源和执行哪些动作。
- 官方 Agent Server API 的 Protocol v2 command 是面向 thread 的 command envelope，包含 id、method 和 params；run.start、input.respond 等会将 run 放入后台执行队列。
- 官方 Protocol v2 event stream 是 POST SSE 端点，客户端在请求体中提供 channel/namespace 过滤；事件包含序号和数据，客户端通过 since 主动恢复。因为端点是 POST，浏览器原生 EventSource 的 Last-Event-ID 自动恢复机制不适用于这条 Protocol v2 endpoint。
- 官方 Thread Join Stream 端点会持续输出某个 thread 上按顺序执行的 run，调用方需要主动关闭长期连接。

### 本项目设计建议

- 把 LangGraph SDK/API/Protocol 视为集成契约，把 Aegra 视为本项目选定的自托管实现；不要把 LangSmith Deployment 的控制平面、计费或托管能力带入本项目边界。
- 前端使用 assistant-ui 官方 `useStreamRuntime`，不自行创建 `Client`、不调用 `runs.stream`。`@langchain/react` 内部按 v2 规范创建 `Client`/`ThreadStream` 并调用 `/state`、`/stream/events`、`/commands`；业务组件只通过 assistant-ui runtime 交互。需要会话列表时，只实现官方允许的 `RemoteThreadListAdapter` 资源映射，不实现 runtime。
- 生产浏览器请求走 TanStack Start 同源 server route/代理。代理只转发真正需要的 thread、run、state、stream、cancel 和 checkpoint 端点，并保留系统会话/授权边界。
- 前端以 thread_id 作为会话外部标识，以 assistant_id 选择 graph 配置，以 run_id 追踪一次执行；这三个标识不应混用。
- Protocol v2 是浏览器主集成契约。web 不自行实现 command envelope、content-block 转换、SSE 去重、since 恢复或 namespace 合并；`@langchain/react`/`@langchain/langgraph-sdk` 的官方 transport 负责这些能力。
- Aegra auth handler 和 FastAPI 系统授权应使用同一用户身份语义；授权失败应在服务端结束请求，不把“前端隐藏按钮”当成访问控制。

### 版本与兼容性 caveat

- LangChain 官方文档正在使用 LangSmith Deployment、Agent Server 等产品命名；历史资料中的 LangGraph Platform、LangGraph Cloud 和 LangGraph Server 名称可能指向不同版本或部署形态。
- SDK、server 和 adapter 必须按兼容矩阵锁定版本。不能因为 SDK 的最新文档存在某端点，就假定当前 Aegra 版本已经实现该端点。
- 需要单独测试 legacy runs.stream 与 v2 thread stream、v2 command/event stream、checkpoint 编辑、interrupt 恢复和断线重连；它们的事件边界和恢复游标不同。当前 assistant-ui 主路径覆盖 v2；legacy runs.stream 仅作为回归/负向兼容性测试。

### 官方来源

- [LangGraph 官方概览](https://docs.langchain.com/oss/python/langgraph)
- [LangSmith Agent Server 概览](https://docs.langchain.com/langsmith/agent-server-overview)
- [LangSmith Agent Server](https://docs.langchain.com/langsmith/agent-server)
- [LangGraph SDK 参考](https://docs.langchain.com/langgraph-platform/sdk)
- [LangGraph Streaming API](https://docs.langchain.com/langgraph-platform/streaming)
- [LangGraph authentication and access control](https://docs.langchain.com/langgraph-platform/auth)
- [Protocol v2 Command](https://docs.langchain.com/langsmith/agent-server-api/streaming/protocol-v2-command)
- [Protocol v2 Event Stream（SSE）](https://docs.langchain.com/langsmith/agent-server-api/streaming/protocol-v2-event-stream-sse)
- [Create run and stream output](https://docs.langchain.com/langsmith/agent-server-api/thread-runs/create-run-stream-output)
- [Join thread stream](https://docs.langchain.com/langsmith/agent-server-api/threads/join-thread-stream)

## 4. assistant-ui runtime adapters

### 官方事实

- assistant-ui 官方提供 `@assistant-ui/react-langchain`，其 README 明确说明它包装 `@langchain/react` 的 `useStream` 并暴露为 assistant-ui runtime。`@langchain/react` v1 官方文档将 `useStream` 定义为 v2-native stream runtime。
- `@assistant-ui/react-langgraph` 仍建立在 ExternalStoreRuntime 上，但它的官方 helper 只调用 legacy `runs.stream`；它不是本项目 v2 路径。
- 官方要求 graph state 包含 messages key，消息形状为 LangChain-like messages；文档标注支持 React 18 或 React 19。
- 官方 runtime 支持 streaming、subgraph events、UI messages/generative UI、message metadata、interrupts、cancellation，以及基于 checkpoint 的 message editing/regeneration。
- `useStreamRuntime` 直接委托 `useStream`。官方 v2 transport 负责 `/stream/events` POST SSE、`/commands` command envelope、`since` 恢复、消息/content-block 装配、values/toolCalls/interrupts 投影和 cancellation；应用不写 stream callback、SSE parser 或 reducer。
- `useStreamRuntime` 支持 `assistantId`、`apiUrl`、`threadId`、`transport: "sse"` 以及可选的官方 remote thread-list adapter。Aegra 当前 v2 WebSocket 未实现，因此固定 SSE。
- 官方文档使用 getCheckpointId 支持编辑/重新生成时的 checkpoint 分支。
- 官方 runtime 文档列出 onMessageChunk、onValues、onUpdates、onSubgraphValues、onSubgraphUpdates、onMetadata、onInfo、onError、onSubgraphError 和 onCustomEvent 等流事件回调。
- assistant-ui 官方 architecture 文档把职责分为 UI layer、runtime layer、backend/agent layer 和 integration/protocol layer；UI primitives 不应直接访问后端或模型。
- assistant-ui 官方 LangGraph quickstart 在生产环境建议通过自有后端代理 LangGraph 请求，避免 API key 到达客户端，并建议只暴露实际需要的端点。

### 本项目设计建议

- 使用 assistant-ui 自带的 `@assistant-ui/react-langchain/useStreamRuntime` 作为唯一前端 agent runtime，不自行实现 ExternalStoreRuntime、SSE parser、message reducer、command envelope 或 checkpoint 编辑协议。
- 将 AssistantRuntimeProvider、useStreamRuntime 和 runtime 配置逻辑限制在客户端边界；TanStack Start 的服务端只负责页面外壳、同源代理和非实时首屏数据。
- Client 的 apiUrl 指向同源 Start server route，而不是暴露 Aegra 内网 URL 或任何长期密钥。代理层负责系统会话、授权、请求头传递、错误映射和流式响应的连接管理。
- `useStreamRuntime` 负责 thread hydration、message/state projection 和 v2 run lifecycle；这些数据由 Aegra 持久化，不能再在 React localStorage 中复制一套“真状态”。如果要显示历史线程，只实现官方允许的 `RemoteThreadListAdapter`，或由应用会话列表映射到 Aegra `thread_id`，不替换 runtime。
- assistant-ui UI 组件只消费 runtime context。医疗免责声明“AI生成内容仅供参考，不可替代医嘱，请以医生诊断为准”建议作为固定、可访问的 UI 文本渲染，而不是等待 agent token 或写入每条 graph message。
- graph 产生的 message metadata、interrupt 和自定义事件只通过官方 adapter 的类型/回调进入 UI；如果业务需要新的事件，先确认 upstream adapter 是否提供能力，再决定是否升级依赖。业务层只写事件处理器/渲染器，不写第二套 SSE parser 或 reducer。

### 版本与兼容性 caveat

- `@assistant-ui/react-langchain` 和 `@langchain/react` 需要锁版本并做 v2 合同测试；不应在大量业务组件中散落低层 SDK 调用。
- assistant-ui 文档目前同时展示 LangGraph adapter 与 LangChain runtime；本项目只选 `@assistant-ui/react-langchain`，不混用 `@assistant-ui/react-langgraph` 或 AG-UI runtime。
- 官方 production proxy 示例是框架无关原则的示例，示例中的 Next.js 路由不能直接当作 TanStack Start 的实现；在本项目中应通过 Start server route 实现同源代理，这属于本项目适配建议。

### 官方来源

- [assistant-ui LangGraph runtime](https://www.assistant-ui.com/docs/runtimes/langgraph/overview)
- [assistant-ui LangGraph quickstart](https://www.assistant-ui.com/docs/runtimes/langgraph/quickstart)
- [assistant-ui LangGraph streaming](https://www.assistant-ui.com/docs/runtimes/langgraph/streaming)
- [assistant-ui LangGraph interrupts and message editing](https://www.assistant-ui.com/docs/runtimes/langgraph/interrupts)
- [assistant-ui LangChain runtime](https://www.assistant-ui.com/docs/runtimes/langchain)
- [`@assistant-ui/react-langchain` README](https://github.com/assistant-ui/assistant-ui/blob/main/packages/react-langchain/README.md)
- [`@langchain/react` `useStream` docs](https://github.com/langchain-ai/langgraphjs/blob/main/libs/sdk-react/docs/use-stream.md)
- [`@langchain/react` transport docs](https://github.com/langchain-ai/langgraphjs/blob/main/libs/sdk-react/docs/transports.md)
- [assistant-ui architecture](https://www.assistant-ui.com/docs/architecture)
- [assistant-ui 官方 GitHub 仓库](https://github.com/assistant-ui/assistant-ui)

## 5. TanStack Start

### 官方事实

- TanStack Start 是基于 TanStack Router 的 full-stack React framework，提供 full-document SSR、streaming、server functions、server routes、middleware/context、client/server builds 和端到端 TypeScript。
- Start 的路由系统 100% 依赖 TanStack Router；官方文件路由约定使用 src/routes，根路由是 src/routes/__root.tsx，路由树会生成 routeTree.gen.ts。
- 官方文档要求 getRouter() 每次返回新的 router instance；__root.tsx 始终渲染，适合放应用 shell 和全局逻辑。
- Start server functions 通过 createServerFn 定义，在服务端执行、由 Start 处理客户端/服务端之间的序列化；官方建议 server functions 用于 Start 应用内部调用。
- server functions 默认有 same-origin 保护，官方文档讨论 Fetch Metadata、Origin、Referer 和 CSRF middleware；需要被 Start 应用之外的客户端调用时，应使用 server routes。
- server routes 与应用路由共用文件路由体系，处理原始 HTTP request，适合外部 API、webhook、认证入口和需要精确控制响应的端点。
- 官方建议较大项目把 createServerFn 包装、server-only helper 和 client-safe schema 分开，例如 .functions.ts、.server.ts 和普通 .ts。
- 环境变量边界由构建工具决定：服务端可读未加前缀的 process.env；Vite 客户端只应读取 VITE_ 前缀变量；官方明确警告不要把 secret 放入公开前缀。
- 官方环境变量文档特别提醒，在 edge SSR runtime 中不要在模块顶层读取 process.env；应在 request-time handler、middleware 或 server route 中读取。
- Start 当前处于 Release Candidate 阶段。官方说明 API 被视为 stable，但仍可能有 bug；React Server Components 在 Start 中仍是 experimental。
- 官方 hosting 文档支持 Node/Docker、Cloudflare、Netlify、Railway、Nitro、Vercel 等部署目标。

### 本项目设计建议

- apps/web 是 monorepo 中唯一的 TanStack Start 应用；使用官方 TanStack Start Vite plugin，不直接搭建 Vite 低层 SSR server。
- src/routes 只表达 Web 页面和同源 server routes。页面路由、pathless layout、server route 和 loader 按功能模块分目录，避免把所有页面逻辑放在 __root.tsx。
- chat 页面采用 thread 维度的路由标识；路由 loader 只获取首屏需要的 thread 元数据/权限摘要，实时 agent stream 在 hydration 后由 assistant-ui 接管。
- Aegra stream 代理使用 server route，而不是 server function：SSE 是长连接/原始 HTTP 响应，不适合被 server function 的普通序列化 RPC 抽象包裹。
- 同源 server route 负责将浏览器请求连接到 Aegra；FastAPI 业务请求也以明确的 server-only client 调用，避免在组件中混用 Aegra 和业务 API。
- 只在 server-only 模块读取 Aegra/FastAPI 内部 URL、密钥和系统会话验证材料；浏览器只得到非敏感的 UI 配置。
- 不把 React Server Components 作为 MVP 的前置条件；待 TanStack Start v1 和相关 RSC 能力稳定、且确有收益时再单独评估。

### 版本与兼容性 caveat

- Release Candidate 意味着当前 API 可用于试用和生产评估，但升级时仍需执行完整的 SSR、server route、streaming、middleware 和 hydration 回归测试。
- Start 同时支持 Vite 和 Rsbuild；本项目明确选择 Vite，因此不应在同一应用中混合两套构建配置或把 Rsbuild 专属行为当作 Vite 行为。
- routeTree.gen.ts 是生成物，不应手工编辑；路由文件命名变化后要重新生成并让类型检查验证路由树。

### 官方来源

- [TanStack Start 概览](https://tanstack.com/start/latest/docs/framework/react/overview.md)
- [TanStack Start Routing](https://tanstack.com/start/latest/docs/framework/react/guide/routing.md)
- [TanStack Start Server Functions](https://tanstack.com/start/latest/docs/framework/react/guide/server-functions.md)
- [TanStack Start Server Routes](https://tanstack.com/start/latest/docs/framework/react/guide/server-routes.md)
- [TanStack Start Environment Variables](https://tanstack.com/start/latest/docs/framework/react/guide/environment-variables.md)
- [TanStack Start Hosting](https://tanstack.com/start/latest/docs/framework/react/guide/hosting.md)
- [TanStack Start 官方文档索引](https://tanstack.com/start/latest/llms.txt)

## 6. React

### 官方事实

- React 官方当前文档显示 React 19.2。
- React 官方 Rules of React 要求组件和 Hooks 保持纯函数性质；Hooks 只能在组件或自定义 Hook 的顶层调用，不能放在条件、循环或普通函数中。
- React 官方文档推荐使用稳定 key 渲染列表，避免把数组索引作为会变化列表的身份标识。
- 官方 state 文档强调 state 应放在真正需要它的层级，避免重复 state；能够由 props/state 直接推导的值不应无必要地放入 state。
- React 官方文档将 effect 定义为与外部系统同步的机制，并单独提供“可能不需要 effect”的指导。
- React DOM 提供 hydrateRoot 等客户端 API；React server API 提供 renderToReadableStream 等流式 SSR API。
- React use API 可以读取 Promise/Context 等资源；官方文档说明客户端创建的 Promise 应缓存，否则每次 render 创建新 Promise 会产生问题。
- React 官方提供 eslint-plugin-react-hooks 参考；当前规则集合包括 rules-of-hooks、exhaustive-deps 以及若干与组件纯度、effect 和 render 相关的规则。

### 本项目设计建议

- React 组件按“纯展示、交互状态、服务端边界”分层。纯展示组件不直接调用 Aegra/FastAPI；agent runtime 由一个明确的客户端 feature 入口提供。
- 只把 UI 暂态放入 React/assistant-ui runtime；thread、checkpoint、run 和 message 持久状态以 Aegra 为事实来源，业务资源以 FastAPI 为事实来源。
- SSR 阶段渲染应用 shell、路由头信息和非实时数据；不要在服务端初始 render 中创建不可缓存的 agent stream 或每次 render 新建 Promise。
- 组件事件处理、消息列表 key、loading/error/interrupt 状态和取消动作都用语义化组件 API 表达；不要通过全局变量或隐式 DOM 查询绕过 React。
- 使用 React 官方 eslint-plugin-react-hooks 规则；对 hooks 依赖警告必须解释并修正，不能通过关闭规则掩盖不稳定闭包。
- 可访问性上优先使用原生语义元素、label、button、form 和可聚焦控件，再利用 assistant-ui primitives 组合聊天界面；流式输出、错误、取消和 interrupt 状态应有可被辅助技术感知的状态文本。

### 版本与兼容性 caveat

- assistant-ui LangGraph adapter 官方同时支持 React 18/19；本项目建议统一 React 19.2，但所有上游 peer dependency 与构建插件必须在锁文件中验证。
- React 19 的新 API、React Compiler 和 RSC/实验性能力不能因为出现在官方文档中就纳入 MVP 的基础依赖。
- SSR 与 hydration 必须在同一套组件树、路由数据和环境分支下工作；使用 import.meta.env.SSR 或 Start 的服务端边界时，要避免服务端与客户端首屏 markup 不一致。

### 官方来源

- [React 官方文档](https://react.dev/learn)
- [React Thinking in React](https://react.dev/learn/thinking-in-react)
- [React Rules of React](https://react.dev/reference/rules)
- [React hydrateRoot](https://react.dev/reference/react-dom/client/hydrateRoot)
- [React renderToReadableStream](https://react.dev/reference/react-dom/server/renderToReadableStream)
- [React use](https://react.dev/reference/react/use)
- [React common components and HTML attributes](https://react.dev/reference/react-dom/components/common)
- [React eslint-plugin-react-hooks](https://react.dev/reference/eslint-plugin-react-hooks)
- [React 官方仓库中的 eslint-plugin-react-hooks](https://github.com/facebook/react/tree/main/packages/eslint-plugin-react-hooks)

## 7. Vite

### 官方事实

- Vite 的两个核心部分是开发服务器和生产构建命令；开发期利用原生 ESM/HMR，生产构建当前由 Rolldown 生成优化后的静态资源。
- 当前 Vite 官方文档显示 Vite 8，并要求 Node.js 20.19+ 或 22.12+；Node.js 24.x 满足该要求。
- Vite 官方 SSR 文档把 SSR API 定义为低层 API，并建议应用优先使用更高层 framework/plugin。
- Vite SSR 的典型结构包含 index.html、通用 app 代码、entry-client、entry-server 和服务器入口；import.meta.env.SSR 会在构建时静态替换，可用于 tree-shaking。
- Vite 官方 SSR 开发模式建议使用 middleware mode，以便框架/宿主服务器控制请求和 HTML 响应。
- Vite 默认只向客户端暴露 VITE_ 前缀环境变量；这些值会在构建时打包进入客户端，不能包含 API key 或其他 secret。
- Vite 默认生产目标是 Baseline Widely Available 浏览器；当前文档列出 Chrome 111+、Edge 111+、Firefox 114+、Safari 16.4+，可通过 build.target 调整。
- Vite 配置支持 TypeScript、defineConfig、条件化 command/mode/SSR build 配置；Vite 也说明 monorepo 外部依赖和 config loader 在某些 TypeScript workspace 场景下需要注意。

### 本项目设计建议

- TanStack Start 负责高层 SSR 和路由，Vite 只作为其构建/dev server 层；不直接复制 Vite 的低层 SSR 示例来实现第二套服务器。
- apps/web 只保留一个 vite.config.ts，集中维护 Start plugin、React plugin、路径别名和构建条件；packages 不各自启动 Vite server。
- Vite client env 只放公开的功能开关、公开 origin 或非敏感展示信息。Aegra URL、FastAPI 内网地址、session secret 和 provider credentials 留在 Start server runtime。
- 使用 Vite 默认现代浏览器目标；若项目后续需要更老浏览器，再单独评估官方 legacy plugin，而不是在业务组件中手写兼容代码。
- 构建、类型检查和 lint 分成独立质量门；不要把 Vite“能打包”误认为 TypeScript 类型正确或 route/stream contract 正确。

### 版本与兼容性 caveat

- Vite 8 的 Node 约束与 Vite 6/7 不同；Node、Vite、TanStack Start 和 Vitest 要作为一个兼容组升级。
- Vite 的 SSR API 仍是低层 API；如果绕过 Start 自建 SSR server，将重新承担 hydration、路由、middleware、流式响应和部署适配的责任。

### 官方来源

- [Vite Getting Started](https://vite.dev/guide.md)
- [Vite SSR](https://vite.dev/guide/ssr.md)
- [Vite Env Variables and Modes](https://vite.dev/guide/env-and-mode.md)
- [Vite Building for Production](https://vite.dev/guide/build.md)
- [Vite Configuration](https://vite.dev/config/)
- [Vite 官方仓库](https://github.com/vitejs/vite)

## 8. Node.js 24

### 官方事实

- Node.js 官方 release 页面将 v24 标记为 LTS；具体 patch 版本必须在实现时从官方 release index 复核并锁定。
- Node.js 24 官方文档提供 ESM、Web Streams、Fetch/Abort 等现代运行时能力；这些能力与 TanStack Start SSR、SSE 代理和 assistant-ui 的浏览器/服务端边界相容。
- Node.js 24 也包含原生 test runner，但这不是本项目的主测试框架；本项目明确使用 Vitest 和 Playwright。

### 本项目设计建议

- 所有 Node.js 应用、Docker 镜像、CI runner 和本地开发环境统一 Node.js 24.x；在镜像和 CI 中固定到经验证的 24.x patch，而不是使用浮动 latest。
- package.json 的 engines、pnpm 的 packageManager/runtime 约束和 Docker 基础镜像应表达同一 Node major/minor policy。
- 前端使用 ESM 语义；Node-only service code、Vite config、ESLint config 和 Prettier config 要统一模块格式，避免同一包内混用未声明的 CommonJS/ESM 假设。
- 不使用未在目标 Node 24 patch 基线中验证的实验 API；如果上游包的最低 Node 要求上调，应先做整个 monorepo 的升级评估。

### 版本与兼容性 caveat

- Node 24 是本项目锁定的 LTS major；具体 patch 版本由 `.node-version`、容器基础镜像和 CI 一致固定。
- Vite、pnpm、TanStack Start、assistant-ui 和 TypeScript 的实际 peer 范围仍需在锁文件中验证；Node 24 不能替代真实安装、SSR、流式和构建合同测试。

### 官方来源

- [Node.js Previous Releases](https://nodejs.org/en/about/previous-releases)
- [Node.js 官方 release index](https://nodejs.org/dist/index.json)
- [Node.js v22 ESM](https://nodejs.org/download/release/latest-v22.x/docs/api/esm.html)
- [Node.js v22 Web Streams](https://nodejs.org/download/release/latest-v22.x/docs/api/webstreams.html)
- [Node.js v22 Environment Variables](https://nodejs.org/download/release/latest-v22.x/docs/api/environment_variables.html)
- [Node.js v22 Test Runner](https://nodejs.org/download/release/latest-v22.x/docs/api/test.html)

## 9. pnpm

### 官方事实

- pnpm 11 官方安装文档要求 Node.js 至少 v22；pnpm 11 以 pure ESM 形式分发。
- pnpm 官方 workspace 文档要求根目录存在 pnpm-workspace.yaml，并将 workspace 定义为单仓多项目/monorepo 的内置支持。
- workspace: 协议可以强制依赖解析到本地 workspace package，避免本地包不存在时悄悄回退到 registry。
- sharedWorkspaceLockfile 默认是 true；官方设置文档说明这会在 workspace 根生成单一 pnpm-lock.yaml，并将依赖链接到各包。
- 官方安装文档推荐通过 Corepack pin pnpm，并在 package.json 写入 packageManager 字段；pnpm 11 还提供 devEngines.packageManager。
- pnpm package.json 文档支持 engines.node、engines.pnpm；CI 文档说明检测到 CI 时会自动使用 frozen-lockfile，并且 pnpm 11 对不兼容的 lockfile major 会失败。

### 本项目设计建议

- 根目录使用单一 pnpm-workspace.yaml 和单一 pnpm-lock.yaml；不要让 apps/web 或 packages 产生自己的 lockfile。
- 内部 TypeScript package 依赖统一使用 workspace:*、workspace:^ 等显式 workspace 协议；发布边界另行转换版本范围。
- packageManager 固定经过验证的 pnpm 11 patch；同时用 engines.node、engines.pnpm 和 CI 检查防止开发机漂移。
- 根脚本通过 pnpm filter 调度 web、contracts、ui 和测试项目；Python apps/agent、apps/api 继续由 uv/其自身工具管理，不把 Python 虚拟环境塞进 pnpm 依赖图。
- CI 只使用 frozen lockfile 安装；升级 Node、pnpm 或主要前端工具时必须同时重新生成锁文件并验证构建、lint、Vitest 和 Playwright。

### 版本与兼容性 caveat

- pnpm 11 的 pure ESM 会影响旧的 CommonJS 配置脚本和部分自定义工具；共享配置要优先采用官方支持的 ESM/TypeScript 形态。
- pnpm 11 不应读取由未来 pnpm major 生成的 lockfile；CI 应固定 pnpm major，避免“本地能装、CI 不能装”。
- pnpm 官方文档的版本选择器可能显示 next/11.x/10.x；研究时必须记录实际选用的 major，不能只引用 pnpm.io 首页的未标版本文本。

### 官方来源

- [pnpm 安装与版本兼容](https://pnpm.io/next/installation)
- [pnpm Workspaces](https://pnpm.io/workspaces)
- [pnpm package.json](https://pnpm.io/package_json)
- [pnpm Continuous Integration](https://pnpm.io/continuous-integration)
- [pnpm Settings](https://pnpm.io/settings)

## 10. TypeScript

### 官方事实

- TypeScript 官方 registry 已发布 7.x，但本项目按兼容性研究锁定 TypeScript 6.0.3。
- strict 编译选项启用一组更严格的类型检查；官方明确提醒未来版本可能增加 strict 家族检查，从而产生新的类型错误。
- Project References 可以把大型项目拆成更小的项目、强化逻辑边界、改善构建时间，并配合 tsc --build 按依赖顺序构建。
- moduleResolution 的 bundler 模式适用于 bundler；node16/nodenext 适用于现代 Node.js 的 ESM/CJS 解析。bundler 支持 package.json imports/exports，且相对导入不强制扩展名。
- verbatimModuleSyntax 要求通过 type 修饰符明确区分类型导入/导出和运行时值导入/导出，减少 import elision 的歧义。
- isolatedModules 用于提醒那些无法被单文件 transpiler 正确处理的 TypeScript 写法，适合由 Vite 等 bundler 逐文件转换的应用。

### 本项目设计建议

- 根 tsconfig 提供公共严格基线；apps/web、packages/contracts 各有自己的 tsconfig，并通过 references 或清晰的包入口表达依赖边界。
- apps/web 采用 moduleResolution bundler；Node-only 配置和 Node 服务按实际 ESM 运行方式选择 nodenext。不要在同一个 package 内随意切换。
- 统一开启 strict、verbatimModuleSyntax、isolatedModules；noUncheckedIndexedAccess、exactOptionalPropertyTypes 可以作为本项目额外严格项，但它们是本项目选择，不是 TypeScript 官方默认。
- 前端 package 的 noEmit 交给 Vite/Start 构建；类型检查使用 tsc --build 或等价的项目级检查，不把 Vite transpile 当成类型检查。
- packages/contracts 只导出浏览器安全、可序列化的 DTO、枚举和 schema 类型；不得从中导出数据库模型、Aegra server runtime、Node stream 实例或密钥配置。
- 通过 import type 明确纯类型依赖，避免把服务端模块意外带入客户端 bundle。

### 版本与兼容性 caveat

- TypeScript 6.0.3 落在当前 `typescript-eslint` 8.65.0 的 `<6.1.0` peer 范围内；升级时仍必须检查 ESLint parser、Vite、Vitest、TanStack Start、assistant-ui adapter 和编辑器 TypeScript 版本是否一致。TypeScript 7 暂不纳入基线。
- TypeScript 官方文档的 option 页面按 latest 发布；生产构建应锁定 minor/patch，并在 CI 运行完整的项目引用构建。

### 官方来源

- [TypeScript 官方首页](https://www.typescriptlang.org/)
- [TypeScript Handbook](https://www.typescriptlang.org/docs/handbook/intro.html)
- [strict](https://www.typescriptlang.org/tsconfig/strict.html)
- [Project References](https://www.typescriptlang.org/docs/handbook/project-references.html)
- [moduleResolution](https://www.typescriptlang.org/tsconfig/moduleResolution.html)
- [verbatimModuleSyntax](https://www.typescriptlang.org/tsconfig/verbatimModuleSyntax.html)
- [isolatedModules](https://www.typescriptlang.org/tsconfig/isolatedModules.html)

## 11. ESLint

### 官方事实

- ESLint 当前官方文档以 flat config 为主；配置文件可以是 eslint.config.js、eslint.config.mjs、eslint.config.cjs，以及需要额外设置的 TypeScript 配置形式。
- flat config 文件放在项目根目录，并导出配置对象数组；配置对象可以通过 files、ignores、languageOptions、plugins、rules、settings 等字段定义作用域。
- ESLint 官方文档区分 global ignores 与配置对象内的 non-global ignores；使用 globalIgnores 可以明确表达全局忽略目录。
- TypeScript 官方生态的 typescript-eslint quickstart 采用 eslint.config.mjs、@eslint/js 和 typescript-eslint，提供 recommended、strict、stylistic 等 flat config。
- React 官方提供 eslint-plugin-react-hooks；其规则覆盖 Rules of Hooks、effect dependencies、组件纯度和相关 render/effect 风险。
- ESLint 和 Prettier 的职责不同；Prettier 官方提供单独的集成指南，不把 Prettier 的格式化结果当作 ESLint 规则集合。

### 本项目设计建议

- 在 monorepo 根放置一个主 eslint.config.mjs，以 files 匹配 apps/web 和 packages 中的 JS/TS/JSX/TSX；只有真正需要不同运行时或插件的 package 才增加局部配置。
- TypeScript 文件使用 typescript-eslint flat recommended 作为基线；在确认类型信息成本后，再对核心包启用 typed linting/strict，而不是让所有包默认承担不必要的类型分析开销。
- React 前端启用 React 官方 eslint-plugin-react-hooks；路由、服务端代理、contracts 和 UI primitives 可按文件模式叠加规则。
- 将 routeTree.gen.ts、构建输出、coverage、测试产物和临时目录作为明确的全局忽略；生成文件不手工修改，也不把生成物错误地当作业务源码。
- ESLint 只负责代码质量、潜在 bug、hooks 规则和项目约束；格式化交给 Prettier，避免两套规则互相改写。
- CI 的 lint 目标应覆盖整个 workspace，并把 warning 处理策略固定下来；新增规则或升级 major 时必须先审查误报和插件兼容性。

### 版本与兼容性 caveat

- 当前 ESLint 文档版本选择器显示 v10.8.0、v9.39.5 和 v8.57.1；新项目应按 flat config 设计，不新增 legacy .eslintrc 依赖。
- ESLint major 升级可能要求插件更新；尤其要验证 typescript-eslint、React hooks plugin、Start/Vite config 文件和 pure ESM 的加载方式。
- ESLint 官方推荐的 config 文件格式与 pnpm 11 的 pure ESM、Node 24 运行时需要一起验证，不能只在编辑器中验证。

### 官方来源

- [ESLint Configuration Files](https://eslint.org/docs/latest/use/configure/configuration-files)
- [ESLint Configure](https://eslint.org/docs/latest/use/configure/)
- [ESLint Migrate to v10.x](https://eslint.org/docs/latest/use/migrate-to-10.0.0)
- [ESLint Version Support](https://eslint.org/docs/latest/use/version-support)
- [typescript-eslint Getting Started](https://typescript-eslint.io/getting-started/)
- [typescript-eslint 官方文档](https://typescript-eslint.io/)
- [React eslint-plugin-react-hooks](https://react.dev/reference/eslint-plugin-react-hooks)

## 12. Prettier

### 官方事实

- Prettier 官方配置文档支持 package.json/package.yaml 中的 prettier 字段、.prettierrc 系列、prettier.config.js/mjs/cjs/ts/mts/cts 和 TOML 等配置形式，并按规定的优先级解析。
- 配置从被格式化文件所在位置开始向上查找；官方说明统一配置文件能保证 CLI、编辑器和其他工具得到一致结果。
- overrides 可以按扩展名、目录或特定文件应用不同选项；parser 不应随意放到顶层，否则会破坏按扩展名自动推断。
- .prettierignore 使用 gitignore 语法；官方推荐在项目根维护它，并默认忽略版本控制目录和 node_modules。
- CLI 的 --write 会原地修改文件；--check 用于检查格式并在发现未格式化文件时返回非零退出码，官方明确把它定位为 CI 适用的检查。
- Prettier 官方说明 printWidth 是期望的近似行宽，不等于 ESLint max-len 的硬性最大行宽。
- 当前 Prettier 配置文档说明 TypeScript 配置文件需要 Node.js >=22.6.0，并且在 Node.js <24.3.0 时需要 experimental-strip-types 相关运行设置。

### 本项目设计建议

- monorepo 使用一个根 Prettier 配置和一个根 .prettierignore；只有语言/目录确有不同解析需求时才使用 overrides。
- 为避免 Node 24 运行 TypeScript 配置文件的额外 flag，首版优先使用 JSON/YAML 或 ESM JavaScript 配置文件；如果采用 prettier.config.ts，要把官方要求写入工具链验证。
- 统一由 Prettier 规定缩进、引号、分号、尾逗号、Markdown/JSON/TSX 格式；不要在 ESLint 中重复维护等价的样式规则。
- 本项目可以选择 singleQuote、semi、trailingComma: all 等固定值，但这些是团队设计决定，不是 Prettier 的“行业唯一标准”；一旦选定，应由配置文件和 --check 强制。
- 将生成路由树、构建产物、coverage、快照以外的业务源码纳入格式化；对不可改写的生成/外部文件使用 .prettierignore 或局部官方 ignore 语法，并记录原因。

### 版本与兼容性 caveat

- Prettier 的配置文件加载方式受 Node 模块格式影响；Node 24、pnpm 11 pure ESM 和 package.json type 字段必须一起考虑。
- 不要直接使用全局 prettier；CI 和本地统一调用 workspace 内固定版本。升级时同时运行 --check 和编辑器格式化验证。

### 官方来源

- [Prettier Configuration File](https://prettier.io/docs/configuration)
- [Prettier Options](https://prettier.io/docs/options)
- [Prettier Ignoring Code](https://prettier.io/docs/ignore)
- [Prettier CLI](https://prettier.io/docs/cli)
- [Prettier Integrating with Linters](https://prettier.io/docs/integrating-with-linters)
- [Prettier 官方仓库](https://github.com/prettier/prettier)

## 13. Vitest

### 官方事实

- Vitest 是由 Vite 驱动的测试框架；当前官方文档显示 v4.1.10，并要求 Vite >=6.0.0、Node >=20.0.0。
- Vitest 默认识别文件名中包含 .test. 或 .spec. 的测试文件；vitest run 用于一次性运行测试。
- 如果项目已有 vite.config，Vitest 会读取它以复用插件和 Vite 配置；也可以通过单独的 Vitest config 或 VITEST/mode 条件区分测试配置。
- Vitest projects 能在一个进程中定义多个项目配置，官方特别指出它适合 monorepo、不同 environment、不同 alias/plugin 或 browser 配置。
- 官方说明 workspace 这一名称自 Vitest 3.2 起 deprecated，功能由 projects 配置取代；根配置默认不会自动成为一个 project，根配置主要影响全局 reporters、coverage 和插件/setup。
- Vitest coverage 支持 V8 原生覆盖率和 Istanbul instrumentation；默认 provider 是 v8，也可以按配置选择 istanbul。
- Vitest 官方 mocking 文档提供 vi.fn、vi.spyOn、vi.mock 等工具，并明确提醒在测试前后清除或恢复 mocks，避免跨测试污染。
- Vitest 支持 node、jsdom、happy-dom 等环境，并有独立 browser mode 文档；它不等价于完整真实浏览器 E2E。

### 本项目设计建议

- 根 Vitest 配置使用 projects，而不使用已经 deprecated 的 workspace 配置名；为 contracts、UI、Start server/proxy 分别定义清晰的测试项目。
- 纯 contracts、协议转换、状态归一化、错误映射和 server-only 工具优先使用 node environment；React 组件使用 jsdom；需要真实浏览器行为的场景交给 Playwright。
- 测试文件采用模块旁边的 *.test.ts / *.test.tsx，测试名称描述用户可观察行为或契约，不绑定内部函数名；集成测试单独标记，避免每次 unit run 都启动外部服务。
- Aegra SDK、FastAPI 和外部模型调用在 unit/integration 测试中以契约 fixture/mock 隔离；测试重点是请求形状、流事件顺序、断线/取消/错误边界，而不是依赖真实模型随机输出。
- 每个测试保持独立；统一在 beforeEach/afterEach 清理 mock、计时器、全局状态和临时文件。对跨测试共享的 thread、session 或浏览器状态必须显式说明生命周期。
- 覆盖率建议按风险而不是追求一个总百分比：
  - contracts、协议映射、权限/代理和流状态机：建议 90% 左右的语句/分支覆盖；
  - Start route、server-only proxy、错误与认证边界：建议 85% 以上；
  - UI primitives 和 chat 交互逻辑：建议 80% 以上，并由 Playwright 补充真实交互；
  - 生成文件、类型声明、配置胶水和不可执行资源从 coverage include/exclude 中明确处理。
- V8 coverage 适合 Node/Chromium 路径；如果测试环境或覆盖率需求不适配 V8，再按官方配置切换 Istanbul，不应在项目中同时维护两套未解释的指标。

### 版本与兼容性 caveat

- Vitest 当前 v4 文档把 projects 作为 monorepo 方向；升级时不要继续复制旧 workspace 配置。
- Vitest 与 Vite 强耦合；Vite 8、TanStack Start RC、React 19 和 Node 24 的组合必须在同一锁文件中验证。
- 浏览器 mode、jsdom 和 Playwright 的运行时语义不同；同一测试不要同时依赖三者隐含的全局行为。

### 官方来源

- [Vitest Getting Started](https://vitest.dev/guide/)
- [Vitest Configuration](https://vitest.dev/config/)
- [Vitest Test Projects](https://vitest.dev/guide/projects)
- [Vitest Coverage](https://vitest.dev/guide/coverage)
- [Vitest Mocking](https://vitest.dev/guide/mocking)
- [Vitest Browser Mode](https://vitest.dev/guide/browser/)
- [Vitest Migration Guide](https://vitest.dev/guide/migration)
- [Vitest 官方仓库](https://github.com/vitest-dev/vitest)

## 14. Playwright

### 官方事实

- Playwright Test 通过配置文件控制 testDir、fullyParallel、forbidOnly、retries、workers、reporter、projects、use 和 webServer 等运行行为。
- projects 可以在一个配置中运行多个浏览器或多个测试配置；官方示例使用 Chromium 等主要浏览器项目。
- webServer 可以在测试前启动本地开发服务器，使用 command、url、reuseExistingServer、timeout、env 等选项；use.baseURL 允许测试使用相对 URL。
- Playwright fixtures 用于建立每个测试需要的环境；官方强调 fixtures 在测试之间隔离、按需创建、可组合并负责 setup/teardown。
- retries 用于自动重试失败测试；官方将测试结果分类为 passed、flaky 和 failed，并说明失败时 worker 进程可能被销毁并重建。
- 官方 CI 指南建议 CI 中将 workers 设为 1 以优先稳定性和可复现性；需要更大并行度时使用 sharding 分发到多个 CI job。
- Playwright 配置可在失败重试时采集 trace；官方文档还提供 screenshot、video、reporter 和 trace viewer 的配置/查看路径。
- 官方认证指南使用 setup project、storageState 复用登录状态；认证文件可能包含敏感 cookie/header，官方明确不应提交到仓库。
- 官方认证指南区分共享账号和每 worker 账号：不修改共享服务端状态时可以复用一个账号，修改共享状态时应为并行 worker 提供隔离账号/状态。
- 官方 accessibility testing 指南说明自动化检查只能发现一部分问题，推荐将自动扫描、人工评估和包容性用户测试结合；其示例使用 @axe-core/playwright 运行可自动检测的违规检查。

### 本项目设计建议

- 根目录维护一个 Playwright 配置；PR 阶段至少运行 Chromium 的关键路径，定时/发布阶段增加 Firefox 和 WebKit smoke 或全量矩阵，具体矩阵由 CI 资源决定。
- webServer 启动 TanStack Start 的测试/preview 服务，baseURL 使用同源入口；Aegra/FastAPI 通过测试环境的代理地址或确定性契约服务接入，不在每个 spec 中手工启动服务。
- 通过自定义 fixtures 统一准备系统身份、thread、Aegra run fixture、清理数据和 page object；不要用全局可变变量承载跨测试 session。
- 认证 setup 文件放入 playwright/.auth 并加入 ignore；对于会修改 workspace/thread 的测试，按 worker 或测试数据创建隔离身份/资源。
- CI 默认 workers: 1、失败重试只在 CI 开启、trace 采用 on-first-retry；失败保留 HTML report、trace、截图和必要的视频，避免所有成功测试都生成大量产物。
- E2E 覆盖至少包括：SSR 首屏与 hydration、路由权限、创建/加载 thread、流式 token/message 渲染、取消、断线恢复、interrupt、checkpoint 编辑/重新生成、FastAPI/Aegra 错误、空态/超时和页面刷新恢复。
- 可访问性测试覆盖聊天输入、发送/取消按钮、消息列表、流式状态、错误/interrupt 状态、键盘导航、焦点恢复和免责声明；自动检查之外安排人工键盘/读屏抽查。
- E2E 测试用用户可观察定位器和稳定的语义名称；不要把 CSS 层级、生成 class 或内部 React 结构作为主要 locator。

### 版本与兼容性 caveat

- Playwright 会配套管理浏览器二进制；升级 npm package 时应同步执行官方浏览器安装并缓存对应版本，不能只升级 Node package。
- 当前官方 release notes 页面显示 Playwright 1.62；版本升级应同时回归 Chromium、Firefox、WebKit、trace、认证 storageState 和 CI Docker 环境。
- 重试会掩盖 flaky；CI 必须报告 flaky 分类并追踪其趋势，不能把提高 retries 当成稳定性修复。

### 官方来源

- [Playwright Test Configuration](https://playwright.dev/docs/test-configuration)
- [Playwright Fixtures](https://playwright.dev/docs/test-fixtures)
- [Playwright Retries](https://playwright.dev/docs/test-retries)
- [Playwright Continuous Integration](https://playwright.dev/docs/ci)
- [Playwright Accessibility testing](https://playwright.dev/docs/accessibility-testing)
- [Playwright Web server](https://playwright.dev/docs/test-webserver)
- [Playwright Authentication](https://playwright.dev/docs/auth)
- [Playwright Test reporters](https://playwright.dev/docs/test-reporters)
- [Playwright Trace viewer](https://playwright.dev/docs/trace-viewer)
- [Playwright release notes](https://playwright.dev/docs/release-notes)
- [Playwright 官方仓库](https://github.com/microsoft/playwright)

## 15. Monorepo 包边界与目录职责

### 官方事实

- pnpm workspace 提供 monorepo 的依赖和锁文件管理；workspace: 协议可以保证本地包引用。
- TypeScript Project References 用于拆分项目、加强逻辑隔离和改善构建。
- TanStack Start 规定应用路由集中在 src/routes；assistant-ui architecture 将 UI、runtime、backend/agent 和 integration/protocol 分层。
- ESLint flat config 的 files/basePath/ignores 能按目录和文件类型施加规则；Vitest projects 能为不同 package/环境提供独立测试配置。

### 本项目设计建议

建议的职责划分如下，目录名是设计建议而不是任一上游框架的强制目录：

| 目录/包 | 允许依赖 | 应禁止 |
| --- | --- | --- |
| apps/web/src/routes | TanStack Router/Start route API、client-safe loader 数据、server route handler | Aegra graph 实现、数据库模型、浏览器直连密钥 |
| apps/web/src/features/chat | assistant-ui、React、agent integration 的类型 | 自定义 SSE parser、直接读 process.env secret |
| apps/web/src/server | Start server functions/server routes、服务端 HTTP client、系统会话 | 被浏览器 bundle 直接导入 |
| apps/web/src/components | React、assistant-ui primitives、apps/web 本地 feature | FastAPI/Aegra SDK 细节 |
| packages/contracts | TypeScript 类型、JSON-safe schema、API DTO | React、Node stream、数据库、密钥、运行时单例 |
| apps/agent | Python、uv、Aegra、LangGraph graph | pnpm workspace 依赖、前端代码 |
| apps/api | Python、uv、FastAPI、领域服务 | assistant-ui 状态、浏览器路由 |

包边界必须由 package.json exports、TypeScript project references、ESLint import boundary 和 CI build/test 共同验证。仅靠目录名称不能形成真实边界。

关于共享领域包：如果 medical-core 只承载 Python 领域规则/基础设施，则不应被 apps/web 直接 import；如果确实需要跨语言共享，只共享稳定的协议契约，并将 contracts 与 server-only domain core 分开。这个结论是本项目设计建议，不是 TanStack、React 或 Aegra 的官方规定。

### 版本与兼容性 caveat

- pnpm 的 workspace 链接、TypeScript 的 project references、Vite 的 bundler resolution 和 TanStack Start 的 route generation 必须在同一个 monorepo 中一起验证；任何一个配置改变都可能影响包边界。
- 不要因为 pnpm 可以链接任意 workspace package，就把 server-only package 作为 web 依赖；能够解析不代表能够安全打包。

### 官方来源

- [pnpm Workspaces](https://pnpm.io/workspaces)
- [pnpm package.json](https://pnpm.io/package_json)
- [TypeScript Project References](https://www.typescriptlang.org/docs/handbook/project-references.html)
- [TanStack Start Routing](https://tanstack.com/start/latest/docs/framework/react/guide/routing.md)
- [assistant-ui architecture](https://www.assistant-ui.com/docs/architecture)
- [ESLint Configuration Files](https://eslint.org/docs/latest/use/configure/configuration-files)
- [Vitest Test Projects](https://vitest.dev/guide/projects)

## 16. SSR、路由、流式与状态的综合运行时方案

### 官方事实

- TanStack Start 同时提供文件路由、full-document SSR、streaming、server routes 和 server functions。
- React 提供 hydrateRoot 与 renderToReadableStream；Vite 将 SSR API 定义为低层能力，Start 负责更高层集成。
- assistant-ui LangGraph runtime 以 graph state 为事实来源；本项目通过官方 adapter 与最小 JS SDK Client 处理 stream、load、interrupt 和 checkpoint 相关能力。
- Aegra/LangGraph 提供 thread/run/checkpoint 持久化和 SSE/Protocol v2 流式能力，恢复游标取决于使用的端点。

### 本项目设计建议

推荐的请求生命周期：

1. 浏览器请求 chat 路由；TanStack Start 在服务端完成路由匹配、身份检查、首屏 metadata 和非实时 thread 摘要，SSR 输出应用 shell。
2. 客户端 hydration 完成后，才创建 assistant-ui RuntimeProvider 和 LangGraph stream runtime。SSR 不创建不可复用的 agent stream。
3. 用户提交消息后，assistant-ui `useStreamRuntime` 通过同源 Start server route 调用 Aegra Agent Protocol v2。浏览器端不直接拼接 Aegra 内网 URL，也不解析 Aegra 内部事件。
4. Aegra 执行 graph，更新 thread checkpoint，并通过官方 v2 SSE transport 返回 messages、values、tools、lifecycle、custom 或 interrupt 信息。
5. assistant-ui 从 graph state 渲染消息、metadata、interrupt 和取消状态；React state 只承担必要的 UI 暂态。
6. 连接中断时由官方 v2 transport 按 `seq`/`since` 和内置重连机制恢复；运行取消由 `useStream().stop()` 发送官方 command。若产品选择断线后继续后台运行，使用 `disconnect()`/`stop({ cancel: false })`，不把它与用户主动取消混为一谈。
7. 刷新页面时，route 重新确认身份和 thread 权限，assistant-ui 的 load 从 Aegra 恢复 messages/interrupts；不从浏览器缓存重建 durable state。

该方案有意把两种 streaming 分开：

- **文档/页面 streaming**：TanStack Start/React 用于 SSR shell 和非实时页面数据。
- **Agent streaming**：Aegra/LangGraph SSE 由 assistant-ui LangGraph adapter 管理。

这样可以避免把长时间 agent run 绑定在首次 HTML 请求上，也避免在 Start server function 的普通序列化边界中传递长连接。

### 版本与兼容性 caveat

- SSR shell 的成功不证明 hydration、SSE、thread reload 或 checkpoint edit 正确；这些必须分别测试。
- Python LangGraph SDK、JS LangGraph SDK、Aegra SSE、Protocol v2 和 assistant-ui adapter 的事件/恢复语义必须按实际依赖版本建立契约测试。

### 官方来源

- [TanStack Start Overview](https://tanstack.com/start/latest/docs/framework/react/overview.md)
- [TanStack Start Server Routes](https://tanstack.com/start/latest/docs/framework/react/guide/server-routes.md)
- [React hydrateRoot](https://react.dev/reference/react-dom/client/hydrateRoot)
- [React renderToReadableStream](https://react.dev/reference/react-dom/server/renderToReadableStream)
- [assistant-ui LangGraph runtime](https://www.assistant-ui.com/docs/runtimes/langgraph/overview)
- [LangGraph Streaming API](https://docs.langchain.com/langgraph-platform/streaming)
- [Aegra Streaming](https://docs.aegra.dev/guides/streaming)

## 17. 配置、环境变量与安全边界

### 官方事实

- TanStack Start 和 Vite 都区分服务端环境变量与客户端公开环境变量；Vite 的 VITE_ 前缀会被打包进客户端。
- TanStack Start server functions/server routes 可以在服务端读取环境变量；官方环境变量文档提醒 edge runtime 要在请求时读取。
- Aegra 使用 aegra.json，并支持 AEGRA_CONFIG 指定配置文件；auth 和 CORS 是显式配置能力。
- pnpm 和 Node 官方文档提供 packageManager、engines 和运行时版本约束。

### 本项目设计建议

配置分层如下：

| 配置类别 | 示例职责 | 允许位置 |
| --- | --- | --- |
| Node/pnpm 版本 | Node 24、pnpm 11、package manager pin | 根 package.json、Docker、CI |
| Start/Vite 公开配置 | public app name、非敏感 feature flag、公开同源路径 | VITE_ 变量和 web build config |
| Start server-only 配置 | Aegra/FastAPI 内网 URL、代理超时、服务端凭据 | server route/handler 的 request-time env |
| Aegra 运行配置 | graph、auth、HTTP、worker、broker、数据库 | Aegra 服务自己的 aegra.json/secret store |
| 测试配置 | test baseURL、browser projects、fixture accounts | Vitest/Playwright config 与 CI secret |

- Aegra API key、JWT/session secret、FastAPI 内网地址、provider credentials 和数据库连接串永远不放入 VITE_ 变量，也不进入 assistant-ui client helper。
- .env.local、.env.*.local 和认证 storage state 不提交；生产 secret 由部署平台/compose secret 机制注入。
- 配置解析和校验在服务端启动或请求边界完成；错误信息不得把密钥、完整 cookie 或内部 URL 返回到浏览器。
- server route 只提供明确的 allowlist endpoint，不能做任意 URL proxy；流式响应需要设置正确的 content type、连接关闭和超时策略，但具体 header 应由使用的上游官方 API 和部署代理共同验证。

### 版本与兼容性 caveat

- Start/Vite 的公开变量前缀、edge request-time env 和 Node 24 本地 process.env 的行为不能互相替换。
- Aegra 配置的默认 no-auth 只适合受控开发环境；生产配置必须显式开启本系统认证/授权。

### 官方来源

- [TanStack Start Environment Variables](https://tanstack.com/start/latest/docs/framework/react/guide/environment-variables.md)
- [Vite Env Variables and Modes](https://vite.dev/guide/env-and-mode.md)
- [Aegra Configuration](https://docs.aegra.dev/reference/configuration)
- [Aegra Authentication](https://docs.aegra.dev/guides/authentication)
- [pnpm package.json](https://pnpm.io/package_json)
- [Node.js Environment Variables](https://nodejs.org/download/release/latest-v22.x/docs/api/environment_variables.html)

## 18. 可访问性、注释、命名与编码规范

### 官方事实

- React 官方文档通过组件、HTML 常见元素和事件 API 支持标准语义元素与属性；Rules of React 规定组件/Hooks 的纯度和 Hooks 调用规则。
- React 官方提供 eslint-plugin-react-hooks；它可以对 Rules of Hooks 和 effect dependencies 等问题进行静态检查。
- assistant-ui 官方以 primitives 和 runtime 分层；UI 层通过 runtime context 读写，不直接访问 backend/agent。
- Playwright 官方 accessibility 文档明确指出自动化检测不能覆盖全部可访问性问题，推荐自动扫描、人工评估和包容性用户测试结合。
- ESLint flat config、Prettier config 和 TypeScript strict/verbatimModuleSyntax 为 JavaScript/TypeScript 的一致代码质量提供了官方工具基础。

### 本项目设计建议：可访问性

- 优先使用原生语义元素和正确的 label/button/form 结构；消息、发送、取消、重试、interrupt approval 和错误状态必须有可操作的键盘路径。
- 流式输出区域使用明确的状态表达，避免每个 token 都造成焦点跳转；发送后焦点、取消后焦点和错误后的焦点恢复要通过真实浏览器测试验证。
- 对 assistant-ui primitives 做一次键盘、焦点、读屏和窄屏布局审查；不要因为组件来自上游就跳过本项目页面组合层的可访问性测试。
- 固定显示医疗免责声明：AI生成内容仅供参考，不可替代医嘱，请以医生诊断为准。它应在聊天页面和生成内容附近可见、可读，并不依赖流式消息成功。
- 自动化 accessibility scan 只作为回归门；关键路径仍需要人工键盘/读屏检查。

### 本项目设计建议：注释和文档

- 上游官方文档没有规定本项目必须使用中文还是英文注释；团队应统一一种主语言。建议业务决策、风险和边界使用中文，API 名称、包名和标准术语保留英文。
- 注释解释“为什么、约束是什么、何时可以删除”，不重复显而易见的代码；复杂的 SSE 恢复、认证桥接、checkpoint 分支和兼容性 workaround 必须写出原因。
- 导出给其他 package 使用的类型、函数、server route contract 和测试 fixture 应有简短 JSDoc/文档注释；内部实现不为每一行添加注释。
- TODO/FIXME 需要关联可追踪的任务或说明阻塞条件；临时兼容代码必须写明受影响的上游版本和删除条件。
- 生成文件（如 routeTree.gen.ts）不手工添加注释、不手工编辑；应在生成器或源路由处说明规则。

### 本项目设计建议：命名与编码

- React 组件使用 PascalCase；自定义 Hook 使用 use 前缀；普通函数/变量使用 camelCase；类型、接口和组件 props 类型使用 PascalCase；公开常量按团队统一的 SCREAMING_SNAKE_CASE 或 camelCase 约定，不混用。
- 路由文件名遵循 TanStack Router file-based routing 约定；路由参数、pathless layout、grouped route 不通过自定义字符串拼接表达。
- 测试文件统一使用 *.test.ts/tsx 或 *.spec.ts/tsx；测试名称描述行为和结果，而不是被测私有函数。
- 包名使用小写短横线，导出入口稳定；server-only 与 client-safe 文件后缀/目录边界保持一致，避免跨边界隐式导入。
- 所有 TypeScript package 使用 strict 和明确的 type import；不使用 any 逃避跨服务契约，不把未校验的 unknown 直接写入 UI state。
- ESLint 负责 bug/hook/边界规则，Prettier 负责格式，TypeScript 负责静态类型，Vitest/Playwright 负责行为；不让一个工具承担另一个工具的职责。

### 版本与兼容性 caveat

- 注释、命名和覆盖率阈值属于本项目团队规范，不应写成 React、TypeScript、ESLint 或 Playwright 的官方强制标准。
- React/assistant-ui/Playwright 升级后要重新检查键盘焦点、ARIA/语义属性、流式状态和生成内容渲染；静态 lint 通过不等于可访问性通过。

### 官方来源

- [React Rules of React](https://react.dev/reference/rules)
- [React common components](https://react.dev/reference/react-dom/components/common)
- [React eslint-plugin-react-hooks](https://react.dev/reference/eslint-plugin-react-hooks)
- [assistant-ui architecture](https://www.assistant-ui.com/docs/architecture)
- [Playwright Accessibility testing](https://playwright.dev/docs/accessibility-testing)
- [ESLint Configuration Files](https://eslint.org/docs/latest/use/configure/configuration-files)
- [Prettier Configuration](https://prettier.io/docs/configuration)
- [TypeScript strict](https://www.typescriptlang.org/tsconfig/strict.html)

## 19. 测试分层与覆盖范围

### 官方事实

- Vitest 适合 Vite 驱动的 unit/integration 测试，支持 projects、不同 test environment、mocking 和 coverage。
- Playwright Test 提供真实浏览器、fixtures、projects、webServer、retries、trace、认证状态和 CI sharding。
- Playwright 官方 accessibility 指南要求自动检查与人工评估结合。
- assistant-ui、LangGraph SDK 和 Aegra 官方文档分别定义了 runtime、stream、interrupt、checkpoint 和 thread 状态的可观察边界。

### 本项目设计建议

测试层次如下：

| 层次 | 工具 | 必测内容 |
| --- | --- | --- |
| 类型/静态 | TypeScript、ESLint、Prettier check | package boundary、类型导入、hooks、格式和生成文件 |
| 单元 | Vitest/node | contracts、URL/权限决策、事件归一化、错误映射、状态选择器 |
| React 组件 | Vitest/jsdom | composer、message parts、loading/error/interrupt、免责声明和键盘交互 |
| 服务端集成 | Vitest/node | Start server route、身份透传、Aegra/FastAPI proxy、SSE 关闭/错误和超时 |
| 浏览器 E2E | Playwright | SSR/hydration、路由、真实表单、流式 UI、取消、刷新、权限和错误 |
| 可访问性 | Playwright + 官方文档示例方法 + 人工 | 语义、键盘、焦点、状态播报、对比度/标签问题的回归 |
| 发布 smoke | Playwright | 生产 build/preview、Node 24、Docker/CI、外部 API 配置和浏览器安装 |

覆盖率不采用单一“全项目百分比”作为唯一质量标准。建议将协议、权限和代理作为最高风险区域，将 UI 视觉细节与真实浏览器行为结合，将生成物/配置胶水明确排除并记录原因。任何阈值都属于本项目门禁，不是 Vitest 或 Playwright 官方默认。

### 版本与兼容性 caveat

- 真实 Aegra/模型外部 API 不应成为每次 unit run 的随机依赖；集成和发布 smoke 才使用受控外部环境，其他测试用稳定的协议 fixture。
- E2E 的 retries、mock response 和 storageState 不能掩盖真实的 thread 权限错误；测试报告必须能区分产品失败、环境失败和 flaky。

### 官方来源

- [Vitest Getting Started](https://vitest.dev/guide/)
- [Vitest Test Projects](https://vitest.dev/guide/projects)
- [Vitest Mocking](https://vitest.dev/guide/mocking)
- [Vitest Coverage](https://vitest.dev/guide/coverage)
- [Playwright Configuration](https://playwright.dev/docs/test-configuration)
- [Playwright Fixtures](https://playwright.dev/docs/test-fixtures)
- [Playwright Authentication](https://playwright.dev/docs/auth)
- [Playwright Continuous Integration](https://playwright.dev/docs/ci)
- [assistant-ui LangGraph runtime](https://www.assistant-ui.com/docs/runtimes/langgraph/overview)
- [Aegra Streaming](https://docs.aegra.dev/guides/streaming)

## 20. 版本、锁定与升级策略

### 官方事实

- 研究日期的官方页面状态包括：React 文档显示 19.2；Vite 文档显示 8 系列并要求 Node 20.19+ 或 22.12+；TypeScript 首页显示 7.0；pnpm 文档显示 11.x 且要求 Node 22；Vitest 文档显示 4.1.10；ESLint 文档版本选择器显示 v10.8.0、v9.39.5 和 v8.57.1；Playwright release notes 显示 1.62。这里的 Node 20/22 仅是上游工具的最低运行时条件，不是本项目的目标版本；项目统一锁定 Node 24，仍需执行实际兼容性门禁。
- TanStack Start 官方文档仍标注 Release Candidate；assistant-ui LangGraph 文档使用了带 unstable 前缀的 stream factory；Aegra 官方 feature matrix 和 Agent Protocol 文档对未实现能力有明确标注。
- 研究时点的发布元数据显示：`@assistant-ui/react-langchain 0.0.20`、`@assistant-ui/react 0.14.28`、`@langchain/react 1.0.29`、`@langchain/langgraph-sdk 1.9.28`、`aegra-api 0.9.24`；这些是复核快照，不替代项目 lockfile。
- `@assistant-ui/react-langchain 0.0.20` 的 peer 约束要求 `@langchain/react ^1.0.2`；`@langchain/react 1.0.29` 固定依赖 `@langchain/langgraph-sdk 1.9.28`。其 `useStream` 文档和实现明确采用 v2-native `ThreadStream`，默认内置 SSE transport。Aegra `0.9.24` 提供与之匹配的 v2 `/commands`、`/stream/events` 和 state endpoints。

### 本项目设计建议

- 生产依赖使用固定 major/minor/patch 或经审查的精确 lockfile；不在 Docker、CI 或配置文档中使用无约束的 latest。
- Node 24、pnpm 11、Vite 8、TanStack Start RC、React 19、TypeScript 6.0.3、ESLint flat config、Vitest 4 和 Playwright 1.62 作为一个候选兼容基线；正式实现前以实际锁定版本做一次 clean install/build/test。
- 升级顺序建议是：先升级 Node/pnpm 基线，再升级 Vite/Start/Vitest 构建组，再升级 React/assistant-ui，最后升级 ESLint/Prettier/Playwright；每次只改变一个主要兼容组。
- 每次升级必须验证：
  - pnpm frozen-lockfile 安装；
  - TypeScript project references；
  - ESLint flat config 和 React hooks；
  - Prettier check；
  - Start SSR/hydration、server route 和环境变量；
  - assistant-ui `useStreamRuntime` hydration/submit/respond/stop/load checkpoint；
  - Aegra Agent Protocol v2 SSE、`since` 断线恢复、命令响应和认证；
  - Vitest projects/coverage；
  - Playwright 浏览器安装、认证、trace 和 CI workers。
- 对上游不稳定 API（例如 assistant-ui 的 unstable API、TanStack Start RC、Aegra 当前 Protocol v2 限制）保留薄适配边界和版本契约测试；不要把不稳定调用散落到业务组件。

### 版本与兼容性 caveat

- “当前官方文档显示的版本”是研究时点快照，不是永久承诺；实现时必须以锁文件、发布说明和目标运行环境再次确认。
- Node 24 是用户指定基线；后续 major 升级必须重新验证 Node、Vite、TanStack Start、assistant-ui、TypeScript、Playwright 和 Docker 镜像的兼容性。
- 任何版本升级都不能只看安装成功；必须验证流式、SSR、认证和浏览器行为，因为这些能力跨越多个运行时和服务。

### 官方来源

- [Node.js Previous Releases](https://nodejs.org/en/about/previous-releases)
- [Vite Getting Started](https://vite.dev/guide.md)
- [pnpm Installation](https://pnpm.io/next/installation)
- [React 官方文档](https://react.dev/)
- [TypeScript 官方首页](https://www.typescriptlang.org/)
- [ESLint 官方文档](https://eslint.org/docs/latest/)
- [Vitest 官方文档](https://vitest.dev/guide/)
- [Playwright Release notes](https://playwright.dev/docs/release-notes)
- [TanStack Start Overview](https://tanstack.com/start/latest/docs/framework/react/overview.md)
- [assistant-ui LangGraph runtime](https://www.assistant-ui.com/docs/runtimes/langgraph/overview)
- [Aegra Feature support](https://docs.aegra.dev/feature-support)

## 21. 官方来源索引

以下链接均为各项目官方网站、官方文档站或官方源代码仓库：

### Aegra

- [Aegra docs](https://docs.aegra.dev)
- [Aegra llms.txt](https://docs.aegra.dev/llms.txt)
- [Aegra GitHub](https://github.com/aegra/aegra)

### LangGraph / Agent Server / SDK / Protocol

- [LangGraph OSS overview](https://docs.langchain.com/oss/python/langgraph)
- [LangSmith Agent Server overview](https://docs.langchain.com/langsmith/agent-server-overview)
- [LangGraph SDK reference](https://docs.langchain.com/langgraph-platform/sdk)
- [LangGraph streaming](https://docs.langchain.com/langgraph-platform/streaming)
- [LangGraph auth](https://docs.langchain.com/langgraph-platform/auth)
- [Protocol v2 command](https://docs.langchain.com/langsmith/agent-server-api/streaming/protocol-v2-command)
- [Protocol v2 event stream SSE](https://docs.langchain.com/langsmith/agent-server-api/streaming/protocol-v2-event-stream-sse)

### assistant-ui

- [assistant-ui docs](https://www.assistant-ui.com/docs)
- [assistant-ui architecture](https://www.assistant-ui.com/docs/architecture)
- [assistant-ui LangGraph runtime](https://www.assistant-ui.com/docs/runtimes/langgraph/overview)
- [assistant-ui LangGraph quickstart](https://www.assistant-ui.com/docs/runtimes/langgraph/quickstart)
- [assistant-ui LangGraph streaming](https://www.assistant-ui.com/docs/runtimes/langgraph/streaming)
- [assistant-ui GitHub](https://github.com/assistant-ui/assistant-ui)

### TanStack Start / React / Vite

- [TanStack Start overview](https://tanstack.com/start/latest/docs/framework/react/overview.md)
- [TanStack Start routing](https://tanstack.com/start/latest/docs/framework/react/guide/routing.md)
- [TanStack Start server functions](https://tanstack.com/start/latest/docs/framework/react/guide/server-functions.md)
- [TanStack Start server routes](https://tanstack.com/start/latest/docs/framework/react/guide/server-routes.md)
- [React Learn](https://react.dev/learn)
- [React Reference](https://react.dev/reference)
- [Vite guide](https://vite.dev/guide.md)
- [Vite SSR](https://vite.dev/guide/ssr.md)
- [Vite env and modes](https://vite.dev/guide/env-and-mode.md)

### Node.js / pnpm / TypeScript

- [Node.js releases](https://nodejs.org/en/about/previous-releases)
- [Node.js v22 API docs](https://nodejs.org/download/release/latest-v22.x/docs/api/)
- [pnpm installation](https://pnpm.io/next/installation)
- [pnpm workspaces](https://pnpm.io/workspaces)
- [pnpm package.json](https://pnpm.io/package_json)
- [pnpm CI](https://pnpm.io/continuous-integration)
- [TypeScript Handbook](https://www.typescriptlang.org/docs/handbook/intro.html)
- [TypeScript Project References](https://www.typescriptlang.org/docs/handbook/project-references.html)
- [TypeScript TSConfig reference](https://www.typescriptlang.org/tsconfig/)

### ESLint / Prettier

- [ESLint configuration files](https://eslint.org/docs/latest/use/configure/configuration-files)
- [ESLint configure](https://eslint.org/docs/latest/use/configure/)
- [ESLint version support](https://eslint.org/docs/latest/use/version-support)
- [typescript-eslint getting started](https://typescript-eslint.io/getting-started/)
- [Prettier configuration](https://prettier.io/docs/configuration)
- [Prettier ignore](https://prettier.io/docs/ignore)
- [Prettier CLI](https://prettier.io/docs/cli)
- [Prettier integrating with linters](https://prettier.io/docs/integrating-with-linters)

### Vitest / Playwright

- [Vitest guide](https://vitest.dev/guide/)
- [Vitest projects](https://vitest.dev/guide/projects)
- [Vitest coverage](https://vitest.dev/guide/coverage)
- [Vitest mocking](https://vitest.dev/guide/mocking)
- [Playwright configuration](https://playwright.dev/docs/test-configuration)
- [Playwright fixtures](https://playwright.dev/docs/test-fixtures)
- [Playwright retries](https://playwright.dev/docs/test-retries)
- [Playwright CI](https://playwright.dev/docs/ci)
- [Playwright accessibility testing](https://playwright.dev/docs/accessibility-testing)
- [Playwright web server](https://playwright.dev/docs/test-webserver)
- [Playwright authentication](https://playwright.dev/docs/auth)
- [Playwright release notes](https://playwright.dev/docs/release-notes)
