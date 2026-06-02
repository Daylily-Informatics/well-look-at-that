# Codex Token Accounting Fix Ledger

Created: 2026-06-02T11:54:18Z

## Control Ledger

Controlling plan: user request in Codex thread, "Multiagent Ledgered Plan: Fix `wlat` Codex Token Accounting"
Ledger path: `/Users/jmajor/projects/daylily/well-look-at-that/docs/plans/20260602T115418Z_codex_token_accounting_fix_ledger.md`

## Gate 0 Baseline

- Repo: `/Users/jmajor/projects/daylily/well-look-at-that`
- Branch/head: `main` at `cd08d2b33f51f5b79d3d1df3c0e5a8d62f989819`
- Repo state: `git status --short --branch` -> `## main...origin/main`
- Existing plans: `20260602T073236Z_initial_packaging_ledger.md`, `20260602T083433Z_tests_ci_release_report_ledger.md`
- Source audit:
  - `src/well_look_at_that/collectors/codex.py` extracts raw `token_count` events and writes `total_tokens` from `last_token_usage.total_tokens`.
  - `src/well_look_at_that/reports.py` sums raw row `total_tokens` and labels the sum as `Total tokens`.
  - `src/well_look_at_that/value.py` allocates entitlement/value from raw row `total_tokens`.
  - `src/well_look_at_that/plots.py` uses raw row `total_tokens` for burnup, heatmap, sparklines, and raster color.
- Current output bundle inspected: `/Users/jmajor/.codex/docs/codex-github-outcomes-jan-2026-wlat-20260602T085347Z`
- Current metrics from output bundle:
  - Raw token rows: `887,716`
  - Threads with token events: `1,011`
  - Session segments: `1,496`
  - Multi-segment threads: `49`
  - Current unsafe event sum: `125,521,342,183`
  - Session cumulative basis: `117,839,896,229`
  - Inflation current vs session cumulative: `1.065x`
  - Repeated `last_token_usage` groups: `40,808`
  - Repeated cumulative groups: `69,215`
  - Active/archive overlap threads: `2`
- Baseline/final tests: `ruff check src tests` -> passed; `pytest --cov=well_look_at_that --cov-report=term-missing --cov-fail-under=45` -> 20 passed, 83.57% coverage; `python -m build` -> built `well_look_at_that-0.1.4` sdist/wheel.

## Agents

- Agent A, Orchestrator: ledger creation, Gate 0, row status, final consistency.
- Agent B, Collector: raw event preservation, hashes, source metadata, segment ids.
- Agent C, Accounting: derived tables and token algorithms.
- Agent D, Reports/Plots: labels, rollups, reconciliation reports, plot basis changes.
- Agent E, Value: entitlement and dollar allocation basis changes.
- Agent F, Tests/Validation: fixtures, regression tests, full validation commands.
- Agent G, Docs/Release: README updates, PR/release notes, acceptance summary.

## Control Rows

