# WLAT 0.2.2 Period Economic Readiness Ledger

- Created: `20260603T011306Z`
- Repo: `/Users/jmajor/projects/daylily/well-look-at-that`
- Initial branch: `main`
- Initial HEAD: `e36f2cb10f2dfc9b5e9ea16120d873bf1afd4365`
- Target version/tag: `0.2.2`
- Version tag rule: bare semver, no leading `v`

## Gate 0 Baseline

| Item | Evidence |
| --- | --- |
| Repo status | `git status --short --branch` -> `## main...origin/main` |
| Latest tag | `0.2.1` |
| Source archive | `/Users/jmajor/Downloads/wlat-repo-code-0.2.1.tgz` sha256 `2629b26dcd54d955a885bd8434a2dbcfd37d1c4360ef59ec065a046be21695db` |
| Current 28d bundle | `/Users/jmajor/Downloads/wlat-last-4-weeks.tgz` sha256 `7795ce4292c4079e48b8ef766096e35a02de9a5c847b2dcfb9be67993cd7db88` |
| Plan prompt | `/Users/jmajor/Downloads/codex_wlat_v2_2_plan_first_prompt.txt` sha256 `367470aafd524051268744944f94f00665dbb3510a2936e36be5ec94498049d8` |
| Codex rate card PDF | `/Users/jmajor/Downloads/Codex rate card _ OpenAI Help Center.pdf` sha256 `76c9f6d3017762f8c24e1d7b282acf3fcaffaadc81cc4906b80e39ce209347f3` |
| Pro invoice PDF | `/Users/jmajor/Downloads/Invoice-954AFFD0-0118.pdf` sha256 `1943fed1f05be85ca8cc13bb5cc635579aacd1edfc46e1a98d94bf4407cddaa1` |
| Pro receipt PDF | `/Users/jmajor/Downloads/Receipt-2630-3081-9562.pdf` sha256 `a840ceaebfc8bbf9d611938ee2a8b030eaaa270a445580793d33d287914105d9` |
| Purchased credit receipt PDF | `/Users/jmajor/Downloads/Receipt-2289-6345-3204.pdf` sha256 `317adc4bba4abfb48e2ce21f6a6ef8732f2ee2975cc6fa101dd68da879b88c8d` |
| Baseline tests | `.venv/bin/python -m pytest -q` -> 23 passed |
| Baseline coverage | `.venv/bin/python -m pytest --cov=well_look_at_that --cov-report=term-missing --cov-fail-under=45 -q` -> 23 passed, 84.33% |
| Baseline lint | `ruff check src tests` -> all checks passed |

## Current Audit

- `src/well_look_at_that/collectors/codex.py` applies the requested window during raw collection, dropping pre-window token events.
- `src/well_look_at_that/accounting.py` has `accounting_snapshot(output_root, since)` that filters raw rows before rebuilding deltas.
- `src/well_look_at_that/reports.py`, `src/well_look_at_that/plots.py`, and `src/well_look_at_that/value.py` consume window-filtered snapshots.
- The current 28-day bundle does not contain enough pre-window raw data to recompute exact clean period deltas after the fact.
- v2.1 already preserves raw rows, session segment IDs, duplicate active/archive exclusion, explicit thread/session turn metrics, and TSV-only persistence.

## Control Rows

