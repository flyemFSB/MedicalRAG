---
status: accepted
---

# Document ingestion is always asynchronous

Every document ingestion request creates an Ingestion Run and returns without waiting for parsing, embedding, or Milvus indexing. arq worker jobs execute the stages, persist progress and errors, and support idempotent retry from a failed stage. Aegra remains responsible for agent Thread/Run execution and is not used as the ingestion job queue. Documents are not eligible for retrieval until validation and indexing complete. Even small documents use the same state machine so the API, UI, business run events, and failure semantics do not diverge between synchronous and asynchronous paths.
