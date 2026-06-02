# well-look-at-that Initial Packaging Ledger

## Gate 0: Inventory Freeze

- Ledger path: `docs/plans/20260602T073236Z_initial_packaging_ledger.md`
- Local repo path: `/Users/jmajor/projects/daylily/well-look-at-that`
- Target GitHub repo: `Daylily-Informatics/well-look-at-that`
- Source script inspected: `/Users/jmajor/.codex/docs/codex-github-outcomes/codex_github_outcomes.py`
- CLI pattern inspected: Kahlo `app/cli/__init__.py` and `cli-core-yo` v2 README/spec
- GitHub availability: target repo not found before creation
- Python baseline: Python 3.13.13
- Tabular storage decision: TSV only; CSV outputs rejected by code
- Sensitive data boundary: raw prompts, raw command text, credentials, tokens, and PHI excluded from generated reports

## Execution Rows

| ID | Area | Requirement | Status | Category | Approval Gate | Owner | Evidence | Root Cause | Terminal Note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| WLA-001 | repo | Create pip-installable package scaffold for `well-look-at-that`. | SUCCESS | feature_implementation | Gate 1 | Agent A | `pyproject.toml`, `src/well_look_at_that/__init__.py` |  | Package metadata and console script are present. |
| WLA-002 | cli | Build CLI with `cli-core-yo` v2 patterns used by Dayhoff services. | SUCCESS | feature_implementation | Gate 1 | Agent A | `src/well_look_at_that/cli.py`, `tests/test_reports_plots_cli.py` |  | CLI uses immutable `CliSpec`, `create_app`, and registry commands. |
| WLA-003 | codex | Extract Codex token events and threads at event grain. | SUCCESS | feature_implementation | Gate 1 | Agent B | `src/well_look_at_that/collectors/codex.py`, `tests/test_codex_collect.py` |  | One row per `token_count` event is written to TSV. |
| WLA-004 | github | Collect GitHub activity through authenticated read-only `gh` calls. | SUCCESS | feature_implementation | Gate 1 | Agent C | `src/well_look_at_that/collectors/github.py` |  | Commits, PRs, and issues are normalized into TSV. |
| WLA-005 | reports | Generate TSV rollups and Markdown report outputs. | SUCCESS | feature_implementation | Gate 1 | Agent D | `src/well_look_at_that/reports.py`, `tests/test_reports_plots_cli.py` |  | Thread, repo/workstream/outcome, workstream, confidence, and credit-balance TSVs are generated. |
| WLA-006 | plots | Generate dense token plots and entitlement burnup plot. | SUCCESS | feature_implementation | Gate 1 | Agent E | `src/well_look_at_that/plots.py`, `tests/test_reports_plots_cli.py` |  | Raster, token mix, heatmap, burnup, and thread sparkline plots are generated. |
| WLA-007 | value | Assign dollar value from explicit base and purchased token entitlements. | SUCCESS | feature_implementation | Gate 1 | Agent D | `src/well_look_at_that/value.py`, `tests/test_reports_plots_cli.py` |  | Value allocation fails without explicit entitlement TSV and writes TSV allocations when present. |
| WLA-008 | validation | Validate no CSV outputs and scan generated artifacts for secret-like patterns. | SUCCESS | contract_test | Gate 5 | Agent F | `src/well_look_at_that/reports.py`, tests |  | Validation reports CSV count and redaction findings. |
| WLA-009 | github-repo | Create GitHub repo and issue for configurable datastore beyond TSV. | SUCCESS | feature_implementation | Gate 5 | Agent A | `https://github.com/Daylily-Informatics/well-look-at-that`, `https://github.com/Daylily-Informatics/well-look-at-that/issues/1` |  | Public GitHub repo created and datastore issue opened. |

## Final Acceptance

- `.venv/bin/python -m pytest -q` -> 4 passed.
- `.venv/bin/well-look-at-that --json version` -> emitted `{"app": "well-look-at-that", "version": "0.1.0"}`.
- `.venv/bin/python -m build` -> built `well_look_at_that-0.1.0.tar.gz` and `well_look_at_that-0.1.0-py3-none-any.whl`.
- `find /Users/jmajor/projects/daylily/well-look-at-that -name '*.csv' -print` -> no files.
- All rows terminal: yes.
- Objective complete: yes.
