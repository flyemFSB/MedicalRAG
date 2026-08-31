---
status: accepted
---

# The platform owns external model credentials

The first version stores and manages external generation and embedding credentials at the platform level. Workspace members can select only Model Targets authorized by the platform; they cannot read, write, or supply provider API keys. Credentials are injected through a secret manager or environment boundary, are never returned to the frontend, and are excluded from logs and Trace metadata. Workspace-specific BYOK is deferred until a separate encrypted secret-management and billing design exists. This keeps the first authorization model small and prevents external credentials from becoming tenant data.
