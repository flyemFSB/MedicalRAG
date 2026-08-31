---
status: accepted
amends:
  - 0034-structure-first-chunking-preserves-provenance
---

# Chunking adds size caps, sentence-boundary splits, overlap, and atomic tables

Structure-first chunking (ADR 0034) remains the boundary principle: heading sections define Chunks and each Chunk carries its full heading path for provenance. This amendment adds the size discipline that ADR 0034 explicitly deferred:

- **Size cap**: a section whose text exceeds ~500 tokens (tokenizer-counted, not whitespace-split) is split at sentence boundaries; oversized sentences split at clause/character boundaries as a last resort.
- **Overlap**: adjacent sub-chunks produced by a split share 10–15% of trailing/leading text, cut at sentence boundaries, so statements spanning a split stay retrievable from both sides.
- **Atomic tables**: a section whose content is a table is never split; it becomes one Chunk regardless of size. When MinerU Extraction emits table structures, they are serialized with headers preserved so column relations survive indexing.
- **Unchanged invariants**: chunk ids remain `{document_id}:{index}`, provenance fields and heading paths are unchanged, and embedding text still composes heading path + body (ADR 0035).

## Rationale

- Uncapped sections overflow the Embedding Provider's input window and get silently truncated — the vector then represents a fragment while retrieval believes it saw the whole section.
- Sentence-boundary splits avoid the "boundary pollution" failure mode where unrelated half-statements are concatenated into one embedded text.
- Overlap beyond ~20% duplicates evidence across chunks, wasting context budget and letting near-duplicate candidates crowd the Reranker's input.

## Consequences

- The chunking module gains a tokenizer dependency (project-pinned); token counts recorded on Chunks become trustworthy for cost accounting.
- Re-ingestion produces different chunk boundaries than previously published Documents; existing collections keep their old points until documents are re-ingested or re-indexed under the current Embedding Schema Version policy.
- Tests cover: short sections pass through unchanged, long sections split at sentence boundaries with overlap, table sections stay atomic, and heading paths remain correct across splits.
