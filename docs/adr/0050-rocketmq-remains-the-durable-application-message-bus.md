---
status: superseded
---

# RocketMQ remains the durable application message bus

> Superseded by [ADR 0063](0063-arq-replaces-rocketmq-as-the-durable-job-queue.md). This document records the original RocketMQ decision for decision history; the implementation target is arq (Redis job queue) with PostgreSQL as the durable workflow source of truth.

MedicalRAG retains Ragent's RocketMQ responsibility for durable asynchronous application workflows. RocketMQ carries ingestion, extraction, embedding, indexing, and operational domain messages with transaction-message production where required by the source behavior, bounded retries, dead-letter handling, stable message keys, and idempotent consumers. Aegra remains the owner of agent Thread/Run execution, checkpoints, recovery, and Agent Protocol streaming; Redis is not used as a durable replacement for RocketMQ.

## Consequences

- Docker Compose provisions RocketMQ as an explicit dependency with persistent storage, health checks, credentials, and a production upgrade path.
- PostgreSQL remains the source of truth for business state; consumers acknowledge a message only after the corresponding state transition is durably recorded.
- Consumer idempotency is enforced with stable business/message keys, unique constraints or idempotency records, and safe retry from the last durable stage.
- Transaction messages, retries, and dead-letter outcomes are part of the integration-test contract; unit tests use a deterministic in-memory adapter.
