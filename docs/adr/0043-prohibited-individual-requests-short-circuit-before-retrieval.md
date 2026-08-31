---
status: accepted
---

# Prohibited individualized requests short-circuit before retrieval

When Intent and Safety classification identify an individualized diagnosis, prescription, dosage calculation, medication adjustment, surgery recommendation, emergency exclusion, or equivalent prohibited Clinical Decision request, the request stops before Embedding, PostgreSQL lookup, Milvus retrieval, Reranking, and Generation Provider calls. The system returns a fixed safety-guidance response with the product disclaimer and appropriate escalation language. General educational medical questions remain eligible for the evidence pipeline, subject to Evidence requirements and the same disclaimer.

## Consequences

- Safety classification is a mandatory pre-retrieval stage and cannot depend on an external model being available.
- The short-circuit reason, safety class, and policy version are recorded in business run events or the redacted Langfuse observation without sending prohibited content to external providers.
- A prohibited request never receives a partial answer assembled from general medical evidence that could be mistaken for individualized clinical advice.
- Adding or changing a prohibited category requires a safety-policy review and regression tests for boundary cases between educational and individualized questions.
