from __future__ import annotations

from pathlib import Path
from typing import Any

from well_look_at_that.accounting import write_accounting_outputs
from well_look_at_that.collectors.codex import collect_codex
from well_look_at_that.collectors.github import collect_github
from well_look_at_that.model import ensure_output_dirs, parse_window, run_id_now, window_label
from well_look_at_that.plots import generate_plots
from well_look_at_that.reports import generate_reports, validate_outputs
from well_look_at_that.tsv import append_tsv
from well_look_at_that.value import allocate_value

RUN_LOG_COLUMNS = [
    "run_id",
    "command",
    "window",
    "status",
    "token_event_count",
    "thread_count",
    "github_event_count",
    "report_count",
    "plot_count",
    "ledger_path",
]


def backfill_run(
    *,
    codex_home: Path,
    output_root: Path,
    since_spec: str,
    skip_github: bool,
    max_repos: int,
    repo_roots: list[Path] | None = None,
    no_reports: bool = False,
    no_plots: bool = False,
) -> dict[str, Any]:
    output_root = output_root.expanduser()
    ensure_output_dirs(output_root)
    run_id = run_id_now()
    since = parse_window(since_spec)
    label = window_label(since_spec)
    counts: dict[str, Any] = {"run_id": run_id, "since": since_spec}
    codex = collect_codex(
        codex_home=codex_home,
        output_root=output_root,
        since=since,
        run_id=run_id,
        repo_roots=repo_roots,
    )
    counts.update(codex["counts"])
    counts.update(write_accounting_outputs(output_root=output_root, run_id=run_id))
    if skip_github:
        counts["github_skipped"] = 1
    else:
        counts.update(collect_github(output_root=output_root, since=since, run_id=run_id, max_repos=max_repos))
    if not no_reports:
        counts.update(generate_reports(output_root=output_root, since=since, window_label=label, run_id=run_id))
    if not no_plots:
        counts.update(generate_plots(output_root=output_root, since=since, window_label=label, run_id=run_id))
    validation = validate_outputs(output_root=output_root, run_id=run_id)
    ledger_path = write_execution_ledger(output_root=output_root, run_id=run_id, counts=counts, validation=validation)
    status = validation["status"]
    append_tsv(
        output_root / "runs" / "run_log.tsv",
        [
            {
                "run_id": run_id,
                "command": "backfill",
                "window": since_spec,
                "status": status,
                "token_event_count": validation["token_event_count"],
                "thread_count": counts.get("threads_written", 0),
                "github_event_count": counts.get("github_events_written", 0),
                "report_count": counts.get("report_tsv_count", 0),
                "plot_count": counts.get("plot_count", 0),
                "ledger_path": str(ledger_path),
            }
        ],
        RUN_LOG_COLUMNS,
    )
    return {"run_id": run_id, "status": status, "counts": counts, "validation": validation, "ledger_path": str(ledger_path)}


def report_run(*, output_root: Path, window: str) -> dict[str, Any]:
    output_root = output_root.expanduser()
    ensure_output_dirs(output_root)
    run_id = run_id_now()
    since = parse_window(window)
    label = window_label(window)
    write_accounting_outputs(output_root=output_root, run_id=run_id)
    counts = generate_reports(output_root=output_root, since=since, window_label=label, run_id=run_id)
    validation = validate_outputs(output_root=output_root, run_id=run_id)
    return {"run_id": run_id, "status": validation["status"], "counts": counts, "validation": validation}


def plot_run(*, output_root: Path, window: str, entitlements: Path | None) -> dict[str, Any]:
    output_root = output_root.expanduser()
    ensure_output_dirs(output_root)
    run_id = run_id_now()
    since = parse_window(window)
    label = window_label(window)
    write_accounting_outputs(output_root=output_root, run_id=run_id)
    counts = generate_plots(output_root=output_root, since=since, window_label=label, run_id=run_id, entitlements=entitlements)
    validation = validate_outputs(output_root=output_root, run_id=run_id)
    return {"run_id": run_id, "status": validation["status"], "counts": counts, "validation": validation}


def allocate_value_run(*, output_root: Path, window: str, entitlements: Path) -> dict[str, Any]:
    output_root = output_root.expanduser()
    ensure_output_dirs(output_root)
    run_id = run_id_now()
    since = parse_window(window)
    write_accounting_outputs(output_root=output_root, run_id=run_id)
    counts = allocate_value(output_root=output_root, entitlements=entitlements, since=since, run_id=run_id)
    validation = validate_outputs(output_root=output_root, run_id=run_id)
    return {"run_id": run_id, "status": validation["status"], "counts": counts, "validation": validation}


def validate_run(*, output_root: Path) -> dict[str, Any]:
    output_root = output_root.expanduser()
    ensure_output_dirs(output_root)
    run_id = run_id_now()
    validation = validate_outputs(output_root=output_root, run_id=run_id)
    return {"run_id": run_id, "status": validation["status"], "validation": validation}


def write_execution_ledger(*, output_root: Path, run_id: str, counts: dict[str, Any], validation: dict[str, Any]) -> Path:
    rows = [
        (
            "A",
            "Codex Extractor",
            "sessions, archived_sessions, state_5.sqlite",
            "data/codex_token_events.tsv; data/codex_threads.tsv",
            "SUCCESS" if counts.get("token_events_written", 0) else "FAIL",
            f"{counts.get('token_events_written', 0)} token events; {counts.get('threads_written', 0)} threads",
        ),
        (
            "B",
            "GitHub Collector",
            "gh API for repos seen in Codex activity",
            "data/github_events.tsv",
            "SKIPPED" if counts.get("github_skipped") else "SUCCESS",
            f"{counts.get('github_events_written', 0)} GitHub events",
        ),
        (
            "C",
            "Attribution Joiner",
            "thread cwd, git origin, branch, SHA, repo/workstream labels",
            "reports/*rollups.tsv",
            "SUCCESS" if counts.get("report_tsv_count", 0) else "SKIPPED",
            "Attribution confidence retained in event and rollup rows",
        ),
        (
            "D",
            "Entitlement Collector",
            "config/token_entitlements.tsv when supplied",
            "plots/*cumulative_burnup_entitlements.html",
            "SUCCESS" if counts.get("plot_count", 0) else "SKIPPED",
            "No entitlement limits inferred from rate-limit percentages",
        ),
        (
            "E",
            "Plot Builder",
            "TSV reports and event rows",
            "plots/*.html",
            "SUCCESS" if counts.get("plot_count", 0) else "SKIPPED",
            f"{counts.get('plot_count', 0)} plots",
        ),
        (
            "F",
            "Validator",
            "generated TSV/Markdown/HTML artifacts",
            "runs/run_log.tsv",
            validation.get("status", "FAIL"),
            f"csv_file_count={validation.get('csv_file_count')}; redaction_findings={validation.get('redaction_scan', {}).get('finding_count')}",
        ),
    ]
    ledger = output_root / "runs" / f"{run_id}_execution_ledger.md"
    lines = [
        "# Codex Usage To GitHub Outcome Execution Ledger",
        "",
        f"- Run: `{run_id}`",
        f"- Status: `{validation.get('status', 'FAIL')}`",
        "- Tabular persistence: TSV",
        "",
        "| row_id | agent | inputs | outputs | state | validation |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row_id, agent, inputs, outputs, state, note in rows:
        lines.append(f"| {row_id} | {agent} | {inputs} | {outputs} | {state} | {note} |")
    lines.append("")
    ledger.write_text("\n".join(lines), encoding="utf-8")
    return ledger
