from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from well_look_at_that.model import parse_time, safe_int
from well_look_at_that.redaction import scan_paths
from well_look_at_that.tsv import read_tsv, write_tsv


def _events_in_window(output_root: Path, since) -> list[dict[str, str]]:
    rows = read_tsv(output_root / "data" / "codex_token_events.tsv")
    return [row for row in rows if (parse_time(row.get("timestamp")) or since) >= since]


def _sum_tokens(rows: list[dict[str, str]]) -> int:
    return sum(safe_int(row.get("total_tokens")) for row in rows)


def _group_rows(rows: list[dict[str, str]], keys: tuple[str, ...]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, ...], dict[str, Any]] = {}
    for row in rows:
        key = tuple(row.get(name, "") for name in keys)
        dest = grouped.setdefault(
            key,
            {name: row.get(name, "") for name in keys}
            | {
                "event_count": 0,
                "thread_count": set(),
                "total_tokens": 0,
                "input_tokens": 0,
                "cached_input_tokens": 0,
                "output_tokens": 0,
                "reasoning_output_tokens": 0,
                "first_event_at": "",
                "last_event_at": "",
            },
        )
        dest["event_count"] += 1
        dest["thread_count"].add(row.get("thread_id", ""))
        for token_col in (
            "total_tokens",
            "input_tokens",
            "cached_input_tokens",
            "output_tokens",
            "reasoning_output_tokens",
        ):
            dest[token_col] += safe_int(row.get(token_col))
        ts = row.get("timestamp", "")
        if ts and (not dest["first_event_at"] or ts < dest["first_event_at"]):
            dest["first_event_at"] = ts
        if ts and (not dest["last_event_at"] or ts > dest["last_event_at"]):
            dest["last_event_at"] = ts
    output = []
    for dest in grouped.values():
        dest["thread_count"] = len({item for item in dest["thread_count"] if item})
        output.append(dest)
    return sorted(output, key=lambda row: (-safe_int(row["total_tokens"]), str(row.get(keys[0], ""))))


def generate_reports(*, output_root: Path, since, window_label: str, run_id: str) -> dict[str, Any]:
    output_root = output_root.expanduser()
    events = _events_in_window(output_root, since)
    threads = read_tsv(output_root / "data" / "codex_threads.tsv")

    thread_rollups = _group_rows(events, ("thread_id", "github_repo", "workstream_label", "outcome_type", "attribution_confidence"))
    repo_rollups = _group_rows(events, ("github_repo", "workstream_label", "outcome_type", "attribution_confidence"))
    workstream_rollups = _group_rows(events, ("workstream_label", "outcome_type"))
    confidence = _group_rows(events, ("attribution_confidence",))

    rollup_cols = [
        "event_count",
        "thread_count",
        "total_tokens",
        "input_tokens",
        "cached_input_tokens",
        "output_tokens",
        "reasoning_output_tokens",
        "first_event_at",
        "last_event_at",
    ]
    report_root = output_root / "reports"
    write_tsv(
        report_root / f"{run_id}_{window_label}_thread_rollups.tsv",
        thread_rollups,
        ["thread_id", "github_repo", "workstream_label", "outcome_type", "attribution_confidence", *rollup_cols],
    )
    write_tsv(
        report_root / f"latest_{window_label}_thread_rollups.tsv",
        thread_rollups,
        ["thread_id", "github_repo", "workstream_label", "outcome_type", "attribution_confidence", *rollup_cols],
    )
    write_tsv(
        report_root / f"{run_id}_{window_label}_repo_workstream_outcome_rollups.tsv",
        repo_rollups,
        ["github_repo", "workstream_label", "outcome_type", "attribution_confidence", *rollup_cols],
    )
    write_tsv(
        report_root / f"latest_{window_label}_repo_workstream_outcome_rollups.tsv",
        repo_rollups,
        ["github_repo", "workstream_label", "outcome_type", "attribution_confidence", *rollup_cols],
    )
    write_tsv(
        report_root / f"{run_id}_{window_label}_workstream_rollups.tsv",
        workstream_rollups,
        ["workstream_label", "outcome_type", *rollup_cols],
    )
    write_tsv(
        report_root / f"latest_{window_label}_workstream_rollups.tsv",
        workstream_rollups,
        ["workstream_label", "outcome_type", *rollup_cols],
    )
    write_tsv(
        report_root / f"{run_id}_{window_label}_attribution_confidence_summary.tsv",
        confidence,
        ["attribution_confidence", *rollup_cols],
    )
    write_tsv(
        report_root / f"latest_{window_label}_attribution_confidence_summary.tsv",
        confidence,
        ["attribution_confidence", *rollup_cols],
    )

    repo_counter = Counter(row.get("github_repo") or "(no github repo)" for row in events)
    observed_balances = sorted(
        {
            (row.get("timestamp", ""), row.get("credits_balance", ""), row.get("plan_type", ""))
            for row in events
            if row.get("credits_balance")
        }
    )
    write_tsv(
        report_root / f"{run_id}_{window_label}_observed_credit_balances.tsv",
        [
            {"timestamp": timestamp, "credits_balance": balance, "plan_type": plan}
            for timestamp, balance, plan in observed_balances
        ],
        ["timestamp", "credits_balance", "plan_type"],
    )
    write_tsv(
        report_root / f"latest_{window_label}_observed_credit_balances.tsv",
        [
            {"timestamp": timestamp, "credits_balance": balance, "plan_type": plan}
            for timestamp, balance, plan in observed_balances
        ],
        ["timestamp", "credits_balance", "plan_type"],
    )

    markdown = _summary_markdown(
        window_label=window_label,
        run_id=run_id,
        events=events,
        threads=threads,
        repo_rollups=repo_rollups,
        confidence=confidence,
        repo_counter=repo_counter,
    )
    (report_root / f"{run_id}_{window_label}_summary.md").write_text(markdown, encoding="utf-8")
    (report_root / f"latest_{window_label}_summary.md").write_text(markdown, encoding="utf-8")
    return {
        "report_token_events": len(events),
        "report_threads": len({row.get("thread_id") for row in events if row.get("thread_id")}),
        "report_markdown": str(report_root / f"latest_{window_label}_summary.md"),
        "report_tsv_count": 9,
    }


