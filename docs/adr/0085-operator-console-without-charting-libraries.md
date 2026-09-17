---
status: accepted
---

# Operator console ships without charting libraries

The operator console intentionally omits recharts and @antv/g6:

- **Dashboard**: KPI metric cards only. Empty trend chart shells were removed because no time-series metrics API exists yet; reintroducing a chart library before data exists is speculative.
- **Intent tree**: collapsible tree + list dual view using Base UI / app components. A graph canvas (G6) is not required for the edit flows in v1.

This supersedes ADR 0067. If a future product requirement adds multi-series trends or free-form graph editing, re-evaluate charting libraries then against bundle size and React 19 compatibility.
