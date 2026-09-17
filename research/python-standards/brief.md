# Research brief: 高质量 Python 代码标准/规范（适配 MedicalRAG）

## Refined question

哪些业界公认的高质量 Python 代码标准、规范与实践最适配 MedicalRAG（证据优先的医疗 RAG 知识工作台，Python 3.12 monorepo）？在已有 `docs/development-standards.md` 的前提下，外部标准如何对齐、补强或纠偏现有约定？

## Project constraints (must shape recommendations)

- Python 3.12, uv workspace monorepo
- FastAPI + SQLAlchemy async + Alembic
- TaskIQ + RabbitMQ outbox/ingestion worker
- Aegra + LangGraph agent pipeline
- Qdrant hybrid retrieval (dense + sparse/BM25 + RRF)
- loguru + Prometheus + Langfuse (fail-open, no custom OTel stack)
- ruff + pyright + pytest + coverage gate (fail_under=75)
- medical-core must not import frameworks; package boundaries enforced
- Medical safety: no clinical decision without Evidence; log redaction is a hard line
- YAGNI / ponytail: lazy senior-dev minimal correct solutions
- Domain terminology forced by CONTEXT.md

## Scope boundaries

**In scope**
- PEP / typing / style / docstring / lint / format standards
- Async & resource lifecycle standards
- AI/LLM application & RAG engineering standards
- Testing & quality gates
- Architecture & package boundaries
- Security/privacy/logging for medical-adjacent systems
- Any official medical-software process standards that map onto Python engineering practice

**Out of scope**
- Frontend (TypeScript/React) standards
- Non-Python languages
- Implementing code changes in this repo
- Choosing commercial tools/saas vendors

## Assumptions

- Audience: maintainers of MedicalRAG who already have a living `development-standards.md`
- Time frame: current practice as of 2026-09; prefer sources from last 2–3 years, primary docs over blogs
- Goal: actionable adoption checklist, not a history of PEPs
- Report language: 中文（技术名/引用保留原文）

## Depth mode

**deep** — 8 angles, up to 2 follow-up rounds, target 25+ sources

## Date

2026-09-15

## Angles

1. Core Python language & typing standards (PEP 8/257/484+, Google/NumPy docstring, modern 3.12 typing)
2. Modern toolchain standards (ruff, pyright, uv, src-layout, lockfile practices)
3. Async Python standards (asyncio/anyio, cancellation, structured concurrency, FastAPI/SQLAlchemy)
4. AI/LLM & RAG engineering standards (LangGraph, retrieval quality, eval, agent safety)
5. Security, privacy & logging redaction for medical-adjacent systems
6. Testing standards & quality gates (pytest patterns, coverage policy, integration seams)
7. Architecture & package boundary standards (hexagonal, monorepo, dependency direction)
8. Medical software / regulated process standards that influence Python engineering (e.g. IEC 62304, FDA CDS guidance, ISO 27001 mapping)

## Findings layout

- F1–F8 under `research/python-standards/findings/`
- Final: `research/python-standards/REPORT.md`
