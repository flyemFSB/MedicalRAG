---
kind: ticket
label: wayfinder:grilling
status: closed
parent: ../map.md
assignee: codex
depends_on:
  - ragent-capability-migration-matrix.md
  - aegra-fastapi-arq-worker-runtime-contract.md
  - official-python-backend-and-data-stack-research.md
  - official-retrieval-ingestion-and-storage-research.md
title: External provider and data-egress contracts
---

## Question

What provider-neutral contracts, credentials, request redaction, timeout/retry/quota/circuit policy, streaming behavior, and failure fallback apply to generation, dense Embedding, Reranking, and MinerU APIs?

## Resolution

- **Contracts** — application-owned `GenerationProvider` (streaming), `EmbeddingProvider`, `RerankerProvider`, and a `MinerUProvider` client ([ADR 0009](../../adr/0009-use-application-owned-model-provider-interfaces.md), [ADR 0007](../../adr/0007-external-apis-provide-generation-and-embeddings.md)). Generation uses OpenAI-compatible endpoints with a capability manifest (Responses preferred, Chat Completions fallback, capability allowlist for reasoning/temperature/tools/vision); Embedding uses `/v1/embeddings`; Reranker and MinerU use their native provider protocols and are never forced into an OpenAI shape (compatibility research §3).
- **Credentials** — platform-owned, operator-managed secrets ([ADR 0010](../../adr/0010-platform-owns-model-credentials.md)); never Workspace data; injected at the composition root; never enter the client bundle or logs.
- **Request redaction and egress** — the Data Egress Policy governs what may leave: only de-identified, policy-permitted content ([ADR 0008](../../adr/0008-first-version-excludes-identifiable-patient-data.md)); no Identifiable Patient Data. MinerU receives a short-lived, least-privilege source URL rather than long-lived storage credentials ([ADR 0015](../../adr/0015-mineru-api-is-the-external-extraction-provider.md)).
- **Timeout / retry / quota / circuit** — per-provider bounded timeout; retries only on non-streamed requests for transient 5xx per provider policy; no auto-replay after tokens have streamed; provider quotas/rate limits respected; a Redis-backed three-state circuit guards unhealthy candidates; on total failure the system returns a deterministic evidence-insufficiency result.
- **Streaming** — Generation streams through the application `GenerationStreamEvent`, the graph converts it to Agent Protocol v2 messages/content-block events; there is no post-generation blocking gate once tokens start ([ADR 0041](../../adr/0041-generation-is-streamed-without-a-blocking-output-gate.md)); cancellation is propagated to the provider.
- **Failure fallback** — a provider outage advances through the routing policy; if every candidate fails, the answer is the grounded evidence-insufficiency fallback; Embedding/Reranker/MinerU failures mark the dependent stage failed with idempotent retry ([ADR 0063](../../adr/0063-arq-replaces-rocketmq-as-the-durable-job-queue.md)) rather than fabricating a result.
