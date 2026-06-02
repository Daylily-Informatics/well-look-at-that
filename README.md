# well-look-at-that

`well-look-at-that` is a local reporting CLI for joining Codex token usage to GitHub activity and outcome-oriented workstreams. It preserves Codex usage at the smallest raw local grain: one row per captured `token_count` event.

The durable tabular format is TSV. The tool does not write CSV files.

## What It Collects

`wlat` reads local Codex state and session archives, then optionally calls GitHub through the `gh` CLI. It writes timestamped run artifacts under an output root, plus `latest_*` report and plot files for the selected window.

Primary local Codex inputs:

- `~/.codex/state_5.sqlite`
- `~/.codex/sessions/**`
- `~/.codex/archived_sessions/**`
- `~/.codex/process_manager/chat_processes.json`
- related Codex logs, goals, memory summaries, and evidence pointers when present

Primary GitHub inputs:

- commits
- pull requests
- pull request files
- issues
- releases and tags

Raw prompts, raw command text, credentials, tokens, and PHI are not stored in generated outputs. Reports use counts, rollups, evidence file paths, line numbers, and redacted snippets where needed.

## Token Accounting Basis

Raw `token_count` events are diagnostic evidence, not validated accounting totals. Codex can emit repeated `last_token_usage` or repeated cumulative usage records within a thread, so summing raw event rows can overstate usage.

`wlat` keeps raw rows but derives separate accounting views:

- Raw grain: one `token_count` event in `data/raw_token_events.tsv`.
- Accounting grain: one session/rollout cumulative segment in `data/token_session_rollups.tsv`.
- Time allocation grain: positive cumulative deltas in `data/token_event_accounting.tsv`.
- Thread grain: rollup across included session segments in `data/token_thread_rollups.tsv`.

Report language is explicit:

- `observed_event_sum_tokens` is the old raw event-row sum and is diagnostic.
- `final_session_total_tokens` is the primary quota approximation.
- `cumulative_delta_tokens` is the basis for day/week/month allocation and burnup plots.
- `deduped_turn_tokens` is a diagnostic turn estimate, not a billing total.

## Requirements

- Python `>=3.12`
- Read access to the local Codex home, usually `~/.codex`
- Optional: GitHub CLI `gh` authenticated with read access to the repos you want correlated
- Optional: explicit token entitlement TSV for dollar-value and subscription/purchased-token overlays

Check GitHub access before running a full backfill:

```console
gh auth status
```

If GitHub access is intentionally unavailable, use `--skip-github`. Without `--skip-github`, GitHub collection fails explicitly when `gh` is missing, unauthenticated, or unable to read a repo.

## Install

### Install From GitHub

Use this for normal local use before the package is published to an internal or public package index:

```console
python -m pip install "well-look-at-that @ git+https://github.com/Daylily-Informatics/well-look-at-that.git@0.1.4"
```

That installs both command names:

```console
well-look-at-that --help
wlat --help
```

`wlat` is the short alias used in examples.

### Editable Developer Install

Use this when working inside a clone:

```console
git clone https://github.com/Daylily-Informatics/well-look-at-that.git
cd well-look-at-that
python -m venv .venv
. .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[dev]"
wlat --json version
```

Expected version for this release:

```json
{
  "app": "well-look-at-that",
  "version": "0.1.4"
}
```

## Generate Datasets From Existing Work

Use `backfill` to extract historical Codex usage and optional GitHub activity. The output root can be any durable directory. For this workspace, Codex report roots normally live under `~/.codex/docs/`.

### Rolling Last 30 Days

```console
wlat backfill \
  --since 30d \
  --codex-home ~/.codex \
  --output-root ~/.codex/docs/codex-github-outcomes \
  --repo-root ~/projects \
  --repo-root ~/IGNORE-THIS
```

### January 2026 Forward

```console
wlat backfill \
  --since 2026-01-01T00:00:00Z \
  --codex-home ~/.codex \
  --output-root ~/.codex/docs/codex-github-outcomes-jan-2026 \
  --repo-root ~/projects \
  --repo-root ~/IGNORE-THIS
```

### Codex-Only Backfill

Use this when you want token/thread reports without GitHub API reads:

```console
wlat backfill \
  --since 30d \
  --codex-home ~/.codex \
  --output-root ~/.codex/docs/codex-github-outcomes \
  --repo-root ~/projects \
  --repo-root ~/IGNORE-THIS \
  --skip-github
```

### Data Only

Use this when you want to collect TSV facts first and build reports later:

```console
wlat backfill \
  --since 30d \
  --output-root ~/.codex/docs/codex-github-outcomes \
  --repo-root ~/projects \
  --repo-root ~/IGNORE-THIS \
  --no-reports \
  --no-plots
```

Then regenerate reports and plots from the existing TSV data:

```console
wlat report --window 30d --output-root ~/.codex/docs/codex-github-outcomes
wlat plot --window 30d --output-root ~/.codex/docs/codex-github-outcomes
wlat validate --output-root ~/.codex/docs/codex-github-outcomes
```

## Ongoing Collection

Run `run-incremental` on a schedule to keep the rolling report current:

```console
wlat run-incremental \
  --window 30d \
  --codex-home ~/.codex \
  --output-root ~/.codex/docs/codex-github-outcomes \
  --repo-root ~/projects \
  --repo-root ~/IGNORE-THIS
```

