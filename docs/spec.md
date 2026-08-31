---
status: research-gated-draft
---

# MedicalRAG Specification

> Draft status: this specification is not implementation-final until the Wayfinder official-documentation research tickets are closed and their findings are reconciled with the selected stack.

## Problem Statement

The current workspace has no application implementation. Ragent is the sole behavior reference: it demonstrates an end-to-end production-oriented RAG platform with conversational memory, query rewriting and splitting, dynamic intent trees with ambiguity guidance, multi-channel retrieval, structured ingestion, streaming responses, model routing and failover, Redis-backed concurrency controls, trace recording, feedback, authentication, and an operator console. Ragent's optional MCP paths are reference-only and are outside this product boundary.

The target product reproduces Ragent's user-visible and operational behavior while applying MedicalRAG's evidence and safety policy and using the requested stack: uv, Python 3.14, FastAPI, PostgreSQL, Redis, TaskIQ, React, Vite (SPA with a same-origin Nginx/Vite proxy), assistant-ui, Qdrant, Langfuse, and Aegra-compatible agent runtime behavior. Production generation, embedding, reranking, and MinerU extraction use external APIs through replaceable adapters. Deterministic fakes are permitted for tests; Ollama and other local model services are not part of the product.

## Solution

Build a full-stack medical RAG workbench with one deep chat orchestration interface. A request passes through memory loading, query rewrite and split, dynamic intent-tree resolution, intent-specific slot extraction, ambiguity handling, strategy-based retrieval, evidence assembly, medical safety policy, answer generation, business run persistence, and redacted Langfuse observation. Domain results remain directly testable as structured state; the live assistant UI consumes Aegra's Agent Protocol v2 stream through the official runtime.

The backend uses PostgreSQL as the durable source of truth, including relational representations of documents, chunks, conversations, messages, business run records, audit events, feedback, intent-tree nodes, slot schemas, model targets, and the transactional outbox. Redis is used for authentication sessions, rate limiting, short-lived coordination, intent-tree caching, pub/sub signals, and the TaskIQ job transport. TaskIQ executes ingestion and other asynchronous domain workflows as Redis-backed jobs with worker-side retries, stable job ids, and PostgreSQL-backed failure/replay; transactional publication uses a PostgreSQL outbox. Aegra's official Langfuse integration is the only AI/RAG Trace backend; API and Worker infrastructure diagnostics use structured logs, metrics, and health checks without an application-wide tracing stack. Langfuse export is fail-open. SQLite and in-memory adapters are permitted only for local smoke tests and deterministic unit tests.

The frontend is a Vite single-page application built with React, Vite, and TypeScript 6.0.3, served statically and proxied same-origin through Nginx in production and the Vite dev server in development. Aegra natively exposes Agent Protocol v2. The browser uses assistant-ui's official `@assistant-ui/react-langchain` `useStreamRuntime`, which wraps `@langchain/react` v1 `useStream` and the `@langchain/langgraph-sdk` v2-native ThreadStream SSE transport. The integration uses the stock `GET /state`, `POST /stream/events`, and `POST /commands` path through a same-origin `/api/agent` proxy; no custom runtime, SSE parser, event bridge, or message reducer is implemented. The application may add only the official remote thread-list adapter and the PostgreSQL Conversation↔Aegra thread mapping needed for product navigation. The main screen exposes conversations, a medical chat thread, evidence/source inspection, and a compact analysis panel for resolved intents and slots. Operator routes expose knowledge ingestion, chunk inspection, intent-tree configuration, trace detail, and model/runtime health. Docker Compose is managed through the root `docker-compose.yml` entrypoint with `dev`, `test`, and `prod` profiles.

## User Stories

