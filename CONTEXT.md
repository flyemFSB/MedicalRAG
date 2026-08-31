# MedicalRAG Domain Context

MedicalRAG is an evidence-first medical knowledge workbench. It helps clinicians, researchers, and knowledge maintainers explore curated medical knowledge without presenting unsupported output as diagnosis or prescription.

## Language

### Knowledge and evidence

**Knowledge Base**:
A user-scoped collection of medical sources that can be searched together.
_Avoid_: Corpus, database, repository

**Document**:
An original source submitted to a Knowledge Base, including its title, content, provenance, and ingestion state.
_Avoid_: File, article, source fragment

**Supported Source**:
A Document whose format is permitted by the product's source policy: `.docx`, `.pptx`, `.xlsx`, `.pdf`, `.md`, `.txt`, `.png`, `.jpg`, or `.jpeg`.
_Avoid_: Arbitrary upload, connector payload

**Chunk**:
A structure-aware portion of a Document that can be independently indexed and cited.
_Avoid_: Segment, vector record

**Evidence**:
A retrieved, provenance-bearing statement or Chunk that supports an answer or explains why the system cannot answer.
_Avoid_: Context, reference, citation

**Hybrid Retrieval**:
The configured combination of retrieval strategies used for one search request, including authorization-scoped exact and structured metadata filtering plus Qdrant dense and sparse semantic/lexical retrieval where the intent requires it.
_Avoid_: Vector search, blended search

**Evidence Fusion**:
The deterministic stage that deduplicates, attributes, scores, caps, and orders results from all retrieval channels.
_Avoid_: Reranking, prompt assembly

**Reranker**:
A provider-backed scoring stage that evaluates a bounded candidate Evidence set against one query and may improve ordering without creating Evidence or changing access and safety rules.
_Avoid_: Evidence Fusion, answer generator

**Citation**:
The user-visible pointer from an answer to an Evidence item.
_Avoid_: Source, evidence

### Medical understanding

**Medical Entity**:
A normalized medical concept such as a disease, drug, symptom, examination, food, department, treatment, or producer.
_Avoid_: Keyword, term, token

**Intent**:
The configured information operation or system action requested by a user and represented by a node in the Ragent-style intent tree.
_Avoid_: Question type, label, command

**Behavioral Parity**:
The target system preserves the reference system's observable user, operator, event, data-contract, and failure behavior while allowing a different implementation.
_Avoid_: Source-code copy, class-for-class port

**Technical Replacement**:
A target-stack capability that fulfills the observable responsibility of a reference capability, even when its library, protocol, or deployment shape differs.
_Avoid_: Equivalent package, renamed dependency

**Structured Medical Metadata**:
Versioned medical attributes and relationships that a retrieval strategy may use alongside document evidence.
_Avoid_: Knowledge graph database, graph service

**Safety Boundary**:
The product rule that limits an answer according to its medical risk class and available Evidence.
_Avoid_: Disclaimer, warning text

**Evidence Answer**:
An answer that explains retrieved medical information and its limitations without making a clinical decision for an individual.
_Avoid_: Diagnosis, recommendation, clinical conclusion

**Clinical Decision**:
An individualized diagnosis, prescription, dosage, triage decision, or treatment decision made for a person.
_Avoid_: Medical answer, suggestion, assessment

**External Model Provider**:
A separately operated API that generates answer text or embeddings for MedicalRAG without receiving ownership of the product's business data.
_Avoid_: Model, AI service, hosted model

**Generation Provider**:
An implementation that streams Evidence Answers from a model under the application-owned generation interface.
_Avoid_: Chat model, completion API

**Embedding Provider**:
An implementation that converts query or Chunk text into vectors under the application-owned embedding interface.
_Avoid_: Vector model, embedding API

**Embedding Schema Version**:
The immutable combination of embedding model, vector dimension, distance metric, normalization, and input-text policy used by one indexed collection.
_Avoid_: Model version, index version

