---
status: accepted
---

# The first version excludes Identifiable Patient Data

The first production version accepts public medical sources and De-identified Medical Data only. It must reject or quarantine input containing Identifiable Patient Data before the content reaches PostgreSQL, Milvus, an External Model Provider, logs, or Trace metadata. Request-time PII/PHI detection and redaction are required at the HTTP, ingestion, and model-egress seams. Supporting real patient records is a separate future compliance project requiring an approved provider, contractual data processing terms, regional controls, retention policy, audit, and encryption review.