1. As a clinician, I want to ask a medical question in natural language, so that I can find relevant curated information without learning a query language.
2. As a clinician, I want the answer to include inspectable evidence, so that I can distinguish documented information from model wording.
3. As a clinician, I want the system to state when information is missing or ambiguous, so that I do not mistake a guess for a clinical fact.
4. As a clinician, I want the system to resolve a question to a configured intent and its slots, so that the correct retrieval strategy can run.
5. As a clinician, I want one question to support multiple Ragent-style sub-question intents, so that clearly independent requests can be processed in one turn.
6. As a clinician, I want dynamic intent-tree nodes and examples to be editable without changing orchestration code, so that domain behavior can evolve safely.
7. As a clinician, I want follow-up references resolved against recent conversation context, so that I can ask natural follow-up questions.
8. As a clinician, I want the system to distinguish a new topic from continuation of the active intent, so that old context does not contaminate retrieval.
9. As a clinician, I want a compound question split only when the text clearly contains separate questions, so that an abstract comparison is not unnecessarily fragmented.
10. As a clinician, I want to see a clarification prompt when the recognized intent is genuinely ambiguous, so that I can choose the intended topic before retrieval runs.
11. As a clinician, I want a safety notice for treatment, medication, diagnosis, and urgent-symptom requests, so that the assistant's scope is clear.
12. As a clinician, I want the answer to avoid unsupported diagnosis and prescribing instructions, so that the tool remains an evidence assistant rather than an autonomous clinician.
13. As a clinician, I want the answer to stream progressively, so that I can begin reading while generation continues.
14. As a clinician, I want to stop a running answer, so that an incorrect or unnecessary request does not consume more model time.
15. As a clinician, I want to regenerate or continue a conversation, so that I can refine the question without losing prior context.
16. As a clinician, I want multiple conversations, so that unrelated cases remain separate.
17. As a clinician, I want conversation history to remain useful after many turns, so that the system can summarize old context instead of exceeding the model window.
18. As a clinician, I want to submit positive or negative feedback on an answer, so that poor retrieval and generation can be reviewed.
19. As a knowledge maintainer, I want to create a knowledge base, so that medical corpora can be isolated by scope.
20. As a knowledge maintainer, I want to submit scanned PDFs, images, Excel workbooks, PowerPoint presentations, and complex multimodal PDFs, so that supported medical sources can become searchable without a bespoke script.
21. As a knowledge maintainer, I want document ingestion to expose parsing, chunking, enrichment, and indexing states, so that a failed document can be repaired at the correct stage.
22. As a knowledge maintainer, I want structure-aware chunks to preserve headings and provenance, so that retrieved context retains the meaning of the source.
23. As a knowledge maintainer, I want to inspect and edit chunks, so that a bad source fragment does not silently influence future answers.
24. As a knowledge maintainer, I want to maintain intent-tree nodes, examples, slot schemas, and safety rules, so that the medical domain can evolve without changing core orchestration code.
25. As a knowledge maintainer, I want to inspect retrieval candidates and evidence provenance, so that a route can be validated independently of answer generation.
26. As an operator, I want to configure multiple model targets with priority and capabilities, so that a failed provider can be replaced without changing chat code.
27. As an operator, I want model health to move through closed, open, and half-open states, so that repeated provider failures do not stall user requests.
28. As an operator, I want request concurrency and rate limits, so that a burst of users cannot exhaust model, database, or Redis capacity.
29. As an operator, I want queued requests to receive status events, so that users understand whether a request is waiting, running, or failed.
30. As an operator, I want a Langfuse trace for every chat run, so that latency, rewriting, intents, slots, retrieval, model selection, and failure details are inspectable.
31. As an operator, I want Langfuse observations to redact secrets and patient-identifying data, so that observability does not become a second data leak.
32. As an operator, I want a dashboard with ingestion, chat, model, and retrieval metrics, so that the system's operational state is visible.
33. As an operator, I want health and readiness endpoints, so that deployment systems can distinguish a live process from a ready dependency graph.
34. As an operator, I want Aegra-compatible thread and run semantics, so that the agent runtime can be self-hosted and scaled independently of the medical domain.
35. As a developer, I want deterministic in-memory adapters, so that domain behavior can be tested without PostgreSQL, Redis, Qdrant, or an external model.
36. As a developer, I want the HTTP and chat orchestration contracts to be small and explicit, so that adapters can be replaced without spreading provider details across the application.
37. As a developer, I want migrations, typed settings, structured logs, and repeatable commands, so that local and production environments share the same operational assumptions.
38. As a security reviewer, I want password hashes, signed sessions, request validation, safe query parameters, and upload limits, so that the platform does not repeat insecure demo defaults.
39. As an accessibility user, I want keyboard navigation, visible focus, semantic labels, reduced-motion behavior, and status text that does not rely on color, so that the workbench remains usable under assistive technology.
40. As a clinician, I want to request a more thorough analysis of a question, so that I can explore deeper evidence without changing the safety boundary.

