---
kind: ticket
label: wayfinder:grilling
status: closed
parent: ../map.md
assignee: codex
depends_on:
  - ragent-capability-migration-matrix.md
  - official-retrieval-ingestion-and-storage-research.md
title: Milvus Hybrid Retrieval schema and ranking contract
---

## Question

What exact Milvus collection schema, dense/sparse/BM25 configuration, text normalization policy, scalar authorization filters, rank-fusion default, external reranker boundary, index-version lifecycle, and retrieval test set will preserve Ragent behavior without Elasticsearch?

## Resolution

> **2026-08-04 superseded（存储轴）**：schema/ranking 契约已迁移到 Qdrant（[ADR 0075](../../adr/0075-qdrant-replaces-milvus-as-the-hybrid-retrieval-engine.md)）：每 Embedding Schema Version 一个 Qdrant collection；dense 字段 + fastembed 静态 `Qdrant/bm25` sparse 字段；检索用 prefetch 双路 + `RrfQuery(k=60)`；授权/eligibility 过滤走 payload `query_filter`。其余分层（外部 Reranker、Evidence Fusion、测试集）不变。本契约保留为历史记录。

- **Collection schema** (per immutable Embedding Schema Version, [ADR 0011](../../adr/0011-embedding-schema-versioned-milvus-collections.md)): PK `pk` (uuid7); authorization/eligibility scalars `workspace_id`, `knowledge_base_id`, `document_id`, `chunk_id`, `published_version_id`, `is_eligible`, `schema_version`; dense field `dense_vector` (dimension + metric fixed by the schema version); sparse field `sparse_vector` produced by a `Function(FunctionType.BM25)` over the `text` field with `SPARSE_INVERTED_INDEX`, `metric_type=BM25`, `bm25_k1=1.2`, `bm25_b=0.75`; `text` holds the structure-aware normalized chunk text ([ADR 0035](../../adr/0035-embedding-text-includes-structural-context.md)). One collection per active schema version; a new embedding model builds a new collection, is validated, then becomes the Active Index Version and the previous collection is released.
- **Hybrid search and ranking** — `client.hybrid_search(collection, [AnnSearchRequest(dense), AnnSearchRequest(sparse)], ranker=Function(FunctionType.RERANK, {"reranker":"rrf","k":60}), limit, output_fields=...)` (the 2.6+/3.0 `Function` API; see tech-stack evaluation §2.1). Default ranker is RRF with k=60 (inside the documented [10,100]); switch to a calibrated `WeightedRanker` only after offline evaluation proves stable dense/sparse weights ([retrieval research](../../research/retrieval-ingestion-and-storage.md) §4). The external Reranker API re-scores the top-N fused candidates ([ADR 0037](../../adr/0037-external-reranker-api-orders-hybrid-candidates.md)); structured/medical-graph evidence bypasses reranking ([ADR 0038](../../adr/0038-medical-graph-evidence-bypasses-reranking.md)); external reranker scores are never fed back as Milvus rank weights.
- **Scalar authorization filters** — every query carries an `expr` restricted to the caller's authorized `workspace_id`/`knowledge_base_id` set (resolved from PostgreSQL) plus `is_eligible = true` so only eligible Published Versions are candidates ([ADR 0005](../../adr/0005-system-knowledge-requires-reviewed-versions.md)). A zero-result hybrid search returns the `Empty` state and a deterministic evidence-insufficiency result.
- **Text normalization** — queries submit the rewritten sub-question text ([ADR 0036](../../adr/0036-query-embeddings-use-rewritten-subquestions.md)); v1 uses Milvus's default analyzer and no custom tokenizer; revisit only if retrieval evaluation demands it.
- **Retrieval test set** — the `eval-retrieval` profile (Recall@k, MRR/nDCG, intent Top-1, branch correctness, empty-recall rate, duplicate rate, P95 latency) on a synthetic or approved de-identified dataset; the set and fixtures are owned by the testing-quality-and-release-gates decision, not a new artifact.
