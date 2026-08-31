# Ragent → MedicalRAG Behavior-Parity Matrix

Behavioral dimension of the Ragent migration matrix (the technical-stack dimension lives in [stack-replacement-matrix.md](stack-replacement-matrix.md)). It records how Ragent's observable **event stream, failure behavior, and admin console routes** are reproduced, per [ADR 0049](../adr/0049-ragent-capability-complete-migration-matrix.md). Status values: `implemented` (reproduced directly), `replaced` (target-native equivalent behavior), `adapted` (exposed through a compatibility port/adapter), `rejected` (typed out-of-scope).

## A. Streaming event vocabulary

Ragent's `StreamCallback` vocabulary → Aegra Agent Protocol v2 typed channels. The target does not reproduce the flat Java callback object; it maps each piece of observable information onto a v2 channel that assistant-ui's official `useStreamRuntime` already consumes ([ADR 0058](../adr/0058-assistant-ui-uses-native-agent-protocol-v2-runtime.md)). Status: **adapted**.

| Ragent stream event | Target in MedicalRAG | Status |
|---|---|---|
| reply-message id | v2 `messages` channel: message id + content-block assembly | adapted |
| content (tokens) | v2 `messages` channel: `content-block-delta` (text/reasoning) | adapted |
| status (queued/running/complete/failed) | v2 `lifecycle` channel; queue status from Redis rate-limit queue | adapted |
| sources / grounding chunks | v2 `values` channel + custom channel carrying Evidence (source id, title, chunk id, snippet, score, citation label) | adapted |
| recommended questions | v2 custom channel `recommended-questions` | adapted |
| errors | v2 `lifecycle` channel error events (typed, scrubbed) | adapted |
| completion | v2 `lifecycle` channel run finished + business `run_events` completion | adapted |

Evidence, intent, slot, and safety metadata ride graph state / custom channels / typed data parts per the specification; the application never invents a second browser protocol ([ADR 0058](../adr/0058-assistant-ui-uses-native-agent-protocol-v2-runtime.md)).

## B. Failure behavior

Ragent's reliability semantics → target equivalents. The observable contract (a request either completes with an answer/guidance/evidence-insufficiency result, or fails with a typed, user-visible reason) is preserved.

| Ragent behavior | Target in MedicalRAG | Status |
|---|---|---|
| Model failover with first-token probing | External Model Router + Redis-backed circuit; outage → deterministic evidence-insufficiency after routing/failover | replaced |
| Three-state circuit breaker (CLOSED/OPEN/HALF_OPEN) | Redis-backed model health circuit with open/half-open recovery | replaced |
| Redis queue-based concurrency limit (ZSET + Lua + Pub/Sub) | Redis rate limiting + queued-request status events (user story 29) | replaced |
| Rate limiting (@ChatRateLimit) | Redis rate limiting at the FastAPI boundary | replaced |
| Task cancellation | Aegra v2 cancellation; orchestrator `Cancelled` terminal state persists run events | adapted |
| Ambiguity short-circuit with guidance | `Guidance` state; clarification message without model call or retrieval mutation | implemented |
| Empty retrieval | `Empty` state; deterministic evidence-insufficiency result | implemented |
| Unknown/malformed classifier output | Empty candidate set or clarification; never a fabricated route | implemented |
| Provider transient errors / retry | Model-router retry + LangGraph `retry_policy` (5xx, exponential backoff, `TimeoutPolicy` on async nodes) | replaced |
| Timeout | `TimeoutPolicy`/`NodeTimeoutError` handled by retry then error_handler (Saga compensation) | replaced |
| Prohibited / clinical-risk request | Safety short-circuit before retrieval ([ADR 0043](../adr/0043-prohibited-individual-requests-short-circuit-before-retrieval.md)) | implemented (MedicalRAG addition) |
| Langfuse exporter failure | Fail-open; degraded observability, never fails a run/state transition/job ack ([ADR 0062](../adr/0062-langfuse-is-the-only-ai-rag-trace-backend.md)) | implemented |
| Ingestion stage failure | Ingestion Run terminal failure + operator failure/replay surface via arq retry/outbox ([ADR 0063](../adr/0063-arq-replaces-rocketmq-as-the-durable-job-queue.md)) | replaced |

## C. Admin console routes

Ragent's operator console pages → MedicalRAG operator routes (Vite SPA + recharts/@antv/g6 per [ADR 0067](../adr/0067-operator-console-charting-recharts-and-g6.md), preview per [ADR 0068](../adr/0068-document-preview-mainstream-per-format-renderers.md)).

| Ragent admin page | Target operator route in MedicalRAG | Status |
|---|---|---|
| Dashboard KPIs | Operator dashboard: ingestion/chat/model/retrieval metrics (recharts) | implemented |
| Knowledge bases | Knowledge base management | implemented |
| Documents / chunks | Document and chunk inspection/editing with provenance | implemented |
| Ingestion pipelines / tasks | Ingestion Run + node logs; partial-failure repair at the correct stage | implemented |
| Intent trees | Intent-tree editor (@antv/g6 graph) with node/example/slot/safety editing | implemented |
| Query-term mapping | Query-term mapping management | implemented |
| Models / settings | Model-target configuration + health; platform model credentials | implemented |
| Traces | Langfuse trace detail for AI/RAG + PostgreSQL business run records (operator opens Langfuse for AI/RAG) | adapted |
| Feedback | Feedback review | implemented |
| Users | User/Workspace management | implemented |
| Change logs (bizlog) | Audit events / operator change log | replaced |
| Sample questions | Recommended-questions configuration | implemented |

## Rejected (typed) behaviors

- MCP parameter extraction, MCP tool routing, URL/Feishu connectors, Ollama/local models, alternate retrieval stores — rejected with typed reasons (see [ADR 0051](../adr/0051-mcp-compatibility-is-out-of-scope.md) and the stack matrix).

## Release gate

This matrix and [stack-replacement-matrix.md](stack-replacement-matrix.md) together form the migration-matrix release gate: a Ragent capability is declared parity-complete only when its row carries a status, a target component, a protocol/data contract, an official-documentation source, and a test seam. The remaining work is fixture/test-seam assignment, tracked by the open testing-quality-and-release-gates decision.
