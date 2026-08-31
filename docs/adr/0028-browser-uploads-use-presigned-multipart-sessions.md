---
status: accepted
---

# Browser uploads use presigned multipart sessions

Large document uploads use an application-created Upload Session and short-lived, least-privilege presigned multipart URLs for direct transfer to MinIO. FastAPI records the intended Document and object key, constrains size and content policy, issues only the required upload permissions, and finalizes the session after verifying object metadata, checksum, detected media type, and ownership. Only then does it create the asynchronous Ingestion Run that performs scanning, Data Egress Policy evaluation, MinerU submission, extraction, chunking, embedding, and Milvus indexing.

## Consequences

- File bytes do not pass through FastAPI memory or the Node SSR process.
- Presigned URLs are short-lived and scoped to one object and one multipart operation; browser CORS is restricted to the application origin.
- File extensions and browser-provided MIME types are advisory; server-side size limits, magic-byte detection, checksum verification, and decompression-bomb limits are mandatory.
- Abandoned multipart uploads require lifecycle cleanup, and completion is idempotent so retries cannot create duplicate Documents or Ingestion Runs.
- The object is not eligible for MinerU or retrieval until validation and security checks succeed.
