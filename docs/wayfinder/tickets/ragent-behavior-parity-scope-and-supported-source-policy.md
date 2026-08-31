---
kind: ticket
label: wayfinder:grilling
status: closed
parent: ../map.md
assignee: codex
depends_on: []
title: Ragent behavior parity scope and supported source policy
---

## Question

What part of Ragent is the migration required to preserve, and which source types are accepted?

## Resolution

The target is capability-complete behavioral parity across production paths, administration, optional adapters, experimental behavior, data contracts, event protocols, failure handling, and operations. The supported source allowlist is `.docx`, `.pptx`, `.xlsx`, `.pdf`, `.md`, `.txt`, `.png`, `.jpg`, and `.jpeg`; unsupported connectors receive typed rejection.

## Evidence

- [Specification](../../spec.md)
- [Reference source audit](../../reference/source-audit.md)
- [Capability-complete migration ADR](../../adr/0049-ragent-capability-complete-migration-matrix.md)
