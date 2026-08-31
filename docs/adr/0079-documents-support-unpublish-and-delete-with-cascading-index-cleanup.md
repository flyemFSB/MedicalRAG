---
status: accepted
---

# Documents support unpublish and delete with cascading index cleanup

A Document's lifecycle does not end at publication. Two operator-initiated transitions complete it:

1. **Unpublish** (soft, reversible): the Document's publication eligibility flag is cleared, so its Chunks stop passing the `is_eligible` filter immediately. Indexed points stay in place; republishing restores eligibility without re-ingestion.
2. **Delete** (hard, irreversible): the Document record and all its indexed points are removed. Point removal cascades by `document_id` payload filter and is executed asynchronously by the worker through the transactional outbox — the same durable pattern as ingestion jobs (ADR 0013/0073). Deletion completes only when the worker confirms zero remaining points for the document.

Both transitions are exposed as authenticated API routes scoped by Workspace membership and operator role. A periodic reconciliation job scans Qdrant for points whose `document_id` no longer exists in PostgreSQL (orphan Chunks) and removes them; scan results are recorded as operational metrics.

## Rationale

- Expired guidelines and retracted literature must stop influencing answers; medical compliance requires both a fast kill switch (unpublish) and true erasure (delete) — the "RAG can delete" property that fine-tuning lacks.
- Synchronous vector deletion would couple the API to Qdrant availability; the outbox keeps the API transactional and the cleanup retriable.

## Consequences

- New API routes enter the OpenAPI contract; the same commit carries regenerated TypeScript types (ADR 0071 drift gate).
- Unpublish takes effect on the next retrieval (filter-based, no index mutation); delete is eventually consistent — a deleted Document's Chunks may surface for the seconds until the worker drains the outbox, which run events make auditable.
- Tests cover: unpublish hides Chunks from Hybrid Retrieval, republish restores them, delete cascades all points, orphan scan removes dangling points, and non-member/operator authorization failures.