**Active Index Version**:
The Embedding Schema Version currently eligible for new retrieval after a complete and validated index build.
_Avoid_: Latest collection, current vector table

**Data Egress Policy**:
The rules that determine which request content may leave MedicalRAG for an External Model Provider and what must be removed or transformed first.
_Avoid_: Privacy setting, API option

**Identifiable Patient Data**:
Information that can identify or reasonably be linked to a patient, including direct identifiers and unredacted clinical records.
_Avoid_: Medical text, user content

**De-identified Medical Data**:
Medical content processed so that it is not reasonably linkable to an individual under the first-version data policy.
_Avoid_: Anonymous data, scrubbed prompt

### Ownership and access

**User**:
An authenticated person account owned by MedicalRAG that can belong to one or more Workspaces.
_Avoid_: Account, identity, profile

**Authentication Session**:
A time-bounded server-side association between a User and an authenticated browser or client.
_Avoid_: Login token, JWT session, browser identity

**Workspace**:
The isolation scope within which members share Knowledge Bases, Conversations, and operational records.
_Avoid_: Tenant, organization, project

**Workspace Member**:
A User's membership in a Workspace together with the role used to authorize access to its resources.
_Avoid_: Workspace user, account

**System Knowledge**:
Read-only medical knowledge curated and published for all Workspaces.
_Avoid_: Global corpus, public data

**Workspace Knowledge**:
Documents and medical additions owned by one Workspace and unavailable to other Workspaces by default.
_Avoid_: Private corpus, tenant data

**Knowledge Publication**:
The reviewed act of making a version of a source or medical fact available as System Knowledge.
_Avoid_: Upload, sync, deployment

**Published Version**:
The immutable, review-approved revision of a source that is eligible for default retrieval.
_Avoid_: Current document, latest copy

**Ingestion Run**:
The asynchronous, observable execution that transforms a Document into validated Chunks and an indexed Published Version.
_Avoid_: Upload, import, background task

**Multimodal Document**:
A Document whose meaning depends on layout, OCR text, tables, images, formulas, slides, sheets, or other non-plain-text structure.
_Avoid_: File, binary document, attachment

**Extraction Artifact**:
The provenance-preserving intermediate representation produced from a Multimodal Document, including normalized text, structure, tables, assets, and page or region references.
_Avoid_: Parsed text, temporary output

**MinerU Extraction**:
The approved extraction process that converts supported Multimodal Documents into Extraction Artifacts for chunking and indexing.
_Avoid_: OCR job, PDF parser

### Conversation and execution

**Conversation**:
A durable user-owned sequence of Messages that provides continuity for follow-up questions.
_Avoid_: Session, thread

**Message**:
A user, assistant, or system utterance stored inside a Conversation.
_Avoid_: Prompt, response

**Thread**:
The runtime context used by the production agent system to execute and resume a Conversation.
_Avoid_: Conversation, channel

**Run**:
One complete attempt to answer one user request, including analysis, retrieval, generation, persistence, and terminal state.
_Avoid_: Request, job, task

**Trace**:
The redacted, queryable observability record of an Agent Run's AI/RAG stages, timings, metadata, and failures, collected by the self-hosted observability backend. Infrastructure diagnostics remain structured logs, metrics, and health data rather than application-owned Trace spans.
_Avoid_: Log, audit log

**Model Target**:
A configured model provider and capability set that can be selected for a Run.
_Avoid_: Model, provider

**Analysis Depth**:
A per-request option that selects an analysis-capable Model Target, raises the retrieval budget and Evidence cap within policy, and runs an evidence-synthesis stage, without changing the Safety Boundary or the Evidence Answer contract.
_Avoid_: Deep-thinking mode, reasoning mode, chain of thought

**Platform Model Credential**:
An operator-managed secret that authorizes a Model Target for one or more Workspaces without becoming Workspace data.
_Avoid_: Workspace key, user token, BYOK
