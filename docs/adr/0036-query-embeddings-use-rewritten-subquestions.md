---
status: accepted
---

# Query embeddings use rewritten subquestions and trusted entities

For each grounded user request, Dense Retrieval embeds the resolved and rewritten subquestion rather than the entire multi-intent conversation. High-confidence normalized Medical Entities may be appended using the versioned query-input format; low-confidence entities, ambiguous intents, speculative expansions, and unverified patient-specific details are excluded from the vector query. Milvus's sparse/BM25 query uses the approved rewritten text, while PostgreSQL exact/structured filtering may use richer structured intent/entity information than the embedding input.

## Consequences

- Query rewriting, splitting, entity confidence, and query-input policy are recorded in business run events and, for the Aegra-hosted graph, the redacted Langfuse observation so a vector result can be reproduced.
- Ambiguous or system-only requests do not trigger misleading dense queries; an unresolved request follows the clarification or non-retrieval path.
- Query and document embedding policies must remain dimension-, metric-, and normalization-compatible within one Embedding Schema Version.
- External Embedding Provider calls receive only the Data Egress Policy-approved query text and never receive internal IDs, permissions, or hidden authorization metadata.
