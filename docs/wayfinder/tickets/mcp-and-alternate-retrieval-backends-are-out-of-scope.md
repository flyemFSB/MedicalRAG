---
kind: ticket
label: wayfinder:grilling
status: closed
parent: ../map.md
assignee: codex
depends_on: []
title: MCP and alternate retrieval backends are out of scope
---

## Question

Should Ragent's MCP paths and alternate vector/search/graph backends be migrated?

## Resolution

No MCP Server or Client is exposed or connected, and the target does not implement MCP parameter extraction or MCP tool routing. pgvector, Elasticsearch, Neo4j, and LightRAG are not target services; their retained responsibilities are represented by the approved Milvus Hybrid Retrieval and PostgreSQL authorization/structured-data boundary.

## Evidence

- [MCP scope ADR](../../adr/0051-mcp-compatibility-is-out-of-scope.md)
- [Superseded alternate-store ADR](../../adr/0052-milvus-and-postgresql-are-the-only-target-retrieval-stores.md)
- [Active retrieval ADR](../../adr/0056-milvus-is-the-unified-hybrid-retrieval-engine.md)
