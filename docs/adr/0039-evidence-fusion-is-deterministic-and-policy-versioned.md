---
status: accepted
---

# Evidence Fusion is deterministic and policy-versioned

Evidence Fusion follows a fixed, auditable sequence: enforce Workspace and publication authorization, let Milvus combine dense and sparse/BM25 ranks with a configured Weighted or Reciprocal Rank Fusion strategy, deduplicate equivalent candidates while merging provenance, add a monotonic normalized external Reranker score for document Chunks, apply source-quality and Intent-aware tie-breakers, enforce per-channel and per-Intent quotas, and cap the final Evidence set for the model context. The active retrieval and fusion rules are stored as a versioned Retrieval Policy; an LLM never chooses which Evidence survives or how it is ordered.

## Consequences

- Every final Evidence item has channel provenance, raw and derived scores, policy version, publication status, and the reason it was retained or capped.
- PostgreSQL exact/structured filters constrain authorized Milvus candidates; sparse/BM25, dense, and reranked candidates compete only within their configured quotas.
- Score normalization, RRF constants, weights, tie-breakers, quotas, and context caps are deterministic configuration and require offline retrieval evaluation before activation.
- Changing fusion policy does not mutate source Documents or Milvus vectors, but it creates a traceable retrieval-policy version for answer and evaluation comparisons.
