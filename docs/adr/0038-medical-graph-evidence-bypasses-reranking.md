---
status: superseded by ADR-0052
---

# Ragent graph evidence is not a target retrieval channel

Ragent's graph-evidence path was reviewed as part of the migration, but the target does not provision or adapt Neo4j, LightRAG, or another graph retrieval service. Structured medical metadata that remains in scope is stored and queried through PostgreSQL, then participates in the same bounded candidate and Evidence Fusion contract as other approved channels.

## Consequences

- The historical graph-specific quota and bypass rules no longer apply.
- Structured PostgreSQL evidence and document citations remain distinguishable in the final Evidence model and UI.
- Retrieval evaluation reports PostgreSQL exact/structured recall, Milvus recall, reranker quality, and fused answer support separately.
