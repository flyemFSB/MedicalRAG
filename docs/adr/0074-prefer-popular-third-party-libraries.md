---
status: accepted
---

# Prefer popular third-party libraries over custom implementations

Where a maintained, popular library provides the behavior, use it instead of a hand-rolled implementation; reserve custom code for product-specific domain logic that no library provides and for the framework-free domain seam (ADR 0025). Adopted concretely:

- **OpenAI-compatible providers** use the official `openai` SDK (chat completions, streaming, embeddings) rather than hand-rolled HTTP clients. The application-owned provider ports in `medical-core` remain (ADR 0009); only the adapter implementation changed.
- **Structured logging** uses `loguru` with the same safety redlines (safe-field allowlist, forbidden sensitive fields; development-standards §3) enforced at the call site before binding.
- **Streaming** uses the `openai` SDK's async stream (client side) and FastAPI's built-in `EventSourceResponse` (server side, recipe §1.1); no custom SSE parsing.
- **User experience first**: streaming is direct and non-blocking (ADR 0041); UI and copy prioritize clarity and the evidence-first reading.

## Consequences

- `packages/infra` gains `openai` and `loguru` dependencies; `medicalrag_core` stays framework-free (domain logic such as evidence fusion, the state machines, slot validation, and structure-first chunking has no library substitute and remains custom).
- Logs are produced through `loguru`; the structured-logging helper rejects forbidden/unknown fields before binding.
- Any future provider or streaming integration should first check for a popular library before writing custom HTTP/parsing code.

## Full-code audit result (2026-08-02)

Audited every module against available popular libraries. Adopted where a library fit: the `openai` SDK for all provider adapters, `loguru` for logging, and pydantic for the classifier's structured-output parsing (all-or-nothing validation, ADR 0044). Remaining custom code is deliberate and has no better-library substitute:

- **Adapter mappings** (SQLAlchemy row → entity, Milvus hit → Candidate): necessary conversions; no library performs them.
- **Domain algorithms** (evidence fusion, intent tree, chat/ingestion state machines, slot coercion, structure-first chunking, publication validation): product-specific deterministic logic, and ADR 0025 forbids framework dependencies in `medical-core`; the custom tables/services are smaller and more precise than generic libraries (`transitions`, pydantic).
- **Composition roots** (app pipeline assembly) and **prompt assembly**: application wiring and product-specific prompts.
- **Frontend**: assistant-ui official components/hooks, TanStack Router, React — no hand-rolled runtime or parsing.
