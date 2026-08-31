---
status: accepted
---

# Chunking is structure-first and provenance-preserving

MedicalRAG creates Chunks from the normalized Extraction Artifact by respecting document structure before applying semantic or token-budget splitting. Headings, paragraphs, lists, tables, figures, captions, formulas, and page or region boundaries are preserved as meaningful units; an oversized unit is split only when necessary, with the smallest valid structural context repeated or referenced. Tables are not split arbitrarily across rows or columns, and any row-group split retains the header and table identity. Chunking profiles, token budgets, overlap rules, and normalization policies are versioned inputs to indexing rather than hidden constants.

## Consequences

- Every Chunk records its source Document and Published Version, artifact ID, heading path, page or region references, block IDs, source checksum, and Chunking Profile Version.
- Chunk overlap is applied only when it improves continuity within a structural unit; generic character-window overlap must not cross unrelated headings or table boundaries.
- Re-chunking creates a new derived Chunk set and requires a new validation/index build; existing Published Versions and active Milvus collections remain immutable.
- Chunk quality tests must detect orphaned table rows, detached captions, broken heading context, duplicated content, lost provenance, and overlong model inputs.
