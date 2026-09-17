---
status: accepted
related:
  - 0039-evidence-fusion-is-deterministic-and-policy-versioned
  - 0034-structure-first-chunking-preserves-provenance
  - 0077-chunking-adds-size-caps-sentence-boundary-splits-overlap-and-atomic-tables
  - 0015-mineru-api-is-the-external-extraction-provider
---

# Retrieval policy v2 and chunking tolerance adopt reference-implementation quality semantics

A deep comparison against the Java reference project (`ragent`, ADR 0049 parity baseline) surfaced four retrieval-quality mechanisms and two ingestion hygiene gaps that MedicalRAG's pipeline lacked while everything around them already matched. This ADR adopts the mechanisms, bumps the retrieval policy to **v2**, and records two deliberate divergences.

## Decisions

1. **Retrieval policy v2** (`RetrievalPolicy.version = 2`) adds two fields:
   - `intent_min_score` (default **0.35**, `0` disables) — intent candidates below the confidence floor do not reach retrieval and fall through to clarification guidance. Matches the reference constant `INTENT_MIN_SCORE`.
   - `rerank_candidate_limit` (default **40**, `0` disables) — only the top-N candidates by channel score are sent to the external reranker; truncated candidates keep their channel score for fusion ranking. This is the cost ceiling the reference implements as `candidateLimit` in its three-stage retrieval budget funnel.
2. **Chunking tolerance** — sections within `tolerance_tokens` (default **1500**, ≥ `max_tokens`) stay atomic; only larger sections split on sentence boundaries. "Cutting a semantic unit costs more than overshooting the target size." Sentence-split packing still targets `max_tokens` (500).
3. **Table specialization** — pipe tables and MinerU HTML tables are row-split (rows are atomic, never cut mid-row; hard cap `table_rows_per_chunk = 50`). Every chunk repeats the header row in its display content, but the **embedding text carries only the KV body** (`列名: 值; ...`) with no header row: repeated header prefixes pull all chunks of one table toward the same vector direction. Table identity is carried by the heading path, not the header. `Chunk` gains an optional `embedding_text_override`; `embedding_text()` prefers it over the raw text.
4. **Generation prompt hygiene** — evidence is rendered grouped by document (groups keep relevance order) **without document titles**; titles remain available to the frontend evidence panel via Evidence events. In-scope titles invite "出自《XX》" hallucinated attribution. Assistant messages entering conversation history have `[n]` citation markers stripped first.
5. **MinerU hygiene** — image links inside the extraction ZIP (`images/*.jpg`) are stripped from the markdown before chunking (they are dangling relative paths: garbage tokens in chunks/embeddings and dead links in answers). Image asset-ification (object-storage rewrite + preview) is deferred until an image-serving decision exists. A **cross-process concurrency gate** (Redis-backed, default 16 permits, `MEDICALRAG_MINERU_CONCURRENCY`) bounds simultaneous parse jobs toward MinerU; requests that cannot acquire within 30s fail as retryable extraction errors.
6. **Upload trust boundary** — binary formats (pdf/png/jpg/jpeg/docx/pptx/xlsx) are sniffed by magic bytes at upload; a mismatch between claimed extension and byte content returns 415. Text formats are not sniffed.

## Consequences

- `RetrievalPolicy` consumers constructing the object directly (tests, agent entry, API settings) pick up the new defaults; the API/agent read the two new knobs from `MEDICALRAG_RETRIEVAL_*` environment variables, mirrored in the Compose whitelist and `.env.example`.
- Chunking behavior changes for 500–1500-token sections (one chunk instead of sentence-split pieces) and for table sections (row-split KV chunks). Existing fixtures and unit tests are updated to the new expectations.
- Explicitly **not** adopted from the reference: ES keyword channel (replaced by Qdrant sparse/BM25, ADR 0075), LightRAG graph channel and web search channel (out of scope per DECISIONS), configurable pipeline node engine (superseded there by their fixed kernel — mirroring our fixed 9-stage machine), and per-collection retrieval fan-out (single collection + workspace filter).
