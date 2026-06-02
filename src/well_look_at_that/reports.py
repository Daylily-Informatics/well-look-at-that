from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from well_look_at_that.accounting import (
    accounting_snapshot,
    load_raw_token_events,
    write_accounting_outputs,
)
from well_look_at_that.model import (
    TOKEN_ACCOUNTING_RECONCILIATION_COLUMNS,
    TOKEN_THREAD_ROLLUP_COLUMNS,
    parse_time,
    safe_int,
)
from well_look_at_that.redaction import scan_paths
from well_look_at_that.tsv import read_tsv, write_tsv

ROLLUP_METRIC_COLUMNS = [
    "token_event_count",
    "thread_count",
    "session_segment_count",
    "distinct_turn_count",
    "observed_event_sum_tokens",
    "max_cumulative_tokens",
    "cumulative_delta_tokens",
    "unique_last_per_turn_tokens",
    "deduped_turn_tokens",
    "final_session_total_tokens",
    "final_thread_total_tokens",
    "repeated_last_usage_count",
    "repeated_cumulative_count",
    "cumulative_reset_count",
    "missing_turn_id_count",
    "inflation_factor_current_vs_max_cumulative",
    "inflation_factor_current_vs_delta",
    "warning_flags",
]


def _raw_events_in_window(output_root: Path, since) -> list[dict[str, str]]:
    return [
        row
        for row in load_raw_token_events(output_root)
        if (parse_time(row.get("timestamp")) or since) >= since
    ]


def _grain(rows: list[dict[str, Any]], name: str) -> list[dict[str, Any]]:
    return [row for row in rows if row.get("grain") == name]


def _write_report_pair(
    report_root: Path,
    run_id: str,
    window_label: str,
    slug: str,
    rows: list[dict[str, Any]],
    columns: list[str],
) -> None:
    write_tsv(report_root / f"{run_id}_{window_label}_{slug}.tsv", rows, columns)
    write_tsv(report_root / f"latest_{window_label}_{slug}.tsv", rows, columns)


def generate_reports(*, output_root: Path, since, window_label: str, run_id: str) -> dict[str, Any]:
    output_root = output_root.expanduser()
    accounting_counts = {}
    if not (output_root / "data" / "token_session_rollups.tsv").exists():
        accounting_counts = write_accounting_outputs(output_root=output_root, run_id=run_id)
    accounting = accounting_snapshot(output_root, since)
    raw_events = _raw_events_in_window(output_root, since)
    threads = read_tsv(output_root / "data" / "codex_threads.tsv")
    reconciliation = accounting["reconciliation"]

    thread_rollups = accounting["thread_rollups"]
    repo_rollups = _grain(reconciliation, "repo_workstream_outcome")
    workstream_rollups = _grain(reconciliation, "workstream")
    confidence = _grain(reconciliation, "attribution_confidence")
    daily = _grain(reconciliation, "day")
    weekly = _grain(reconciliation, "week")
    monthly = _grain(reconciliation, "month")

    report_root = output_root / "reports"
    _write_report_pair(
        report_root,
        run_id,
        window_label,
        "thread_rollups",
        thread_rollups,
        TOKEN_THREAD_ROLLUP_COLUMNS,
    )
    _write_report_pair(
        report_root,
        run_id,
        window_label,
        "repo_workstream_outcome_rollups",
        repo_rollups,
        ["github_repo", "workstream_label", "outcome_type", "attribution_confidence", *ROLLUP_METRIC_COLUMNS],
    )
    _write_report_pair(
        report_root,
        run_id,
        window_label,
        "workstream_rollups",
        workstream_rollups,
        ["workstream_label", "outcome_type", *ROLLUP_METRIC_COLUMNS],
    )
    _write_report_pair(
        report_root,
        run_id,
        window_label,
        "attribution_confidence_summary",
        confidence,
        ["attribution_confidence", *ROLLUP_METRIC_COLUMNS],
    )
    _write_report_pair(
        report_root,
        run_id,
        window_label,
        "daily_token_accounting",
        daily,
        TOKEN_ACCOUNTING_RECONCILIATION_COLUMNS,
    )
    _write_report_pair(
        report_root,
        run_id,
        window_label,
        "weekly_token_accounting",
        weekly,
        TOKEN_ACCOUNTING_RECONCILIATION_COLUMNS,
    )
    _write_report_pair(
        report_root,
        run_id,
        window_label,
        "monthly_token_accounting",
        monthly,
        TOKEN_ACCOUNTING_RECONCILIATION_COLUMNS,
    )

    observed_balances = sorted(
        {
            (row.get("timestamp", ""), row.get("credits_balance", ""), row.get("plan_type", ""))
            for row in raw_events
            if row.get("credits_balance")
        }
    )
    credit_rows = [
        {"timestamp": timestamp, "credits_balance": balance, "plan_type": plan}
        for timestamp, balance, plan in observed_balances
    ]
    _write_report_pair(
        report_root,
        run_id,
        window_label,
        "observed_credit_balances",
        credit_rows,
        ["timestamp", "credits_balance", "plan_type"],
    )

    markdown = _summary_markdown(
        window_label=window_label,
        run_id=run_id,
        raw_events=raw_events,
        threads=threads,
        thread_rollups=thread_rollups,
        repo_rollups=repo_rollups,
        confidence=confidence,
    )
    (report_root / f"{run_id}_{window_label}_summary.md").write_text(markdown, encoding="utf-8")
    (report_root / f"latest_{window_label}_summary.md").write_text(markdown, encoding="utf-8")
    return {
        "report_token_events": len(raw_events),
        "report_threads": len({row.get("thread_id") for row in raw_events if row.get("thread_id")}),
        "report_markdown": str(report_root / f"latest_{window_label}_summary.md"),
        "report_tsv_count": 16,
        **accounting_counts,
    }


