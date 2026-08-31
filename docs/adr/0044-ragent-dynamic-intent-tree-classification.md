---
status: accepted
---

# Ragent dynamic intent-tree classification

MedicalRAG reproduces Ragent's production intent behavior. Enabled intent nodes are stored in PostgreSQL and cached in Redis. The resolver builds the eligible leaf-node catalog, sends the rewritten subquestion and the known leaf definitions to the configured classifier, parses only known node ids, sorts candidates by score, applies top-N and threshold policies, and routes by node kind. System-only, knowledge-base, and tool-oriented nodes remain distinct downstream paths.

Normalization, explicit multi-question splitting, prohibited-request detection, and safety short-circuits remain deterministic preprocessing and policy stages. They do not replace the Ragent-style leaf-node classifier. An unknown or malformed classifier response produces no invented intent; the ambiguity service may ask a bounded clarification question when the leading candidates cannot be separated safely.

## Consequences

- Intent changes are versioned data changes in the tree and do not require application-code edits.
- Redis provides cross-process intent-tree caching and invalidation; PostgreSQL remains the source of truth.
- LLM output is constrained to known node ids and cannot create an intent, downgrade a safety class, or bypass a short-circuit.
- Tests cover tree loading, leaf filtering, score parsing, threshold/top-N behavior, node-kind routing, ambiguity guidance, and malformed or unknown output.
