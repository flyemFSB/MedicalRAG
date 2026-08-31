---
kind: ticket
label: wayfinder:grilling
status: closed
parent: ../map.md
assignee: codex
depends_on: []
title: Unified Milvus Hybrid Retrieval boundary
---

## Question

Which retrieval stores and ranking stages are in the target?

## Resolution

> **2026-08-04 superseded**：存储轴定案已由 Milvus 改为 Qdrant（[ADR 0075](../../adr/0075-qdrant-replaces-milvus-as-the-hybrid-retrieval-engine.md)）；「唯一检索引擎 + 外部 Reranker 分层」的边界不变，dense/sparse 候选与 RRF 融合改由 Qdrant prefetch + RrfQuery(k=60) 承担。本决议保留为历史记录。

Milvus is the sole retrieval engine. External dense Embeddings and Milvus Full Text Search/BM25 provide dense and sparse candidates; Milvus performs configured Weighted or Reciprocal Rank Fusion; application Evidence Fusion applies authorization, provenance, quotas, and policy; an external Reranker API performs bounded candidate reranking. PostgreSQL remains authoritative for permission and structured metadata filtering.

## Evidence

- [Unified Milvus Hybrid Retrieval ADR](../../adr/0056-milvus-is-the-unified-hybrid-retrieval-engine.md)
- [Milvus Multi-Vector Hybrid Search](https://milvus.io/docs/multi-vector-search.md)
- [Milvus Full Text Search](https://milvus.io/docs/full-text-search.md)
