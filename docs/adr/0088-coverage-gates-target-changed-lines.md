---
status: accepted
related:
  - 0080-production-hardening-baseline
---

# Coverage gates target changed lines; repo totals only guard against regression

`ADR 0080` recorded a coverage gate of "≥80%, baseline 82%" and shipped it as `[tool.coverage.report] fail_under = 80` over the whole Python source tree. Measured on 2026-09-14 that gate is **red**: 75.57% (4090 statements / 999 missed), identical under SQLite and real PostgreSQL and with or without the `integration` marker, so it is not an environment artifact. A permanently red gate is not a gate: it is a check everyone learns to route around, while the number it guards keeps drifting.

The external evidence points the same way as the measurement. Google's own guidance puts the gate on the **changelist** (99% per-commit is reasonable, 90% is the floor) and says project-level totals above 90% are rarely worth it; Sonar's built-in gate is defined on **new code**; `diff-cover`'s framing is "if you touch a line of code, that line should be covered"; and a fixed total is documented to degrade from floor into ceiling ("instead of treating 80% like a floor, engineers treat it like a ceiling"). Coverage totals are also demonstrably insensitive to the thing that matters: a change set can be almost entirely untested while the total stays put. Sources and evidence grades: `docs/research/quality-and-coverage-gates-best-practices.md`.

## Decisions

