---
status: superseded by ADR-0056 (chain now terminates at ADR-0075)
---

# Milvus, Elasticsearch, and PostgreSQL are the target retrieval stores

> **2026-08 superseded（链尾）**：整个 Milvus 决策链已被 [ADR 0075](0075-qdrant-replaces-milvus-as-the-hybrid-retrieval-engine.md) 取代——Qdrant 是唯一检索引擎。

This decision was superseded when the project chose to implement lexical/BM25 retrieval inside Milvus rather than operate Elasticsearch as a second retrieval store. The active retrieval boundary is defined by ADR-0056.

## Consequences

- Historical consequences are retained for decision traceability only.
