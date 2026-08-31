---
status: accepted
---

# TaskIQ replaces arq as the durable job queue

arq 0.28 is maintenance-only and declares a redis-py upper bound of `<6`, which conflicts with the pinned redis-py 8.1 baseline required by the application-owned Redis session and auth adapters (version-baseline §1, gate 3). The Worker therefore uses TaskIQ with `taskiq-redis` (`ListQueueBroker`), which supports redis-py 8.x and installs cleanly on Python 3.14. This preserves [ADR 0063](../../adr/0063-arq-replaces-rocketmq-as-the-durable-job-queue.md) responsibilities — durable asynchronous application workflows, worker-side retries, stable job ids, the PostgreSQL transactional outbox, and PostgreSQL-backed failure/replay — with only the broker implementation changed.

## Consequences

- arq is not installed; ingestion/extraction/embedding/indexing/reconciliation/operational jobs run on a TaskIQ `ListQueueBroker`.
- Job idempotency is expressed by the PostgreSQL `UNIQUE(ingestion_run_id, stage)` stage log and the outbox's unique constraint rather than an arq `_job_id` deduplication window.
- Redis remains the delivery mechanism, not a durable message log; PostgreSQL preserves retryable state, and there is no silent fallback to an alternate broker.
- version-baseline §1 and ADR 0063 wording should name TaskIQ as the broker implementation; the durable-workflow boundary is unchanged.
