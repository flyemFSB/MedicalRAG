---
kind: ticket
label: wayfinder:grilling
status: closed
parent: ../map.md
assignee: codex
depends_on: []
title: Runtime ownership and streaming boundary
---

## Question

Which runtime owns chat execution, business APIs, persistence, and browser streaming?

## Resolution

Aegra owns LangGraph Thread/Run execution, checkpoints, worker leases, recovery, and Agent Protocol v2 streaming. FastAPI owns authentication, authorization, business APIs, knowledge management, configuration, and domain services. PostgreSQL owns durable business data; Redis owns sessions, short-lived coordination, and the arq job transport; arq executes durable asynchronous workflows. assistant-ui uses the official `@assistant-ui/react-langchain/useStreamRuntime`, which consumes Aegra's native v2 `/state`, `/stream/events`, and `/commands` endpoints through the official `@langchain/react`/`@langchain/langgraph-sdk` SSE transport. No custom assistant-ui runtime, protocol bridge, SSE parser, or message reducer is allowed. A same-origin Start proxy and optional official remote thread-list resource mapping remain application integration, not runtime implementation.

## Evidence

- [Architecture](../../architecture.md)
- [Aegra production runtime ADR](../../adr/0001-aegra-is-the-production-runtime.md)
- [assistant-ui v2 runtime ADR](../../adr/0058-assistant-ui-uses-native-agent-protocol-v2-runtime.md)