## Implementation Decisions

- The central application module is a chat orchestrator with a small interface: accept a chat request and return a structured answer result or an asynchronous stream of typed events. It owns ordering and short-circuit rules; adapters own persistence, model calls, retrieval, and external runtime integration.
- The agent runtime is a Python LangGraph `StateGraph` hosted by Aegra. LangChain is used inside nodes for model/provider adapters, prompts, structured output, tools, and retrieval primitives. The root workflow does not use LangChain `create_agent` because the Ragent-compatible pipeline is controlled, bounded, and explicitly branched rather than an open-ended ReAct loop.
- The request pipeline follows this order: authenticate, apply rate limit, load memory, rewrite and optionally split, resolve the dynamic intent tree, extract intent-specific slots, detect ambiguity, handle system-only intents, retrieve through the selected strategies, assemble grounded context, apply the medical safety policy, call the selected model, persist messages and the business run, and emit completion metadata. Aegra records the associated redacted AI/RAG observation through its official Langfuse integration.
- Intent definitions mirror Ragent's tree model. Each node contains an id, parent, level, kind, description, examples, prompt metadata, enabled state, and optional slot schema. Only eligible leaf nodes are classified; returned ids are whitelisted against the loaded tree.
- Intent resolution uses Redis-cached PostgreSQL tree data, structured LLM output, score ordering, top-N/threshold filtering, and a separate ambiguity-guidance step. Unknown or malformed model output produces an empty candidate set or clarification rather than a fabricated route.
- Document retrieval is strategy-based. The first implementation uses Qdrant dense and sparse/BM25 Hybrid Retrieval with PostgreSQL authorization-scoped exact/structured filtering, plus external Embedding and Reranker Providers. Results are fused, deduplicated, source-ranked, and capped before prompt assembly.
- Evidence is a first-class result object with source id, title, document id, chunk id, snippet, intent provenance, score, and citation label. The application emits citation metadata only for retrieved Evidence; it does not buffer or block already-streamed model text for post-generation citation validation.
- The answer policy is evidence-first and medical-safe: no diagnosis, prescription, dosage, or emergency reassurance is generated as fact when the retrieved evidence does not support it. Treatment and urgent-symptom intents receive a concise scope notice and escalation language.
- LLM providers implement a streaming interface through external OpenAI-compatible HTTP endpoints. A provider outage produces a deterministic evidence-insufficiency result after failover; the product does not deploy Ollama or another local model service.
- The chat orchestrator accepts an Analysis Depth option that selects an analysis-capable Model Target, raises the retrieval budget and Evidence cap within policy, and runs an evidence-synthesis stage; it never changes the Safety Boundary, the Evidence Answer contract, citation rules, or the Data Egress Policy.
- Model routing uses priority, capability matching, timeout, retry, and a three-state health circuit. The circuit state is stored in Redis when available and falls back to process-local state for development.
- Redis adapters cover authentication sessions, rate limiting, short-lived query cache, intent-tree cache, and pub/sub. TaskIQ adapters cover asynchronous jobs and domain events with stable job ids, worker-side retries, a PostgreSQL transactional outbox for coupled publication, and a PostgreSQL-backed failure/replay surface. Aegra is a mandatory production runtime exposed through native Agent Protocol v2; local orchestration fixtures are limited to deterministic tests. Python `langgraph` and `langgraph-sdk` belong to the agent/server side. The browser uses assistant-ui's official `useStreamRuntime`; `@langchain/react` owns the v2-native SDK transport and the application does not directly implement the protocol.
- Aegra owns Thread/Run execution, checkpoints, recovery, worker leases, and Agent Protocol streaming. TaskIQ does not replace Aegra's runtime; it executes durable application workflows such as ingestion, indexing, and operational events.
- The root `docker-compose.yml` is the canonical deployment entrypoint. Profiles select local development, integration testing, or self-hosted production topology while preserving service names, networks, health checks, and persistent-volume contracts.
- Authentication uses Argon2id password hashing and server-side Redis Authentication Sessions in secure cookies. Every user-owned resource is scoped by the authenticated User, Workspace membership, or an explicit operator role.
- The frontend is a Vite SPA using TanStack Router, Vite as the build tool, TypeScript 6.0.3, assistant-ui's official `@assistant-ui/react-langchain` runtime, and the built-in v2 SSE transport through a same-origin Nginx/Vite proxy. No custom runtime, message reducer, protocol bridge, or SSE parser is introduced. The operator console uses recharts for dashboard KPIs and @antv/g6 for the intent-tree editor; document preview uses native md/txt/images plus pdfjs-dist (PDF), docx-preview (docx), and SheetJS + TanStack Table (xlsx), with pptx a typed unsupported in v1; the deep-thinking toggle maps to the Analysis Depth request option.
- The backend exposes ordinary JSON APIs for business operations and Aegra's native Agent Protocol v2 endpoints for the assistant-ui chat path. Evidence, intent, slot, and safety metadata use compatible graph state, custom channels, or typed data/UI parts.
- PostgreSQL migrations cover identity, conversations, messages, knowledge bases, documents, chunks, intent-tree nodes, slot schemas, query-term mappings, chat runs, ingestion runs, run events, audit events, feedback, model targets, and ingestion artifacts. Every business record uses a UUIDv7 identifier generated by the application with Python 3.14 `uuid.uuid7()`; PostgreSQL columns are typed `uuid` and stable TaskIQ job ids derive from the business aggregate id. Business run records may store an optional `langfuse_trace_id` for correlation; PostgreSQL does not store Langfuse observations as a span tree. Qdrant stores versioned dense and sparse indexes; PostgreSQL stores vector metadata and index ownership, not the dense vector collection itself.
- The project uses Python 3.14 as its declared runtime and uv as the dependency and command runner. Type annotations use modern Python syntax, Pydantic v2 models validate trust-boundary inputs, and async I/O is used for FastAPI, SQLAlchemy, Redis, TaskIQ, and model calls.
- Aegra's official Langfuse integration is the sole AI/RAG Trace path. It uses the current Python SDK/server-compatible v4 line (research snapshot `4.14.1`) where applicable, and records only scrubbed operation metadata, status, latency, counts, model/provider information, token usage where available, and safe error classes. FastAPI, Worker, and domain services do not initialize Langfuse clients, add manual observations, or export a second trace. The integration is fail-open; its internal OpenTelemetry use, if required by Aegra, is an implementation detail rather than a MedicalRAG platform dependency.
- The Python workspace contains `packages/medical-core`, `packages/infra`, and `packages/contracts`. `medical-core` is the shared domain seam holding entities, state machines, policies, ports, and deterministic services; the chat pipeline (LangGraph graph assembly and Aegra binding) lives in `apps/agent`, not in `medical-core`. `infra` is shared by API, Agent, and Worker and owns business run/audit repositories, structured logging, metrics, and health adapters; it is not nested under `apps/api`; each application owns its own composition root. `packages/contracts` uses OpenAPI single-direction generation for `/api` types and pins Agent Protocol v2 for `/api/agent` (ADR 0071). The repository-level `infra/` directory is reserved for Compose and deployment assets.
- No standalone `packages/ui`, `packages/testkit`, `packages/config`, `packages/common`, or `packages/utils` exists. Web components stay in `apps/web`; test fakes and fixtures stay with their member; configuration stays with each runtime; shared behavior must belong to an explicit domain or adapter module.
- The PostgreSQL run/audit repository is an adapter in `packages/infra/persistence` or `packages/infra/observability` and stores durable business lifecycle data, not Trace observations. Its records contain scrubbed IDs, timings, versions, statuses, counts, failure codes, and an optional Langfuse trace correlation id. Aegra owns the Langfuse integration; its export contains only scrubbed IDs, timings, versions, statuses, counts, and error classes by default.

