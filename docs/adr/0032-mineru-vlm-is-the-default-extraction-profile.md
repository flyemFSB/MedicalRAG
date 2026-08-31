---
status: accepted
---

# MinerU VLM is the default extraction profile

For PDF, image, DOCX, PPTX, and XLSX sources, the first version submits MinerU API tasks with `model_version=vlm`. This is the default because the supported scope includes scanned pages, OCR, tables, formulas, embedded images, and layout-dependent meaning. The selected extraction profile, provider task, and effective provider metadata are persisted on the Ingestion Run and Extraction Artifact. Markdown and plain-text sources may use a deterministic text normalizer when no multimodal interpretation is required, while preserving the same artifact contract.

## Consequences

- Extraction quality and provenance take priority over the lower cost or latency of the `pipeline` profile for the initial supported multimodal formats.
- A provider failure does not silently downgrade a run to another model version; an operator or retry policy must explicitly select a different Extraction Profile and record the reason.
- VLM output must retain page, region, asset, table, and warning metadata needed for structure-aware chunking and citations.
- Provider quota, page limits, file-size limits, timeout budgets, and cost monitoring are first-class operational controls.