1. **The blocking coverage gate is changed lines, on pull requests.** `scripts/ci/check_patch_coverage.py --base origin/<base_ref>` runs `diff-cover` over the `coverage.xml` produced by the unit/contract run, with a floor of **80%** of changed lines (Sonar's new-code default; Google's 90% is the next step once this proves maintainable). New dev-group dependency: `diff-cover`.
2. **The repo total becomes a floor, not a target.** `fail_under` moves from 80 to **75** — the measured water level (75.57% on 2026-09-14, line-only;口径与水位已按「修订」节改为行 + 分支，实测 75.23%）。 Its only job is to fail a *regression*. Raising it is a test-writing task, never a number edit. This is the degenerate form of a coverage ratchet and needs no tooling beyond the value itself.
3. **Only the unit/contract layer measures coverage.** The patch gate reads the `-m "not integration"` run. Integration tests execute against real PostgreSQL at merge level (ADR 0080 layering unchanged); folding them in would raise the number without adding a verdict, and Google's guidance is to measure coverage from small tests only.
4. **`relative_files = true` is load-bearing, and the gate guards it.** Without it, `coverage.xml` writes absolute `<source>` paths and bare `class` filenames; `diff-cover` then cannot align report paths with git paths and exits **0** printing "No lines with coverage information in this diff." — a gate that silently never fires, indistinguishable from "this PR only touched docs". The script's first job is therefore an alignment check: every changed `src` file that has executable statements must appear in the report, otherwise the gate fails loudly with the offending paths.
5. **The gate is PR-scoped and needs real history.** It runs only on `pull_request`; direct pushes to `main` are not patch-gated. The python job checks out with `fetch-depth: 0`, because `origin/<base_ref>` does not exist in a shallow clone and the gate would error instead of judging.
6. **Escape valve and known limits.** `# pragma: no cover` stays the reviewed way to exclude a genuinely untestable line; the threshold is not the escape valve. `diff-cover` needs path alignment and can miss changes inside multi-line statements (`--expand-coverage-report` exists if that is ever observed).
7. **`medical-core` carries a 100% line-coverage gate.** It is the pure-logic and Safety Boundary seam — deterministic, no I/O, no framework — so exhaustive coverage is actually achievable there, and it is the one place where a silently unexecuted branch is a safety question rather than a cost question. Enforced over the same unit run with `uv run coverage report --include="packages/medical-core/src/*" --fail-under=100` (one extra second, no new tooling). Measured after adoption: 908 statements, 0 missed, repo total 76.43%.

## Rejected

- **Mutation score as a gate.** Google's own paper reports that computing a whole-repo mutation score at any point in time is prohibitively expensive (they run per-diff incremental mutants instead); StrykerJS ships `break: null` — never failing a build on the score; and equivalent-mutant rates span 0.4%–35% with equivalence being undecidable. At this repo's scale the cost dominates the signal.
- **A new-code (time-window) gate through a coverage service.** It needs a second consumer to justify itself (ADR 0060 deletion test), and Codecov's monorepo flags and carry-forward defaults add failure modes the changed-line gate does not have.
- **Flipping branch coverage onto the same threshold.** The denominator changes (one per line *plus* one per branch destination), so an 80 measured before the flip is not the same standard after it; generated-expression false positives and unsupported `sysmon` cores (3.12/3.13) come along for free.
- **Raising the total instead.** Project-level >90% is explicitly "rarely worth it" in the same Google guidance, and totals are inflated by large tests — see decision 3.

## Consequences

- The coverage gate becomes satisfiable and meaningful: it fails on untested *changes* rather than on inherited debt, so the answer to a red gate is always "test the lines you changed".
- The 100% gate on `medical-core` pays for itself immediately as a dead-code detector: its first run surfaced an unreachable duplicate guidance branch in `ChatPipeline.run_stream` (the empty-`resolution` case is already handled by `_route`), which was deleted instead of being covered by a test that could never fail.
- Documentation may no longer claim an 82% baseline (ADR 0080 amended); `AGENTS.md` and `docs/version-baseline.md` carry the new wording.
- New dev dependency `diff-cover`; PR checkouts get heavier (`fetch-depth: 0`). Both are PR-level costs only.
- Unchanged by this ADR: mutation testing, predictive test selection, assertion-density metrics, coverage services, property-based testing as a gate, and moving integration/E2E to PR level — all rejected with reasons in the same research note.

## 修订（2026-09-14，对抗式测试审查后）

审查对上述门禁做了破坏性实测（合成未覆盖改动 → 看门禁是否真的变红），结论：变更行门禁与对齐守卫确实能红（实测缺失文件 exit 1、5 行未测新文件 0% exit 1）；以下四条因此被修订。

1. **决策 7 的分支缺口被修复：分支数据全局采集。** 原实现只有行覆盖，而决策 7 的理由是「静默未执行的分支是安全问题」——两者不匹配；实测 medical-core 分支覆盖 99%，4 个 partial（`chat/pipeline.py` 148→151、189→196；`chunking/chunking.py` 113→115、249→251）。现 `[tool.coverage.run] branch = true`，medical-core 的 `fail_under=100` 因而同时覆盖行与分支。处理方式（符合「不写永远不会失败的测试」）：189 → 补公共接缝测试（词映射空命中不改候选集）；113 → 删掉不可达守卫（两个调用方均已挡掉空数据行）；148 与 249 → 保留守卫 + `# pragma: no branch`（前者为「DoneEvent 之后再抛错不得改写已完成 Run」的顺序不变量，后者为防空切片，两者在公有接缝上都不可观察），注释写明理由。**代价与约束**：分母变为「行 + 分支目的地」，数字与开启前不可比；总量地板按同一「水位」规则重钉为 75（实测 75.23%，2026-09-14）：抬高需补测试，不得为绿灯下调。
2. **作用域限制登记（不装作已覆盖）。** 变更行门禁只看 `*/src/*.py`：`apps/api/migrations/**`（新迁移的数据处理代码）、`scripts/**`、`apps/web/**` 不在内；`alembic check` 只证明 schema 无漂移，不证明迁移正确。最小补偿：新增迁移 downgrade 往返回滚测试（`apps/api/tests/test_migration.py`）。
3. **门禁自身有可证伪面。** `scripts/ci/*` 的判定逻辑不属于任何源包，此前零测试；现登记为接缝并配 `scripts/ci/tests/test_check_patch_coverage.py`（对齐守卫、同名文件消歧），已用变异验证：把守卫改成永远放行时该测试变红。
4. **载体现状如实声明（文档不得声称机器未执行的东西）。** `eval-retrieval` 此前无阈值、恒绿，现带指标下限（`_MIN_METRICS`）并注明**不执行真实检索器**（候选集来自 fixtures）；E2E 与 `eval-answer` 当前无 CI 载体，`integration.yml` 触发于 `push: main`（postsubmit，非 PR 阻断），三者均已在 `docs/testing-seams.md` 登记为已知缺口与明确不覆盖。

遗留未做（有触发条件再上）：真实检索器（Qdrant dense+sparse + 融合）与真实 RabbitMQ 投递的集成用例（需 compose test profile 扩服务，且 fastembed 静态模型会引入下载依赖）；E2E 接入 CI（前置：本地连续稳定通过）。