| ID | Area | Requirement | Status | Category | Gate | Owner | Evidence | Root Cause | Terminal Note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| WLA22-000 | Gate 0 | Create ledger, record repo/archive/output/pricing evidence, baseline tests | SUCCESS | plan_amendment | Gate 0 | Agent A | This ledger; Gate 0 baseline above |  | Baseline captured before implementation edits |
| WLA22-001 | Collector | Split collection history from report window | SUCCESS | feature_implementation | Gate 1 | Agent B | `collect_codex(... since=None)` in `src/well_look_at_that/runner.py`; `--last-days 28` run `20260603T032422Z` collected `890942` raw events | Window was destructively applied during extraction | Raw collection now uses available history; report window is applied after accounting |
| WLA22-002 | Accounting | Compute full-history event deltas before period filtering | SUCCESS | feature_implementation | Gate 1 | Agent C | `period_accounting_snapshot`; test `test_period_snapshot_uses_pre_window_baseline_for_first_delta` | Deltas were rebuilt from already-filtered rows | Period delta fixture returns `300`, not `1300` |
| WLA22-003 | Accounting | Add optimized baseline mode with `is_window_baseline_event` | SUCCESS | feature_implementation | Gate 1 | Agent C | `token_event_accounting.tsv` column `is_window_baseline_event`; `window_boundary_diagnostics.tsv` count `549` | In-window first deltas lacked explicit baseline state | Pre-window baseline rows are marked and excluded from period usage |
| WLA22-004 | Accounting | Add lifetime vs period metrics | SUCCESS | feature_implementation | Gate 1 | Agent C | `period_cumulative_delta_tokens`; `intersecting_session_lifetime_total_tokens`; summary report text | Lifetime totals were easy to confuse with period use | Reports separate period consumption from intersecting-session lifetime totals |
| WLA22-005 | Accounting | Add boundary uncertainty diagnostics | SUCCESS | feature_implementation | Gate 1 | Agent C | `data/window_boundary_diagnostics.tsv`; summary boundary uncertainty `3.119979%` | Boundary status was implicit | Missing and exact baselines are visible with uncertainty fields |
| WLA22-006 | Reports/Plots | Rewrite reports and plots for period-correct deltas | SUCCESS | feature_implementation | Gate 1 | Agent D | `/Users/jmajor/Downloads/wlat-v2.2-28d/reports/latest_28d_summary.md`; plots generated in `plots/` | Report wording used unsafe totals | Summary names `period_cumulative_delta_tokens` as primary period basis |
| WLA22-007 | Value/Pricing | Add credit-price and subscription scenarios | SUCCESS | feature_implementation | Gate 1 | Agent E | `config/token_prices.yml`; `reports/economic_cost_scenarios.tsv`; `$0.04/credit` scenario rows | Pricing inputs were not explicit | Cost outputs require explicit config and preserve subscription as internal allocation |
| WLA22-008 | Attribution | Add attribution diagnostics and confidence shares | SUCCESS | feature_implementation | Gate 1 | Agent F | `data/token_attribution_diagnostics.tsv`; readiness strong share `38.911650%`; derived share `61.088350%` | Unknown/derived allocation could be hidden | Confidence shares are emitted and unknowns are not silently reassigned |
| WLA22-009 | Economics | Add economic token usage/readiness tables | SUCCESS | feature_implementation | Gate 1 | Agent G | `reports/economic_token_usage_by_day.tsv`; week/month/repo/workstream/outcome tables; `economic_readiness.tsv` | Economic readiness was not machine-readable | Aggregate/trend readiness PASS; repo/workstream/outcome CAUTION; chargeback FAIL |
| WLA22-010 | Validator | Add period, uncertainty, attribution, pricing invariants | SUCCESS | contract_test | Gate 5 | Agent H | `.venv/bin/wlat --json validate --output-root /Users/jmajor/Downloads/wlat-v2.2-28d` -> `SUCCESS`, `validation_error_count=0` | Validator did not catch known period-boundary issues | Validation checks raw/accounting parity, period rollups, readiness, CSV, and redaction |
| WLA22-011 | Tests | Add deterministic boundary/economic fixtures | SUCCESS | contract_test | Gate 5 | Agent I | `.venv/bin/python -m pytest -q` -> `27 passed`; coverage `86.03%` | Boundary and pricing cases were under-specified | Added pre-window, missing-baseline, in-window-start, and cost-scenario tests |
| WLA22-012 | Docs/Bundle | Update README/examples, manifest, clean tarball | SUCCESS | feature_implementation | Gate 5 | Agent J | `README.md`; `examples/README.md`; `examples/token_prices.example.yml`; tar hygiene checks returned no `._*` or `.csv` entries | Docs lagged accounting semantics | Docs explain v2.2 accounting, no-`v` version rule, price config, and cwd/repo-root attribution |
| WLA22-013 | Acceptance | Build, backfill, validate, package, release `0.2.2` | SUCCESS | contract_test | Gate 5 | Agent A | `python -m build` -> 0.2.2 sdist/wheel; backfill `20260603T032422Z` -> SUCCESS; validate `20260603T033539Z` -> SUCCESS; tarballs listed below | Needed clean reproducible release artifacts | Implementation accepted; PR/tag publication proceeds from clean validated commit |

## Pricing Evidence

- Purchased credits: `1,076` credits for `$43.04`, giving `$0.04/credit`.
- Pro subscription: `$200.00/month`.
- The Codex rate-card PDF supplies token-based credits per 1M input, cached input, and output tokens.
- The Codex usage dashboard PDFs show remaining shared agentic usage percentages but do not expose an included base token/credit allocation.

## Final Status Summary

- All control rows are terminal.
- Objective status: implementation complete and release-ready from local validation.
- Package version: `0.2.2`.
- End-to-end backfill run: `20260603T032422Z`.
- Standalone validation run: `20260603T033539Z`.
- Raw token events: `890942`.
- Event accounting rows: `890942`.
- 28-day event rows: `256927`.
- Primary 28-day period basis: `37126477848` `period_cumulative_delta_tokens`.
- Boundary uncertain period tokens: `1158338438`.
- Boundary uncertainty percent: `3.119979`.
- Strong attribution token share: `38.911650`.
- Derived attribution token share: `61.088350`.
- Economic readiness: aggregate PASS, day/week/month trend PASS, repo/workstream/outcome CAUTION, chargeback/invoicing FAIL.
- Validation errors: `0`.
- CSV files: `0`.
- Redaction findings: `0`.
- Data/report bundle: `/Users/jmajor/Downloads/wlat-v2.2-28d.tgz` sha256 `3fcf8cf8780eb6999228ff8732abe8852360c5f0d4eb536d312babaeb82c41e0`.
- Repo-code bundle: `/Users/jmajor/Downloads/wlat-repo-code-0.2.2.tgz` sha256 `381a6473fed6cf60a09e47b438901ecef06e9ca65c11341ea9a510423e5e6d32`.
- Tar hygiene: no `._*` entries and no `.csv` entries found in either generated tarball.
