# wlat v2.1 Token Accounting Fix Ledger

Run timestamp: `20260602T193944Z`
Repo: `/Users/jmajor/projects/daylily/well-look-at-that`
Current baseline: `beca0c53f915`, tag `0.1.4`
Supplied code archive: `/Users/jmajor/Downloads/wlat-v2-code.tgz`
Supplied output bundle: `/Users/jmajor/Downloads/wlat-v2.tgz`

## Gate 0 Baseline

- Worktree at start: clean on `main...origin/main`.
- Baseline checks before edits:
  - `.venv/bin/python -m pytest -q` -> 20 passed.
  - `.venv/bin/ruff check src tests` -> all checks passed.
- Existing v2 output bundle contains the expected tables, including `raw_token_events.tsv`, `token_event_accounting.tsv`, `token_turn_estimates.tsv`, `token_session_rollups.tsv`, `token_thread_rollups.tsv`, and `token_accounting_reconciliation.tsv`.
- Existing v2 defects verified from supplied bundle headers/samples:
  - `token_turn_estimates.tsv` uses ambiguous `unique_last_per_turn_tokens`.
  - `token_thread_rollups.tsv` sets `final_thread_total_tokens` equal to `final_session_total_tokens` on multi-segment rows.
  - `token_accounting_reconciliation.tsv` thread rows with token events show `session_segment_count = 0`.
  - Existing validator only checks TSV/no-CSV/redaction basics and does not fail these semantic accounting defects.

## Control Rows

| ID | Agent | Area | Status | Requirement | Evidence / Acceptance | Notes |
|---|---|---:|---|---|---|---|
| WLA21-000 | A Orchestrator | Gate 0 | SUCCESS | Create ledger, record repo/archive/output-bundle state, current HEAD/tag, existing v2 failures | This ledger; baseline commands above. | Initial inventory complete. |
| WLA21-001 | B Schema | Data model | SUCCESS | Add explicit columns for `unique_last_per_thread_turn_tokens` and `unique_last_per_session_turn_tokens`; deprecate ambiguous `unique_last_per_turn_tokens` in report text | `model.py`; regenerated v2 summary includes both explicit metrics and alias warning. |  |
| WLA21-002 | C Accounting | Raw preservation | SUCCESS | Preserve one row per raw `token_count` event; keep compatibility TSV readable | Fresh v2.1 validation: 889,591 raw/compat token events. |  |
| WLA21-003 | C Accounting | Session grain | SUCCESS | Keep primary `sum(max(total_token_usage.total_tokens) per included session_segment_id)` basis | Fresh v2.1 final session total: 116,948,005,458. |  |
| WLA21-004 | C Accounting | Event deltas | SUCCESS | Keep one accounting row per raw event and compute positive cumulative deltas per included session segment | Fresh v2.1 cumulative delta: 116,948,005,458; validator SUCCESS. |  |
| WLA21-005 | C Accounting | Thread max | SUCCESS | Define `final_thread_total_tokens` as max cumulative per logical `thread_id`, diagnostic only | Fresh v2.1 final thread max cumulative: 40,389,483,983; multi-segment fixture passes. |  |
| WLA21-006 | C Accounting | Method D | SUCCESS | Compute exact `unique_last_per_thread_turn_tokens` grouped by `thread_id`, `turn_id`, `last_token_usage_hash`; missing turn rows stay per raw event/content hash | Fresh v2.1 thread/turn total: 42,939,688,743; method D fixture passes. |  |
| WLA21-007 | C Accounting | Session turn estimate | SUCCESS | Rename current session-scoped estimate to `unique_last_per_session_turn_tokens` | Fresh v2.1 session/turn total: 120,045,880,901. |  |
| WLA21-008 | C Accounting | Repeated counts | SUCCESS | Recompute repeated last/cumulative diagnostics directly from raw rows at target grain using `(thread_id, usage_hash)` | Fresh v2.1 repeated last/cumulative totals: 588,227 / 590,654. |  |
| WLA21-009 | C Accounting | Distinct turns | SUCCESS | Compute direct distinct `(thread_id, turn_id)` counts per target grain; missing turn ids do not collapse | Fresh v2.1 distinct thread-turn count: 10,594. |  |
| WLA21-010 | D Reconciliation | Thread rows | SUCCESS | Fix `grain=thread` reconciliation `session_segment_count` and related metrics | Validator rejects zero segment counts; fresh v2.1 validation SUCCESS. |  |
| WLA21-011 | D Reconciliation | Time rows | SUCCESS | Populate day/week/month `token_event_count`; reconcile cumulative deltas and event counts | Fresh day/week/month event counts all 889,591 and deltas all 116,948,005,458. |  |
| WLA21-012 | D Reports | Text/naming | SUCCESS | Explain raw grain, accounting grain, primary basis, thread max diagnostic, turn diagnostics, deprecated aliases | `README.md`; generated summary wording verified. |  |
| WLA21-013 | E Value | Non-economic guard | SUCCESS | Confirm value allocation remains `cumulative_delta_tokens` based and does not use raw row totals | `value.py` unchanged semantically; regression suite passes. |  |
| WLA21-014 | F Validator | Invariants | SUCCESS | Fail validation on raw loss, bad row coverage, bad session/thread/time reconciliation, misleading names, CSV/redaction findings | `reports.py` validator invariants; full validation SUCCESS on v2.1 bundle. |  |
| WLA21-015 | F Tests | Fixtures | SUCCESS | Add compact fixtures for repeats, resets, missing turns, duplicates, multi-segment threads, time buckets, method D | 23 tests pass; coverage 84.33%. |  |
| WLA21-016 | G Docs | README/examples | SUCCESS | Update README for v2.1 semantics; add `examples/` with entitlement TSV and backfill/validate commands | `README.md`; `examples/README.md`; `examples/token_entitlements.example.tsv`. |  |
| WLA21-017 | G Packaging | Bundles | SUCCESS | Strip AppleDouble `._*`; document compatibility alias; avoid unnecessary huge duplicate bundles where possible | `/Users/jmajor/Downloads/wlat-v2.1.tgz`; `tar -tzf ... | grep '/._'` returned none. |  |
| WLA21-018 | A Acceptance | Gate 5 | SUCCESS | Run full tests, lint, build, generate new bundle, validate, summarize before/after totals | Test/build/backfill/validate logs below; all rows terminal and objective complete. |  |

