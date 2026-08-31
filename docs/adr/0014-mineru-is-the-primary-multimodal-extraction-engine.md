---
status: superseded by ADR-0015
---

# MinerU is the primary multimodal extraction engine

The first version supports scanned PDFs, images, Excel workbooks, PowerPoint presentations, and complex multimodal PDFs. MinerU is the primary layout-aware and OCR extraction engine, executed only inside the asynchronous Ingestion Run rather than inside the FastAPI request process. Office sources retain native structure such as worksheets, cells, slides, text boxes, tables, and embedded assets; when necessary they are structurally parsed or rendered before MinerU produces the canonical Extraction Artifact. Every artifact records the source hash, parser name and version, page or region provenance, extracted assets, warnings, and confidence metadata before chunking and indexing. This is a deliberate ingestion-platform commitment because parser choice, GPU scheduling, artifact shape, and provenance affect the entire search and citation model.
