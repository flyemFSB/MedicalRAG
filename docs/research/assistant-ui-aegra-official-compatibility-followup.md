# Aegra Agent Protocol v2 与 assistant-ui 官方适配器兼容性复核（Follow-up）

> 勘误（2026-07-26）：本报告遗漏了 `@assistant-ui/react-langchain@0.0.20`，此前“没有 assistant-ui 官方 v2 runtime”的总括结论不成立。该包的官方 `useStreamRuntime` 包装 `@langchain/react@1.0.29` 的 v2-native `useStream`；后者依赖 `@langchain/langgraph-sdk@1.9.28`，默认通过 `ThreadStream` + `ProtocolSseTransportAdapter` 访问 Agent Protocol v2。Aegra 官方文档明确声明 v2 streaming 原生提供、由最新 LangGraph SDK 及 Vue/React `useStream()` 使用，并给出相同的 `/threads/{id}/commands`、`/threads/{id}/stream/events` 端点。因此，`@assistant-ui/react-langchain` 构成 assistant-ui 官方 runtime 到 Aegra Agent Protocol v2 的直接标准协议连接路径。本项目以 [ADR 0058](../adr/0058-assistant-ui-uses-native-agent-protocol-v2-runtime.md) 为准；下文关于 `react-langgraph`、`react-ag-ui` 和 `react-a2a` 的边界事实仍然有效。

## 复核范围与结论摘要

- 复核日期：2026-07-26。
- 资料范围：仅使用 assistant-ui 官方仓库/文档/发布包、LangChain 官方 LangGraph JS SDK、Aegra 官方仓库/文档/PyPI、AG-UI 官方仓库/发布包、A2A 官方规范/仓库。
- 本报告不修改实现代码；它只记录协议事实、适配器边界和本项目的选型约束。

### 原报告结论（已勘误）

对 `react-langgraph`、`react-ag-ui`、`react-a2a` 三个包的逐项结论仍然有效，但“当前不存在任何 assistant-ui 官方 v2 runtime”的总括结论已被 `@assistant-ui/react-langchain@0.0.20` 推翻。当前可以同时满足以下三项：

1. 使用 Aegra Agent Protocol v2 streaming；
2. 使用 assistant-ui 官方 `@assistant-ui/react-langchain/useStreamRuntime`；
3. 不自定义 runtime、协议桥接、SSE parser 或事件转换。

规范组合是：`@assistant-ui/react-langchain` → `@langchain/react/useStream` → `@langchain/langgraph-sdk ThreadStream` → Aegra v2。以下关于 AG-UI/A2A 需要桥接的分析，不适用于该 v2-native LangChain runtime。

需要区分“官方 runtime 直连”和“零配置”：前者可以满足，后者不成立。应用仍需提供 `apiUrl`、`assistantId` 以及 Aegra 所需的认证配置，并自行决定是否接入 assistant-ui 的线程列表持久化；这些是应用配置或可选的线程列表适配，不是自定义 runtime、SSE parser、事件转换或 Aegra 协议桥接。基础聊天路径不需要另写 v2 生命周期接入代码。

## 版本与官方资料基线