## Testing Decisions

- Tests verify external behavior at the chat orchestrator interface and HTTP endpoints. They do not assert private helper call order, SQL string spelling, or framework internals.
- Deterministic tests use in-memory adapters for the intent tree, document retriever, memory, model, rate limiter, and business run repository. This keeps medical routing and safety behavior runnable in CI without external services.
- Intent tests cover tree loading, leaf filtering, known and unknown node ids, score ordering, threshold and top-N behavior, multiple sub-questions, topic switching, ambiguity guidance, empty output, and structured LLM parsing.
- Slot tests cover required and optional fields, missing slots, enum constraints, multi-turn updates, and invalid model output.
- Retrieval tests cover score ordering, evidence deduplication, strategy merge, empty results, provenance preservation, and result caps.
- Pipeline tests cover the normal grounded path, system-only path, ambiguity short circuit, empty retrieval path, provider fallback, cancellation, safety notice, message persistence, business run completion, and Langfuse observation correlation.
- API tests cover validation errors, authentication, ownership, SSE event order, feedback, health/readiness, document ingestion, and operator authorization.
- Persistence tests run against SQLite for repository behavior and PostgreSQL in the optional integration profile. Migration tests verify that the schema can be created from an empty database.
- Redis tests run in the optional integration profile; the process-local fallback is covered by unit tests.
- TaskIQ enqueue, worker retry, outbox relay, failure/replay, and idempotency contracts run in the optional integration profile; deterministic domain tests use an in-memory job adapter.
- Frontend tests focus on route rendering, accessible labels, empty/loading/error states, chat adapter event handling, source panel behavior, and responsive shell behavior. Visual verification is done with a production build and browser screenshots when a browser is available.
- Observability tests cover business run/audit persistence, Aegra/Langfuse observation metadata, redaction of prompts/document text/patient identifiers/secrets, structured-log correlation fields, metrics, sampling, and fail-open exporter failure. API/Worker correctness and business persistence do not depend on Langfuse availability.
- The required minimum check for every non-trivial module is one runnable test at the highest seam that exposes the behavior. Broader coverage is reserved for shared orchestration, persistence, security, and user-facing workflows.

