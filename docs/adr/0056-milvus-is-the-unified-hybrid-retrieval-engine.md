---
status: superseded by ADR-0075
---

# Milvus is the unified Hybrid Retrieval engine

> **2026-08 superseded**：唯一检索引擎已由 Milvus 替换为 Qdrant 单容器（[ADR 0075](0075-qdrant-replaces-milvus-as-the-hybrid-retrieval-engine.md)）。dense + sparse/BM25 混合检索、RRF 融合、授权/发布过滤、外部 Reranker 分层的职责不变，具体 API 按 Qdrant prefetch + RrfQuery(k=60) 实现。

MedicalRAG uses Milvus as the only retrieval engine. Each indexed Chunk stores the versioned dense representation produced by the external Embedding Provider and the sparse/BM25 representation supported by Milvus Full Text Search. A Hybrid Retrieval request sends the rewritten subquestion to Milvus, applies authorization and publication filters, combines dense and sparse candidate lists with Milvus's documented Weighted or Reciprocal Rank Fusion capability, and then passes the bounded result set through the application Evidence Fusion stage and external Reranker API. PostgreSQL remains authoritative for permissions, publication state, provenance, exact filters, and structured medical metadata; it is not a full-text retrieval substitute.

## Consequences

- Docker Compose provisions Milvus but no Elasticsearch, pgvector, Neo4j, LightRAG, or other retrieval database.
- Milvus collection schema and indexes must version the dense model, dimension, metric, sparse/BM25 configuration, text normalization policy, and fusion policy. A schema or ranking change creates a new index version rather than mutating the active one in place.
- The ingestion pipeline writes both dense and sparse/BM25 indexable fields before a Published Version becomes retrieval-eligible.
- Hybrid retrieval tests must cover dense-only, sparse-only, fused, filtered, empty, duplicate, and rank-fusion cases. Milvus's internal ranker and the application's Evidence Fusion stage are separate contracts.
- Official references: [Multi-Vector Hybrid Search](https://milvus.io/docs/multi-vector-search.md), [Full Text Search](https://milvus.io/docs/full-text-search.md), and [Keyword Match](https://milvus.io/docs/keyword-match.md).
