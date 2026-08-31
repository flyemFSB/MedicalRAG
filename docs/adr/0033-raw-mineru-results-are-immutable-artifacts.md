---
status: accepted
---

# Raw MinerU results are immutable artifacts

After a successful MinerU task, the ingestion worker downloads the provider's original result package, such as `full.zip`, and stores it as an immutable, private raw Extraction Artifact in MinIO. A separate versioned normalization step reads that artifact and creates MedicalRAG's canonical Extraction Artifact containing normalized text, structure, tables, assets, warnings, and provenance references. Raw provider output is never overwritten by cleanup, re-chunking, or re-indexing; a new normalization or extraction profile creates a new derived artifact linked to the same source and provider task.

## Consequences

- Chunking, entity extraction, and embedding rebuilds can replay from stored artifacts without resubmitting the source to MinerU.
- Raw and normalized artifacts carry source checksum, provider task ID, Extraction Profile, parser/provider versions, content type, byte size, and creation timestamps.
- Object keys are immutable and private; access is mediated by Workspace authorization and short-lived download URLs.
- Artifact retention and deletion must remove the raw package and all derived artifacts consistently while preserving the minimum audit record required by policy.
