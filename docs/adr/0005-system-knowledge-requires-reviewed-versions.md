---
status: accepted
---

# System Knowledge requires reviewed versions

System Knowledge must pass an explicit lifecycle of draft, review, approval, publication, and retirement. A Published Version is immutable and is the only version indexed for default Milvus retrieval. Publishing records the reviewer, time, source version, and change note; updates create a new version rather than silently modifying an existing one. Retired versions leave historical business run, Langfuse metadata, and Citation records intact but are excluded from new retrieval. This decision makes medical content governance auditable and prevents an unnoticed edit from changing clinical answers.
