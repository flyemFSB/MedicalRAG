# Architecture Decision Records

Accepted ADRs only. Superseded decisions and planning notes live in the local `_archive/docs/` tree (not published on GitHub).

Status values: `accepted` (current), `amended` (current with later amendment noted in the ADR or a newer ADR).

## Index

| ADR | Decision |
|---|---|
| [0001](0001-aegra-is-the-production-runtime.md) | Aegra is the production Thread/Run runtime |
| [0002](0002-postgres-owns-business-conversations-aegra-owns-runtime-state.md) | Postgres owns business conversations; Aegra owns runtime state |
| [0003](0003-workspace-is-the-resource-isolation-scope.md) | Workspace is the resource isolation scope |
| [0004](0004-system-knowledge-is-read-only-and-workspace-knowledge-is-private.md) | System knowledge is read-only; workspace knowledge is private |
| [0005](0005-system-knowledge-requires-reviewed-versions.md) | System knowledge requires reviewed versions |
| [0006](0006-medicalrag-is-an-evidence-explanation-tool.md) | MedicalRAG is an evidence explanation tool |
| [0007](0007-external-apis-provide-generation-and-embeddings.md) | External APIs provide generation and embeddings |
| [0008](0008-first-version-excludes-identifiable-patient-data.md) | v1 excludes identifiable patient data |
| [0009](0009-use-application-owned-model-provider-interfaces.md) | Application-owned model provider interfaces |
| [0010](0010-platform-owns-model-credentials.md) | Platform owns model credentials |
| [0012](0012-hybrid-retrieval-is-required-for-medical-questions.md) | Hybrid retrieval is required for medical questions |
| [0013](0013-document-ingestion-is-always-asynchronous.md) | Document ingestion is always asynchronous |
| [0015](0015-mineru-api-is-the-external-extraction-provider.md) | MinerU API is the external extraction provider |
| [0016](0016-official-mineru-cloud-api.md) | Official MinerU Cloud API |
| [0018](0018-application-owned-authentication.md) | Application-owned authentication |
| [0019](0019-server-side-redis-sessions-with-secure-cookies.md) | Server-side Redis sessions with secure cookies |
| [0020](0020-same-origin-entrypoint-for-web-and-api.md) | Same-origin entrypoint for web and API |
| [0023](0023-aegra-runs-as-an-independent-compose-runtime.md) | Aegra runs as an independent Compose runtime |
| [0024](0024-aegra-reuses-the-application-session.md) | Aegra reuses the application session |
| [0025](0025-shared-medical-application-package-for-fastapi-and-aegra.md) | Shared medical application package for FastAPI and Aegra |
| [0028](0028-browser-uploads-use-presigned-multipart-sessions.md) | Browser uploads use presigned multipart sessions |
| [0029](0029-first-version-excludes-malware-scanning.md) | v1 excludes malware scanning |
| [0030](0030-supported-document-format-allowlist.md) | Supported document format allowlist |
| [0031](0031-mineru-callback-first-with-polling-reconciliation.md) | MinerU callback-first with polling reconciliation |
| [0032](0032-mineru-vlm-is-the-default-extraction-profile.md) | MinerU VLM is the default extraction profile |
| [0033](0033-raw-mineru-results-are-immutable-artifacts.md) | Raw MinerU results are immutable artifacts |
| [0034](0034-structure-first-chunking-preserves-provenance.md) | Structure-first chunking preserves provenance |
| [0035](0035-embedding-text-includes-structural-context.md) | Embedding text includes structural context |
| [0036](0036-query-embeddings-use-rewritten-subquestions.md) | Query embeddings use rewritten sub-questions |
| [0037](0037-external-reranker-api-orders-hybrid-candidates.md) | External reranker API orders hybrid candidates |
| [0039](0039-evidence-fusion-is-deterministic-and-policy-versioned.md) | Evidence fusion is deterministic and policy-versioned |
| [0041](0041-generation-is-streamed-without-a-blocking-output-gate.md) | Generation streams without a blocking output gate |
| [0042](0042-fixed-medical-ai-disclaimer.md) | Fixed medical AI disclaimer |
| [0043](0043-prohibited-individual-requests-short-circuit-before-retrieval.md) | Prohibited individual requests short-circuit before retrieval |
| [0044](0044-ragent-dynamic-intent-tree-classification.md) | Ragent dynamic intent-tree classification |
| [0049](0049-ragent-capability-complete-migration-matrix.md) | Ragent capability-complete migration matrix |
| [0051](0051-mcp-compatibility-is-out-of-scope.md) | MCP compatibility is out of scope |
| [0053](0053-docker-compose-yml-is-the-deployment-entrypoint.md) | Root `docker-compose.yml` is the deployment entrypoint |
| [0055](0055-monorepo-uses-independent-uv-and-pnpm-workspaces.md) | Monorepo uses independent uv and pnpm workspaces |
| [0058](0058-assistant-ui-uses-native-agent-protocol-v2-runtime.md) | assistant-ui uses native Agent Protocol v2 runtime |
| [0060](0060-shared-infra-package-and-pruned-package-graph.md) | Shared infra package and pruned package graph |
| [0064](0064-uv-manages-python-314-runtime.md) | uv manages the Python 3.12 runtime baseline |
| [0065](0065-aliyun-mirrors-for-pnpm-uv-and-apt.md) | Aliyun mirrors for pnpm, uv, and apt |
| [0066](0066-uuidv7-is-the-universal-business-identifier.md) | UUIDv7 is the universal business identifier |
| [0068](0068-document-preview-mainstream-per-format-renderers.md) | Document preview: mainstream per-format renderers |
| [0069](0069-deep-thinking-is-analysis-depth-option.md) | Deep thinking is an analysis depth option |
| [0070](0070-vite-spa-with-nginx-proxy-is-the-frontend-runtime.md) | Vite SPA with Nginx proxy is the frontend runtime |
| [0071](0071-openapi-single-source-contract-generation.md) | OpenAPI single-source contract generation |
| [0073](0073-taskiq-replaces-arq-as-the-durable-job-queue.md) | TaskIQ replaces arq as the durable job queue |
| [0074](0074-prefer-popular-third-party-libraries.md) | Prefer popular third-party libraries |
| [0075](0075-qdrant-replaces-milvus-as-the-hybrid-retrieval-engine.md) | Qdrant replaces Milvus as the hybrid retrieval engine |
| [0076](0076-aegra-owns-langfuse-ingestion-via-otlp.md) | Aegra owns observability export via OTLP (fail-open) |
| [0077](0077-chunking-adds-size-caps-sentence-boundary-splits-overlap-and-atomic-tables.md) | Chunking: size caps, sentence splits, overlap, atomic tables |
| [0078](0078-chunks-carry-generated-background-context-before-embedding.md) | Chunks carry generated background context before embedding |
| [0079](0079-documents-support-unpublish-and-delete-with-cascading-index-cleanup.md) | Documents support unpublish/delete with index cleanup |
| [0080](0080-production-hardening-baseline.md) | Production hardening baseline |
| [0081](0081-openai-sdk3-httpx2-alignment.md) | OpenAI SDK 3.x and httpx2 alignment |
| [0082](0082-phoenix-replaces-langfuse-as-observability-backend.md) | Phoenix replaces Langfuse as observability backend |
| [0083](0083-pnpm-12-js-package-manager-baseline.md) | pnpm 12 is the JS package manager baseline |
| [0084](0084-typescript-7-native-compiler-baseline.md) | TypeScript 7 native compiler is the frontend typecheck baseline |
| [0085](0085-operator-console-without-charting-libraries.md) | Operator console ships without charting libraries |
| [0086](0086-rabbitmq-replaces-redis-streams-as-taskiq-transport.md) | RabbitMQ replaces Redis Streams as the TaskIQ transport |
| [0087](0087-retrieval-policy-v2-chunking-tolerance-and-table-specialization.md) | Retrieval policy v2 and chunking tolerance adopt reference-implementation quality semantics |
| [0088](0088-coverage-gates-target-changed-lines.md) | Coverage gates target changed lines; repo totals only guard against regression |