| ID | Area | Requirement | Status | Category | Gate | Owner | Evidence | Root Cause | Terminal Note |
|---|---|---|---|---|---|---|---|---|---|
| WLA-TOK-000 | Gate 0 | Create ledger, record repo state, current output bundle metrics, source audit, baseline tests | SUCCESS | plan_amendment | Gate 0 | Agent A | Ledger created; repo clean; source audit and output metrics recorded above. |  | Gate 0 inventory recorded before runtime edits. |
| WLA-TOK-001 | Collector | Preserve all raw `token_count` rows and add canonical `raw_token_events.tsv` | SUCCESS | feature_implementation | Gate 1 | Agent B | `collectors/codex.py`; audit `raw_token_events.tsv` has 888,744 raw rows plus header. |  | Raw rows preserved and canonical raw TSV produced. |
| WLA-TOK-002 | Collector | Add `source_path`, active/archive flags, payload hashes, missing-usage flags, raw/synthetic event ids | SUCCESS | feature_implementation | Gate 1 | Agent B | `tests/test_token_accounting.py::test_collector_writes_raw_event_metadata_and_compatibility_tsv`; `TOKEN_EVENT_COLUMNS` includes metadata. |  | Proven by collector fixture assertions. |
| WLA-TOK-003 | Collector | Add stable `session_segment_id` from `(thread_id, rollout_path/source_path)` | SUCCESS | feature_implementation | Gate 1 | Agent B | `accounting.py`; collector test asserts nonempty segment id; audit `token_session_rollups.tsv` has 1,496 rows plus header. |  | Segment ids drive session rollups. |
| WLA-TOK-004 | Accounting | Implement session rollups using max cumulative per session segment | SUCCESS | feature_implementation | Gate 1 | Agent C | `accounting.py`; `token_session_rollups.tsv`; repeat fixture expects final session total 10 from repeated 30 observed tokens. |  | Primary accounting basis implemented. |
| WLA-TOK-005 | Accounting | Implement cumulative positive deltas with repeat and reset handling | SUCCESS | feature_implementation | Gate 1 | Agent C | `tests/test_token_accounting.py::test_cumulative_reset_starts_new_delta_span`; audit summary delta total 116,830,117,664. |  | Positive delta and reset warning behavior implemented. |
| WLA-TOK-006 | Accounting | Implement turn estimates using unique `last_token_usage` per turn/hash, no fake turn collapse | SUCCESS | feature_implementation | Gate 1 | Agent C | `tests/test_token_accounting.py::test_missing_turn_id_keeps_event_grain_for_turn_estimate`; `token_turn_estimates.tsv`. |  | Missing turn ids stay event-grain for diagnostics. |
| WLA-TOK-007 | Accounting | Implement duplicate segment diagnostics and active/archive overlap warnings | SUCCESS | feature_implementation | Gate 1 | Agent C | `tests/test_token_accounting.py::test_duplicate_active_archived_segment_is_excluded_from_primary_accounting`. |  | Exact duplicate segments are excluded from primary accounting and warned. |
| WLA-TOK-008 | Reports | Stop labeling raw event-row sums as validated `Total tokens` | SUCCESS | feature_implementation | Gate 1 | Agent D | Audit summary labels `Observed event-row sum tokens (diagnostic)`, `Final session total tokens`, and `Cumulative delta tokens`. |  | Unsafe total label removed from summary. |
| WLA-TOK-009 | Reports | Add thread/repo/workstream/outcome/day/week/month reconciliation rollups | SUCCESS | feature_implementation | Gate 1 | Agent D | Audit reports include thread, repo/workstream/outcome, daily, weekly, monthly TSVs; `token_accounting_reconciliation.tsv` has 1,338 rows plus header. |  | Required reconciliation views generated. |
| WLA-TOK-010 | Plots | Use `cumulative_delta_tokens` for burnup and time intensity; keep raster diagnostic | SUCCESS | feature_implementation | Gate 1 | Agent D | `plots.py`; plot text states raster is diagnostic and burnup uses cumulative-delta accounting. |  | Plot bases changed; raster retained as diagnostic. |
| WLA-TOK-011 | Value | Use derived accounting basis, not raw event `total_tokens`, for entitlement consumption | SUCCESS | feature_implementation | Gate 1 | Agent E | `value.py`; `VALUE_ALLOCATION_COLUMNS` includes `accounting_basis`; report/value fixture passes with cumulative deltas. |  | Entitlement consumption uses `cumulative_delta_tokens`. |
| WLA-TOK-012 | Backward Compatibility | Keep `codex_token_events.tsv` readable; deprecate old `total_tokens` meaning in reports | SUCCESS | legitimate_safety_handling | Gate 1 | Agent B | Audit contains both `codex_token_events.tsv` and `raw_token_events.tsv`; existing compatibility tests pass. |  | Compatibility TSV remains readable; reports deprecate raw total semantics. |
| WLA-TOK-013 | Tests | Add fixture matrix for repeats, resets, missing turn ids, archive overlap, duplicate content, multi-segment threads | SUCCESS | contract_test | Gate 5 | Agent F | `tests/test_token_accounting.py`; focused test run -> 20 passed. |  | Required fixture classes covered. |
| WLA-TOK-014 | Validation | Run full pytest, coverage, ruff, build, and January backfill audit | SUCCESS | contract_test | Gate 5 | Agent F | `ruff check src tests` passed; pytest coverage 20 passed/83.57%; build succeeded; backfill run `20260602T120610Z` SUCCESS; validate run `20260602T121345Z` SUCCESS. |  | Full validation completed. |
| WLA-TOK-015 | Docs | Update README to explain raw vs accounting grain and uncertainty warnings | SUCCESS | feature_implementation | Gate 5 | Agent G | `README.md` now documents raw/accounting/time/thread grains and metric basis names. |  | User-facing accounting guidance updated. |
| WLA-TOK-016 | Final Acceptance | Verify no `OPEN`, `IN_PROGRESS`, or `ATTEMPTING_BUGFIX` rows remain | SUCCESS | contract_test | Gate 5 | Agent A | All rows in this table are `SUCCESS`; no `FAIL` or `BLOCKED` rows. |  | Ledger terminal and objective complete. |

## Implementation Rules

- Do not delete or collapse raw token events.
- Treat `observed_event_sum_tokens` as diagnostic only.
- Primary quota approximation: `sum(max(total_token_usage.total_tokens) per included session_segment_id)`.
- Time allocation basis: positive cumulative deltas within each session segment, ordered by `(timestamp, line_number)`.
- Missing `turn_id` rows must remain event-grain for turn diagnostics.
- Duplicate active/archive segments may be excluded from primary accounting only when ordered token payload hashes match exactly.
- Value allocation must not perform economic interpretation until accounting validation passes.

## Terminal Summary

- Status counts: `SUCCESS=17`, `OPEN=0`, `IN_PROGRESS=0`, `ATTEMPTING_BUGFIX=0`, `FAIL=0`, `BLOCKED=0`.
- Objective complete: yes.
- Audit output root: `/Users/jmajor/.codex/docs/codex-github-outcomes-accounting-audit`
- Audit summary:
  - Token events: `888,744`
  - Observed event-row sum tokens: `125,670,800,218`
  - Final session total tokens: `116,830,117,664`
  - Cumulative delta tokens: `116,830,117,664`
  - CSV files: `0`
  - Redaction findings: `0`
