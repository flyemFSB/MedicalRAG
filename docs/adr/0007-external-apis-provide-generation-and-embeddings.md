---
status: accepted
---

# External APIs provide generation and embeddings

MedicalRAG uses External Model Providers for both answer generation and embedding creation. Docker Compose will not host a local generation or embedding model in the first production design. Provider access is isolated behind generation and embedding adapters with explicit Model Target configuration, per-provider timeout, retry, circuit, quota, and audit controls. Secrets are injected at runtime and raw model payloads are not logged. The Data Egress Policy must run before every external call, and the product must fail safely when a provider is unavailable rather than fabricate a model answer. This preserves provider replaceability while making external data transfer an explicit security and compliance seam.
