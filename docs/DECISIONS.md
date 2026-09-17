# Decisions (current)

Authoritative list of locked product and architecture decisions. Full text: [docs/adr/](adr/).  
Planning tickets, research notes, and superseded ADRs are local-only under `_archive/docs/` (not on GitHub).

## Product and safety

- Evidence-first medical RAG workbench; evidence explanation tool, not autonomous clinical decision support ([0006](adr/0006-medicalrag-is-an-evidence-explanation-tool.md)).
- v1 excludes identifiable patient data and malware scanning ([0008](adr/0008-first-version-excludes-identifiable-patient-data.md), [0029](adr/0029-first-version-excludes-malware-scanning.md)).
- Fixed medical AI disclaimer; prohibited individual requests short-circuit before retrieval ([0042](adr/0042-fixed-medical-ai-disclaimer.md), [0043](adr/0043-prohibited-individual-requests-short-circuit-before-retrieval.md)).
- Workspace is the isolation scope; system knowledge is read-only and version-reviewed; workspace knowledge is private ([0003](adr/0003-workspace-is-the-resource-isolation-scope.md)–[0005](adr/0005-system-knowledge-requires-reviewed-versions.md)).

## Runtime and packages

- Aegra owns Thread/Run and Agent Protocol v2 streaming; FastAPI owns business APIs; Postgres owns business conversations ([0001](adr/0001-aegra-is-the-production-runtime.md), [0002](adr/0002-postgres-owns-business-conversations-aegra-owns-runtime-state.md), [0058](adr/0058-assistant-ui-uses-native-agent-protocol-v2-runtime.md)).
- Shared domain seam in `packages/medical-core` + adapters in `packages/infra`; apps do not import each other ([0025](adr/0025-shared-medical-application-package-for-fastapi-and-aegra.md), [0060](adr/0060-shared-infra-package-and-pruned-package-graph.md)).
- Chat pipeline assembly lives in `apps/agent`; the `packages/assembly` seam was dissolved after the API dropped its SSE chat path (single consumer fails the deletion test; [0060](adr/0060-shared-infra-package-and-pruned-package-graph.md)).
- Monorepo: uv workspace for Python, pnpm workspace for JS; task orchestration stays native to each ecosystem (no third-party task runner) ([0055](adr/0055-monorepo-uses-independent-uv-and-pnpm-workspaces.md), [0083](adr/0083-pnpm-12-js-package-manager-baseline.md)).
- Python 3.12 baseline via uv; UUIDv7 for all business ids ([0064](adr/0064-uv-manages-python-314-runtime.md), [0066](adr/0066-uuidv7-is-the-universal-business-identifier.md)).

## Storage, ingestion, retrieval

- Hybrid retrieval only on Qdrant (dense + sparse/BM25 + RRF); Postgres is authority for permissions and metadata—not a retrieval engine ([0012](adr/0012-hybrid-retrieval-is-required-for-medical-questions.md), [0075](adr/0075-qdrant-replaces-milvus-as-the-hybrid-retrieval-engine.md)).
- Ingestion is always asynchronous; MinerU official API is the multimodal extraction provider ([0013](adr/0013-document-ingestion-is-always-asynchronous.md), [0015](adr/0015-mineru-api-is-the-external-extraction-provider.md), [0016](adr/0016-official-mineru-cloud-api.md)).
- Structure-first chunking with provenance; optional generated background context before embedding ([0034](adr/0034-structure-first-chunking-preserves-provenance.md), [0077](adr/0077-chunking-adds-size-caps-sentence-boundary-splits-overlap-and-atomic-tables.md), [0078](adr/0078-chunks-carry-generated-background-context-before-embedding.md)).
- Retrieval policy v2 (intent score floor 0.35, rerank candidate cap 40) + chunking tolerance + table KV embedding + MinerU image/concurrency hygiene ([0087](adr/0087-retrieval-policy-v2-chunking-tolerance-and-table-specialization.md)).
- Evidence fusion is deterministic and policy-versioned; optional external reranker ([0037](adr/0037-external-reranker-api-orders-hybrid-candidates.md), [0039](adr/0039-evidence-fusion-is-deterministic-and-policy-versioned.md)).

## Jobs, API, frontend, ops

- Durable app workflows: TaskIQ + Postgres outbox (not Aegra’s queue) ([0073](adr/0073-taskiq-replaces-arq-as-the-durable-job-queue.md)).
- Same-origin web + API; Vite SPA served by Nginx in prod ([0020](adr/0020-same-origin-entrypoint-for-web-and-api.md), [0070](adr/0070-vite-spa-with-nginx-proxy-is-the-frontend-runtime.md)).
- Operator console ships without recharts/G6 — KPI cards + custom intent-tree UI ([0085](adr/0085-operator-console-without-charting-libraries.md)).
- Document preview: pdfjs-dist + docx-preview only; xlsx unsupported in v1 (SheetJS removed for CVE/stale upstream) ([0068](adr/0068-document-preview-mainstream-per-format-renderers.md), [0080](adr/0080-production-hardening-baseline.md)).
- OpenAPI is the single contract source for TS types ([0071](adr/0071-openapi-single-source-contract-generation.md)).
- Root `docker-compose.yml` is the only Compose entrypoint; middleware ports bind loopback ([0053](adr/0053-docker-compose-yml-is-the-deployment-entrypoint.md)).
- Observability: self-hosted Phoenix on the optional `observability` profile; Aegra is the sole fail-open OTLP owner ([0076](adr/0076-aegra-owns-langfuse-ingestion-via-otlp.md), [0082](adr/0082-phoenix-replaces-langfuse-as-observability-backend.md)).
- Production hardening: CI gates, rate limits, non-root images, coverage floor ([0080](adr/0080-production-hardening-baseline.md)).
- Prefer popular libraries; openai SDK 3.x on httpx2 ([0074](adr/0074-prefer-popular-third-party-libraries.md), [0081](adr/0081-openai-sdk3-httpx2-alignment.md)).

## Out of scope

- MCP compatibility; alternate retrieval backends (pgvector, Elasticsearch, Neo4j, LightRAG) ([0051](adr/0051-mcp-compatibility-is-out-of-scope.md)).
- Clinical diagnosis, triage, prescribing, or regulated clinical workflow certification.

## How to change a decision

1. Write a new ADR in `docs/adr/` (or amend an accepted one if still accurate).
2. Update this file’s bullet if the change is user-visible architecture/product.
3. Mark the old ADR `status: superseded` and move it to local `_archive/docs/adr/`.

## YAGNI cleanup (ponytail audit, 2026-09)

- Non-streaming `/api/chat/stream` debug path and its assembly/settings surface were deleted; production chat is Aegra v2 only ([0058](adr/0058-assistant-ui-uses-native-agent-protocol-v2-runtime.md)).
- `platform_credentials` and `audit_events` read-only scaffolding (no writer, endpoints always empty) were dropped; rebuild table + repo + endpoint together with the write path when the ADR 0010 secret-manager and ADR 0018 audit-write capabilities are actually scheduled.
- Slot extraction (`intent/slot.py`, `IntentNode.slot_schema`, classifier slots) is parked until a real schema source exists (`slot_schemas` table was already dropped as dead).
- `IntentKind.TOOL` removed until a tool route exists; intent-tree admin API and editor now offer `knowledge | system` only.
- `eval-citation` command deleted; RC gate remains `eval-answer` per ADR 0080 (docs metric name corrected to `chunk_hit_at_1`).
