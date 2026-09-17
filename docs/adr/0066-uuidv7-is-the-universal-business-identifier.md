---
status: accepted
---

# UUIDv7 is the universal business identifier

MedicalRAG uses UUID version 7 (UUIDv7) as the primary key for every business record: users, workspaces, conversations, messages, knowledge bases, documents, chunks, Ingestion Runs, chat Runs, run events, audit events, feedback, intent-tree nodes, slot schemas, model targets, and outbox rows. IDs are generated in the application layer, not by the database. This replaces Ragent's Snowflake distributed-id scheme, which the stack replacement matrix (local archive) had left open.

Python 3.14's standard-library `uuid` module provides `uuid.uuid7()`, so no third-party ID library or coordinating service is required. UUIDv7 is time-ordered and random within each time quantum, giving monotonic-ish, collision-free, index-friendly identifiers that any process (API, Agent, arq Worker, or evaluation) can create independently of the write database.

## Why not the alternatives

- **Snowflake**: needs worker-id coordination and a deployment contract; provides no advantage over UUIDv7 in a single-writer-per-aggregate async application, and has no Python standard-library implementation.
- **PostgreSQL `bigint identity`**: couples identifier generation to the write database, complicating parallel creation from Worker/Agent processes and cross-service references.
- **Random UUIDv4**: not time-ordered, so it fragments B-tree indexes and gives no pagination ordering.
- **UUIDv7**: time-ordered (good index locality), sortable, 122 bits of randomness, no coordination.

## Consequences

- PostgreSQL columns are typed `uuid`; application code generates identifiers via `uuid.uuid7()` before insert so API, Agent, and Worker can create rows independently.
- Time-ordering supports cursor pagination by id and keeps recent rows hot in the same index pages.
- Stable arq job ids derive from the business aggregate id, for example `ingest_document:<uuid7>` and `reconcile_mineru:<uuid7>` (see [ADR 0063](0063-arq-replaces-rocketmq-as-the-durable-job-queue.md)).
- Implementation must verify `uuid.uuid7()` availability and monotonicity on the exact Python 3.14 patch chosen for the baseline before declaring it final.
