---
kind: ticket
label: wayfinder:research
status: closed
parent: ../map.md
assignee: codex
depends_on: []
research_file: ../../research/agent-and-frontend-stack.md
title: Official Aegra, Agent Protocol v2, assistant-ui, and frontend-stack research
---

## Question

What do the official documents for Aegra, Agent Protocol v2, LangGraph Server/SDK, assistant-ui's LangChain React runtime, TanStack Start, React, Vite, Node.js, pnpm, TypeScript, ESLint, Prettier, Vitest, and Playwright recommend for runtime integration, routing, state, streaming, accessibility, builds, dependency boundaries, and tests?

## Resolution

Aegra is the independent Python 3.14/uv Agent Protocol server and owns LangGraph assistant, thread, run, checkpoint, recovery, and Agent Protocol v2 streaming state. The browser integration uses TanStack Start's same-origin server route as an authentication and routing boundary, while FastAPI remains the source of truth for application identity, authorization, medical business APIs, and domain data.

The web app uses React, Vite, Node.js 24, TypeScript 6, pnpm, and Turborepo. Turborepo only orchestrates JavaScript/TypeScript tasks; uv owns Python dependencies and commands. The frontend uses assistant-ui's official `@assistant-ui/react-langchain/useStreamRuntime`, which wraps `@langchain/react` v1 `useStream` and `@langchain/langgraph-sdk` `ThreadStream` for Agent Protocol v2. It consumes Aegra's `/state`, `/stream/events`, and `/commands` contracts through SSE.

The application must not implement a custom runtime, protocol bridge, SSE parser, command envelope, content-block reducer, `ExternalStoreRuntime`, or checkpoint protocol. `@assistant-ui/react-langgraph` is not the target adapter because its documented helper uses legacy `runs.stream`; it remains only a compatibility/reference path. The application may add the official remote thread-list adapter and the Conversation-to-Aegra `thread_id` mapping required by product navigation. Aegra's no-auth mode is not a production option; the existing application session and authorization model remains authoritative.

The selected dependency versions are research snapshots, not permanent compatibility guarantees. Lock exact versions and run contract tests for v2 commands/events, state hydration, `since` reconnect, cancellation, interrupts, checkpoint editing, authorization, TanStack SSR/hydration, and browser E2E behavior before implementation is considered ready.

## Evidence

- [Agent and frontend stack research](../../research/agent-and-frontend-stack.md)
- [Architecture](../../architecture.md)
- [Specification](../../spec.md)
- [Native Agent Protocol v2 runtime ADR](../../adr/0058-assistant-ui-uses-native-agent-protocol-v2-runtime.md)