| 组件 | 本次复核版本/固定提交 | 官方证据 |
| --- | --- | --- |
| `@assistant-ui/react-langgraph` | `0.14.13`；assistant-ui commit [`396ea1f`](https://github.com/assistant-ui/assistant-ui/commit/396ea1fda2cbee9a254daba7531a50d5ac62b961) | [package.json](https://github.com/assistant-ui/assistant-ui/blob/396ea1fda2cbee9a254daba7531a50d5ac62b961/packages/react-langgraph/package.json) |
| `@assistant-ui/react-langchain` | `0.0.20` | [发布包 `package.json`](https://unpkg.com/@assistant-ui/react-langchain@0.0.20/package.json)、[发布 README](https://unpkg.com/@assistant-ui/react-langchain@0.0.20/README.md) |
| `@assistant-ui/react-ag-ui` | `0.0.46`；同一 assistant-ui commit | [package.json](https://github.com/assistant-ui/assistant-ui/blob/396ea1fda2cbee9a254daba7531a50d5ac62b961/packages/react-ag-ui/package.json) |
| `@assistant-ui/react-a2a` | `0.2.23`；同一 assistant-ui commit | [README](https://github.com/assistant-ui/assistant-ui/blob/396ea1fda2cbee9a254daba7531a50d5ac62b961/packages/react-a2a/README.md) |
| `@assistant-ui/react-ai-sdk` | `1.4.0` | [assistant-ui 官方仓库](https://github.com/assistant-ui/assistant-ui) |
| `@langchain/react` | `1.0.29`；依赖 `@langchain/langgraph-sdk` `1.9.28` | [发布包 `package.json`](https://unpkg.com/@langchain/react@1.0.29/package.json)、[发布 README](https://unpkg.com/@langchain/react@1.0.29/README.md) |
| `@langchain/langgraph-sdk` | `1.9.28`；LangGraph JS SDK commit [`a41e418`](https://github.com/langchain-ai/langgraphjs/commit/a41e4185dd663092e1d622b43844ff5130d6fd6c) | [Streaming 文档](https://github.com/langchain-ai/langgraphjs/blob/a41e4185dd663092e1d622b43844ff5130d6fd6c/libs/sdk/docs/streaming.md) |
| `@ag-ui/client` / `@ag-ui/core` | `0.0.57` | [`@ag-ui/client` 发布类型](https://unpkg.com/@ag-ui/client@0.0.57/dist/index.d.ts)、[`@ag-ui/core` 发布类型](https://unpkg.com/@ag-ui/core@0.0.57/dist/index.d.ts) |
| `aegra-api` | PyPI `0.9.24`；Aegra commit [`d142457`](https://github.com/aegra/aegra/commit/d142457a95aa61e638ccfd9af8ddaee86108db7e) | [PyPI](https://pypi.org/project/aegra-api/0.9.24/)、[Aegra README](https://github.com/aegra/aegra/blob/d142457a95aa61e638ccfd9af8ddaee86108db7e/README.md) |
| A2A | assistant-ui adapter声明支持 A2A v1.0；A2A 官方规范为独立协议 | [A2A 官方 README](https://github.com/a2aproject/A2A/blob/main/README.md)、[A2A 规范](https://a2a-protocol.org/latest/specification/) |

版本说明：`aegra-api` 是 Python 包，不是 npm 包；不能用 npm registry 的 404 误判 Aegra 不存在或版本缺失。

## 一、三个协议的边界

### 1. Aegra Agent Protocol v2

这是 Aegra 为 LangGraph server/最新 LangGraph SDK 提供的线程级 agent execution/control streaming 协议。Aegra 官方 streaming 文档明确描述了以下合同：

- `POST /threads/{thread_id}/commands`：发送 `run.start`、`input.respond` 等线程命令，返回 JSON response envelope。
- `POST /threads/{thread_id}/stream/events`：按 channel 打开的线程级 SSE 流；它不是单个 run 的独立流。
- SSE 的 `data` 是 Aegra/Agent Protocol v2 envelope，包含 `type`、`seq`、`event_id`、`method`、`params` 等字段。
- `params.data` 使用 content-block/lifecycle 等事件，例如 `message-start`、`content-block-delta`、`message-finish`、`started`、`completed`、`interrupted`。
- 客户端通过 `seq`/`since` 进行恢复，通过 `run.start` 启动运行，通过 `input.respond` 响应中断。

官方证据：

- [Aegra Agent Protocol v2 streaming guide](https://docs.aegra.dev/guides/streaming.md#agent-protocol-v2-event-streaming) 描述 v2 的线程级 stream、两个端点、channels、content-block events 和 SDK 用法。
- [Aegra v2 route source](https://github.com/aegra/aegra/blob/d142457a95aa61e638ccfd9af8ddaee86108db7e/libs/aegra-api/src/aegra_api/api/event_streaming.py) 的模块说明、路由和 `_frame_events` 明确写出 `stream/events`、`commands`、`method`、`seq`、SSE envelope。
- [LangGraph JS SDK streaming 文档](https://github.com/langchain-ai/langgraphjs/blob/a41e4185dd663092e1d622b43844ff5130d6fd6c/libs/sdk/docs/streaming.md) 将 `client.threads.stream(...)` 定义为 thread-centric v2 protocol connection，并将 `client.runs.*` 标为 legacy。

### 2. AG-UI

AG-UI 是独立的 Agent-User Interaction Protocol。AG-UI 官方 README 将其定义为面向 agent 与用户界面的开放、轻量、事件驱动协议；它可以使用 SSE、WebSocket、webhook 等传输，但真正的兼容性来自 AG-UI event/input contract，而不是来自“使用 SSE”这一点。

其事件模型包含例如：

```text
RUN_STARTED
TEXT_MESSAGE_START
TEXT_MESSAGE_CONTENT
TEXT_MESSAGE_END
TOOL_CALL_START / TOOL_CALL_ARGS / TOOL_CALL_END / TOOL_CALL_RESULT
STATE_SNAPSHOT / STATE_DELTA
RUN_FINISHED / RUN_ERROR
```

官方证据：

- [AG-UI 官方 README](https://github.com/ag-ui-protocol/ag-ui/blob/main/README.md) 定义 AG-UI 的定位、事件驱动模型、可用传输和与 A2A 的关系。
- [`@ag-ui/client@0.0.57` 发布类型](https://unpkg.com/@ag-ui/client@0.0.57/dist/index.d.ts) 定义 `AbstractAgent`、`HttpAgent`、`Observable<BaseEvent>`、`RunAgentInput` 和 AG-UI event subscriber；`HttpAgent`不是任意 SSE JSON 的通用解码器。
- [`@ag-ui/core@0.0.57` 发布类型](https://unpkg.com/@ag-ui/core@0.0.57/dist/index.d.ts) 定义标准事件 schema 和事件 discriminator。

Aegra README 中的“Works with AG-UI / CopilotKit”是 Aegra 的产品集成声明；它不能单独证明 Aegra v2 的 wire event 已经是 AG-UI event，也不能证明任意 AG-UI client 可以直接请求 Aegra v2 endpoint。Aegra v2 专门的官方 streaming 文档仍描述其自身的 `method`/`params`/`seq` envelope 和 LangGraph `threads.stream` 客户端合同。

### 3. A2A

A2A（Agent2Agent）是面向 agent-to-agent discovery、communication 和 long-running task collaboration 的独立协议。其官方合同包括：

- Agent Card discovery；
- JSON-RPC 2.0 over HTTP(S)；
- `message:send`、`message:stream` 等方法；
- Task、Task status、Artifact 及其流式更新。

官方证据：

- [A2A 官方 README](https://github.com/a2aproject/A2A/blob/main/README.md) 明确区分 agent-to-agent 互操作、Agent Card、JSON-RPC、SSE streaming、Task 和 Artifact。
- [A2A 官方规范](https://a2a-protocol.org/latest/specification/) 定义协议的 JSON-RPC、Agent Card、Task 和 streaming 数据模型。
- [`@assistant-ui/react-a2a` README](https://github.com/assistant-ui/assistant-ui/blob/396ea1fda2cbee9a254daba7531a50d5ac62b961/packages/react-a2a/README.md) 明确声明该包是 A2A v1.0 集成，并使用 Agent Card、`message:send`/`message:stream`、Task/Artifact 等概念。

### 协议对比

| 维度 | Aegra Agent Protocol v2 | AG-UI | A2A |
| --- | --- | --- | --- |
| 主要目标 | 线程级 agent run、状态、生命周期和中断控制 | agent 与用户界面的实时交互 | 不同 agent 之间发现、协作和任务交换 |
| 典型入口 | `/threads/{id}/commands`、`/threads/{id}/stream/events` | AG-UI agent endpoint，返回 AG-UI events | Agent Card、JSON-RPC `message:send`/`message:stream` |
| 事件/结果 | `method` + `params.data` + `seq`/`event_id`，content-block/lifecycle | `RUN_*`、`TEXT_MESSAGE_*`、`TOOL_CALL_*`、`STATE_*` 等 | Task、Artifact、Task status update、Message |
| assistant-ui 官方包 | `react-langgraph` 当前直接面向 legacy runs API | `react-ag-ui` | `react-a2a` |
| 是否因使用 SSE 自动兼容 | 否 | 否 | 否 |

结论：Aegra Agent Protocol v2、AG-UI、A2A 不能因为都可以使用 SSE，或都含有“agent”字样，就视为同一个协议。

## 二、assistant-ui 官方 adapter 逐项核查

### 1. `@assistant-ui/react-langgraph`

#### 官方事实

`unstable_createLangGraphStream` 的源码把所需 client 类型收窄为：

```ts
type LangGraphStreamClient = {
  runs: Pick<Client["runs"], "stream">;
};
```

其最终调用为：

```ts
return client.runs.stream(externalId, assistantId, payload);
```

helper 自动承担的职责仅包括：

- 从 `config.initialize()` 获取 external thread ID；
- 把 assistant-ui 的 messages/state 映射为 legacy run input；
- 转发 `AbortSignal`、`command`、checkpoint 和 run config；
- 设置默认 legacy `streamMode` 和 `onDisconnect`；
- 把结果交给 assistant-ui 的 LangGraph message/event 处理逻辑。

它不调用 `client.threads.stream()`，也不请求 Aegra v2 的 `/commands` 或 `/stream/events`。

官方证据：

- [assistant-ui `createLangGraphStream.ts`](https://github.com/assistant-ui/assistant-ui/blob/396ea1fda2cbee9a254daba7531a50d5ac62b961/packages/react-langgraph/src/createLangGraphStream.ts) 的类型定义和最后一行调用。
- [LangGraph SDK legacy runs 文档](https://github.com/langchain-ai/langgraphjs/blob/a41e4185dd663092e1d622b43844ff5130d6fd6c/libs/sdk/docs/runs.md) 定义 `runs.stream` 及其 legacy 状态。
- [LangGraph SDK v2 streaming 文档](https://github.com/langchain-ai/langgraphjs/blob/a41e4185dd663092e1d622b43844ff5130d6fd6c/libs/sdk/docs/streaming.md) 定义另一条 `threads.stream` 合同。

#### 生命周期仍需应用接入

`useLangGraphRuntime` 的 `stream` 是必选项；`create`、`load`、`delete`、`getCheckpointId`、事件回调和 thread-list adapter 是应用可提供的生命周期接入点。官方类型和 quickstart 没有把远程业务线程、权限、列表和 checkpoint 历史匹配隐藏在 `unstable_createLangGraphStream` 中。

官方证据：

- [assistant-ui LangGraph types](https://github.com/assistant-ui/assistant-ui/blob/396ea1fda2cbee9a254daba7531a50d5ac62b961/packages/react-langgraph/src/types.ts) 定义 `stream`、`create`、`load`、`delete`、`getCheckpointId` 等选项。
- [assistant-ui LangGraph quickstart](https://www.assistant-ui.com/docs/runtimes/langgraph/quickstart) 展示应用提供 thread create/load 等远程生命周期逻辑。

#### 兼容结论

**不能直接连接 Aegra Agent Protocol v2。** 当前包与 Aegra legacy `/threads/{id}/runs/stream` 的核心合同相容，但与 v2 `client.threads.stream()`/`stream/events` 的 thread stream、content-block envelope 和 command lifecycle 不是同一个输入输出类型。

### 2. `@assistant-ui/react-ag-ui`

#### 官方事实

该包的官方 README 明确写作“AG-UI protocol integration”，使用方式是：

```tsx
const agent = new HttpAgent({ url: AG_UI_AGENT_URL });
const runtime = useAgUiRuntime({ agent });
```

其 `UseAgUiRuntimeOptions` 类型要求 `agent: AbstractAgent`，而不是 LangGraph `Client` 或 Aegra `ThreadStream`。assistant-ui runtime 会消费 `AbstractAgent` 发出的 AG-UI `BaseEvent`。

官方证据：

- [`react-ag-ui` README](https://github.com/assistant-ui/assistant-ui/blob/396ea1fda2cbee9a254daba7531a50d5ac62b961/packages/react-ag-ui/README.md) 说明该包面向 AG-UI-compatible backend。
- [`useAgUiRuntime` 源码](https://github.com/assistant-ui/assistant-ui/blob/396ea1fda2cbee9a254daba7531a50d5ac62b961/packages/react-ag-ui/src/useAgUiRuntime.ts) 把 `options.agent` 传入 `AgUiThreadRuntimeCore`。
- [`react-ag-ui` 类型](https://github.com/assistant-ui/assistant-ui/blob/396ea1fda2cbee9a254daba7531a50d5ac62b961/packages/react-ag-ui/src/runtime/types.ts) 将 `agent` 类型声明为 `@ag-ui/client` 的 `AbstractAgent`，并声明 `RUN_*`、`TEXT_MESSAGE_*`、`TOOL_CALL_*`、`STATE_*` 等 AG-UI event。

#### 兼容结论

**不能直接连接 Aegra v2。** Aegra v2 的 SSE `data` 是：

```json
{
  "type": "event",
  "seq": 2,
  "event_id": "...:2",
  "method": "messages",
  "params": {
    "data": {
      "event": "content-block-delta",
      "index": 0,
      "delta": {"type": "text-delta", "text": "Hello"}
    },
    "namespace": []
  }
}
```

这不是 `@ag-ui/core` 的 `TEXT_MESSAGE_CONTENT` 等 AG-UI event。即使两者都是 SSE，也缺少相同的请求入口、事件 discriminator、run lifecycle 和 resume contract。

### 3. `@assistant-ui/react-a2a`

#### 官方事实

该包的 README 明确声明支持 A2A v1.0，并提供 Agent Card discovery、A2A HTTP client、`message:send`、`message:stream`、Task、Artifact 和 SSE。

#### 兼容结论

**不能连接 Aegra v2。** Aegra v2 没有以 A2A Agent Card/JSON-RPC/Task/Artifact 作为其线程执行入口；它提供的是 Aegra/LangGraph 的 `assistant_id`、thread ID、commands 和 protocol event envelope。若要使用 A2A adapter，必须另行提供 A2A facade，这已经是协议桥接/新增服务，不是直接适配。

### 4. `@assistant-ui/react-ai-sdk` 与其他官方包

- `@assistant-ui/react-ai-sdk` 面向 Vercel AI SDK 的 UI message/data stream 合同，不是 Aegra v2 adapter。
- `@assistant-ui/react-mcp` 属于 MCP 连接/配置能力，不是 Aegra v2 聊天 runtime。
- 截至本次固定的 assistant-ui 官方仓库和发布包，未发现名为 Aegra、Agent Protocol v2 或 Aegra ThreadStream 的专用 adapter；但这不等于没有基于标准 LangGraph v2 协议的官方 runtime。`@assistant-ui/react-langchain` 正是本报告此前遗漏的标准协议路径。

### 5. `@assistant-ui/react-langchain@0.0.20`（遗漏项，当前推荐）

#### assistant-ui 官方发布包事实

该包的官方 README 将自身定义为：包装 `@langchain/react` 的 `useStream`，并将其暴露为 assistant-ui runtime。发布包的 `package.json` 声明 `@langchain/react: ^1.0.2` 为 peer dependency，因而 `@langchain/react@1.0.29` 满足其版本要求。

发布的 [`dist/useStreamRuntime.js`](https://unpkg.com/@assistant-ui/react-langchain@0.0.20/dist/useStreamRuntime.js) 明确：

```js
import { STREAM_CONTROLLER, useChannel, useStream } from "@langchain/react";
// ...
const stream = useStream(options);
// ...
return useExternalStoreRuntime(/* assistant-ui runtime options */);
```

外层 `useStreamRuntime` 再通过 `useRemoteThreadListRuntime` 返回官方 assistant-ui runtime。它自动完成的不是 Aegra 专用转换，而是：

- 将 assistant-ui 消息转换为 LangChain 消息并提交给 `stream.submit()`；
- 将 `stream.messages`、工具调用、interrupt、state 和 custom channel 转换为 assistant-ui 可消费的 projections；
- 将工具结果、reload、edit、cancel、interrupt/respond 接入底层 `useStream`；
- 将 assistant-ui 当前 thread external ID 传给 `useStream`，并支持可选的 `cloud`/thread-list adapter。

#### `@langchain/react@1.0.29` 官方事实

其官方 README 明确称 v1 `useStream` 为 **v2-native**，采用 session-based transport；root hook 负责 thread lifecycle、transport 以及 `values`、`messages`、`toolCalls`、`interrupts` 等投影。发布包 `package.json` 固定依赖 `@langchain/langgraph-sdk: 1.9.28`，而不是旧版 `runs.*` 客户端。

官方发布的 [`dist/use-stream.js`](https://unpkg.com/@langchain/react@1.0.29/dist/use-stream.js) 创建 `StreamController`；该 controller 的官方源码使用 `client.threads.stream(threadId, { assistantId, transport })`。LangGraph JS SDK 的 [`ThreadsClient.stream`](https://github.com/langchain-ai/langgraphjs/blob/a41e4185dd663092e1d622b43844ff5130d6fd6c/libs/sdk/src/client/threads/index.ts) 在默认 SSE transport 下创建 `ProtocolSseTransportAdapter`，其官方实现定义：

- `GET /threads/{thread_id}/state` 用于线程 hydration；
- `POST /threads/{thread_id}/stream/events` 打开按 channel 过滤的 SSE 事件流；
- `POST /threads/{thread_id}/commands` 发送 `run.start`、`input.respond` 等 protocol command。

LangGraph SDK 官方 streaming 文档同时把 `client.threads.stream(...)` 标为推荐的 thread-centric v2 protocol，把 `client.runs.*` 标为 legacy。

#### Aegra 官方事实

Aegra 官方 [streaming guide](https://docs.aegra.dev/guides/streaming.md#agent-protocol-v2-event-streaming) 明确写出：v2 streaming 原生提供给最新 LangGraph JS/Python SDK 及 Vue/React `useStream()` composables；同一节列出的端点正是 `/threads/{thread_id}/commands` 与 `/threads/{thread_id}/stream/events`。Aegra 官方 [event streaming route source](https://github.com/aegra/aegra/blob/d142457a95aa61e638ccfd9af8ddaee86108db7e/libs/aegra-api/src/aegra_api/api/event_streaming.py) 还明确实现了这两个 POST 路由，并规定 v2 SSE frame 是带 `seq`、`event_id`、`method`、`params` 的 protocol event envelope；`/state` 由同一套标准 thread API 用于 hydration。

因此真实调用链是：

```text
@assistant-ui/react-langchain@0.0.20
  useStreamRuntime()
    ↓ official assistant-ui runtime adapter
@langchain/react@1.0.29
  useStream() / StreamController
    ↓ v2-native official React binding
@langchain/langgraph-sdk@1.9.28
  Client.threads.stream() / ThreadStream
    ↓ ProtocolSseTransportAdapter
Aegra Agent Protocol v2
  GET  /threads/{id}/state
  POST /threads/{id}/stream/events
  POST /threads/{id}/commands
```

#### 兼容性判断与边界

**结论：是。** 在 Aegra v2 已启用、运行时满足 Aegra 官方能力检查、`apiUrl`/认证/`assistantId` 配置正确的前提下，`@assistant-ui/react-langchain@0.0.20` 构成 assistant-ui 官方 runtime 直连 Aegra Agent Protocol v2 的路径。这里的“直连”指应用代码不需要实现新的 `AssistantRuntime`、自定义 `AbstractAgent`、SSE parser、事件映射或 `/commands`/`/stream/events` 生命周期；assistant-ui、`@langchain/react` 和 LangGraph SDK 各自的官方层直接串接。

仍由应用负责的只是边界配置和可选业务接入：

- 提供 `apiUrl`、`assistantId`、认证 headers/API key 或官方 `fetch`/caller 配置，并挂载 `AssistantRuntimeProvider`；
- 确保 Aegra v2 flag、底层 LangGraph/native v3 event 能力和用户授权已满足 Aegra 官方要求；
- 如果需要跨会话的 thread list、创建/删除/持久化策略，再提供 assistant-ui 的 `cloud` 或 thread-list adapter；基础聊天示例不要求自定义协议生命周期代码。

上述配置不改变“官方 runtime 直连”的判断，也不把 Aegra v2 误称为 AG-UI 或 A2A。

## 三、兼容矩阵

| 组合 | 直接兼容 | 是否保留 Aegra v2 | 是否需要自定义协议/运行时代码 | 判断 |
| --- | --- | --- | --- | --- |
| `@assistant-ui/react-langchain@0.0.20` + `@langchain/react@1.0.29` + Aegra v2 | 是 | 是 | 否（仅应用配置；线程列表持久化为可选接入） | 推荐；assistant-ui 官方 runtime 通过官方 v2-native LangChain 路径直连 |
| `@assistant-ui/react-langgraph` + Aegra legacy `/runs/stream` | 是 | 否 | 否（生命周期仍需应用接入） | 官方现成路径，但违反 v2 必选 |
| `@assistant-ui/react-langgraph` + Aegra v2 `/stream/events` | 否 | 是 | 是 | 需要把 v2 ThreadStream 投影为 legacy LangGraph events |
| `@assistant-ui/react-ag-ui` + Aegra v2 | 否 | 是 | 是 | 需要自定义 `AbstractAgent`/transport 和 Aegra→AG-UI event mapping |
| `@assistant-ui/react-a2a` + Aegra v2 | 否 | 是 | 是 | 需要 A2A facade；协议语义也发生变化 |
| assistant-ui + Aegra v2 + 自定义 `AssistantRuntime` | 可实现 | 是 | 是 | 能做，但违反“不自定义 runtime” |
| assistant-ui 官方 `useAgUiRuntime` + 自定义 AG-UI `AbstractAgent` | 间接可实现 | 是 | 是；但 runtime 本身仍为官方 | 若允许自定义 transport，这是最小折中 |
| LangGraph 官方 `client.threads.stream`/`useStream` + Aegra v2 | 是 | 是 | 否 | 官方 v2 路径，但不使用 assistant-ui 官方 runtime adapter |

## 四、选型结论与可行替代组合

### 方案 A（推荐）：`react-langchain` 官方 runtime 直连 Aegra v2

```text
@assistant-ui/react-langchain/useStreamRuntime
        ↓
@langchain/react/useStream（v2-native）
        ↓
@langchain/langgraph-sdk Client.threads.stream / ThreadStream
        ↓
ProtocolSseTransportAdapter
        ↓
Aegra Agent Protocol v2
```

该方案同时满足本项目的三项硬约束：使用 Aegra Agent Protocol v2 streaming、使用 assistant-ui 官方 runtime、不自定义 runtime 或协议桥接。应用只需按官方 API 配置 `apiUrl`、`assistantId`、认证和可选 thread-list 持久化；不需要另写 `run.start`、`input.respond`、SSE parser、重连/去重或 Aegra→AG-UI 事件映射。

官方证据：[assistant-ui `react-langchain` README](https://unpkg.com/@assistant-ui/react-langchain@0.0.20/README.md)、[`useStreamRuntime` 发布源码](https://unpkg.com/@assistant-ui/react-langchain@0.0.20/dist/useStreamRuntime.js)、[`@langchain/react` v1 README](https://unpkg.com/@langchain/react@1.0.29/README.md)、[Aegra v2 streaming guide](https://docs.aegra.dev/guides/streaming.md#agent-protocol-v2-event-streaming)。

### 方案 B：只使用 LangGraph 官方 v2 React SDK

直接使用 `@langchain/react/useStream` 或 `@langchain/langgraph-sdk` 的 `Client.threads.stream`，不使用 assistant-ui runtime。协议合同同样完整，但不满足本项目希望使用 assistant-ui 的 UI runtime，因此仅作为最小官方协议验证或故障隔离方案。

### 方案 C：`react-ag-ui` + 自定义 Aegra→AG-UI bridge

```text
@assistant-ui/react-ag-ui/useAgUiRuntime
        ↓
自定义 AbstractAgent / transport / 事件映射
        ↓
@langchain/langgraph-sdk Client.threads.stream
        ↓
Aegra Agent Protocol v2
```

这是间接可实现方案，不是直接兼容；需要自行处理 `seq`/`event_id`/`since`、命令、重连、content-block、工具、状态、生命周期和 interrupt 映射。它违反本项目“不自定义任何 runtime/协议桥接”的选型约束，不采用。

### 方案 D：`react-langgraph` + Aegra legacy streaming

`@assistant-ui/react-langgraph` 的官方合同是 `client.runs.stream`，对应 `/threads/{thread_id}/runs/stream` 等 legacy runs API。它可用于旧服务兼容或回归验证，但不满足“必须使用 Agent Protocol v2 streaming”，不作为主路径。

### 方案 E：A2A facade

在 Aegra v2 后再提供 A2A v1.0 facade，然后使用 `@assistant-ui/react-a2a`。这不是 Aegra v2 的直接消费，会引入 Agent Card、JSON-RPC、Task/Artifact 语义转换和额外服务边界；除非明确需要 agent-to-agent 对外能力，否则不应为了 UI 接入而引入。

## 五、官方事实与推断的分界

### 官方事实

1. Aegra 官方文档和源码提供 `/threads/{id}/commands`、`/threads/{id}/stream/events`，并定义 v2 envelope、channels、content-block/lifecycle 和 thread-scoped streaming。
2. LangGraph JS SDK 官方文档把 `client.threads.stream()` 定义为 v2 thread stream，把 `client.runs.*` 标为 legacy。
3. `@assistant-ui/react-langgraph` 的官方源码要求 `client.runs.stream`，并直接调用它。
4. `@assistant-ui/react-langchain@0.0.20` 的官方 README 和发布源码明确包装 `@langchain/react` 的 `useStream`，并通过 `useExternalStoreRuntime` 暴露 assistant-ui runtime。
5. `@langchain/react@1.0.29` 官方 README 明确将 v1 `useStream` 称为 v2-native；其发布包依赖 `@langchain/langgraph-sdk@1.9.28`。
6. LangGraph SDK 官方 `ThreadsClient.stream` 源码默认创建 `ProtocolSseTransportAdapter`，并使用 `/state`、`/stream/events`、`/commands` 这组 thread-centric v2 路径。
7. Aegra 官方 streaming guide 明确声明 v2 由最新 LangGraph SDK 及 Vue/React `useStream()` 使用；Aegra 官方 route source 实现同一组 v2 endpoints。
8. `@assistant-ui/react-ag-ui` 的官方源码要求 `@ag-ui/client` 的 `AbstractAgent`，并按 AG-UI event 处理消息、工具、状态和生命周期。
9. `@assistant-ui/react-a2a` 的官方 README 面向 A2A v1.0 的 Agent Card、JSON-RPC、Task、Artifact 和 stream。
10. AG-UI 官方 README 将 AG-UI 定义为独立的 Agent-User Interaction Protocol，并明确它与 A2A 的目标不同。

### 基于合同差异的推断

1. `react-langgraph` 不能直接消费 Aegra v2：这是由其输入类型/调用端点与 Aegra v2端点不一致推导出的兼容性结论。
2. `react-ag-ui` 不能把 Aegra v2 envelope 自动当作 AG-UI event：这是由两套事件 discriminator、请求生命周期和数据结构不同推导出的结论。
3. `react-a2a` 不能直接消费 Aegra v2：这是由 A2A Agent Card/JSON-RPC/Task合同与 Aegra commands/thread envelope不一致推导出的结论。
4. Aegra README 的“AG-UI / CopilotKit”说明 Aegra存在相关产品集成，但没有在 v2 streaming 官方合同中声明其输出就是 AG-UI，也没有给出 `@assistant-ui/react-ag-ui` 的直接接入示例。因此不能把该宣传性集成声明扩大解释为“v2 可被 assistant-ui AG-UI adapter 直接消费”。
5. `@assistant-ui/react-langchain` 不是 Aegra 专用 adapter，但由于它无自定义中间层地调用官方 v2-native `useStream`，而 Aegra 官方明确实现并服务该协议，所以“assistant-ui 官方 runtime 直连 Aegra v2”是基于多方官方合同对齐得出的兼容性判断，而不是 `react-langgraph` 或 AG-UI adapter 的事实。
6. “官方仓库当前没有 Aegra 专用 assistant-ui adapter”仍是对本次版本和官方目录的检索结论；它不再等价于“assistant-ui 没有官方 v2 直连路径”，也不是对未来 release 的永久否定。

## 六、对本项目的决策建议

如果“必须 Aegra v2”且“不自定义任何 runtime”是不可改变的，实施计划应固定为方案 A：

- 使用 `@assistant-ui/react-langchain@0.0.20` + `@langchain/react@1.0.29`，并让其解析到 `@langchain/langgraph-sdk@1.9.28`。
- 不使用 `@assistant-ui/react-langgraph` 作为 v2 adapter；它仍是 legacy `runs.stream` 路径。
- 不把 Aegra v2 称为 AG-UI 或 A2A；三者必须在架构图、接口说明和测试合同中分开命名。
- 不实现自定义 `AssistantRuntime`、`AgentServerAdapter`、`AbstractAgent`、SSE parser 或 Aegra→AG-UI 事件映射；只配置官方 runtime 的 API URL、assistant、认证和可选 thread-list adapter。
- 不为满足 assistant-ui UI 而改用 A2A；A2A 是 agent-to-agent 协议，不是 Aegra v2 的别名或兼容层。

Aegra v2 必须保持启用，且必须满足 Aegra 官方能力检查；否则官方 SDK 可能收到 v2 disabled/runtime-too-old 的 503，这属于部署兼容性问题，不是 assistant-ui adapter 缺失。

## 官方来源索引

- [assistant-ui LangGraph stream helper](https://github.com/assistant-ui/assistant-ui/blob/396ea1fda2cbee9a254daba7531a50d5ac62b961/packages/react-langgraph/src/createLangGraphStream.ts)
- [assistant-ui LangGraph types](https://github.com/assistant-ui/assistant-ui/blob/396ea1fda2cbee9a254daba7531a50d5ac62b961/packages/react-langgraph/src/types.ts)
- [assistant-ui LangGraph quickstart](https://www.assistant-ui.com/docs/runtimes/langgraph/quickstart)
- [assistant-ui AG-UI README](https://github.com/assistant-ui/assistant-ui/blob/396ea1fda2cbee9a254daba7531a50d5ac62b961/packages/react-ag-ui/README.md)
- [assistant-ui AG-UI runtime](https://github.com/assistant-ui/assistant-ui/blob/396ea1fda2cbee9a254daba7531a50d5ac62b961/packages/react-ag-ui/src/useAgUiRuntime.ts)
- [assistant-ui A2A README](https://github.com/assistant-ui/assistant-ui/blob/396ea1fda2cbee9a254daba7531a50d5ac62b961/packages/react-a2a/README.md)
- [`@assistant-ui/react-langchain@0.0.20` README](https://unpkg.com/@assistant-ui/react-langchain@0.0.20/README.md)
- [`@assistant-ui/react-langchain@0.0.20` `useStreamRuntime` 发布源码](https://unpkg.com/@assistant-ui/react-langchain@0.0.20/dist/useStreamRuntime.js)
- [`@langchain/react@1.0.29` README](https://unpkg.com/@langchain/react@1.0.29/README.md)
- [`@langchain/react@1.0.29` `useStream` 发布源码](https://unpkg.com/@langchain/react@1.0.29/dist/use-stream.js)
- [LangGraph SDK v2 streaming](https://github.com/langchain-ai/langgraphjs/blob/a41e4185dd663092e1d622b43844ff5130d6fd6c/libs/sdk/docs/streaming.md)
- [LangGraph SDK `ThreadsClient.stream`](https://github.com/langchain-ai/langgraphjs/blob/a41e4185dd663092e1d622b43844ff5130d6fd6c/libs/sdk/src/client/threads/index.ts)
- [LangGraph SDK `ProtocolSseTransportAdapter`](https://github.com/langchain-ai/langgraphjs/blob/a41e4185dd663092e1d622b43844ff5130d6fd6c/libs/sdk/src/client/stream/transport/http.ts)
- [LangGraph SDK `StreamController`](https://github.com/langchain-ai/langgraphjs/blob/a41e4185dd663092e1d622b43844ff5130d6fd6c/libs/sdk/src/stream/controller.ts)
- [LangGraph SDK legacy runs](https://github.com/langchain-ai/langgraphjs/blob/a41e4185dd663092e1d622b43844ff5130d6fd6c/libs/sdk/docs/runs.md)
- [Aegra streaming guide](https://docs.aegra.dev/guides/streaming.md)
- [Aegra v2 event streaming source](https://github.com/aegra/aegra/blob/d142457a95aa61e638ccfd9af8ddaee86108db7e/libs/aegra-api/src/aegra_api/api/event_streaming.py)
- [Aegra README](https://github.com/aegra/aegra/blob/d142457a95aa61e638ccfd9af8ddaee86108db7e/README.md)
- [AG-UI official README](https://github.com/ag-ui-protocol/ag-ui/blob/main/README.md)
- [`@ag-ui/client@0.0.57` types](https://unpkg.com/@ag-ui/client@0.0.57/dist/index.d.ts)
- [`@ag-ui/core@0.0.57` types](https://unpkg.com/@ag-ui/core@0.0.57/dist/index.d.ts)
- [A2A official README](https://github.com/a2aproject/A2A/blob/main/README.md)
- [A2A official specification](https://a2a-protocol.org/latest/specification/)

## 七、纠正后的本项目决策

本项目固定选择上文方案 A，正确主路径是：

```text
@assistant-ui/react-langchain/useStreamRuntime
        ↓
@langchain/react/useStream（v2-native）
        ↓
@langchain/langgraph-sdk ThreadStream + built-in SSE
        ↓
Aegra Agent Protocol v2
```

因此不需要自定义 `AssistantRuntime`、`AgentServerAdapter`、AG-UI
`AbstractAgent`、SSE parser 或 Aegra→AG-UI 事件映射。应用侧仍可实现与协议
无关的同源代理、系统会话校验、Conversation↔thread_id 资源映射和可选的
官方远程线程列表适配器，但这些不能改变或替代官方 v2 transport。
