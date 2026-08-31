---
status: accepted
---

# Workspace is the resource isolation scope

MedicalRAG introduces Workspace and Workspace Member from the first production version. Knowledge Bases, Documents, Chunks, Conversations, Messages, Evidence, Feedback, business run events, and Langfuse trace metadata are scoped to a Workspace; Users gain access through Workspace membership and roles. A default Workspace is created for a single-workspace deployment, while the shared medical ontology and built-in intent catalog remain read-only system data. This avoids a later cross-table migration when the product expands to hospitals, departments, or research teams and makes authorization rules explicit at every resource seam.
