# well-look-at-that

`well-look-at-that` packages the local Codex usage attribution workflow as a pip-installable Daylily CLI. It preserves Codex token usage at the smallest locally captured unit: one row per `token_count` event.

The durable tabular store is TSV. The tool does not write CSV files.

## Install

```console
python -m pip install -e ".[dev]"
```

## CLI

The CLI is built with `cli-core-yo` v2 and exposes:

```console
well-look-at-that backfill --since 30d --codex-home ~/.codex --output-root ~/.codex/docs/codex-github-outcomes --skip-github
well-look-at-that report --window 30d --output-root ~/.codex/docs/codex-github-outcomes
well-look-at-that plot --window 30d --output-root ~/.codex/docs/codex-github-outcomes
well-look-at-that allocate-value --window 30d --output-root ~/.codex/docs/codex-github-outcomes --entitlements ~/.codex/docs/codex-github-outcomes/config/token_entitlements.tsv
well-look-at-that validate --window 30d --output-root ~/.codex/docs/codex-github-outcomes
```

Use `--skip-github` when authenticated `gh` access is intentionally unavailable. Without `--skip-github`, GitHub collection fails explicitly if `gh` is missing, unauthenticated, or unable to read a repo.

## Outputs

Runs write timestamped artifacts under the output root:

- `data/codex_token_events.tsv`
- `data/codex_threads.tsv`
- `data/github_events.tsv`
- `reports/latest_<window>_summary.md`
- `reports/latest_<window>_thread_rollups.tsv`
- `reports/latest_<window>_repo_workstream_outcome_rollups.tsv`
- `reports/latest_<window>_attribution_confidence_summary.tsv`
- `plots/latest_<window>_token_event_raster.html`
- `plots/latest_<window>_token_mix_stacked_area.html`
- `plots/latest_<window>_repo_outcome_heatmap.html`
- `plots/latest_<window>_cumulative_burnup_entitlements.html`
- `plots/latest_<window>_top_threads_sparklines.html`
- `runs/<run_id>_execution_ledger.md`

Raw prompts, raw command text, credentials, tokens, and PHI are not stored in outputs. Evidence pointers use file paths and line numbers.

## Entitlements And Value

`allocate-value` requires an explicit entitlement TSV. It does not infer base subscription or purchased token allocation from rate-limit percentages.

Expected columns:

```text
window_start	window_end	base_subscription_usd	base_subscription_tokens	purchased_usd	purchased_tokens	source	confidence	evidence_path
```

When entitlement rows are present, the burnup plot overlays base subscription allocation and purchased-token allocation. Observed purchased-credit balances from token events are reported separately because credit-to-token conversion is not locally exposed.

## Validation

```console
python -m pytest -q
python -m build
```
