---
kind: ticket
label: wayfinder:grilling
status: closed
parent: ../map.md
assignee:
depends_on:
  - monorepo-toolchain-and-package-boundaries.md
  - aegra-fastapi-arq-worker-runtime-contract.md
  - identity-workspace-and-safety-boundary.md
  - official-agent-and-frontend-stack-research.md
title: Frontend routes, generated contracts, and assistant-ui surface
---

## Question

What Vite SPA route/features structure (TanStack Router), generated API contract, assistant-ui state/data parts, Aegra adapter configuration, accessibility behavior, loading/error/cancellation states, and browser test seams are required?

## Resolution

Use `@assistant-ui/react-langchain@0.0.20` and its official `useStreamRuntime`, backed by `@langchain/react@1.0.29` and the v2-native `@langchain/langgraph-sdk@1.9.28` transport. Configure the built-in SSE branch with `assistantId` and same-origin `apiUrl: "/api/agent"`; do not use `@assistant-ui/react-langgraph`, `unstable_createLangGraphStream`, `runs.stream`, AG-UI, A2A, `HttpAgentServerAdapter`, or any custom runtime/bridge. The same-origin Nginx/Vite proxy forwards the system session to Aegra and preserves the streaming response. If the product needs a conversation picker, implement only the official remote thread-list resource adapter and map PostgreSQL Conversation records to Aegra `thread_id`; this does not replace the runtime. The graph exposes a LangChain-compatible `messages` state key, while evidence, intent, safety, and citations use supported state/custom/data parts. Browser contracts cover hydration, v2 commands, content-block streaming, lifecycle completion, stop/disconnect, `since` reconnect, refresh hydration, and interrupt resume.

## Evidence

- [assistant-ui LangChain runtime](https://www.assistant-ui.com/docs/runtimes/langchain)
- [`@assistant-ui/react-langchain` README](https://github.com/assistant-ui/assistant-ui/blob/main/packages/react-langchain/README.md)
- [`@langchain/react` v2 `useStream`](https://github.com/langchain-ai/langgraphjs/blob/main/libs/sdk-react/docs/use-stream.md)
- [Aegra Agent Protocol v2 streaming](https://docs.aegra.dev/guides/streaming)
- [ADR 0058](../../adr/0058-assistant-ui-uses-native-agent-protocol-v2-runtime.md)