## Out of Scope

- Clinical diagnosis, autonomous triage, prescribing, dosage calculation, or replacing a licensed clinician.
- Training a new general-purpose medical language model.
- Importing a full external reference project's source datasets into this workspace.
- Reimplementing the entire Aegra deployment platform; only the integration seam and compatible thread/run behavior needed by this product are included.
- Running a local MinerU GPU pipeline; supported multimodal sources are processed through the official MinerU cloud API.
- Billing, multi-tenant enterprise SSO, external patient record integration, and regulated clinical workflow certification.
- MCP Server/Client protocol compatibility and external MCP server connections.
- MCP parameter extraction and MCP tool routing.
- URL and Feishu ingestion; ingestion is limited to `.docx`, `.pptx`, `.xlsx`, `.pdf`, `.md`, `.txt`, `.png`, `.jpg`, and `.jpeg` uploads processed through the MinerU API where applicable.
- Ollama, local LLM/embedding/reranker services, and any other local model server.
- Alternate Ragent retrieval products such as pgvector, Elasticsearch, Neo4j, and LightRAG. Their retained responsibilities are implemented through application-owned PostgreSQL exact/structured filtering and Qdrant dense/sparse Hybrid Retrieval.
- Claiming that a current dependency version is safe merely because it is newest; lockfiles and upgrade checks remain deployment responsibilities.

## Further Notes

Ragent is treated as the behavior reference, not as code to copy. Its module separation, event flow, dynamic intent tree, pipeline ordering, retrieval strategies, and failure handling are translated into Python modules with fewer and deeper seams. Medical safety, document provenance, and external-provider boundaries are added as product constraints.

This document is the local specification requested by the `to-spec` workflow. No issue-tracker connector is available in the current Codex tool set, so it could not be published or labeled automatically.
