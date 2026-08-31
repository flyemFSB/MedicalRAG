---
kind: ticket
label: wayfinder:grilling
status: closed
parent: ../map.md
assignee: codex
depends_on: []
title: arq durable workflow boundary
---

## Question

Is arq retained, and how does it relate to Aegra and Redis?

## Resolution

arq replaces RocketMQ as the asynchronous job executor for document ingestion, MinerU processing, chunking, embeddings, Milvus indexing, reconciliation, and operational asynchronous events. Jobs use stable job ids, worker-side retries, bounded timeouts, and idempotent state guards; transactional publication uses the PostgreSQL outbox; jobs that exhaust retries surface on the PostgreSQL-backed failure/replay view. arq is not a durable replacement for Aegra Thread/Run state or Redis sessions, and it is not a durable message log: PostgreSQL is the durable source of truth.

## Evidence

- [arq replaces RocketMQ as the durable job queue ADR](../../adr/0063-arq-replaces-rocketmq-as-the-durable-job-queue.md)
- [Migration boundary ADR](../../adr/0049-ragent-capability-complete-migration-matrix.md)
