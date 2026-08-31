---
status: accepted
---

# MCP compatibility is outside the target product boundary

Ragent's MCP Server and MCP Client paths are reference capabilities only and are not migrated into MedicalRAG. The target exposes no MCP endpoint, does not connect to external MCP servers, does not implement MCP parameter extraction or MCP tool routing, and does not add an MCP Compose service. The current product has no internal tool requirement; a future tool requirement would require a new explicit domain, authorization, approval, and data-egress decision rather than an incidental MCP adapter.

## Consequences

- The migration matrix marks both MCP Server and MCP Client capabilities as `rejected` with a typed unsupported-capability reason.
- assistant-ui connects only through its official LangGraph Server adapter; no browser-side MCP transport or custom MCP bridge is required.
- Adding MCP later requires a new boundary, authentication, tool-approval, and data-egress decision rather than an incidental adapter.
