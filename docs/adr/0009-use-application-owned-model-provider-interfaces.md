---
status: accepted
---

# Use application-owned model provider interfaces

The application defines its own `GenerationProvider` and `EmbeddingProvider` interfaces. The default external transport is OpenAI-compatible HTTP, but provider-specific SDKs and wire formats remain behind infrastructure Adapters. Generation and embedding targets may use different providers and are configured through Model Target records rather than imported into Domain or Application modules. This keeps the medical pipeline independent of vendor SDKs and allows routing, timeout, retry, circuit, capability matching, and provider replacement to remain local platform behavior.
