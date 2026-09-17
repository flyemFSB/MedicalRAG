---
status: superseded
superseded_by: 0085-operator-console-without-charting-libraries
---

# Operator console charting: recharts for KPIs, @antv/g6 for the intent tree

Superseded. The shipped console does not depend on recharts or @antv/g6:

- Operator dashboard renders KPI cards only (trend chart block removed; no metrics API for series data).
- Intent-tree editor uses a custom collapsible tree + list dual view, not a graph canvas.

See [DECISIONS.md](../DECISIONS.md) for the current console approach. Historical rationale for the original charting choice remains in git history.
