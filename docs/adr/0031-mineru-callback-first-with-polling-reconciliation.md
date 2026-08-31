---
status: accepted
---

# MinerU completion uses callback first and polling as reconciliation

The MinerU cloud adapter submits asynchronous extraction tasks with a callback URL and a per-task seed, validates the provider callback using MinerU's documented `checksum` contract, and acknowledges only accepted, idempotently recorded notifications. An arq worker reconciliation job polls the official task-status endpoint for tasks whose callback is delayed, duplicated, rejected, or never delivered. Provider task identifiers and the application `data_id` are unique keys for deduplication; callback retries and polling races must converge on one Ingestion Run state transition.

## Consequences

- The callback endpoint is a provider-facing internal route, not a browser-authenticated route; it accepts only valid MinerU signatures, known task mappings, bounded payloads, and expected state transitions.
- MinerU result links are downloaded by the server, checked for status and integrity, and copied into the appropriate MinIO artifact key before downstream processing.
- A short-lived, least-privilege source URL is supplied to MinerU and is allowed to expire after the provider has fetched the source; it is never stored as a permanent public document URL.
- Polling uses bounded exponential backoff, provider rate limits, task deadlines, and a terminal compensation state rather than an unbounded loop.
- Callback delivery, polling, result download, checksum validation, and retry decisions are visible as ingestion run events and structured operational logs.

## References

- [MinerU API documentation](https://mineru.net/apiManage/docs)
