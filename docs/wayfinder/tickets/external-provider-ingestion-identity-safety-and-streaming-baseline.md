---
kind: ticket
label: wayfinder:grilling
status: closed
parent: ../map.md
assignee: codex
depends_on: []
title: External provider, ingestion, identity, safety, and streaming baseline
---

## Question

What provider, ingestion, authentication, safety, and generation-output boundaries are already fixed?

## Resolution

Generation, dense Embedding, Reranking, and MinerU use external APIs. MinerU handles the approved multimodal formats. Authentication uses only the application-owned server-side session system. The fixed Chinese disclaimer is always shown. Generation streams directly without a blocking post-generation validation gate.

## Evidence

- [Specification](../../spec.md)
- [MinerU API ADR](../../adr/0015-mineru-api-is-the-external-extraction-provider.md)
- [Authentication ADR](../../adr/0018-application-owned-authentication.md)
- [Streaming ADR](../../adr/0041-generation-is-streamed-without-a-blocking-output-gate.md)
- [Disclaimer ADR](../../adr/0042-fixed-medical-ai-disclaimer.md)
