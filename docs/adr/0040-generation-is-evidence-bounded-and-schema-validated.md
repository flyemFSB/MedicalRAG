---
status: superseded by ADR-0041
---

# Generation is evidence-bounded and schema-validated

The Generation Provider receives only the user-approved query context, Safety Boundary, and the Evidence Package produced by Evidence Fusion. Retrieved documents are treated as untrusted reference data rather than instructions. The model must return a validated structured result containing answer content, Citation identifiers, limitations, and safety metadata; the server rejects citations that do not resolve to the current Evidence set and rejects claims or output states that violate the medical policy. Model credentials and provider calls remain server-side and pass through the Data Egress Policy.

## Consequences

- Aegra may stream status, analysis, and Evidence data parts while generation runs, but the final answer content is committed only after schema, citation, and safety validation.
- Invalid, incomplete, uncited, or provider-failed output is discarded and replaced by a deterministic evidence-insufficiency or safe-scope response; it is never presented as a successful Evidence Answer.
- Prompt-injection text inside Documents is delimited as data and cannot change system policy, tool permissions, Workspace scope, or citation rules.
- The structured answer contract, prompt-policy version, model target, validation outcome, and fallback reason are recorded in business run events and the redacted Langfuse observation without storing hidden chain-of-thought.
