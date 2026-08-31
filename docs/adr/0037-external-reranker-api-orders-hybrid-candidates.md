---
status: accepted
---

# Hybrid candidates are reranked through an external API

After PostgreSQL authorization filtering and Milvus dense/sparse Hybrid Retrieval produce a bounded candidate set, MedicalRAG calls an external Reranker API to score candidate Evidence against each grounded subquestion. The Reranker is an application-owned `RerankerProvider` port with provider adapters; it may reorder or score candidates but cannot create Evidence, change Workspace authorization, remove mandatory high-precision metadata evidence, apply the medical Safety Boundary, or write directly to the answer. A deterministic Evidence Fusion stage combines Milvus channel provenance, source quality, retrieval scores, and the reranker score to produce the final Evidence order and cap.

## Consequences

- Reranker input is restricted by the Data Egress Policy and contains only the approved query and bounded candidate text; internal IDs, permissions, secrets, and hidden trace data are excluded.
- Candidate limits, timeout, retry, rate limit, model target, provider version, score calibration, and latency are observable through business run events, structured logs, metrics, and the Aegra-hosted Langfuse observation where applicable.
- A Reranker outage, quota error, or invalid response falls back to deterministic channel ranking and does not make an otherwise grounded answer unavailable.
- Reranking is applied to evidence candidates, not to arbitrary model-generated text; every final Citation must still point to a retrieved Evidence item.
- Reranker model changes are evaluated with the retrieval test set and may require a new ranking-policy version, but they do not change the Milvus embedding collection.