For scheduled use, keep the command explicit. Include every local root that should be considered for repo attribution. Do not rely on hidden discovery of moved repos, scratch worktrees, or ignored directories.

## Outputs

Each run writes timestamped artifacts under the output root. Common paths:

```text
data/codex_token_events.tsv
data/raw_token_events.tsv
data/token_event_accounting.tsv
data/token_turn_estimates.tsv
data/token_session_rollups.tsv
data/token_thread_rollups.tsv
data/token_accounting_reconciliation.tsv
data/codex_threads.tsv
data/github_events.tsv
reports/latest_<window>_summary.md
reports/latest_<window>_thread_rollups.tsv
reports/latest_<window>_repo_workstream_outcome_rollups.tsv
reports/latest_<window>_daily_token_accounting.tsv
reports/latest_<window>_weekly_token_accounting.tsv
reports/latest_<window>_monthly_token_accounting.tsv
reports/latest_<window>_attribution_confidence_summary.tsv
plots/latest_<window>_token_event_raster.html
plots/latest_<window>_token_mix_stacked_area.html
plots/latest_<window>_repo_outcome_heatmap.html
plots/latest_<window>_cumulative_burnup_entitlements.html
plots/latest_<window>_top_threads_sparklines.html
runs/<run_id>_execution_ledger.md
```

The raw event-grain TSV is the source evidence table. Thread, repo, workstream, outcome, day, week, and month reports aggregate upward from derived accounting views.

## Token Value And Entitlements

`allocate-value` requires an explicit entitlement TSV. It does not infer base subscription allocation or purchased-token allocation from rate-limit percentages.

Expected entitlement columns:

```text
window_start	window_end	base_subscription_usd	base_subscription_tokens	purchased_usd	purchased_tokens	source	confidence	evidence_path
```

Example:

```text
window_start	window_end	base_subscription_usd	base_subscription_tokens	purchased_usd	purchased_tokens	source	confidence	evidence_path
2026-06-01T00:00:00Z	2026-07-01T00:00:00Z	200.00	100000000	50.00	25000000	manual invoice entry	manual	~/.codex/docs/codex-github-outcomes/config/token_entitlements.tsv
```

Run value allocation and entitlement-aware plots:

```console
wlat allocate-value \
  --window 30d \
  --output-root ~/.codex/docs/codex-github-outcomes \
  --entitlements ~/.codex/docs/codex-github-outcomes/config/token_entitlements.tsv

wlat plot \
  --window 30d \
  --output-root ~/.codex/docs/codex-github-outcomes \
  --entitlements ~/.codex/docs/codex-github-outcomes/config/token_entitlements.tsv
```

When entitlement rows are present, the burnup plot can overlay base subscription allocation and purchased-token allocation. Usage in that plot is cumulative-delta accounting, not raw event-row summation. Observed purchased-credit balances from Codex token events are reported separately unless a valid conversion is explicitly supplied in data that the tool understands.

## Attribution Guidelines For Future Work

Codex captures the working directory associated with sessions. That directory is one of the strongest local signals for associating token use with a repository or workstream. Better working-directory hygiene produces better reports.

Recommended practice:

- Start Codex from the repository root when the work belongs to one repo.
- Start Codex from a stable project root when the work spans multiple repos, for example `~/projects/daylily` or `~/projects/lsmc`.
- Avoid starting repo work from `$HOME`, `/tmp`, `~/.codex`, or an unrelated parent directory.
- For scratch or sensitive repos under ignored locations, pass those roots explicitly with repeated `--repo-root` options.
- Keep repo remotes configured. `git remote get-url origin`, branch, and SHA are strong attribution signals.
- Use feature branches and PRs for meaningful work. Branch names, commits, PR titles, labels, and changed files improve outcome classification.
- Put durable plans and ledgers in `docs/plans/` inside the repo when work is substantial.
- Use issue or PR identifiers in branch names, commit messages, or plan filenames when they exist.
- Keep docs, tests, infra, and feature work in distinct commits or PRs when possible. That improves outcome taxonomy.
- When a Codex session moves across repos, start a new session from the new repo root if you want clean attribution.

For work that has no GitHub repo, the captured `cwd` can still be used as a project/workstream key. Add that directory as `--repo-root` in later backfills when it represents real work.

## Attribution Confidence

Reports mark attribution confidence instead of silently guessing. Typical evidence strength:

- `exact`: token event or thread evidence maps directly to a known thread, repo root, Git SHA, PR, issue, or GitHub artifact.
- `strong`: multiple local signals agree, such as Codex `cwd`, session metadata, git origin, and process working directory.
- `derived`: attribution comes from path matching, workstream labels, plan filenames, branch names, or timestamp proximity.
- `weak`: only partial evidence exists, usually a directory name or sparse session metadata.
- `manual`: attribution came from explicit user-provided roots or entitlement data.

## Validation

Development checks:

```console
python -m pytest -q
python -m pytest --cov=well_look_at_that --cov-report=term-missing --cov-fail-under=45
ruff check src tests
python -m build
```

Report validation:

```console
wlat validate --output-root ~/.codex/docs/codex-github-outcomes
```

Validation checks TSV-only output discipline and redaction scan findings. A clean validation means no CSV files were generated and no configured redaction pattern was found in report outputs.
