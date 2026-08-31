---
status: accepted
---

# Generation is streamed directly without a blocking output gate

The assistant displays generated answer tokens as soon as they arrive from the Aegra/LangGraph stream. MedicalRAG does not buffer the complete answer or block presentation on post-generation schema validation, Citation binding, or Safety validation. Evidence Fusion, prompt policy, server-side authentication and authorization, input validation, Data Egress Policy, and provider-request controls remain active before generation; this decision changes only the handling of generated output after the model starts streaming.

## Consequences

- Time to first visible answer content is minimized, and cancellation can stop an in-flight provider request without waiting for a final validation pass.
- The product cannot claim that every streamed sentence has been server-validated against Evidence before display; unsupported or uncited model text may be visible until the run ends.
- Citation metadata, provider status, safety signals, and any post-run diagnostics may be recorded in business run events, structured logs, metrics, or the redacted Langfuse observation, but they do not retroactively alter already displayed tokens.
- UI copy, answer styling, and product documentation must clearly distinguish streamed model generation from authoritative medical fact and keep Evidence inspection available beside the response.
- ADR-0040's validate-before-commit requirement is intentionally superseded; reintroducing a blocking output gate requires a new decision.
