---
status: accepted
---

# Aegra is the production execution runtime

MedicalRAG uses Aegra as a mandatory production runtime for Thread and Run execution, Agent Protocol streaming, worker coordination, recovery, and horizontal scaling. Durable application workflows such as document ingestion and indexing use arq (Redis job queue) rather than Aegra's agent queue. The medical domain remains owned by the local ChatOrchestrator: it defines entities, intents, retrieval, evidence, safety boundaries, and answer invariants. Aegra is integrated through an adapter and is not allowed to become the owner of medical rules or storage semantics. A local runtime may remain for deterministic development tests, but production behavior must exercise the Aegra seam. This choice is accepted because runtime durability, resumable streaming, and worker coordination are deployment requirements rather than optional conveniences; keeping Aegra behind an adapter preserves the ability to test and evolve the medical domain independently.
