---
status: superseded by ADR-0075
---

# Milvus Standalone is the Compose vector store

> **2026-08 superseded**：Compose 向量存储已由 Milvus Standalone 替换为 Qdrant 单容器（[ADR 0075](0075-qdrant-replaces-milvus-as-the-hybrid-retrieval-engine.md)）；Qdrant 无元数据/对象存储依赖，「Compose 需为 Milvus 预置依赖」的后果随之失效。

Docker Compose provides Milvus Standalone for local development, integration tests, and self-hosted deployments. Production may replace it with a managed Milvus-compatible service behind the same application-owned vector-store port. Milvus is the sole dense-vector index; PostgreSQL stores Chunk metadata, collection ownership, Embedding Schema Versions, build manifests, active-index pointers, and publication state, but PostgreSQL extensions such as pgvector are not part of the target retrieval path.

## Consequences

- The Compose profile must provision Milvus's required metadata and object-storage dependencies with persistent volumes, health checks, and explicit credentials.
- Every collection is bound to one immutable Embedding Schema Version; changing model, dimension, metric, normalization, or input policy requires a new collection and validated cutover.
- Only approved Published Versions may be inserted into the active collection, and failed or partial builds cannot become retrieval sources.
- Milvus backup, compaction, index-build capacity, consistency level, and production topology are operational concerns documented separately from the medical domain.