def _summary_markdown(
    *,
    window_label: str,
    run_id: str,
    raw_events: list[dict[str, str]],
    threads: list[dict[str, str]],
    thread_rollups: list[dict[str, Any]],
    repo_rollups: list[dict[str, Any]],
    confidence: list[dict[str, Any]],
) -> str:
    observed_event_sum = sum(safe_int(row.get("total_tokens")) for row in raw_events)
    final_session_total = sum(safe_int(row.get("final_session_total_tokens")) for row in thread_rollups)
    cumulative_delta = sum(safe_int(row.get("cumulative_delta_tokens")) for row in thread_rollups)
    thread_ids = {row.get("thread_id") for row in raw_events if row.get("thread_id")}
    repo_counter = Counter(row.get("github_repo") or "(no github repo)" for row in raw_events)
    lines = [
        "# Codex Token Usage To GitHub Outcome Report",
        "",
        f"- Run: `{run_id}`",
        f"- Window: `{window_label}`",
        "- Raw grain: one `token_count` event",
        "- Accounting grain: session/rollout cumulative segment",
        "- Event-row token sums are diagnostic and likely inflated.",
        f"- Token events: {len(raw_events):,}",
        f"- Threads with token events: {len(thread_ids):,}",
        f"- Indexed thread records: {len(threads):,}",
        f"- Observed event-row sum tokens (diagnostic): {observed_event_sum:,}",
        f"- Final session total tokens (primary accounting approximation): {final_session_total:,}",
        f"- Cumulative delta tokens (time allocation basis): {cumulative_delta:,}",
        "- Tabular data format: TSV",
        "- Raw prompts and raw command text are excluded.",
        "",
        "## Top Repositories Or Workspaces",
        "",
    ]
    repo_totals: dict[str, dict[str, int]] = {}
    for row in repo_rollups:
        repo = row.get("github_repo") or "(no github repo)"
        dest = repo_totals.setdefault(repo, {"final": 0, "delta": 0, "observed": 0})
        dest["final"] += safe_int(row.get("final_session_total_tokens"))
        dest["delta"] += safe_int(row.get("cumulative_delta_tokens"))
        dest["observed"] += safe_int(row.get("observed_event_sum_tokens"))
    for repo, count in repo_counter.most_common(20):
        totals = repo_totals.get(repo, {"final": 0, "delta": 0, "observed": 0})
        lines.append(
            f"- `{repo}`: {totals['final']:,} final-session tokens; "
            f"{totals['delta']:,} delta tokens; {totals['observed']:,} observed event-sum tokens; "
            f"{count:,} events"
        )
    lines.extend(["", "## Top Outcome Rollups", ""])
    ranked = sorted(repo_rollups, key=lambda row: -safe_int(row.get("final_session_total_tokens")))[:20]
    for row in ranked:
        repo = row.get("github_repo") or "(no github repo)"
        lines.append(
            f"- `{repo}` / `{row.get('workstream_label')}` / `{row.get('outcome_type')}`: "
            f"{safe_int(row.get('final_session_total_tokens')):,} final-session tokens; "
            f"{safe_int(row.get('cumulative_delta_tokens')):,} delta tokens; "
            f"{safe_int(row.get('token_event_count')):,} events"
        )
    lines.extend(["", "## Attribution Confidence", ""])
    for row in confidence:
        lines.append(
            f"- `{row.get('attribution_confidence')}`: "
            f"{safe_int(row.get('final_session_total_tokens')):,} final-session tokens; "
            f"{safe_int(row.get('observed_event_sum_tokens')):,} observed event-sum tokens; "
            f"{safe_int(row.get('token_event_count')):,} events"
        )
    return "\n".join(lines) + "\n"


def validate_outputs(*, output_root: Path, run_id: str) -> dict[str, Any]:
    output_root = output_root.expanduser()
    generated = [
        path
        for root in ("data", "reports", "plots", "runs")
        for path in (output_root / root).glob("**/*")
        if path.is_file()
    ]
    csv_paths = [str(path) for path in generated if path.suffix.lower() == ".csv"]
    scan = scan_paths(generated)
    events = read_tsv(output_root / "data" / "codex_token_events.tsv")
    raw_events = read_tsv(output_root / "data" / "raw_token_events.tsv")
    session_rollups = read_tsv(output_root / "data" / "token_session_rollups.tsv")
    return {
        "run_id": run_id,
        "token_event_count": len(events),
        "raw_token_event_count": len(raw_events),
        "token_session_rollup_count": len(session_rollups),
        "csv_file_count": len(csv_paths),
        "csv_paths": csv_paths,
        "redaction_scan": scan,
        "status": "SUCCESS" if events and session_rollups and not csv_paths and scan["finding_count"] == 0 else "FAIL",
    }
