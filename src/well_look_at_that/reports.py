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
    "unique_last_per_thread_turn_tokens",
    "unique_last_per_session_turn_tokens",
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
    final_thread_total = sum(safe_int(row.get("final_thread_total_tokens")) for row in thread_rollups)
    thread_turn_total = sum(safe_int(row.get("unique_last_per_thread_turn_tokens")) for row in thread_rollups)
    session_turn_total = sum(safe_int(row.get("unique_last_per_session_turn_tokens")) for row in thread_rollups)
    thread_ids = {row.get("thread_id") for row in raw_events if row.get("thread_id")}
    repo_counter = Counter(row.get("github_repo") or "(no github repo)" for row in raw_events)
    lines = [
        "# Codex Token Usage To GitHub Outcome Report",
        "",
        f"- Run: `{run_id}`",
        f"- Window: `{window_label}`",
        "- Raw grain: one `token_count` event",
        "- Accounting grain: session/rollout cumulative segment",
        "- Primary usage basis: final session cumulative totals and cumulative positive deltas.",
        "- Event-row token sums are diagnostic and likely inflated.",
        "- Logical-thread max cumulative totals are diagnostic and can undercount resumed or multi-segment threads.",
        "- Turn estimates are diagnostic, not billing truth.",
        f"- Token events: {len(raw_events):,}",
        f"- Threads with token events: {len(thread_ids):,}",
        f"- Indexed thread records: {len(threads):,}",
        f"- Observed event-row sum tokens (diagnostic): {observed_event_sum:,}",
        f"- Final session total tokens (primary accounting approximation): {final_session_total:,}",
        f"- Cumulative delta tokens (time allocation basis): {cumulative_delta:,}",
        f"- Final thread max cumulative tokens (diagnostic): {final_thread_total:,}",
        f"- Unique last per thread/turn tokens (diagnostic): {thread_turn_total:,}",
        f"- Unique last per session/turn tokens (diagnostic): {session_turn_total:,}",
        "- Deprecated `unique_last_per_turn_tokens` is a session-turn compatibility alias.",
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
    event_accounting = read_tsv(output_root / "data" / "token_event_accounting.tsv")
    turn_estimates = read_tsv(output_root / "data" / "token_turn_estimates.tsv")
    session_rollups = read_tsv(output_root / "data" / "token_session_rollups.tsv")
    thread_rollups = read_tsv(output_root / "data" / "token_thread_rollups.tsv")
    reconciliation = read_tsv(output_root / "data" / "token_accounting_reconciliation.tsv")
    validation_errors = _accounting_validation_errors(
        raw_events=raw_events,
        events=events,
        event_accounting=event_accounting,
        turn_estimates=turn_estimates,
        session_rollups=session_rollups,
        thread_rollups=thread_rollups,
        reconciliation=reconciliation,
    )
    status = (
        "SUCCESS"
        if events
        and raw_events
        and session_rollups
        and not csv_paths
        and scan["finding_count"] == 0
        and not validation_errors
        else "FAIL"
    )
    return {
        "run_id": run_id,
        "token_event_count": len(events),
        "raw_token_event_count": len(raw_events),
        "token_event_accounting_count": len(event_accounting),
        "token_turn_estimate_count": len(turn_estimates),
        "token_session_rollup_count": len(session_rollups),
        "token_thread_rollup_count": len(thread_rollups),
        "token_reconciliation_count": len(reconciliation),
        "csv_file_count": len(csv_paths),
        "csv_paths": csv_paths,
        "redaction_scan": scan,
        "validation_error_count": len(validation_errors),
        "validation_errors": validation_errors,
        "status": status,
    }


def _accounting_validation_errors(
    *,
    raw_events: list[dict[str, str]],
    events: list[dict[str, str]],
    event_accounting: list[dict[str, str]],
    turn_estimates: list[dict[str, str]],
    session_rollups: list[dict[str, str]],
    thread_rollups: list[dict[str, str]],
    reconciliation: list[dict[str, str]],
) -> list[str]:
    errors: list[str] = []
    if len(raw_events) != len(events):
        errors.append("raw_token_events.tsv and codex_token_events.tsv row counts differ")
    if len(event_accounting) != len(raw_events):
        errors.append("token_event_accounting.tsv must have one row per raw token event")
    raw_ids = {row.get("event_id") for row in raw_events if row.get("event_id")}
    accounting_ids = {row.get("event_id") for row in event_accounting if row.get("event_id")}
    if raw_ids and raw_ids != accounting_ids:
        errors.append("token_event_accounting.tsv event ids do not match raw token events")

    included_sessions = [row for row in session_rollups if safe_int(row.get("accounting_included"))]
    session_final = sum(safe_int(row.get("final_session_total_tokens")) for row in included_sessions)
    session_delta = sum(safe_int(row.get("cumulative_delta_tokens")) for row in included_sessions)
    thread_final = sum(safe_int(row.get("final_session_total_tokens")) for row in thread_rollups)
    thread_delta = sum(safe_int(row.get("cumulative_delta_tokens")) for row in thread_rollups)
    if session_final != thread_final:
        errors.append("thread final_session_total_tokens do not reconcile to included sessions")
    if session_delta != thread_delta:
        errors.append("thread cumulative_delta_tokens do not reconcile to included sessions")

    for row in session_rollups:
        if (
            safe_int(row.get("accounting_included"))
            and not safe_int(row.get("cumulative_reset_count"))
            and safe_int(row.get("final_session_total_tokens")) != safe_int(row.get("cumulative_delta_tokens"))
        ):
            errors.append(f"monotonic session delta mismatch: {row.get('session_segment_id')}")
            break

    for row in thread_rollups:
        if safe_int(row.get("session_segment_count")) > 1 and safe_int(row.get("final_thread_total_tokens")) == safe_int(
            row.get("final_session_total_tokens")
        ):
            errors.append(f"multi-segment thread max duplicates session total: {row.get('thread_id')}")
            break
    thread_errors = _thread_rollup_validation_errors(raw_events, session_rollups, thread_rollups)
    errors.extend(thread_errors)

    for row in reconciliation:
        if row.get("grain") == "thread" and safe_int(row.get("token_event_count")) and not safe_int(
            row.get("session_segment_count")
        ):
            errors.append(f"thread reconciliation missing session_segment_count: {row.get('group_key')}")
            break

    for grain in ("day", "week", "month"):
        grain_rows = [row for row in reconciliation if row.get("grain") == grain]
        if raw_events and grain_rows and not sum(safe_int(row.get("token_event_count")) for row in grain_rows):
            errors.append(f"{grain} reconciliation token_event_count is zero")
        if sum(safe_int(row.get("token_event_count")) for row in grain_rows) != len(raw_events):
            errors.append(f"{grain} reconciliation token_event_count does not reconcile to raw events")
        if sum(safe_int(row.get("cumulative_delta_tokens")) for row in grain_rows) != sum(
            safe_int(row.get("cumulative_delta_tokens")) for row in event_accounting
        ):
            errors.append(f"{grain} reconciliation cumulative_delta_tokens does not reconcile")

    required_columns = (
        "unique_last_per_thread_turn_tokens",
        "unique_last_per_session_turn_tokens",
    )
    for name, rows in (
        ("token_turn_estimates.tsv", turn_estimates),
        ("token_thread_rollups.tsv", thread_rollups),
        ("token_accounting_reconciliation.tsv", reconciliation),
    ):
        if rows and not all(column in rows[0] for column in required_columns):
            errors.append(f"{name} missing explicit unique-last columns")
    return errors


def _thread_rollup_validation_errors(
    raw_events: list[dict[str, str]],
    session_rollups: list[dict[str, str]],
    thread_rollups: list[dict[str, str]],
) -> list[str]:
    errors: list[str] = []
    raw_by_thread: dict[str, list[dict[str, str]]] = {}
    sessions_by_thread: dict[str, list[dict[str, str]]] = {}
    for row in raw_events:
        raw_by_thread.setdefault(row.get("thread_id", ""), []).append(row)
    for row in session_rollups:
        sessions_by_thread.setdefault(row.get("thread_id", ""), []).append(row)

    for row in thread_rollups:
        thread_id = row.get("thread_id", "")
        raw_rows = raw_by_thread.get(thread_id, [])
        session_rows = sessions_by_thread.get(thread_id, [])
        if not raw_rows:
            continue
        expected_segments = len({event.get("session_segment_id", "") for event in raw_rows if event.get("session_segment_id")})
        expected_thread_max = max((safe_int(event.get("cumulative_total_tokens")) for event in raw_rows), default=0)
        expected_distinct_turns = len({(event.get("thread_id", ""), event.get("turn_id", "")) for event in raw_rows if event.get("turn_id")})
        expected_missing_turns = sum(1 for event in raw_rows if not event.get("turn_id"))
        expected_repeated_last = _repeated_usage_count(raw_rows, "last_token_usage_hash")
        expected_repeated_cumulative = _repeated_usage_count(raw_rows, "total_token_usage_hash")
        expected_thread_turn = _unique_last_per_thread_turn_tokens(raw_rows)
        expected_session_turn = _unique_last_per_session_turn_tokens(raw_rows)
        expected_session_final = sum(
            safe_int(session.get("final_session_total_tokens"))
            for session in session_rows
            if safe_int(session.get("accounting_included"))
        )
        expected_delta = sum(
            safe_int(session.get("cumulative_delta_tokens"))
            for session in session_rows
            if safe_int(session.get("accounting_included"))
        )
        checks = (
            ("session_segment_count", expected_segments),
            ("final_thread_total_tokens", expected_thread_max),
            ("max_cumulative_tokens", expected_thread_max),
            ("distinct_turn_count", expected_distinct_turns),
            ("missing_turn_id_count", expected_missing_turns),
            ("repeated_last_usage_count", expected_repeated_last),
            ("repeated_cumulative_count", expected_repeated_cumulative),
            ("unique_last_per_thread_turn_tokens", expected_thread_turn),
            ("unique_last_per_session_turn_tokens", expected_session_turn),
            ("final_session_total_tokens", expected_session_final),
            ("cumulative_delta_tokens", expected_delta),
        )
        for column, expected in checks:
            if safe_int(row.get(column)) != expected:
                errors.append(f"thread rollup {column} mismatch for {thread_id}")
                return errors
    return errors


def _turn_key(row: dict[str, str]) -> str:
    return row.get("turn_id") or row.get("content_event_hash") or row.get("event_id") or ""


def _unique_last_per_thread_turn_tokens(rows: list[dict[str, str]]) -> int:
    seen: set[tuple[str, str, str]] = set()
    total = 0
    for row in sorted(rows, key=lambda item: (item.get("timestamp", ""), safe_int(item.get("line_number")))):
        last_hash = row.get("last_token_usage_hash") or row.get("event_id", "")
        key = (row.get("thread_id", ""), _turn_key(row), last_hash)
        if key in seen:
            continue
        seen.add(key)
        total += safe_int(row.get("total_tokens"))
    return total


def _unique_last_per_session_turn_tokens(rows: list[dict[str, str]]) -> int:
    seen: set[tuple[str, str, str, str]] = set()
    total = 0
    for row in sorted(rows, key=lambda item: (item.get("timestamp", ""), safe_int(item.get("line_number")))):
        last_hash = row.get("last_token_usage_hash") or row.get("event_id", "")
        key = (row.get("thread_id", ""), row.get("session_segment_id", ""), _turn_key(row), last_hash)
        if key in seen:
            continue
        seen.add(key)
        total += safe_int(row.get("total_tokens"))
    return total


def _repeated_usage_count(rows: list[dict[str, str]], column: str) -> int:
    counts: dict[tuple[str, str], int] = {}
    for row in rows:
        value = row.get(column)
        if value:
            key = (row.get("thread_id", ""), value)
            counts[key] = counts.get(key, 0) + 1
    return sum(max(0, count - 1) for count in counts.values())
