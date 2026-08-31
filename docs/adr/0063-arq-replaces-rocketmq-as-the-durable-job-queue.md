---
status: accepted
---

# arq replaces RocketMQ as the durable application job queue

> Supersedes [ADR 0050](0050-rocketmq-remains-the-durable-application-message-bus.md).

MedicalRAG executes durable asynchronous application workflows through `arq`, the asyncio Redis job queue, instead of Apache RocketMQ. Ingestion, MinerU extraction, chunking, embedding, Milvus indexing, reconciliation, and operational asynchronous events run as arq jobs in the `apps/worker` process. Aegra remains the owner of agent Thread/Run execution, checkpoints, recovery, and Agent Protocol streaming.

The responsibility shift is deliberate. RocketMQ is a Java-ecosystem broker whose Python client, gRPC Proxy endpoint, broker-side retry, and transaction-message machinery add a broker service and deployment surface that the product does not otherwise need. arq runs inside the existing Python 3.14/uv worker, uses the Redis already required for sessions, rate limits, caches, and pub/sub, and keeps PostgreSQL as the durable workflow source of truth.

## Mapping of the former RocketMQ contract

- **Producer** → the arq enqueue interface in `packages/infra`. Stable `job_id` values make retried enqueues idempotent.
- **Consumer** → arq job functions registered in `apps/worker` `WorkerSettings`. Each ingestion stage is one job with explicit `job_timeout`, `max_tries`, and retry backoff.
- **Transaction messages** → the transactional outbox pattern. Where publication must be coupled to a local business outcome, the worker writes a job row to a PostgreSQL `outbox` table inside the same transaction as the state change, and an outbox relay enqueues it to arq only after commit.
- **Broker-side retry / reconsume** → worker-side arq retries (`_max_tries`, `retry_jobs`) combined with PostgreSQL state-transition guards, so a stage resumes from the last durable point instead of replaying an entire message.
- **Dead-letter queue** → a PostgreSQL-backed failure surface. Jobs that exhaust retries leave the Ingestion Run in a terminal failure state, recorded in `ingestion_runs`/`run_events`; the operator failure/review view lists them and supports bounded replay. arq has no built-in DLQ, so this surface is application-owned.
- **Message keys** → stable job ids derived from the business aggregate (for example `ingest_document:<run_id>`, `reconcile_mineru:<task_id>`).
- **Idempotent consumers** → stable job ids plus unique constraints or idempotency records in PostgreSQL; a replayed job re-enters from the last durable stage.

Redis is the job transport, so its durability is bounded by Redis. Pending and in-flight work remains recoverable from the PostgreSQL outbox and Ingestion Run state after a Redis loss; the plan does not claim a broker-level durable message log beyond PostgreSQL.

## Consequences

- Docker Compose no longer provisions RocketMQ (no NameServer, Broker, or Proxy services, volumes, or credentials). Redis serves the arq transport alongside its existing responsibilities.
- `apps/worker` is the arq Worker entrypoint; `packages/infra` ships the arq adapter (enqueue settings, outbox relay, worker settings) rather than a RocketMQ client.
- The MinerU callback/polling reconciliation stage and every other asynchronous ingestion stage are arq jobs with stable job ids and PostgreSQL-guarded state transitions.
- Readiness reflects the arq worker lease and Redis connectivity; an unavailable Redis degrades job delivery but PostgreSQL preserves retryable workflow state.
- Integration tests cover arq worker behavior, outbox relay, retry exhaustion, failure recording, and replay; deterministic unit tests use an in-memory job adapter.
- ADR 0050's claim that Redis is not a durable replacement for RocketMQ is superseded: PostgreSQL is the durable source of truth and arq/Redis is the delivery mechanism.