def _summary_markdown(
    *,
    window_label: str,
    run_id: str,
    events: list[dict[str, str]],
    threads: list[dict[str, str]],
    repo_rollups: list[dict[str, Any]],
    confidence: list[dict[str, Any]],
    repo_counter: Counter[str],
) -> str:
    total_tokens = _sum_tokens(events)
    thread_ids = {row.get("thread_id") for row in events if row.get("thread_id")}
    lines = [
        "# Codex Token Usage To GitHub Outcome Report",
        "",
        f"- Run: `{run_id}`",
        f"- Window: `{window_label}`",
        f"- Native grain: one `token_count` event",
        f"- Token events: {len(events):,}",
        f"- Threads with token events: {len(thread_ids):,}",
        f"- Indexed thread records: {len(threads):,}",
        f"- Total tokens: {total_tokens:,}",
        "- Tabular data format: TSV",
        "- Raw prompts and raw command text are excluded.",
        "",
        "## Top Repositories Or Workspaces",
        "",
    ]
    for repo, count in repo_counter.most_common(20):
        tokens = sum(safe_int(row.get("total_tokens")) for row in events if (row.get("github_repo") or "(no github repo)") == repo)
        lines.append(f"- `{repo}`: {tokens:,} tokens; {count:,} events")
    lines.extend(["", "## Top Outcome Rollups", ""])
    for row in repo_rollups[:20]:
        repo = row.get("github_repo") or "(no github repo)"
        lines.append(
            f"- `{repo}` / `{row.get('workstream_label')}` / `{row.get('outcome_type')}`: "
            f"{safe_int(row.get('total_tokens')):,} tokens; {safe_int(row.get('event_count')):,} events"
        )
    lines.extend(["", "## Attribution Confidence", ""])
    for row in confidence:
        lines.append(
            f"- `{row.get('attribution_confidence')}`: {safe_int(row.get('total_tokens')):,} tokens; "
            f"{safe_int(row.get('event_count')):,} events"
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
    return {
        "run_id": run_id,
        "token_event_count": len(events),
        "csv_file_count": len(csv_paths),
        "csv_paths": csv_paths,
        "redaction_scan": scan,
        "status": "SUCCESS" if events and not csv_paths and scan["finding_count"] == 0 else "FAIL",
    }
