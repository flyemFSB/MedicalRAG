---
status: accepted
---

# MinerU is integrated through an API

MinerU is used through an API adapter rather than being executed inside the FastAPI process or bundled as a local MinerU GPU worker in Docker Compose. An asynchronous Ingestion Run stores the original source in object storage, submits an idempotent extraction request after the Data Egress Policy check, and converts the provider result into a provenance-preserving Extraction Artifact. The adapter owns authentication, request signing, polling or webhook completion, timeout handling, retries, rate limits, provider errors, and compensation; Aegra owns the durable execution and resume state. The API deployment location remains a separate operational decision: it may be an approved external MinerU service or an internally deployed MinerU API.

## Consequences

- FastAPI returns `202 Accepted` with an `ingestion_run_id`; parsing and indexing never block the HTTP request.
- Docker Compose does not include a MinerU GPU service.
- Raw sources and provider artifacts require retention, access-control, checksum, and deletion policies.
- The deployment choice must be confirmed before finalizing data-egress, network, secret, and capacity settings.
