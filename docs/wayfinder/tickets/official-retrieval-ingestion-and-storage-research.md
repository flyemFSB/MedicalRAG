---
kind: ticket
label: wayfinder:research
status: closed
parent: ../map.md
assignee: codex
depends_on: []
research_file: ../../research/retrieval-ingestion-and-storage.md
title: Official Milvus, MinerU, and object-storage research
---

## Question

What do the official documents for Milvus/PyMilvus Hybrid Search, dense and sparse vectors, BM25 Full Text Search, filtering, index lifecycle, consistency, MinerU API, MinIO/S3-compatible storage, and external-provider data transfer recommend for schema design, ingestion, querying, versioning, callbacks, retries, security, and tests?

## Resolution

Research complete and reconciled. The research document captured official guidance for Milvus Hybrid Search / BM25, MinerU API, and MinIO/S3-compatible storage and now carries a reconciliation note. Reconciled to the current plan: Milvus 2.6+/3.0 uses the `Function/FunctionType` RERANK API for hybrid retrieval (RRFRanker/WeightedRanker are the 2.5-era classes, still exported), and MinIO is pinned to the last AGPL release ([ADR 0017](../../adr/0017-s3-compatible-object-storage-with-minio.md)). See [tech-stack-objective-evaluation](../../research/tech-stack-objective-evaluation.md) §2.1. The Milvus schema/ranking/zero-result details graduate to the already-open [Milvus Hybrid Retrieval schema and ranking contract](milvus-hybrid-retrieval-contract.md) ticket.
