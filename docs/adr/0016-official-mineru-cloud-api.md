---
status: accepted
---

# MinerU uses the official cloud API

MedicalRAG uses the official MinerU cloud API as its multimodal extraction provider. The first version does not deploy or operate an internal MinerU API. Before any source or source URL is submitted, the ingestion pipeline must apply the Data Egress Policy and reject identifiable patient data or content that the configured policy does not permit to leave the platform. The MinerU credential is platform-managed, provider requests are made only by the ingestion adapter, and provider retention, quota, region, and deletion behavior must be captured in deployment configuration and operational runbooks.

## Consequences

- MinerU processing is an external data transfer and must be visible in the ingestion run events and structured operational logs.
- The product must provide an explicit provider-status and failure state when the cloud API is unavailable, rate-limited, or over quota.
- API credentials, request limits, timeouts, webhook authentication, and callback reachability are deployment concerns rather than workspace concerns.
- The deployment must document the permitted data classes and the MinerU service's retention and processing-region guarantees before production use.
