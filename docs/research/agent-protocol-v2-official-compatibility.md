# Agent Protocol v2、Aegra 与 assistant-ui 官方兼容性研究

- 研究日期：2026-07-26
- 研究范围：Aegra Agent Protocol v2、`@langchain/langgraph-sdk`、`@langchain/react`、`@assistant-ui/react-langchain`、`@assistant-ui/react-langgraph`。
- 目标：在不自定义 assistant-ui runtime、Agent Protocol bridge、SSE parser 或事件 reducer 的前提下，确定 Aegra v2 浏览器主路径。

> **计划变更（2026-08-01）：** 本文是历史调研快照。按 [ADR 0064](../adr/0064-uv-manages-python-314-runtime.md)，Python 运行时基线从 3.12 提高到 3.14；正文中 `aegra-api` 的 `>=3.12` 要求被 3.14 满足但需在 3.14 上重新验证。

## 结论

本项目采用：

```text
@assistant-ui/react-langchain/useStreamRuntime
    -> @langchain/react/useStream
    -> @langchain/langgraph-sdk ThreadStream
    -> Aegra Agent Protocol v2 HTTP/SSE
```

这条路径满足：

- 浏览器使用 assistant-ui 官方 runtime；
- Agent Protocol v2 是实际生产流协议；
- 不自行实现 runtime、SSE 解码、content-block 装配、命令 envelope、重连游标或协议转换。

`@assistant-ui/react-langgraph` 不属于该路径。它的
`unstable_createLangGraphStream` 当前明确调用 legacy `client.runs.stream()`。

## 版本快照

| 包/服务 | 版本 | 事实 |
| --- | --- | --- |
| `@assistant-ui/react` | `0.14.28` | assistant-ui 核心 runtime/UI |
| `@assistant-ui/react-langchain` | `0.0.20` | 官方 `useStreamRuntime` adapter |
| `@langchain/react` | `1.0.29` | v2-native React `useStream` |
| `@langchain/langgraph-sdk` | `1.9.28` | 被 `@langchain/react` 固定依赖，提供 `ThreadStream` |
| `@assistant-ui/react-langgraph` | `0.14.13` | legacy `runs.stream` adapter，不用于浏览器主路径 |
| `aegra-api` | `0.9.24` | Aegra Agent Protocol server，Python `>=3.12` |

版本来源：npm registry、PyPI 和上游官方仓库，均于 2026-07-26 复核。版本是方案快照，实施时仍必须提交 lockfile 并运行合同测试。

## 官方事实

### 1. assistant-ui 的两个 LangGraph 相关包不是同一条协议路径

`@assistant-ui/react-langgraph@0.14.13` 的官方 helper 只要求一个具有
`runs.stream` 的 client，源码最终调用：

```ts
client.runs.stream(threadId, assistantId, payload)
```

因此它消费的是 legacy `POST /threads/{thread_id}/runs/stream`，不是 Aegra
v2 的 thread-scoped `/stream/events`。

`@assistant-ui/react-langchain@0.0.20` 的官方 README 和源码则明确说明：
它把 `@langchain/react` 的 `useStream` 暴露为 assistant-ui runtime。

一手来源：

