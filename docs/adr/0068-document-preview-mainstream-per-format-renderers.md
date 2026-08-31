---
status: accepted
---

# Document preview: native rendering plus mainstream per-format renderers

The MedicalRAG knowledge and operator UI previews supported source formats in place. Ragent previews Markdown, plain text, images, and Excel client-side; MedicalRAG extends that to the supported format allowlist using a consistent rule:

- `.md` and `.txt` render with the existing react-markdown and `<pre>` path;
- `.png`, `.jpg`, and `.jpeg` render with native `<img>`;
- `.pdf` renders with **pdfjs-dist** (Mozilla's standard client renderer, Apache-2.0);
- `.docx` renders with **docx-preview** (Apache-2.0, browser build, jszip-only dependency);
- `.xlsx` is parsed with **SheetJS (xlsx, Apache-2.0 CE)** and rendered as a table with the existing **@tanstack/react-table**;
- `.pptx` is a **typed unsupported** result in v1 — there is no maintained free client-side pptx renderer (`@opendocsg/pptx2html` has no published release, and `@js-preview` has no pptx sub-package).

This supersedes the earlier `@js-preview` family choice from the [stack replacement matrix](../reference/stack-replacement-matrix.md). The format-specific mainstream libraries are used at one to two orders of magnitude higher adoption than `@js-preview` (weekly downloads: pdfjs-dist ~21.6M, xlsx ~11.8M, docx-preview ~1.2M vs `@js-preview/*` <5K) and each is independently maintained, so a failure in one format does not take the others down.

## Why not the alternatives

- **`@js-preview` family**: single-author, low adoption, and no pptx sub-package (pptx requires the paid `pptx-preview` source).
- **`@opendocsg/pptx2html`**: no published npm release, so not a viable client-side pptx option.
- **Server-side office conversion for v1** (LibreOffice headless or OnlyOffice Document Server): adds a heavy Docker service; OnlyOffice Document Server 9.4 (AGPL, active) remains the **post-v1 option** if office preview becomes a real product need — it would render docx/xlsx/pptx uniformly server-side.
- **Commercial heavy viewers**: licensing and bundle cost with no parity benefit.

## Consequences

- `apps/web` depends on `pdfjs-dist`, `docx-preview`, and SheetJS `xlsx`; their current releases are verified against the React 19.2 / Vite 8 / TypeScript 6 baseline.
- `.pptx` sources receive the typed unsupported-source result at the preview boundary (they remain ingested via MinerU; only in-UI preview is unsupported in v1).
- Previewed objects are served from MinIO through a signed, least-privilege, same-origin read path with expiring URLs; no document text is baked into HTML previews.
- A single preview component switches on the MIME/source format and falls back to the typed unsupported-source state otherwise.
- OnlyOffice Document Server is deliberately not provisioned in v1; if office preview is later required, it is evaluated as a separate service with its own AGPL and operational review.