## Superseded (not published; local `_archive/docs/adr/`)

| Was | Replaced by | Topic |
|---|---|---|
| 0011 / 0017 / 0026 / 0027 / 0052 / 0054 / 0056 | [0075](0075-qdrant-replaces-milvus-as-the-hybrid-retrieval-engine.md) | Milvus/MinIO retrieval stack |
| 0014 | [0015](0015-mineru-api-is-the-external-extraction-provider.md) / [0016](0016-official-mineru-cloud-api.md) | MinerU primary engine → official API |
| 0021 | [0070](0070-vite-spa-with-nginx-proxy-is-the-frontend-runtime.md) | TanStack Start SSR → Vite SPA |
| 0022 | [0058](0058-assistant-ui-uses-native-agent-protocol-v2-runtime.md) | assistant-ui LangGraph adapter → native v2 |
| 0038 | [0037](0037-external-reranker-api-orders-hybrid-candidates.md) | Graph evidence bypasses reranking |
| 0040 | [0041](0041-generation-is-streamed-without-a-blocking-output-gate.md) | Schema-validated generation gate |
| 0050 / 0063 | [0073](0073-taskiq-replaces-arq-as-the-durable-job-queue.md) | RocketMQ / arq → TaskIQ |
| 0057 | [0001](0001-aegra-is-the-production-runtime.md) + [0058](0058-assistant-ui-uses-native-agent-protocol-v2-runtime.md) | Pure Python LangGraph runtime |
| 0059 / 0061 / 0062 / 0072 | [0082](0082-phoenix-replaces-langfuse-as-observability-backend.md) | Langfuse / Tempo observability |
| 0067 | [0085](0085-operator-console-without-charting-libraries.md) | recharts / G6 console charting |

## Rules

1. New decisions: open a new ADR under `docs/adr/`, status `accepted` only when implemented or explicitly locked.
2. When a decision is replaced, mark the old ADR `status: superseded` and move the file to `_archive/docs/adr/` (local only); update this index.
3. Do not link to archived files from published docs; cite the superseding ADR number instead.