- [react-langgraph `createLangGraphStream.ts`](https://github.com/assistant-ui/assistant-ui/blob/main/packages/react-langgraph/src/createLangGraphStream.ts)
- [react-langchain README](https://github.com/assistant-ui/assistant-ui/blob/main/packages/react-langchain/README.md)
- [react-langchain `useStreamRuntime.ts`](https://github.com/assistant-ui/assistant-ui/blob/main/packages/react-langchain/src/useStreamRuntime.ts)
- [react-langchain 0.0.20 registry metadata](https://registry.npmjs.org/@assistant-ui%2freact-langchain/0.0.20)

### 2. `@langchain/react` v1 的 `useStream` 是 v2-native

官方 `@langchain/react` v1 README 将 `useStream` 定义为 v2-native，并说明它提供：

- thread lifecycle 和 hydration；
- `values`、`messages`、`toolCalls`、`interrupts` 等根投影；
- content-block 消息组装；
- cancellation、interrupt resume 和 reconnect；
- 内置 SSE transport。

其 v1 `useStream` 实现创建 `ThreadStream`，不是 legacy `runs.stream`。内置
SSE transport 的默认路径为：

- `GET /threads/{thread_id}/state`；
- `POST /threads/{thread_id}/stream/events`；
- `POST /threads/{thread_id}/commands`。

一手来源：

- [`@langchain/react` README](https://github.com/langchain-ai/langgraphjs/blob/main/libs/sdk-react/README.md)
- [`useStream` 文档](https://github.com/langchain-ai/langgraphjs/blob/main/libs/sdk-react/docs/use-stream.md)
- [transport 文档](https://github.com/langchain-ai/langgraphjs/blob/main/libs/sdk-react/docs/transports.md)
- [`useStream` 源码](https://github.com/langchain-ai/langgraphjs/blob/main/libs/sdk-react/src/use-stream.ts)
- [HTTP/SSE transport 源码](https://github.com/langchain-ai/langgraphjs/blob/main/libs/sdk/src/client/stream/transport/http.ts)

### 3. LangGraph JS SDK 的 `ThreadStream` 直接实现 v2

`@langchain/langgraph-sdk@1.9.28` 的 `ThreadsClient.stream()`返回
`ThreadStream`，并使用 `ProtocolSseTransportAdapter`。该 adapter 的默认路径
就是 `/threads/:thread_id/stream/events`；command 通过同一 thread 的
`/commands` 端点提交。v2 stream 以 `channels` 订阅，使用 `since` 恢复。

一手来源：

- [`ThreadsClient.stream`](https://github.com/langchain-ai/langgraphjs/blob/main/libs/sdk/src/client/threads/index.ts)
- [`ProtocolSseTransportAdapter`](https://github.com/langchain-ai/langgraphjs/blob/main/libs/sdk/src/client/stream/transport/http.ts)
- [`ThreadStream` 类型与模块](https://github.com/langchain-ai/langgraphjs/blob/main/libs/sdk/src/client/stream/types.ts)
- [`@langchain/langgraph-sdk` 1.9.28 registry metadata](https://registry.npmjs.org/@langchain%2flanggraph-sdk/1.9.28)

### 4. Aegra 原生提供相同的 v2 endpoints

Aegra 官方 v2 streaming 文档和源码提供：

- `POST /threads/{thread_id}/commands`：`run.start`、`input.respond`；
- `POST /threads/{thread_id}/stream/events`：按 channel 过滤的 SSE；
- SSE envelope：`type`、`seq`、`event_id`、`method`、`params`；
- content-block 消息事件：`message-start`、`content-block-delta`、`message-finish`；
- lifecycle 事件：started、completed、failed、interrupted；
- `seq`/`since` 断线恢复。

Aegra 文档还说明 v2 HTTP/SSE + commands 是当前 SDK/React `useStream()`
使用的路径；WebSocket 与部分其他 protocol commands 尚未实现。因此本项目
固定内置 `transport: "sse"`，不选择 WebSocket。

一手来源：

- [Aegra Streaming guide](https://docs.aegra.dev/guides/streaming)
- [Aegra v2 route source](https://github.com/aegra/aegra/blob/main/libs/aegra-api/src/aegra_api/api/event_streaming.py)
- [Aegra API `pyproject.toml`](https://github.com/aegra/aegra/blob/main/libs/aegra-api/pyproject.toml)
- [Aegra 0.9.24 PyPI metadata](https://pypi.org/pypi/aegra-api/0.9.24/json)

## 事实与设计推断的分界

### 官方事实

1. `react-langgraph` 的 helper 走 `runs.stream`。
2. `react-langchain` 的 `useStreamRuntime` 包装 `@langchain/react/useStream`。
3. `@langchain/react/useStream` v1 使用 v2-native `ThreadStream` 和内置 SSE。
4. Aegra 提供 `state`、`stream/events`、`commands` 三类 v2 HTTP endpoints。
5. Aegra v2 当前支持 HTTP/SSE，不应把 WebSocket 当作已支持路径。

### 本项目设计推断

- `@assistant-ui/react-langchain` 是本项目的官方 assistant-ui runtime adapter；它不是 AG-UI adapter，也不需要 Aegra→AG-UI 转换。
- `@assistant-ui/react-ag-ui` 和 `@assistant-ui/react-a2a` 不使用，因为它们分别要求 AG-UI 和 A2A 合同，而不是 Aegra v2 合同。
- 同源 `/api/agent` 代理是应用网络边界，不是 runtime 或 protocol bridge。它只转发 v2 HTTP 请求/响应、保留流式响应并转发系统 session cookie。
- PostgreSQL Conversation↔Aegra `thread_id` 映射、Workspace 授权、Aegra auth handler 和可选官方远程 thread-list adapter 是应用资源接入，不是 runtime 实现。

## 本项目禁止的实现

- 自定义 `AssistantRuntime`；
- 自定义 `AgentServerAdapter` 或 `HttpAgentServerAdapter`（Aegra 已是标准 v2 server）；
- 自定义 SSE 解码、`seq`/`since` 去重或 reconnect loop；
- Aegra v2→AG-UI 事件转换；
- `@assistant-ui/react-langgraph` + `unstable_createLangGraphStream`；
- 浏览器直接调用 `client.runs.stream`；
- 浏览器直接暴露 Aegra 内网地址、API key 或第二套登录体系。

## 允许且必要的应用接入

- `useStreamRuntime({ assistantId, apiUrl: "/api/agent", transport: "sse" })` 配置；
- TanStack Start 同源 proxy route；
- 复用系统 HttpOnly session 的 Aegra auth 校验；
- Conversation↔thread_id 资源映射和权限校验；
- 可选官方 `RemoteThreadListAdapter`，用于会话列表；
- Python LangGraph graph、Ragent 节点、Milvus Hybrid Retrieval、证据和医疗安全策略；
- 使用官方 runtime 暴露的 hooks/selectors 渲染 evidence、intent、safety、citation 和固定医疗免责声明。

## 版本与发布门禁

依赖升级必须作为同一个 v2 compatibility group 处理，并运行：

1. 新 thread hydration；
2. `run.start` command 与首个消息；
3. content-block delta/finish 与最终消息；
4. values、custom、tools、lifecycle channel；
5. stop/cancel 与 disconnect/continue；
6. SSE 中断后的 `since` 恢复；
7. 页面刷新后的 thread hydration；
8. interrupt 的 `input.respond` resume；
9. 系统 session、Workspace authorization 和跨用户 thread isolation；
10. Aegra v2 disabled/old runtime 的明确错误处理。

legacy `runs.stream` 只保留为兼容性回归测试，不作为浏览器生产路径。
