---
status: accepted
---

# System knowledge is read-only and Workspace knowledge is private

MedicalRAG separates System Knowledge from Workspace Knowledge. System Knowledge contains curated medical entities, aliases, intents, and published graph or document evidence and is read-only to Workspace users. Workspace Knowledge is private to its owning Workspace and is always filtered by `workspace_id` in both PostgreSQL and Milvus queries. The first version does not support direct cross-Workspace sharing; a future promotion workflow must review and publish a Workspace source into System Knowledge before it becomes globally visible. This prevents accidental cross-tenant leakage and keeps the provenance of shared medical knowledge explicit.
