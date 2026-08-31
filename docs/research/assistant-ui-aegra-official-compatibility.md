# `@assistant-ui/react-langgraph` 与 Aegra/LangGraph Server 官方兼容性结论

> 历史复核说明：本文只审计 `@assistant-ui/react-langgraph@0.14.13` 及其 `unstable_createLangGraphStream`。它准确记录了该包仍使用 legacy `runs.stream` 的事实，但不再代表 MedicalRAG 的浏览器方案。项目当前方案由 [ADR 0058](../adr/0058-assistant-ui-uses-native-agent-protocol-v2-runtime.md) 和 [Agent Protocol v2 官方兼容性研究](agent-protocol-v2-official-compatibility.md) 定义，使用 `@assistant-ui/react-langchain/useStreamRuntime`。

## 复核范围

- 访问日期：2026-07-26。
- assistant-ui `main`：`@assistant-ui/react-langgraph` `0.14.13`，`@assistant-ui/react` `0.14.28`，commit [`396ea1f`](https://github.com/assistant-ui/assistant-ui/commit/396ea1fda2cbee9a254daba7531a50d5ac62b961)。
- Aegra `main`：`aegra-api` `0.9.24`，commit [`d142457`](https://github.com/aegra/aegra/commit/d142457a95aa61e638ccfd9af8ddaee86108db7e)。
- LangGraph JS SDK `main`：`@langchain/langgraph-sdk` `1.9.28`，commit [`a41e418`](https://github.com/langchain-ai/langgraphjs/commit/a41e4185dd663092e1d622b43844ff5130d6fd6c)。

本次复核同时以当前官方文档页面和发布包元数据为准：

- [assistant-ui LangGraph Runtime](https://www.assistant-ui.com/docs/runtimes/langgraph/overview)、[Quickstart](https://www.assistant-ui.com/docs/runtimes/langgraph/quickstart)、[Streaming](https://www.assistant-ui.com/docs/runtimes/langgraph/streaming)、[Interrupts](https://www.assistant-ui.com/docs/runtimes/langgraph/interrupts)、[Threads](https://www.assistant-ui.com/docs/runtimes/langgraph/threads)。
- [Aegra 文档索引](https://docs.aegra.dev/llms.txt)、[Streaming](https://docs.aegra.dev/guides/streaming)、[Threads and state](https://docs.aegra.dev/guides/threads-and-state)、[Migration](https://docs.aegra.dev/migration)、[OpenAPI](https://docs.aegra.dev/openapi.json)。
- [LangGraph JS SDK README](https://github.com/langchain-ai/langgraphjs/blob/main/libs/sdk/README.md)、[legacy runs](https://github.com/langchain-ai/langgraphjs/blob/main/libs/sdk/docs/runs.md)、[recommended v2 streaming](https://github.com/langchain-ai/langgraphjs/blob/main/libs/sdk/docs/streaming.md)。

## 重点结论

### 1. `useLangGraphRuntime`：只有 `stream` 必选，线程胶水仍由应用提供

`UseLangGraphRuntimeOptions` 的 `stream` 是必选；`create`、`load`、`delete`、`getCheckpointId`、`eventHandlers` 和 thread-list adapter 都是可选类型。但使用远端 Aegra/LangGraph Server 时：

- `create` 通常由应用调用 `client.threads.create()`，并返回 `{ externalId: thread_id }`。
- `load` 由应用调用 `client.threads.getState()`，把 `state.values.messages` 和中断信息映射为 runtime 所需结构。
- `getCheckpointId` 由应用根据 `client.threads.getHistory()` 匹配消息历史；没有它就没有 edit/regenerate。
- thread picker、search、delete 等需要应用提供 `unstable_threadListAdapter` 或对应回调。

官方证据（访问日期均为 2026-07-26）：

- [assistant-ui types.ts](https://github.com/assistant-ui/assistant-ui/blob/396ea1fda2cbee9a254daba7531a50d5ac62b961/packages/react-langgraph/src/types.ts)：回调类型定义。
- [assistant-ui useLangGraphRuntime.ts](https://github.com/assistant-ui/assistant-ui/blob/396ea1fda2cbee9a254daba7531a50d5ac62b961/packages/react-langgraph/src/useLangGraphRuntime.ts)：无 `create` 时 external ID 仍可能为 `undefined`。
- [assistant-ui quickstart](https://www.assistant-ui.com/docs/runtimes/langgraph/quickstart)：官方示例显式实现 `create` 与 `load`。
- [assistant-ui interrupts](https://www.assistant-ui.com/docs/runtimes/langgraph/interrupts)：checkpoint callback 与 edit/regenerate 约束。

### 2. `unstable_createLangGraphStream`：只封装 `client.runs.stream`

helper 的职责非常窄：

- 调用 `config.initialize()` 获取 external thread ID。
- 默认传递 `streamMode: ["messages", "updates", "custom"]`。
- 默认传递 `onDisconnect: "cancel"`。
- 转发 `input`、`abortSignal`、`command`、`checkpoint` 和 `runConfig`。
- 最终调用 `client.runs.stream(externalId, assistantId, payload)`。

它不负责创建/加载/删除线程、鉴权、thread list、checkpoint history 匹配、run polling/join、`streamSubgraphs`、run-level metadata/context，也不接入 v2 `client.threads.stream`。

官方证据：

- [assistant-ui createLangGraphStream.ts](https://github.com/assistant-ui/assistant-ui/blob/396ea1fda2cbee9a254daba7531a50d5ac62b961/packages/react-langgraph/src/createLangGraphStream.ts)：client 只要求 `runs.stream`，并展示全部 payload 映射。
- [LangGraph SDK RunsClient.stream](https://github.com/langchain-ai/langgraphjs/blob/a41e4185dd663092e1d622b43844ff5130d6fd6c/libs/sdk/src/client/runs/index.ts#L25-L120)：对应 legacy `POST /threads/{thread_id}/runs/stream`。

### 3. Aegra legacy runs API：与 adapter 核心路径兼容

Aegra 官方实现提供：

- `POST /threads/{thread_id}/runs/stream`
- `POST /threads/{thread_id}/runs`
- `POST /threads/{thread_id}/runs/wait`
- `GET /threads/{thread_id}/runs/{run_id}/join`
- `GET /threads/{thread_id}/runs/{run_id}/stream`
- run 查询、列表、取消和删除 API

其 legacy SSE 支持 `values`、`updates`、`messages`、`messages-tuple`、`custom`、`events` 和 `debug`。Aegra 还会内部启用 debug/updates 来跟踪 checkpoint 和 interrupt；未显式请求 updates 时，interrupt update 会按兼容规则映射为 values。`messages/partial`、`messages/complete`、`metadata` 和 custom events 均有对应实现。

官方证据：

- [Aegra README](https://github.com/aegra/aegra/blob/d142457a95aa61e638ccfd9af8ddaee86108db7e/README.md#L28-L32)：声明使用相同 LangGraph SDK/API，并支持 legacy 与 v2 streaming。
- [Aegra runs API](https://github.com/aegra/aegra/blob/d142457a95aa61e638ccfd9af8ddaee86108db7e/libs/aegra-api/src/aegra_api/api/runs.py#L44-L140)：create 与 create-and-stream。
- [Aegra run wait/join/reconnect](https://github.com/aegra/aegra/blob/d142457a95aa61e638ccfd9af8ddaee86108db7e/libs/aegra-api/src/aegra_api/api/runs.py#L265-L427)：wait、join、existing-run stream 与 Last-Event-ID。
- [Aegra streaming guide](https://github.com/aegra/aegra/blob/d142457a95aa61e638ccfd9af8ddaee86108db7e/docs/guides/streaming.mdx#L33-L109)：stream modes、custom events 和事件类型。
- [Aegra graph streaming](https://github.com/aegra/aegra/blob/d142457a95aa61e638ccfd9af8ddaee86108db7e/libs/aegra-api/src/aegra_api/services/graph_streaming.py#L133-L157)：debug/updates/interrupt 兼容逻辑。
- [Aegra message streaming](https://github.com/aegra/aegra/blob/d142457a95aa61e638ccfd9af8ddaee86108db7e/libs/aegra-api/src/aegra_api/services/graph_streaming.py#L357-L447)：tuple、partial/complete 与 interrupt remap。

### 4. Threads、state、checkpoint、interrupt：server 有能力，但映射仍由应用完成

Aegra 实现 `threads.create/search/update/delete`、`state`、指定 checkpoint state 和 history。`ThreadState` 包含 `values`、`tasks`、`interrupts`、`metadata` 和 checkpoint 信息，满足 assistant-ui `load` 所需的核心数据。

assistant-ui 的 resume 最小路径是 `command: { resume: string }`；helper 将其转发给 SDK，Aegra 的 `RunCreate` 接受 command。需要注意：LangGraph SDK 的 `Command.resume` 是 `unknown`，但 assistant-ui 当前公开的 `LangGraphCommand` 将其收窄为 `string`；结构化 resume、多中断按 ID 响应等高级场景需要应用直接调用 SDK 或自定义 bridge。

官方证据：

- [Aegra threads API](https://github.com/aegra/aegra/blob/d142457a95aa61e638ccfd9af8ddaee86108db7e/libs/aegra-api/src/aegra_api/api/threads.py#L153-L180)：thread CRUD。
- [Aegra state API](https://github.com/aegra/aegra/blob/d142457a95aa61e638ccfd9af8ddaee86108db7e/libs/aegra-api/src/aegra_api/api/threads.py#L320-L407)：current state。
- [Aegra checkpoint/history API](https://github.com/aegra/aegra/blob/d142457a95aa61e638ccfd9af8ddaee86108db7e/libs/aegra-api/src/aegra_api/api/threads.py#L565-L758)：checkpoint 与 history。
- [Aegra ThreadState](https://github.com/aegra/aegra/blob/d142457a95aa61e638ccfd9af8ddaee86108db7e/libs/aegra-api/src/aegra_api/models/threads.py#L121-L133)：`values/tasks/interrupts/checkpoint` 字段。
- [assistant-ui LangGraphCommand](https://github.com/assistant-ui/assistant-ui/blob/396ea1fda2cbee9a254daba7531a50d5ac62b961/packages/react-langgraph/src/useLangGraphMessages.ts)：assistant-ui 的 command 类型。
- [LangGraph SDK Command](https://github.com/langchain-ai/langgraphjs/blob/a41e4185dd663092e1d622b43844ff5130d6fd6c/libs/sdk/src/types.ts#L29-L46)：SDK 支持 `resume?: unknown`。
- [Aegra RunCreate](https://github.com/aegra/aegra/blob/d142457a95aa61e638ccfd9af8ddaee86108db7e/libs/aegra-api/src/aegra_api/models/runs.py#L30-L64)：Aegra command/resume 输入。

### 5. Agent Protocol v2：Aegra 支持，但当前 helper 不直接接入

Aegra v2 提供：

- `POST /threads/{thread_id}/stream/events`
- `POST /threads/{thread_id}/commands`
- thread-scoped channels、lifecycle、content-block messages、`input.requested`/`input.respond` 和同一 stream 上的 HITL resume。

但 assistant-ui helper 仍然只调用 `client.runs.stream`；LangGraph SDK 的 v2 入口是 `client.threads.stream`。因此 Aegra v2 的兼容性不能理解为当前 assistant-ui helper 已自动覆盖 v2 channels、content-block lifecycle 或结构化 HITL resume。需要 v2 专属能力时，应用仍需自定义 runtime stream/bridge。

### 6. 最新 LangGraph JS SDK 的推荐路径与本项目的取舍

`@langchain/langgraph-sdk` `1.9.28` 的官方 README 和 streaming 文档已经把
`client.threads.stream()` 定为新代码的推荐 v2 API，并将 `client.runs.stream()`
标记为 legacy。这个事实不改变本项目的接入结论：当前
`@assistant-ui/react-langgraph` `0.14.13` 的官方
`unstable_createLangGraphStream` 类型只要求 `runs.stream`，实现也明确调用
`client.runs.stream()`。因此本项目必须同时记录这两个事实：

1. Aegra 需要启用并测试 legacy `POST /threads/{thread_id}/runs/stream`，因为它是当前 assistant-ui 官方适配器的直接合同。
2. 不应为了追随 SDK 的 v2 推荐路径而把 `client.threads.stream()` 直接塞进 assistant-ui。v2 返回的是 `ThreadStream`，不是 adapter 所需的 `AsyncGenerator<{ event, data }>`；若强行使用，就需要自行做事件投影、消息组装、interrupt/resume 和生命周期桥接，反而重新引入本项目明确要避免的自定义协议层。
3. v2 可以作为独立的后续互操作/能力验证路径保留，但不作为本项目浏览器聊天主路径，除非未来 assistant-ui 官方 adapter 原生改用 v2。

这是版本锁定下的兼容性决策，不是声称 legacy API 永久优于 v2；升级 assistant-ui 或 SDK 时必须重新运行协议合同测试。

### 7. “仍需自行实现”的准确清单

| 仍需由 MedicalRAG 实现 | 不应重复实现 |
| --- | --- |
| `Client` 初始化、Aegra URL、assistant ID 和认证请求边界 | SSE 解码、Last-Event-ID/重连基础机制 |
| `create` / `load`，或完整 `unstable_threadListAdapter` | assistant-ui runtime、消息累加与 LangChain 消息转换 |
| 业务线程与 Aegra `thread_id` 的映射、Workspace 授权和列表展示 | `values` / `updates` / `custom` / `messages` 事件分发 |
| 需要编辑/重新生成时的 `getCheckpointId` 与历史匹配 | AbortSignal 取消传递、运行队列和基础 interrupt 状态处理 |
| 同源代理、Cookie/Authorization 转发和安全策略 | Aegra 的 threads/runs/checkpoint 存储与运行调度 |
| Python LangGraph 图、Ragent 业务节点、Milvus Hybrid Retrieval、证据与安全策略 | Aegra 的 Agent Protocol HTTP/SSE 服务实现 |

因此，“需要自行实现”仍然存在，但范围是应用生命周期和业务接入；不存在一个需要自行开发的 Aegra 专用流协议 adapter。

官方证据：

- [Aegra v2 event endpoints](https://github.com/aegra/aegra/blob/d142457a95aa61e638ccfd9af8ddaee86108db7e/libs/aegra-api/src/aegra_api/api/event_streaming.py#L1-L10)：v2 路径说明。
- [Aegra v2 route implementation](https://github.com/aegra/aegra/blob/d142457a95aa61e638ccfd9af8ddaee86108db7e/libs/aegra-api/src/aegra_api/api/event_streaming.py#L91-L167)：events/commands、channel 校验与 feature gate。
- [Aegra v2 SDK tests](https://github.com/aegra/aegra/blob/d142457a95aa61e638ccfd9af8ddaee86108db7e/libs/aegra-api/tests/e2e/test_event_streaming/test_sdk_v2_e2e.py#L171-L215)：`input.requested` 与 resume。
- [LangGraph SDK threads.stream](https://github.com/langchain-ai/langgraphjs/blob/a41e4185dd663092e1d622b43844ff5130d6fd6c/libs/sdk/src/client/threads/index.ts#L433-L497)：v2 thread-centric client。
- [assistant-ui helper](https://github.com/assistant-ui/assistant-ui/blob/396ea1fda2cbee9a254daba7531a50d5ac62b961/packages/react-langgraph/src/createLangGraphStream.ts)：明确调用 `client.runs.stream`。

## 关键 caveat

- **认证不是 helper 的职责。** SDK 通过 `apiUrl`、`apiKey`、`defaultHeaders`、`onRequest` 配置请求；Aegra 配置 auth 后所有核心 API 需要认证，未配置时为 no-auth mode。应用仍需实现 token/header 或 server proxy。
- **subgraphs 不是 helper 的完整配置面。** Aegra `RunCreate` 支持 `stream_subgraphs`，但 `unstable_createLangGraphStream` 没有对应 option；需要 subgraph stream 时应自定义 payload/stream。
- **run metadata/context 不会自动转发。** helper 转发的是 SDK `config`，不是独立的 run-level `metadata`/`context`；Aegra 对 run metadata 还有 32 key、primitive value、字符串长度等校验。
- **取消主路径兼容，显式 action 有差异。** helper/Aegra create-and-stream 都默认 disconnect cancel；但 SDK cancel 类型是 `interrupt | rollback`，Aegra cancel endpoint 当前接受 `cancel | interrupt`，不要假设 `rollback` 完全等价。
- **Aegra Thread JSON 不是 LangGraph Cloud Thread 的全字段复刻。** Aegra 的 `Thread` 主要提供 id/status/metadata/owner/timestamps；assistant-ui 基于 `thread_id`/`metadata` 的 adapter 可用，但依赖完整 Cloud Thread 字段的代码需要单独验证。

官方证据：

- [LangGraph SDK ClientConfig](https://github.com/langchain-ai/langgraphjs/blob/a41e4185dd663092e1d622b43844ff5130d6fd6c/libs/sdk/src/client/base.ts)；[Aegra authentication guide](https://docs.aegra.dev/guides/authentication)；[Aegra no-auth mode](https://docs.aegra.dev/guides/authentication#no-auth-mode)。访问日期：2026-07-26。
- [Aegra `stream_subgraphs`](https://github.com/aegra/aegra/blob/d142457a95aa61e638ccfd9af8ddaee86108db7e/libs/aegra-api/src/aegra_api/models/runs.py#L74-L78)；[assistant-ui helper options](https://github.com/assistant-ui/assistant-ui/blob/396ea1fda2cbee9a254daba7531a50d5ac62b961/packages/react-langgraph/src/createLangGraphStream.ts)。访问日期：2026-07-26。
- [Aegra run metadata validation](https://github.com/aegra/aegra/blob/d142457a95aa61e638ccfd9af8ddaee86108db7e/libs/aegra-api/src/aegra_api/models/runs.py#L80-L126)；[assistant-ui payload mapping](https://github.com/assistant-ui/assistant-ui/blob/396ea1fda2cbee9a254daba7531a50d5ac62b961/packages/react-langgraph/src/createLangGraphStream.ts)。访问日期：2026-07-26。
- [assistant-ui disconnect default](https://github.com/assistant-ui/assistant-ui/blob/396ea1fda2cbee9a254daba7531a50d5ac62b961/packages/react-langgraph/src/createLangGraphStream.ts)；[Aegra cancel endpoint](https://github.com/aegra/aegra/blob/d142457a95aa61e638ccfd9af8ddaee86108db7e/libs/aegra-api/src/aegra_api/api/runs.py#L430-L481)。访问日期：2026-07-26。
- [Aegra Thread model](https://github.com/aegra/aegra/blob/d142457a95aa61e638ccfd9af8ddaee86108db7e/libs/aegra-api/src/aegra_api/models/threads.py#L36-L49)；[LangGraph SDK Thread schema](https://github.com/langchain-ai/langgraphjs/blob/a41e4185dd663092e1d622b43844ff5130d6fd6c/libs/sdk/src/schema.ts#L193-L224)。访问日期：2026-07-26。

## 最终判断

**Aegra/LangGraph Server 已承担 server-side 的 threads、runs、SSE、state/checkpoint persistence 和 interrupt 基础设施；应用不应重复实现这些协议。**

**但 assistant-ui 当前 helper 不是完整 server lifecycle client：应用仍需提供 client/auth、thread create/load/list/delete、state 映射和 checkpoint history 匹配；v2 专属能力及 helper 未暴露的高级 payload 仍需应用层 bridge。**
