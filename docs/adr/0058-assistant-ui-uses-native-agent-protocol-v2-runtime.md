---
status: accepted
supersedes:
  - 0022-assistant-ui-uses-the-official-langgraph-adapter.md
  - 0057-python-langgraph-graph-runtime-without-js-sdk.md
---

# assistant-ui uses the official v2-native LangChain React runtime

MedicalRAG uses `@assistant-ui/react-langchain`'s `useStreamRuntime` as the
only browser agent runtime. The package officially wraps
`@langchain/react` v1 `useStream`, which uses the v2-native
`@langchain/langgraph-sdk` `ThreadStream` transport. Aegra is consumed through
its native Agent Protocol v2 SSE and command endpoints.

The browser integration does not use `@assistant-ui/react-langgraph`,
`unstable_createLangGraphStream`, `client.runs.stream`,
`@assistant-ui/react-ag-ui`, a custom `AgentServerAdapter`, a custom assistant-ui
runtime, an SSE parser, a v2 event bridge, or a second message reducer.

## Canonical browser path

```text
assistant-ui components
    -> @assistant-ui/react-langchain/useStreamRuntime
    -> @langchain/react/useStream
    -> @langchain/langgraph-sdk ThreadStream + built-in SSE transport
    -> Aegra Agent Protocol v2
```

The built-in transport calls the following Aegra endpoints:

- `GET /threads/{thread_id}/state` for hydration;
- `POST /threads/{thread_id}/stream/events` for channel-filtered SSE;
- `POST /threads/{thread_id}/commands` for `run.start` and interrupt resume.

`transport: "sse"` is the selected transport because Aegra's current v2
implementation supports HTTP/SSE and commands; its v2 WebSocket transport is
not part of the supported path. The browser `apiUrl` is a same-origin
`/api/agent` route proxied to Aegra, so the existing HttpOnly session cookie
remains the only user authentication mechanism.

## Application boundary

The stock runtime owns thread hydration, v2 command envelopes, SSE decoding,
content-block assembly, channel subscriptions, reconnect/since handling,
message projections, tool-call assembly, cancellation, and interrupt resume.
MedicalRAG still owns application configuration and domain behavior:

- `assistantId` and same-origin `apiUrl` configuration;
- the same-origin Nginx/Vite proxy and session forwarding;
- Aegra's auth handler, which validates the existing system session and maps
  it to the Aegra user identity/permissions;
- the mapping between a PostgreSQL Conversation and an Aegra `thread_id`;
- an optional official `RemoteThreadListAdapter` for the product's conversation
  list, if the UI exposes one;
- the Python LangGraph graph, Ragent behavior, Milvus Hybrid Retrieval,
  evidence/safety policy, and domain APIs.

These are application and domain integrations, not a custom runtime or a
custom Agent Protocol implementation.

## Graph/UI contract

The graph exposes a LangChain-compatible `messages` state key. Evidence,
intent, safety, progress, and citation data are exposed through supported
state values, custom channels, or assistant-ui data/UI message facilities;
they are not encoded by a new browser protocol. The fixed medical disclaimer
`AI生成内容仅供参考，不可替代医嘱，请以医生诊断为准` is rendered by the
application UI and is not delayed until generation completes.

## Compatibility and release gate

The initial compatibility baseline is:

- `@assistant-ui/react` `0.14.28`;
- `@assistant-ui/react-langchain` `0.0.20`;
- `@langchain/react` `1.0.29`;
- `@langchain/langgraph-sdk` `1.9.28` (used by `@langchain/react`);
- `aegra-api` `0.9.24`;
- Python `3.14` and a LangGraph version satisfying Aegra's native v3 event
  requirement.

The lockfile and CI must contract-test the v2 path against Aegra: hydration,
run start, token/content-block streaming, values/custom channels, lifecycle
completion, cancellation, reconnect with `since`, refresh hydration, and
interrupt resume. A legacy `runs.stream` test is only a regression/negative
compatibility test; it is not the browser production path.

## References

- [assistant-ui LangChain runtime](https://www.assistant-ui.com/docs/runtimes/langchain)
- [`@assistant-ui/react-langchain` source](https://github.com/assistant-ui/assistant-ui/tree/main/packages/react-langchain)
- [`@langchain/react` useStream](https://github.com/langchain-ai/langgraphjs/blob/main/libs/sdk-react/docs/use-stream.md)
- [`@langchain/react` transports](https://github.com/langchain-ai/langgraphjs/blob/main/libs/sdk-react/docs/transports.md)
- [LangGraph JS SDK ThreadStream](https://github.com/langchain-ai/langgraphjs/blob/main/libs/sdk/src/client/threads/index.ts)
- [Aegra streaming guide](https://docs.aegra.dev/guides/streaming)
- [Aegra v2 event routes](https://github.com/aegra/aegra/blob/main/libs/aegra-api/src/aegra_api/api/event_streaming.py)
