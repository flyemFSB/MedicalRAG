---
kind: ticket
label: wayfinder:grilling
status: closed
parent: ../map.md
assignee: codex
depends_on:
  - ragent-capability-migration-matrix.md
  - monorepo-toolchain-and-package-boundaries.md
  - official-python-backend-and-data-stack-research.md
  - official-agent-and-frontend-stack-research.md
  - official-devops-quality-security-and-observability-research.md
title: Aegra, FastAPI, and arq worker runtime contract
---

## Question

What exact process topology, shared package boundary, Thread/Run handoff, arq job schema, outbox usage, retry/failure-replay policy, idempotency key, and readiness behavior separate Aegra chat execution from FastAPI-owned asynchronous workflows?

## Resolution

- **Process topology** — four runtime processes plus infrastructure. `apps/api` (FastAPI) owns auth, business/admin APIs, and ingestion kickoff; it enqueues only by writing the PostgreSQL outbox and never runs arq consumers or the LangGraph graph. `apps/agent` runs Aegra's Agent Protocol v2 server with the LangGraph chat graph and owns Thread/Run/checkpoint/recovery/streaming; it does not consume arq jobs. `apps/worker` is the arq Worker executing ingestion/extraction/embedding/indexing/reconciliation jobs and the outbox relay, with its own async engine. `apps/web` is the Vite SPA served by Nginx, which proxies `/api` → FastAPI and `/api/agent` → Aegra (SSE passes straight through, [ADR 0070](../../adr/0070-vite-spa-with-nginx-proxy-is-the-frontend-runtime.md)). Each process owns its composition root ([ADR 0060](../../adr/0060-shared-infra-package-and-pruned-package-graph.md)); shared adapters live in `packages/infra`.
- **Thread/Run handoff** — FastAPI maps a PostgreSQL Conversation to an Aegra `thread_id`; the browser talks to Aegra through the same-origin `/api/agent` proxy using the official v2 adapter. The Agent graph persists messages and business run completion through the `infra` run/audit repository. There is no internal HTTP chain between API and Agent for the chat path.
- **arq job schema and outbox** — the outbox table is `(id uuidv7, aggregate_type, aggregate_id, event_type, payload jsonb, created_at, processed_at)` with a partial index on `created_at WHERE processed_at IS NULL`. The job row is written in the same PostgreSQL transaction as the business state change; Redis is never touched inside that transaction. The outbox relay (an arq job in `apps/worker`) claims rows with `FOR UPDATE SKIP LOCKED`, wakes on `pg_notify`, enqueues with `_job_id=f'outbox:{id}'`, and marks `processed_at` after a successful (including de-duplicated) enqueue. Stable job ids derive from the aggregate: `ingest_document:<uuid7>`, `reconcile_mineru:<uuid7>`.
- **Retry / failure-replay** — per-job `max_tries`, `job_timeout`, and `keep_result`; transient errors raise `Retry(defer=…)`; exhausting retries records a terminal failure in `ingestion_runs`/`run_events`. The operator failure/replay view lists terminal-failed runs and supports bounded replay from the last durable stage. Delivery is at-least-once; exactly-once is not promised.
- **Idempotency keys** — deterministic `_job_id` plus consumer-side unique constraints (for example `UNIQUE(ingestion_run_id, stage)`) and safe re-entry from the last durable stage ([ADR 0063](../../adr/0063-arq-replaces-rocketmq-as-the-durable-job-queue.md)).
- **Readiness** — liveness per process; readiness reflects each process's required dependencies (PostgreSQL, Redis, and Milvus where used); the arq worker readiness reflects Redis + PostgreSQL; degraded dependency states surface as degraded health. Langfuse export is fail-open and never gates readiness or business persistence ([ADR 0062](../../adr/0062-langfuse-is-the-only-ai-rag-trace-backend.md)).
