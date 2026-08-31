---
status: accepted
---

# Every Ragent capability receives a target-stack migration mapping

MedicalRAG treats the complete Ragent migration as behavioral parity across the reference project's production paths, administration flows, optional adapters, experimental capabilities, data contracts, event protocols, and failure semantics. A Java class or dependency is not translated mechanically. Each source capability must be recorded in a migration matrix with one target status:

- `implemented`: reproduced directly with the target stack;
- `replaced`: reproduced by a target-native capability with equivalent observable behavior;
- `adapted`: exposed through a compatibility port and a target-specific adapter;
- `rejected`: intentionally outside the product contract, with a typed user/operator-visible reason.

The runtime ownership boundary is fixed: Aegra owns LangGraph Thread/Run execution, checkpoints, recovery, workers, and Agent Protocol streaming; FastAPI owns application APIs, authentication, authorization, knowledge management, configuration, and domain services; PostgreSQL owns durable business data, authorization-scoped exact/structured filtering, and the transactional outbox; Redis owns sessions, rate limits, short-lived cache, queue coordination, cross-process signals, and the arq job transport; arq executes asynchronous application jobs with stable job ids, worker-side retries, and PostgreSQL-backed failure/replay; Milvus is the sole dense and sparse/BM25 retrieval engine; `packages/infra` owns concrete adapters; external APIs provide generation, dense embeddings, reranking, and MinerU extraction. Ollama and other local model services are not target providers.

The ingestion contract is intentionally narrower than Ragent's connector surface. Only `.docx`, `.pptx`, `.xlsx`, `.pdf`, `.md`, `.txt`, `.png`, `.jpg`, and `.jpeg` are supported. Feishu, URL ingestion, and other unsupported connectors receive a typed unsupported-source result rather than an undocumented partial implementation.

## Consequences

- The migration plan must inventory optional Ragent modules such as alternate vector stores, keyword stores, message brokers, local-model adapters, graph-oriented experiments, MCP services, URL/Feishu connectors, and administration routes so each receives an explicit rejected or replaced status.
- arq replaces RocketMQ as the background job executor with stable job ids, worker-side retries, a PostgreSQL transactional outbox for coupled publication, and a PostgreSQL-backed failure/replay surface; MCP Server/Client paths, MCP parameter extraction, URL/Feishu connectors, local-model adapters, and alternate retrieval products are explicitly rejected rather than silently omitted.
- Every inventory row must identify its target component, ownership boundary, protocol or data contract, official documentation source, test seam, and status.
- A target-native replacement is accepted only when it preserves the source capability's externally observable behavior and failure semantics; similar library names are not sufficient.
- Unsupported source connectors remain visible in the migration matrix and receive deterministic rejection behavior, so their omission cannot be mistaken for an unfinished migration.
- The migration matrix is the release gate for declaring Ragent parity complete.
