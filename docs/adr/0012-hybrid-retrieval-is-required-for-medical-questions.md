---
status: accepted
---

# Hybrid retrieval is required for medical questions

The first version combines authorization-scoped PostgreSQL exact/structured filtering with Milvus dense and sparse/BM25 Hybrid Retrieval. An external Embedding Provider supplies dense query vectors; Milvus's full-text/BM25 capability supplies sparse lexical recall; Milvus combines the candidate lists with a documented Weighted or Reciprocal Rank Fusion strategy. Application-level Evidence Fusion then preserves provenance, applies policy and quotas, and passes a bounded set to the external Reranker. No separate pgvector, Elasticsearch, Neo4j, or LightRAG service is part of this retrieval path.
