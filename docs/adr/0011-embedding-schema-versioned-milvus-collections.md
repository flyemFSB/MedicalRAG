---
status: superseded by ADR-0075
---

# Embedding schema versions own separate Milvus Collections

> **2026-08 superseded**：向量库已由 Milvus 替换为 Qdrant（[ADR 0075](0075-qdrant-replaces-milvus-as-the-hybrid-retrieval-engine.md)）。「一个不可变 Embedding Schema Version 绑定一个索引集合、变更即新建并验证后切换 Active Index Version」的约束不变，集合载体由 Milvus Collection 改为 Qdrant Collection。

Each Milvus Collection is bound to one immutable Embedding Schema Version. The first version uses one configured embedding target; changing the model, dimension, metric, normalization, or input-text policy creates a new Collection, performs a complete idempotent rebuild, validates recall and integrity, and switches the Active Index Version only after success. Old collections remain available for rollback and historical run/Langfuse observation interpretation until explicitly retired. Mixed embedding spaces are never stored in one Collection.
