---
status: accepted
---

# Embedding text includes structural context

The canonical document embedding input is a deterministic composition of the Document title, heading path, table title or headers when applicable, and normalized Chunk body. Structural labels are separated with stable field markers and normalized consistently; access-control fields, object keys, internal IDs, raw Citation URLs, Trace data, and unrelated operational metadata are not embedded. Query embedding uses a separately versioned but compatible policy so question normalization and medical intent context can evolve without silently changing the document vector space.

## Consequences

- The exact embedding input and its hash are persisted with each indexed Chunk for reproducibility and audit.
- A change to field order, separators, normalization, heading inclusion, table representation, query policy, model, dimension, metric, or normalization requires a new Embedding Schema Version and Milvus collection.
- Structural context improves retrieval for short medical fragments and tables but consumes input tokens; token budgets and truncation rules must be measured rather than applied invisibly.
- Sensitive or access-control metadata cannot be smuggled into vectors as a substitute for authorization filtering.
