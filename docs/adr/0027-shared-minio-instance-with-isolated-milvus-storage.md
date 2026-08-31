---
status: superseded by ADR-0075
---

# Compose MinIO is shared with isolated Milvus storage

> **2026-08 superseded**：Milvus 与检索路径的 MinIO 已随 Qdrant 单容器部署一并移除（[ADR 0075](0075-qdrant-replaces-milvus-as-the-hybrid-retrieval-engine.md)）。「文档存储与向量存储必须隔离」的原则不变，但 v1 无此场景。

In development and test Compose environments, the MinIO service used for original documents and Extraction Artifacts is also used as the S3-compatible object store required by Milvus Standalone. The two workloads are isolated with separate buckets or prefixes, separate access users and credentials, independent lifecycle rules, and deny-by-default policies; application document credentials cannot read Milvus internal objects, and Milvus credentials cannot read medical documents. Production may split the stores across independent object-storage services without changing application ports.

## Consequences

- Local setup remains compact while storage ownership and blast radius remain explicit.
- MinIO backup and restore procedures must cover the document and Milvus storage domains independently.
- Bucket names, prefixes, lifecycle policies, and credentials are deployment configuration, not hard-coded domain assumptions.
- Tests must verify that the document-storage adapter and Milvus adapter cannot cross the configured bucket boundary.
