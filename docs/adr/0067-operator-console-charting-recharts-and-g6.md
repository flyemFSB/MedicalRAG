---
status: accepted
---

# Operator console charting: recharts for KPIs, @antv/g6 for the intent tree

The MedicalRAG operator console reproduces Ragent's administration surface, which uses recharts for dashboard KPIs and @antv/g6 for graph-style visualization. MedicalRAG assigns those two libraries to the two concrete operator needs: the operator dashboard (ingestion, chat, model, and retrieval metrics) uses **recharts**, and the interactive intent-tree editor uses **@antv/g6**.

This closes the charting gap recorded in the [stack replacement matrix](../reference/stack-replacement-matrix.md). Both libraries are already proven in Ragent's console, so this preserves observable admin behavior without introducing a charting stack the reference never used.

## Why not the alternatives

- **ECharts**: capable but heavier and not the reference's stack; adopting it would break admin-console parity for no user-visible gain.
- **Chart.js / d3**: lower-level; require more custom work for the KPI and tree visuals the console already has.
- **TanStack Chart**: newer and less established for the exact KPI chart set.

## Consequences

- `apps/web` depends on recharts (dashboard/trend charts) and @antv/g6 (intent-tree node graph), and recharts' and g6's current releases are verified against the React 19.2 / Vite 8 / TypeScript 6 frontend baseline before implementation is final.
- G6 renders the intent-tree graph; edit state and persistence remain application-owned data flowing through the ordinary admin API, not a separate graph store.
- Both libraries stay inside `apps/web`; `packages/medical-core` remains free of charting dependencies.
- Bundle size is watched in CI for the operator routes so charting does not bloat the chat entrypoint.
