# Reference Source Audit

This audit records the behavior read from `D:\yzb\ragent`. It is a behavior map for the implementation, not a copy of the reference project's code.

## Ragent

### Platform and module layering

Ragent is a Spring Boot 3 Java backend split into `framework`, `infra-ai`, `bootstrap`, and `mcp-server`, with a Vite/React frontend. `framework` owns response conventions, exception handling, request/user/trace context propagation, idempotency, SSE sending, distributed ids, and queue support. `infra-ai` owns model clients, routing, token counting, reranking, HTTP error normalization, and health. `bootstrap` owns product domains. `mcp-server` owns MCP tools and executors.

### Chat request path

The chat entry creates or reuses a conversation id and a task id, creates a stream callback, enters a queue limiter, and runs a trace wrapper. The stream pipeline then performs:

1. Load bounded conversation memory and persist the new user message.
2. Rewrite the question and split explicit multi-question input.
3. Resolve each sub-question against an intent tree.
4. Detect ambiguity and short-circuit with a guidance prompt when needed.
5. Short-circuit system-only intents to a model response without retrieval.
6. Run retrieval across configured channels.
7. Return a deterministic empty result message when no evidence exists.
8. Emit document sources and grounding chunks.
9. Build structured prompt messages and stream the model output.
10. Persist the assistant message, recommended questions, trace nodes, and feedback metadata.

The callback event vocabulary includes reply-message id, status, content, sources, grounding chunks, recommended questions, errors, and completion. The frontend consumes the stream as a live chat transcript.

### Retrieval and RAG

Retrieval is strategy-based and multi-channel. The codebase contains vector stores/retrievers for Milvus and pgvector, keyword stores/retrievers for Elasticsearch and database-backed search, graph query support, rerankers, and decorator-style synchronization from vector writes to keyword and graph indexes. For MedicalRAG, Milvus is the sole retrieval engine for dense and sparse/BM25 Hybrid Retrieval, while PostgreSQL provides authorization-scoped exact and structured filtering; pgvector, Elasticsearch, Neo4j, and LightRAG are not target services or compatibility adapters. Results pass through post-processors before the prompt is built.

Query rewriting preserves product names and hard constraints, removes politeness and answer-format instructions, resolves pronouns with history, and splits only explicit multiple questions. Prompt templates enforce source-only answering and prevent leaking internal document tags or retrieval jargon.

### Intent and guidance

The intent tree is persisted and queried as nodes with levels, kinds, prompts, descriptions, examples, and scores. Enabled nodes are cached in Redis. Leaf nodes are supplied to the classifier, and returned ids are checked against the loaded tree before routing. System-only, knowledge-base, and tool-oriented node kinds take different downstream paths.

Guidance groups candidates by normalized intent context, discards low-confidence or duplicate candidates, asks an ambiguity checker for confirmation, and returns a bounded list of user-facing choices. Unknown or malformed classifier output does not create a new intent.

### Ingestion

Document ingestion is a database-defined pipeline with task-level and node-level status/logs. The reference source fetchers cover uploaded files, HTTP URLs, and Feishu. Its parsers cover Markdown, Tika-supported documents, CSV, Excel, images, and MinerU-backed PDF. Structured chunks preserve headings, paragraphs, lists, code, tables, images, and provenance. Chunking strategies include fixed-size, structure-aware, and block-aware packing with token limits. Enhancement and enrichment nodes can add summaries, keywords, and metadata before embedding and indexing. MedicalRAG intentionally narrows this boundary to uploaded `.docx`, `.pptx`, `.xlsx`, `.pdf`, `.md`, `.txt`, `.png`, `.jpg`, and `.jpeg` files; URL and Feishu fetching are rejected.

### Reliability and operations

The source contains workload-specific executors, TTL context propagation, Redis queue-based concurrency control with Lua and pub/sub, rate limiting, task cancellation, model selection by capability/priority, first-token probing, and a three-state model circuit breaker. AOP records trace nodes around retrieval and other expensive stages. Operator pages cover dashboard KPIs, knowledge bases, documents/chunks, ingestion pipelines/tasks, intent trees, query terms, model/settings, traces, feedback, users, and change logs.

### Frontend behavior

The React/Vite frontend includes login, chat, conversation list, welcome/recommended questions, Markdown and code rendering, sources, feedback buttons, streaming state, deep-thinking toggle, document preview, and admin routes for dashboard, knowledge, ingestion, intent, query-term mapping, traces, models, sample questions, users, settings, and change logs.

## Translation Rules

- Translate Ragent's large number of Java extension interfaces into a smaller set of deep Python interfaces where variation is real: retrieval, model, memory, slot extraction, trace, and runtime.
- Preserve event ordering and short-circuit semantics because they affect user-visible behavior.
- Preserve the dynamic intent-tree model, node kinds, leaf classification, score filtering, ambiguity guidance, and intent-specific slot schemas.
- Keep MedicalRAG's safety policy, evidence provenance, external-provider boundaries, and supported document formats as product constraints rather than reference-project behavior.
- Prefer PostgreSQL, Redis, Milvus, and the requested Docker Compose deployment over introducing unrelated infrastructure from the reference project.
- Replace RocketMQ with arq for Ragent's durable asynchronous messaging: stable job ids, worker-side retries, a PostgreSQL transactional outbox for coupled publication, and a PostgreSQL-backed failure/replay surface. Aegra remains the owner of agent Thread/Run execution and Agent Protocol streaming.
- Reject Ragent's MCP Server and MCP Client compatibility paths, including MCP parameter extraction and tool routing. Intent-specific slots remain an application-owned structured-output step; they are not an MCP compatibility layer.
- Reject Ragent's URL/Feishu source fetchers, Ollama integration, local model services, and local model adapters. Production model, embedding, reranker, and MinerU calls use external APIs; deterministic fakes exist only in tests.
- Preserve Ragent's inspectable execution semantics through Aegra's official Langfuse integration for redacted AI/RAG observations and PostgreSQL business `run_events`; do not add application-owned OpenTelemetry, Collector, Tempo, Grafana, or custom Trace runtime. API and Worker diagnostics use structured logs, metrics, and health checks, while PostgreSQL may store the Langfuse trace id for correlation.
- Replace Ragent's Snowflake distributed ids with UUIDv7 business ids (Python 3.14 `uuid.uuid7()`, [ADR 0066](../adr/0066-uuidv7-is-the-universal-business-identifier.md)) and derive stable arq job ids from them. Operator charting (recharts + @antv/g6), document preview (per-format renderers, [ADR 0068](../adr/0068-document-preview-mainstream-per-format-renderers.md)), and the deep-thinking mode (Analysis Depth option) are closed by ADR 0067–0069; the [stack replacement matrix](stack-replacement-matrix.md) is the tracking artifact.
- Treat all reference data as sample configuration, not as a license to make unsupported clinical claims.
