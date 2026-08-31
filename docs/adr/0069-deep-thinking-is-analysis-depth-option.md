---
status: accepted
---

# Deep-thinking mode is a per-request Analysis Depth option

Ragent's frontend offers a "deep-thinking" toggle that produces a more thorough answer. MedicalRAG's evidence-first safety policy forbids exposing hidden chain-of-thought or generating conclusions the retrieved Evidence does not support, so the toggle cannot mean unrestricted reasoning. Instead, deep-thinking mode is modeled as a per-request **Analysis Depth** option on the chat orchestrator.

When Analysis Depth is selected, the Run:

1. selects an analysis-capable **Model Target** through a capability flag (`analysis_depth`);
2. raises the retrieval depth budget within policy — more candidate Evidence and a higher Evidence cap;
3. runs an evidence-synthesis stage that assembles a more complete Evidence Answer from the retrieved, provenance-bearing Evidence.

The option does **not** change the Safety Boundary, the Evidence Answer contract, citation rules, or the Data Egress Policy. It is recorded on the business Run and observable in Trace/business records, so operator inspection stays unchanged.

## Why not the alternatives

- **A raw chain-of-thought mode**: violates the medical Safety Boundary and the "no unsupported clinical conclusion" rule.
- **A new intent route**: Analysis Depth is a modifier on an existing intent, not a different kind of question.
- **Rejecting it outright**: breaks behavioral parity with Ragent's visible deep-thinking toggle.

## Consequences

- Model Targets gain an optional `analysis_depth` capability flag; the router uses it when a deeper analysis is requested.
- The orchestrator accepts an Analysis Depth option that scales retrieval budget and Evidence cap within policy limits; the safety stage still runs identically.
- The frontend toggle maps to the Analysis Depth option on the Run request.
- A glossary term "Analysis Depth" is added to `CONTEXT.md`; the specification gains a user story for the option.
