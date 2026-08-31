---
status: superseded
superseded_by: 0058-assistant-ui-uses-native-agent-protocol-v2-runtime.md
---

# assistant-ui uses the official LangGraph adapter with a minimal JS SDK surface

> Superseded by [ADR 0058](0058-assistant-ui-uses-native-agent-protocol-v2-runtime.md). This document records the rejected legacy `runs.stream` design for historical traceability; it is not the implementation target.

The frontend uses `@assistant-ui/react-langgraph` with `@langchain/langgraph-sdk`'s `Client`, and Aegra is directly compatible with the adapter's legacy LangGraph Server stream contract; no Aegra-specific server adapter or custom stream parser is required. The browser reaches Aegra through the same-origin gateway. The frontend SDK surface is intentionally limited to `Client`, `threads.create`, `threads.getState`, and `runs.stream` through assistant-ui's `unstable_createLangGraphStream`, with the optional `threads.getHistory`/`threads.delete` operations needed for message editing or thread management. The latest SDK documentation recommends `client.threads.stream()` for new v2 integrations, but the current assistant-ui helper explicitly calls `client.runs.stream()`, so this project follows the adapter's legacy contract and does not add a v2-to-assistant-ui bridge. The application still supplies the adapter's `create` and `load` lifecycle callbacks (or a complete `unstable_threadListAdapter`); these are small resource-lifecycle mappings, not a second transport implementation. Assistant discovery/creation, store, cron, raw run polling, Protocol v2 content-block handling, and alternate transports are not part of the browser integration. MedicalRAG keeps authentication, Workspace authorization, medical domain nodes, retrieval, safety policy, model credentials, and MinerU credentials on the server.

## Consequences

- The Aegra endpoint must preserve the LangGraph Server contract for assistants, threads, runs, streaming, cancellation, and resume.
- Medical agent state must expose standard LangGraph message state; evidence, intent, entity, and safety details use compatible metadata or typed UI/data parts rather than a second transport protocol.
- No custom browser streaming protocol, SSE parser, message reducer, or assistant-ui runtime is permitted. The official SDK and adapter own those concerns; application code is limited to Client construction, thread/state lifecycle callbacks, authorization proxying, and domain UI.
- Python `langgraph-sdk` remains available for server-side integration and contract tests; the JS SDK is used only in the web agent-integration module with the minimal surface described above.
- Contract tests exercise the official SDK/adapter path against an Aegra test instance or a protocol-faithful fixture, including `create`, `load`, message streaming, values/updates, cancellation, error, reconnect, and checkpoint behavior. The primary browser path is legacy `runs.stream`; Agent Protocol v2 is tested separately and is not passed directly to the current adapter.

## References

- [assistant-ui LangGraph UI Runtime](https://www.assistant-ui.com/docs/runtimes/langgraph/overview)
- [assistant-ui LangGraph adapter README](https://github.com/assistant-ui/assistant-ui/blob/main/packages/react-langgraph/README.md)
- [Aegra README](https://github.com/aegra/aegra)
