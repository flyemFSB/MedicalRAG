---
kind: ticket
label: wayfinder:grilling
status: closed
parent: ../map.md
assignee: codex
depends_on:
  - aegra-fastapi-arq-worker-runtime-contract.md
  - milvus-hybrid-retrieval-contract.md
  - official-retrieval-ingestion-and-storage-research.md
  - official-devops-quality-security-and-observability-research.md
title: Ingestion and MinerU state machine
---

## Question

What are the exact ingestion stages, durable state transitions, callback and polling reconciliation rules, immutable artifact boundaries, retry/compensation semantics, and publication gate for the approved document formats?

## Resolution

- **Stages** — each stage is an arq job with its own durable record, resumable from the last committed stage ([ADR 0063](../../adr/0063-arq-replaces-rocketmq-as-the-durable-job-queue.md)): `accepted` (source object stored to MinIO under an unguessable, Workspace-scoped key; format validated against the allowlist, [ADR 0030](../../adr/0030-supported-document-format-allowlist.md)) → `extracting` (MinerU submission) → `extracted` (result ZIP downloaded, checksum-validated, copied to immutable artifact keys, [ADR 0033](../../adr/0033-raw-mineru-results-are-immutable-artifacts.md)) → `chunking` (structure-first chunking with provenance, [ADR 0034](../../adr/0034-structure-first-chunking-preserves-provenance.md)) → `enriching` (optional summaries/keywords/metadata) → `embedding` (embedding text includes structural context, [ADR 0035](../../adr/0035-embedding-text-includes-structural-context.md)) → `indexing` (Milvus dense+sparse upsert) → `published` (a reviewed Published Version becomes eligible, `is_eligible=true`).
- **Durable state transitions** — every transition is recorded in `ingestion_runs`/`run_events`; only forward transitions are allowed; retry resumes from the last durable stage. Ingestion is always asynchronous ([ADR 0013](../../adr/0013-document-ingestion-is-always-asynchronous.md)).
- **Callback and polling reconciliation** ([ADR 0031](../../adr/0031-mineru-callback-first-with-polling-reconciliation.md)) — the MinerU callback is primary with checksum validation; a reconciliation arq job polls the task-status endpoint for delayed, duplicated, rejected, or never-delivered callbacks using bounded exponential backoff; deduplication keys are the provider task id and the application `data_id`; callback and polling races converge on a single Ingestion Run transition.
- **Immutable artifacts** ([ADR 0033](../../adr/0033-raw-mineru-results-are-immutable-artifacts.md)) — the raw MinerU result is stored once and never mutated; derived artifacts are versioned; all object keys are unguessable and Workspace-scoped.
- **Retry and compensation** — per-stage arq retries with backoff; a stage failure marks the node failed while preserving the task and prior node logs; a partial failure can be repaired at the correct stage; delivery is at-least-once with `UNIQUE(ingestion_run_id, stage)` idempotency.
- **Publication gate** — a document is not eligible for default retrieval until validation and indexing complete and the Published Version is approved ([ADR 0013](../../adr/0013-document-ingestion-is-always-asynchronous.md), [ADR 0005](../../adr/0005-system-knowledge-requires-reviewed-versions.md)); System Knowledge publication requires review; the allowlist admits only the approved formats, so URL/Feishu ingestion receives a typed unsupported-source result.