## Validation Log

- Gate 0 baseline:
  - `.venv/bin/python -m pytest -q` -> 20 passed.
  - `.venv/bin/ruff check src tests` -> all checks passed.
- Implementation validation:
  - `.venv/bin/python -m pytest -q` -> 23 passed.
  - `.venv/bin/python -m pytest --cov=well_look_at_that --cov-report=term-missing --cov-fail-under=45` -> 23 passed, 84.33% coverage.
  - `.venv/bin/ruff check src tests` -> all checks passed.
  - `.venv/bin/python -m build` -> built `well_look_at_that-0.2.1.tar.gz` and `well_look_at_that-0.2.1-py3-none-any.whl`.
  - Supplied v2 bundle regenerated in `/tmp/wlat-v2-check.vKyoZi/wlat-20260602` -> report and validate SUCCESS, 888,855 token events.
  - Fresh v2.1 backfill `/Users/jmajor/Downloads/wlat-v2.1` -> run `20260602T195839Z` SUCCESS, 889,591 token events, 5,400 GitHub events, 0 CSV files, 0 redaction findings.
  - Standalone validate `/Users/jmajor/Downloads/wlat-v2.1` -> run `20260602T200817Z` SUCCESS.

## Acceptance Metrics

Supplied v2 bundle after v2.1 regeneration:

- `observed_event_sum_tokens`: 125,689,093,249
- `final_session_total_tokens`: 116,848,168,953
- `cumulative_delta_tokens`: 116,848,168,953
- `final_thread_total_tokens`: 40,289,647,478
- `unique_last_per_thread_turn_tokens`: 42,839,404,205
- `unique_last_per_session_turn_tokens`: 119,945,596,363
- repeated last/cumulative counts: 588,225 / 590,646
- day/week/month token event counts: 888,855 / 888,855 / 888,855

Fresh v2.1 bundle:

- Output root: `/Users/jmajor/Downloads/wlat-v2.1`
- Tarball: `/Users/jmajor/Downloads/wlat-v2.1.tgz`
- `observed_event_sum_tokens`: 125,789,473,868
- `final_session_total_tokens`: 116,948,005,458
- `cumulative_delta_tokens`: 116,948,005,458
- `final_thread_total_tokens`: 40,389,483,983
- `unique_last_per_thread_turn_tokens`: 42,939,688,743
- `unique_last_per_session_turn_tokens`: 120,045,880,901
- repeated last/cumulative counts: 588,227 / 590,654
- day/week/month token event counts: 889,591 / 889,591 / 889,591
