---
status: accepted
---

# Chunks carry generated background context before embedding

At ingestion time, the enrichment stage may generate a short (50–100 token) background note per Chunk that situates it inside its Document — what the section is about and where it sits (document title, chapter, topic). The same contextualized text feeds **both** the dense embedding input and the sparse/BM25 index text, so lexical search can also match the situating wording. This implements the industry "Contextual Retrieval" recipe (Anthropic, 2024): reported top-20 retrieval failure-rate reductions are −35% (contextual embeddings alone), −49% (+ contextual BM25), −67% (+ reranking).

Rules:

- Generation uses a low-cost Model Target and processes all Chunks of a Document **in document order**, so providers with prompt caching amortize the shared document prefix.
- The feature is feature-flagged off by default; enabling it changes the embedding/sparse **input-text policy**, which bumps the Embedding Schema Version and requires a full re-index into a new collection (ADR 0011/0036 hard constraint).
- Only Data Egress Policy-approved, de-identified Document content is sent to the External Model Provider.
- Enrichment failure degrades to plain chunks (no fabricated context); the Ingestion Run records the degradation but does not fail.

## Rationale

- Structure-first chunks lose antecedents ("该药物", "上述标准") and term definitions when read in isolation; a generated situating note restores matchable context at index time instead of paying query-time latency.
- Using the identical contextualized string for dense and sparse channels keeps the two representations symmetric (ADR 0075) and captures the full measured benefit.

## Consequences

- The enrichment port gains a concrete provider implementation wired in the worker composition root behind the flag; unit tests use a fake enricher asserting the composed embedding/index text.
- One extra model call per Chunk at ingest; cost is bounded by prompt caching and stays a one-time indexing cost, never a query-time cost.
- Evaluation must compare flagged vs unflagged runs on the golden set before defaulting the flag on; rollout follows the one-variable-at-a-time discipline.
