---
status: superseded
superseded_by: 0058-assistant-ui-uses-native-agent-protocol-v2-runtime.md
---

# Python LangGraph is the graph runtime; the web app uses only the necessary JS SDK APIs

> Superseded by [ADR 0058](0058-assistant-ui-uses-native-agent-protocol-v2-runtime.md). The Python LangGraph/Aegra graph decision remains valid; only the browser transport/runtime decision below has been replaced by the native Agent Protocol v2 path.

MedicalRAG uses the Python LangGraph Graph API (`StateGraph`) inside the Aegra agent runtime. LangChain is used beneath the graph for model/provider integrations, prompts, structured output, tools, and retrieval primitives. The top-level workflow is not implemented with LangChain `create_agent`: Ragent's behavior is a controlled Agentic RAG pipeline with explicit short-circuits, bounded fan-out, deterministic evidence fusion, and a terminal streaming stage rather than an open-ended ReAct loop.

The decision to use LangGraph is a runtime decision, not a consequence of the word "Agentic". LangChain alone is sufficient to reproduce one Ragent-style request. LangGraph is required here because the selected deployment contract keeps Aegra as the production Thread/Run runtime and requires checkpoint-aware state, resumable streaming, worker execution, and the graph-shaped server contract consumed by assistant-ui.

The frontend keeps `@assistant-ui/react-langgraph` as the official assistant-ui integration and uses `@langchain/langgraph-sdk` only through the minimal official `Client` surface. Aegra is directly compatible with the adapter's legacy LangGraph Server contract, so no Aegra-specific server adapter, custom SSE parser, or browser runtime is required. The adapter uses `threads.create`, `threads.getState`, and `runs.stream` through `unstable_createLangGraphStream`; the application supplies the `create`/`load` lifecycle callbacks, while `threads.getHistory` and `threads.delete` are added only if message editing or thread deletion is enabled. Although SDK `1.9.28` recommends `client.threads.stream()` for new v2 code, the current assistant-ui helper is explicitly built on `runs.stream`; switching protocols would require a custom event/lifecycle bridge and is therefore out of scope.

## Consequences

- `apps/agent` owns Python `langgraph`, Aegra graph configuration, graph state, nodes, edges, checkpoints, and runtime-facing stream behavior.
- Python `langgraph-sdk` remains available for Python server-side integration and contract tests; the web package also depends on `@langchain/langgraph-sdk` because the user selected the official direct adapter path.
- The web agent-integration module may import only the SDK `Client` and the assistant-ui `unstable_createLangGraphStream` helper. It must not use assistants, store, crons, raw polling, WebSocket transport, or unrelated SDK modules unless a later requirement explicitly adds them.
- The official SDK/adapter owns SSE parsing, message accumulation, abort signals, event routing, thread/run transport, checkpoint transport, and legacy resumable-run mechanics; MedicalRAG does not duplicate those implementations. MedicalRAG still owns the small resource-lifecycle mappings (`Client` construction, `create`, `load`, and optional thread-list/checkpoint callbacks).
- The graph state exposes a `messages` key using LangChain-compatible message shapes. Evidence, intent, safety, business run metadata, and Langfuse correlation data use typed state or supported metadata/data parts and never become an untyped second protocol.
- `packages/medical-core` remains independent of FastAPI, Aegra, LangGraph SDK details, React, and assistant-ui. `packages/infra` owns concrete provider/database/structured-observability adapters; graph nodes are thin bindings around core ports and those injected adapters. Aegra owns the Langfuse integration.
- TypeScript is locked to `6.0.3` for the initial frontend baseline. The lockfile and CI must still verify TypeScript type checking, the Vite SPA production build, Vitest projects, and the official SDK/adapter contract against the selected assistant-ui/Aegra versions.

## Alternatives rejected

- **LangChain only**: behaviorally sufficient for Ragent, but it would require reimplementing the selected Aegra Thread/Run/checkpoint/stream runtime contract in application code.
- **LangChain `create_agent` as the root**: its generic agent loop is broader and less deterministic than the Ragent pipeline; it would make short-circuit, evidence, and safety invariants harder to express and test.
- **A custom assistant-ui runtime or custom browser protocol**: rejected; the official SDK and adapter already provide the required transport and state integration.

## References

- [LangChain products and runtimes](https://docs.langchain.com/oss/python/concepts/products)
- [LangChain agents](https://docs.langchain.com/oss/python/langchain/agents)
- [LangGraph workflows and agents](https://docs.langchain.com/oss/python/langgraph/workflows-agents)
- [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
- [LangGraph streaming](https://docs.langchain.com/oss/python/langgraph/streaming)
- [assistant-ui LangGraph adapter README](https://github.com/assistant-ui/assistant-ui/blob/main/packages/react-langgraph/README.md)
- [assistant-ui LangGraph runtime](https://www.assistant-ui.com/docs/runtimes/langgraph/overview)
- [Aegra threads and state](https://docs.aegra.dev/guides/threads-and-state)
- [Aegra streaming](https://docs.aegra.dev/guides/streaming)
- [TypeScript 6.0.3 metadata](https://registry.npmjs.org/typescript/6.0.3)
