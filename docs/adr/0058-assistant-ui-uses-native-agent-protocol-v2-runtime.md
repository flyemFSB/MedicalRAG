---
status: accepted
supersedes:
  - 0022-assistant-ui-uses-the-official-langgraph-adapter.md
  - 0057-python-langgraph-graph-runtime-without-js-sdk.md
---

# assistant-ui uses the official LangGraph React runtime

MedicalRAG uses `@assistant-ui/react-langgraph` as the only browser agent
runtime. The package officially bridges assistant-ui to LangGraph / Agent
Protocol v2 streams. Aegra is consumed through its native Agent Protocol v2
SSE and command endpoints.

The browser integration does not use a custom `AgentServerAdapter`, a custom
assistant-ui runtime, an SSE parser, a v2 event bridge, or a second message
reducer.

## Canonical browser path

```text
assistant-ui components
    -> @assistant-ui/react-langgraph (useLangGraphRuntime)
    -> @langchain/langgraph-sdk Client
    -> Aegra Agent Protocol v2
```

## Why not the alternatives

- **Custom runtime / protocol bridge**: re-implements v2 envelopes, SSE framing, reconnect, and cancellation; high defect surface on a medical workbench.
- **`@assistant-ui/react-langchain` + `@langchain/react` `useStream`**: superseded by the official LangGraph adapter path now used in this repo.
- **Direct `client.runs.stream` only**: skips assistant-ui thread/message state management the UI already depends on.

## Consequences

- `apps/web` depends on `@assistant-ui/react`, `@assistant-ui/react-langgraph`, `@assistant-ui/react-markdown`, and `@langchain/langgraph-sdk`.
- Python LangGraph / Aegra remain server-side; the browser never owns medical domain rules.
- Evidence and safety metadata ride on message `additional_kwargs.custom` produced by the graph and rendered by assistant-ui components.
