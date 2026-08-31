---
status: accepted
---

# The first version has a fixed passive-document allowlist

The first version accepts only `.docx`, `.pptx`, `.xlsx`, `.pdf`, `.md`, `.txt`, `.png`, `.jpg`, and `.jpeg`. PDF sources may be scanned, image-heavy, layout-rich, or otherwise multimodal; the Office formats are the modern Open XML variants. Legacy `.xls` and `.ppt`, macro-enabled Office formats such as `.xlsm`, `.pptm`, and `.docm`, archives, executable content, audio, video, and all other extensions are rejected at the upload boundary.

## Consequences

- Extension, detected media type, and file signature must agree before an Upload Session can be finalized.
- The ingestion test matrix covers every allowed extension, empty and malformed files, encrypted files, oversized files, mismatched extensions, and rejected formats.
- MinerU API parsing is the primary path for supported multimodal sources; Markdown and plain text still produce the same provenance-preserving Extraction Artifact contract.
- Adding another format requires a new security, parser, provenance, and retrieval review rather than silently widening the upload filter.
