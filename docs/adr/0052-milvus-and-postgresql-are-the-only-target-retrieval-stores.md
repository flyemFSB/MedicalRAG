---
status: superseded by ADR-0054 (chain now terminates at ADR-0075)
---

# Milvus and PostgreSQL are the only target retrieval stores

> **2026-08 superseded（链尾）**：整个 Milvus 决策链已被 [ADR 0075](0075-qdrant-replaces-milvus-as-the-hybrid-retrieval-engine.md) 取代——Qdrant 是唯一检索引擎。

This decision was superseded when Elasticsearch was explicitly restored as the target lexical retrieval store. The active retrieval-store boundary is defined by ADR-0054.

## Consequences

- Historical consequences are retained for decision traceability only.
