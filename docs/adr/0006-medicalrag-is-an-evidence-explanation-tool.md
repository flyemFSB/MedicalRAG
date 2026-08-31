---
status: accepted
---

# MedicalRAG is an evidence-explanation tool, not a clinical decision maker

MedicalRAG may explain reviewed medical knowledge, show structured relationships, identify possible related conditions with explicit uncertainty, and provide escalation guidance. It must not make an individualized diagnosis, prescribe or adjust medication, calculate dosage, recommend surgery, rule out an emergency, or reassure a user that medical care is unnecessary. The safety policy is enforced before model invocation; post-run safety signals may be recorded for observation, but generated tokens are not held behind a blocking output gate. An answer without sufficient Evidence must be a bounded insufficiency response. This decision defines the product's safety scope independently of any model's instructions or confidence.
