from __future__ import annotations

import datetime as dt
from collections import defaultdict
from pathlib import Path
from typing import Any

from well_look_at_that.model import (
    TOKEN_ACCOUNTING_RECONCILIATION_COLUMNS,
    TOKEN_EVENT_ACCOUNTING_COLUMNS,
    TOKEN_SESSION_ROLLUP_COLUMNS,
    TOKEN_THREAD_ROLLUP_COLUMNS,
    TOKEN_TURN_ESTIMATE_COLUMNS,
    parse_time,
    safe_int,
    sha1_text,
)
from well_look_at_that.tsv import read_tsv, write_tsv

TOKEN_PARTS = (
    ("cumulative_input_tokens", "delta_input_tokens"),
    ("cumulative_cached_input_tokens", "delta_cached_input_tokens"),
    ("cumulative_output_tokens", "delta_output_tokens"),
    ("cumulative_reasoning_output_tokens", "delta_reasoning_output_tokens"),
)


def load_raw_token_events(output_root: Path) -> list[dict[str, str]]:
    output_root = output_root.expanduser()
    raw_path = output_root / "data" / "raw_token_events.tsv"
    legacy_path = output_root / "data" / "codex_token_events.tsv"
    rows = read_tsv(raw_path if raw_path.exists() else legacy_path)
    return [_normalize_raw_row(row) for row in rows]


def write_accounting_outputs(*, output_root: Path, run_id: str) -> dict[str, Any]:
    output_root = output_root.expanduser()
    raw_rows = load_raw_token_events(output_root)
    accounting = build_accounting(raw_rows)
    data_root = output_root / "data"
    write_tsv(
        data_root / "token_event_accounting.tsv",
        accounting["event_accounting"],
        TOKEN_EVENT_ACCOUNTING_COLUMNS,
    )
    write_tsv(
        data_root / "token_turn_estimates.tsv",
        accounting["turn_estimates"],
        TOKEN_TURN_ESTIMATE_COLUMNS,
    )
    write_tsv(
        data_root / "token_session_rollups.tsv",
        accounting["session_rollups"],
        TOKEN_SESSION_ROLLUP_COLUMNS,
    )
    write_tsv(
        data_root / "token_thread_rollups.tsv",
        accounting["thread_rollups"],
        TOKEN_THREAD_ROLLUP_COLUMNS,
    )
    write_tsv(
        data_root / "token_accounting_reconciliation.tsv",
        accounting["reconciliation"],
        TOKEN_ACCOUNTING_RECONCILIATION_COLUMNS,
    )
    return {
        "accounting_run_id": run_id,
        "raw_token_events_seen": len(raw_rows),
        "token_event_accounting_rows": len(accounting["event_accounting"]),
        "token_turn_estimate_rows": len(accounting["turn_estimates"]),
        "token_session_rollup_rows": len(accounting["session_rollups"]),
        "token_thread_rollup_rows": len(accounting["thread_rollups"]),
        "token_reconciliation_rows": len(accounting["reconciliation"]),
    }


def accounting_snapshot(output_root: Path, since=None) -> dict[str, list[dict[str, Any]]]:
    rows = load_raw_token_events(output_root)
    if since is not None:
        rows = [row for row in rows if (parse_time(row.get("timestamp")) or since) >= since]
    return build_accounting(rows)


def build_accounting(raw_rows: list[dict[str, str]]) -> dict[str, list[dict[str, Any]]]:
    segments = _segments(raw_rows)
    inclusion = _segment_inclusion(segments)
    event_accounting: list[dict[str, Any]] = []
    turn_estimates: list[dict[str, Any]] = []
    session_rollups: list[dict[str, Any]] = []

    for segment_id, rows in sorted(segments.items()):
        rows = _sort_events(rows)
        included, duplicate_of = inclusion[segment_id]
        segment_events, session, turns = _rollup_segment(segment_id, rows, included, duplicate_of)
        event_accounting.extend(segment_events)
        session_rollups.append(session)
        turn_estimates.extend(turns)

    turn_estimates = _annotate_thread_turn_estimates(turn_estimates)
    thread_rollups = _thread_rollups(raw_rows, session_rollups)
    reconciliation = _reconciliation(raw_rows, session_rollups, thread_rollups, event_accounting)
    return {
        "event_accounting": event_accounting,
        "turn_estimates": turn_estimates,
        "session_rollups": session_rollups,
        "thread_rollups": thread_rollups,
        "reconciliation": reconciliation,
    }


def _normalize_raw_row(row: dict[str, str]) -> dict[str, str]:
    normalized = dict(row)
    source_path = normalized.get("source_path") or normalized.get("rollout_path") or ""
    thread_id = normalized.get("thread_id") or ""
    normalized["source_path"] = source_path
    normalized["rollout_path"] = normalized.get("rollout_path") or source_path
    normalized["session_segment_id"] = normalized.get("session_segment_id") or sha1_text(
        f"{thread_id}\t{source_path}"
    )
    if "is_active_session" not in normalized:
        normalized["is_active_session"] = "1" if "/sessions/" in source_path else "0"
    if "is_archived_session" not in normalized:
        normalized["is_archived_session"] = "1" if "/archived_sessions/" in source_path else "0"
    normalized["last_token_usage_hash"] = normalized.get("last_token_usage_hash") or _usage_hash(
        normalized,
        ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_output_tokens", "total_tokens"),
    )
    normalized["total_token_usage_hash"] = normalized.get("total_token_usage_hash") or _usage_hash(
        normalized,
        (
            "cumulative_input_tokens",
            "cumulative_cached_input_tokens",
            "cumulative_output_tokens",
            "cumulative_reasoning_output_tokens",
            "cumulative_total_tokens",
        ),
    )
    normalized["token_count_payload_hash"] = normalized.get("token_count_payload_hash") or sha1_text(
        "|".join(
            [
                normalized.get("last_token_usage_hash", ""),
                normalized.get("total_token_usage_hash", ""),
                normalized.get("timestamp", ""),
            ]
        )
    )
    normalized["content_event_hash"] = normalized.get("content_event_hash") or sha1_text(
        "|".join(
            [
                thread_id,
                normalized.get("turn_id", ""),
                normalized.get("last_token_usage_hash", ""),
                normalized.get("total_token_usage_hash", ""),
            ]
        )
    )
    return normalized


def _usage_hash(row: dict[str, str], keys: tuple[str, ...]) -> str:
    values = [str(safe_int(row.get(key))) for key in keys]
    if not any(safe_int(value) for value in values):
        return ""
    return sha1_text("|".join(values))


def _segments(rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[row.get("session_segment_id") or ""].append(row)
    return {key: value for key, value in grouped.items() if key}


def _sort_events(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return sorted(rows, key=lambda row: (row.get("timestamp", ""), safe_int(row.get("line_number"))))


def _segment_inclusion(
    segments: dict[str, list[dict[str, str]]],
) -> dict[str, tuple[int, str]]:
    signatures: dict[tuple[str, str], list[str]] = defaultdict(list)
    for segment_id, rows in segments.items():
        ordered = _sort_events(rows)
        thread_id = ordered[0].get("thread_id", "") if ordered else ""
        signature = sha1_text(
            "\n".join(row.get("token_count_payload_hash") or row.get("content_event_hash") or row.get("event_id", "") for row in ordered)
        )
        signatures[(thread_id, signature)].append(segment_id)

    inclusion = dict.fromkeys(segments, (1, ""))
    for segment_ids in signatures.values():
        if len(segment_ids) <= 1:
            continue
        winner = sorted(segment_ids, key=lambda item: (_archive_rank(segments[item]), _source_path(segments[item])))[0]
        for segment_id in segment_ids:
            if segment_id != winner:
                inclusion[segment_id] = (0, winner)
    return inclusion


def _archive_rank(rows: list[dict[str, str]]) -> int:
    if any(safe_int(row.get("is_active_session")) for row in rows):
        return 0
    if any(safe_int(row.get("is_archived_session")) for row in rows):
        return 1
    return 2


def _source_path(rows: list[dict[str, str]]) -> str:
    return rows[0].get("source_path") or rows[0].get("rollout_path") or "" if rows else ""


def _rollup_segment(
    segment_id: str,
    rows: list[dict[str, str]],
    included: int,
    duplicate_of: str,
) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    first = rows[0] if rows else {}
    observed = sum(safe_int(row.get("total_tokens")) for row in rows)
    cumulative_values = [safe_int(row.get("cumulative_total_tokens")) for row in rows]
    max_cumulative = max(cumulative_values, default=0)
    final_session = max_cumulative if included else 0
    distinct_turns = {row.get("turn_id") for row in rows if row.get("turn_id")}
    missing_turn_count = sum(1 for row in rows if not row.get("turn_id"))
    repeated_last = _repeated_hash_count(rows, "last_token_usage_hash")
    repeated_cumulative = _repeated_hash_count(rows, "total_token_usage_hash")
    zero_cumulative = sum(1 for row in rows if safe_int(row.get("cumulative_total_tokens")) == 0)
    warning_flags: set[str] = set()
    if duplicate_of:
        warning_flags.add("duplicate_segment_excluded")
    if missing_turn_count:
        warning_flags.add("missing_turn_id")
    if any(safe_int(row.get("missing_total_token_usage")) for row in rows):
        warning_flags.add("missing_total_token_usage")
    if repeated_last:
        warning_flags.add("repeated_last_usage")
    if repeated_cumulative:
        warning_flags.add("repeated_cumulative")

    event_rows: list[dict[str, Any]] = []
    previous_total = 0
    previous_parts = {column: 0 for column, _ in TOKEN_PARTS}
    cumulative_delta = 0
    reset_count = 0
    turn_groups: dict[tuple[str, str], dict[str, Any]] = {}

    for row in rows:
        current_total = safe_int(row.get("cumulative_total_tokens"))
        if current_total >= previous_total:
            delta_total = current_total - previous_total
            reset = 0
        else:
            delta_total = current_total
            reset = 1
            reset_count += 1
            warning_flags.add("cumulative_reset")
        previous_total = current_total
        if not included:
            delta_total = 0

        deltas: dict[str, int] = {}
        for cumulative_col, delta_col in TOKEN_PARTS:
            current = safe_int(row.get(cumulative_col))
            previous = previous_parts[cumulative_col]
            if current >= previous:
                value = current - previous
            else:
                value = current
            previous_parts[cumulative_col] = current
            deltas[delta_col] = value if included else 0

        cumulative_delta += delta_total
        event_rows.append(
            {
                "event_id": row.get("event_id", ""),
                "session_segment_id": segment_id,
                "thread_id": row.get("thread_id", ""),
                "turn_id": row.get("turn_id", ""),
                "timestamp": row.get("timestamp", ""),
                "line_number": row.get("line_number", ""),
                "github_repo": row.get("github_repo", ""),
                "workstream_label": row.get("workstream_label", ""),
                "outcome_type": row.get("outcome_type", ""),
                "attribution_confidence": row.get("attribution_confidence", ""),
                "observed_event_sum_tokens": safe_int(row.get("total_tokens")),
                "cumulative_delta_tokens": delta_total,
                "accounting_included": included,
                "cumulative_reset": reset,
                "warning_flags": ";".join(sorted(warning_flags)),
                "last_token_usage_hash": row.get("last_token_usage_hash", ""),
                "total_token_usage_hash": row.get("total_token_usage_hash", ""),
                **deltas,
            }
        )

        turn_key = row.get("turn_id") or row.get("content_event_hash") or row.get("event_id", "")
        last_hash = row.get("last_token_usage_hash") or row.get("event_id", "")
        group_key = (turn_key, last_hash)
        turn = turn_groups.setdefault(
            group_key,
            {
                "session_segment_id": segment_id,
                "thread_id": row.get("thread_id", ""),
                "turn_id": row.get("turn_id", ""),
                "turn_group_key": sha1_text("|".join(group_key)),
                "github_repo": row.get("github_repo", ""),
                "workstream_label": row.get("workstream_label", ""),
                "outcome_type": row.get("outcome_type", ""),
                "attribution_confidence": row.get("attribution_confidence", ""),
                "first_event_at": row.get("timestamp", ""),
                "last_event_at": row.get("timestamp", ""),
                "token_event_count": 0,
                "observed_event_sum_tokens": 0,
                "unique_last_per_thread_turn_tokens": 0,
                "unique_last_per_session_turn_tokens": safe_int(row.get("total_tokens")),
                "unique_last_per_turn_tokens": safe_int(row.get("total_tokens")),
                "deduped_turn_tokens": safe_int(row.get("total_tokens")),
                "repeated_last_usage_count": 0,
                "missing_turn_id_count": 0,
            },
        )
        turn["token_event_count"] += 1
        turn["observed_event_sum_tokens"] += safe_int(row.get("total_tokens"))
        if not row.get("turn_id"):
            turn["missing_turn_id_count"] += 1
        if row.get("timestamp", "") < turn["first_event_at"]:
            turn["first_event_at"] = row.get("timestamp", "")
        if row.get("timestamp", "") > turn["last_event_at"]:
            turn["last_event_at"] = row.get("timestamp", "")

    for turn in turn_groups.values():
        turn["repeated_last_usage_count"] = max(
            0,
            safe_int(turn["token_event_count"]) - 1,
        )

    unique_last = sum(safe_int(turn["unique_last_per_session_turn_tokens"]) for turn in turn_groups.values())
    session = {
        "session_segment_id": segment_id,
        "thread_id": first.get("thread_id", ""),
        "source_path": first.get("source_path", ""),
        "rollout_path": first.get("rollout_path", ""),
        "is_active_session": 1 if any(safe_int(row.get("is_active_session")) for row in rows) else 0,
        "is_archived_session": 1 if any(safe_int(row.get("is_archived_session")) for row in rows) else 0,
        "accounting_included": included,
        "duplicate_segment_of": duplicate_of,
        "github_repo": first.get("github_repo", ""),
        "workstream_label": first.get("workstream_label", ""),
        "outcome_type": first.get("outcome_type", ""),
        "attribution_confidence": first.get("attribution_confidence", ""),
        "first_event_at": min((row.get("timestamp", "") for row in rows if row.get("timestamp")), default=""),
        "last_event_at": max((row.get("timestamp", "") for row in rows if row.get("timestamp")), default=""),
        "token_event_count": len(rows),
        "distinct_turn_count": len(distinct_turns),
        "observed_event_sum_tokens": observed,
        "max_cumulative_tokens": max_cumulative,
        "final_session_total_tokens": final_session,
        "cumulative_delta_tokens": cumulative_delta,
        "unique_last_per_session_turn_tokens": unique_last,
        "unique_last_per_turn_tokens": unique_last,
        "deduped_turn_tokens": unique_last,
        "repeated_last_usage_count": repeated_last,
        "repeated_cumulative_count": repeated_cumulative,
        "cumulative_reset_count": reset_count,
        "missing_turn_id_count": missing_turn_count,
        "zero_cumulative_event_count": zero_cumulative,
        "inflation_factor_current_vs_max_cumulative": _factor(observed, max_cumulative),
        "inflation_factor_current_vs_delta": _factor(observed, cumulative_delta),
        "warning_flags": ";".join(sorted(warning_flags)),
    }
    return event_rows, session, list(turn_groups.values())


def _repeated_hash_count(rows: list[dict[str, str]], column: str) -> int:
    hashes = [row.get(column, "") for row in rows if row.get(column)]
    return max(0, len(hashes) - len(set(hashes)))


def _annotate_thread_turn_estimates(turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str]] = set()
    output: list[dict[str, Any]] = []
    for turn in sorted(
        turns,
        key=lambda row: (
            row.get("thread_id", ""),
            row.get("first_event_at", ""),
            row.get("session_segment_id", ""),
            row.get("turn_group_key", ""),
        ),
    ):
        row = dict(turn)
        key = (
            str(row.get("thread_id") or ""),
            str(row.get("turn_id") or row.get("turn_group_key") or ""),
            str(row.get("turn_group_key") or ""),
        )
        if key in seen:
            row["unique_last_per_thread_turn_tokens"] = 0
        else:
            seen.add(key)
            row["unique_last_per_thread_turn_tokens"] = safe_int(
                row.get("unique_last_per_session_turn_tokens")
            )
        row["unique_last_per_turn_tokens"] = row["unique_last_per_session_turn_tokens"]
        row["deduped_turn_tokens"] = row["unique_last_per_session_turn_tokens"]
        output.append(row)
    return output


def _thread_rollups(
    raw_rows: list[dict[str, str]],
    session_rollups: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows_by_thread: dict[str, list[dict[str, str]]] = defaultdict(list)
    sessions_by_thread: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in raw_rows:
        rows_by_thread[str(row.get("thread_id") or "")].append(row)
    for row in session_rollups:
        sessions_by_thread[str(row.get("thread_id") or "")].append(row)

    output = []
    for thread_id, rows in rows_by_thread.items():
        sessions = sessions_by_thread.get(thread_id, [])
        first = _first_row(rows, sessions)
        warnings = _warning_flags(rows, sessions)
        session_count = len({row.get("session_segment_id", "") for row in rows if row.get("session_segment_id")})
        included_sessions = [row for row in sessions if safe_int(row.get("accounting_included"))]
        active_count = sum(1 for row in sessions if safe_int(row.get("is_active_session")))
        archived_count = sum(1 for row in sessions if safe_int(row.get("is_archived_session")))
        active_archived_overlap = 1 if active_count and archived_count else 0
        if active_archived_overlap:
            warnings.add("active_archived_overlap")
        if session_count > 1:
            warnings.add("multi_segment_thread")
        excluded_duplicates = sum(1 for row in sessions if not safe_int(row.get("accounting_included")))
        max_cumulative = _thread_max_cumulative(rows)
        session_unique = sum(safe_int(row.get("unique_last_per_session_turn_tokens")) for row in sessions)
        thread_unique = _unique_last_per_thread_turn_tokens(rows)
        dest = {
            "thread_id": thread_id,
            "github_repo": first.get("github_repo", ""),
            "workstream_label": first.get("workstream_label", ""),
            "outcome_type": first.get("outcome_type", ""),
            "attribution_confidence": first.get("attribution_confidence", ""),
            "first_event_at": min((row.get("timestamp", "") for row in rows if row.get("timestamp")), default=""),
            "last_event_at": max((row.get("timestamp", "") for row in rows if row.get("timestamp")), default=""),
            "token_event_count": len(rows),
            "distinct_turn_count": _distinct_turn_count(rows),
            "session_segment_count": session_count,
            "included_session_segment_count": len(included_sessions),
            "excluded_duplicate_session_segment_count": excluded_duplicates,
            "active_session_segment_count": active_count,
            "archived_session_segment_count": archived_count,
            "active_archived_overlap": active_archived_overlap,
            "observed_event_sum_tokens": sum(safe_int(row.get("total_tokens")) for row in rows),
            "max_cumulative_tokens": max_cumulative,
            "final_session_total_tokens": sum(safe_int(row.get("final_session_total_tokens")) for row in included_sessions),
            "final_thread_total_tokens": max_cumulative,
            "cumulative_delta_tokens": sum(safe_int(row.get("cumulative_delta_tokens")) for row in included_sessions),
            "unique_last_per_thread_turn_tokens": thread_unique,
            "unique_last_per_session_turn_tokens": session_unique,
            "unique_last_per_turn_tokens": session_unique,
            "deduped_turn_tokens": session_unique,
            "repeated_last_usage_count": _repeated_usage_count(rows, "last_token_usage_hash"),
            "repeated_cumulative_count": _repeated_usage_count(rows, "total_token_usage_hash"),
            "cumulative_reset_count": sum(safe_int(row.get("cumulative_reset_count")) for row in sessions),
            "missing_turn_id_count": sum(1 for row in rows if not row.get("turn_id")),
            "warning_flags": ";".join(sorted(warnings)),
        }
        dest["inflation_factor_current_vs_max_cumulative"] = _factor(
            safe_int(dest["observed_event_sum_tokens"]),
            safe_int(dest["max_cumulative_tokens"]),
        )
        dest["inflation_factor_current_vs_delta"] = _factor(
            safe_int(dest["observed_event_sum_tokens"]),
            safe_int(dest["cumulative_delta_tokens"]),
        )
        output.append(dest)
    return sorted(output, key=lambda row: (-safe_int(row["final_session_total_tokens"]), row["thread_id"]))


def _first_row(rows: list[dict[str, str]], session_rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    for row in sorted(rows, key=lambda item: (item.get("timestamp", ""), safe_int(item.get("line_number")))):
        if row:
            return row
    return session_rows[0] if session_rows else {}


def _warning_flags(rows: list[dict[str, str]], session_rows: list[dict[str, Any]] | None = None) -> set[str]:
    warnings: set[str] = set()
    for row in rows:
        if not row.get("turn_id"):
            warnings.add("missing_turn_id")
        if safe_int(row.get("missing_total_token_usage")):
            warnings.add("missing_total_token_usage")
    for row in session_rows or []:
        if row.get("warning_flags"):
            warnings.update(str(row["warning_flags"]).split(";"))
    return {flag for flag in warnings if flag}


def _thread_max_cumulative(rows: list[dict[str, str]]) -> int:
    return max((safe_int(row.get("cumulative_total_tokens")) for row in rows), default=0)


def _sum_thread_max_cumulative(rows: list[dict[str, str]]) -> int:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[row.get("thread_id", "")].append(row)
    return sum(_thread_max_cumulative(thread_rows) for thread_rows in grouped.values())


def _distinct_turn_count(rows: list[dict[str, str]]) -> int:
    return len({(row.get("thread_id", ""), row.get("turn_id", "")) for row in rows if row.get("turn_id")})


def _turn_key(row: dict[str, str]) -> str:
    return row.get("turn_id") or row.get("content_event_hash") or row.get("event_id") or ""


def _unique_last_per_thread_turn_tokens(rows: list[dict[str, str]]) -> int:
    seen: set[tuple[str, str, str]] = set()
    total = 0
    for row in _sort_events(rows):
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
    for row in _sort_events(rows):
        last_hash = row.get("last_token_usage_hash") or row.get("event_id", "")
        key = (row.get("thread_id", ""), row.get("session_segment_id", ""), _turn_key(row), last_hash)
        if key in seen:
            continue
        seen.add(key)
        total += safe_int(row.get("total_tokens"))
    return total


def _repeated_usage_count(rows: list[dict[str, str]], column: str) -> int:
    counts: dict[tuple[str, str], int] = defaultdict(int)
    for row in rows:
        value = row.get(column)
        if value:
            counts[(row.get("thread_id", ""), value)] += 1
    return sum(max(0, count - 1) for count in counts.values())


def _reconciliation(
    raw_rows: list[dict[str, str]],
    session_rollups: list[dict[str, Any]],
    thread_rollups: list[dict[str, Any]],
    event_accounting: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    sessions_by_id = {str(row.get("session_segment_id") or ""): row for row in session_rollups}
    events_by_id = {str(row.get("event_id") or ""): row for row in event_accounting}
    thread_rollups_by_id = {str(row.get("thread_id") or ""): row for row in thread_rollups}
    rows: list[dict[str, Any]] = []
    rows.extend(_rollup_reconciliation("thread", thread_rollups))
    rows.extend(_raw_reconciliation("repo", raw_rows, sessions_by_id, events_by_id, lambda row: row.get("github_repo") or ""))
    rows.extend(
        _raw_reconciliation(
            "workstream",
            raw_rows,
            sessions_by_id,
            events_by_id,
            lambda row: row.get("workstream_label") or "",
        )
    )
    rows.extend(
        _raw_reconciliation(
            "outcome",
            raw_rows,
            sessions_by_id,
            events_by_id,
            lambda row: row.get("outcome_type") or "",
        )
    )
    rows.extend(
        _raw_reconciliation(
            "attribution_confidence",
            raw_rows,
            sessions_by_id,
            events_by_id,
            lambda row: row.get("attribution_confidence") or "",
        )
    )
    rows.extend(
        _raw_reconciliation(
            "repo_workstream_outcome",
            raw_rows,
            sessions_by_id,
            events_by_id,
            lambda row: "|".join(
                [
                    row.get("github_repo") or "",
                    row.get("workstream_label") or "",
                    row.get("outcome_type") or "",
                    row.get("attribution_confidence") or "",
                ]
            ),
        )
    )
    for grain in ("day", "week", "month"):
        rows.extend(_time_reconciliation(grain, raw_rows, sessions_by_id, events_by_id, thread_rollups_by_id))
    return rows


def _rollup_reconciliation(grain: str, source_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for source in source_rows:
        dest = _empty_reconciliation(grain, str(source.get("thread_id") or source.get("group_key") or ""))
        for column in (
            "thread_id",
            "github_repo",
            "workstream_label",
            "outcome_type",
            "attribution_confidence",
            "token_event_count",
            "distinct_turn_count",
            "session_segment_count",
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
            "warning_flags",
        ):
            dest[column] = source.get(column, dest.get(column, ""))
        dest["thread_count"] = 1 if source.get("thread_id") else 0
        dest["session_segment_count_metric"] = dest["session_segment_count"]
        _merge_time(dest, source)
        _set_factors(dest)
        rows.append(dest)
    return sorted(rows, key=lambda row: (row["grain"], row["group_key"]))


def _raw_reconciliation(
    grain: str,
    raw_rows: list[dict[str, str]],
    sessions_by_id: dict[str, dict[str, Any]],
    events_by_id: dict[str, dict[str, Any]],
    key_fn,
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in raw_rows:
        grouped[str(key_fn(row) or "")].append(row)
    return [
        _group_reconciliation(
            grain,
            group_key,
            rows,
            sessions_by_id,
            events_by_id,
            include_session_final=True,
        )
        for group_key, rows in sorted(grouped.items())
    ]


def _time_reconciliation(
    grain: str,
    raw_rows: list[dict[str, str]],
    sessions_by_id: dict[str, dict[str, Any]],
    events_by_id: dict[str, dict[str, Any]],
    thread_rollups_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    periods: dict[str, tuple[str, str]] = {}
    for row in raw_rows:
        ts = parse_time(row.get("timestamp"))
        if ts is None:
            continue
        start, end = _period(grain, ts)
        grouped[start].append(row)
        periods[start] = (start, end)
    output = []
    for group_key, rows in sorted(grouped.items()):
        dest = _group_reconciliation(
            grain,
            group_key,
            rows,
            sessions_by_id,
            events_by_id,
            include_session_final=False,
        )
        dest["period_start"], dest["period_end"] = periods[group_key]
        thread_ids = {row.get("thread_id", "") for row in rows if row.get("thread_id")}
        dest["final_thread_total_tokens"] = sum(
            safe_int(thread_rollups_by_id.get(thread_id, {}).get("final_thread_total_tokens"))
            for thread_id in thread_ids
        )
        output.append(dest)
    return output


def _group_reconciliation(
    grain: str,
    group_key: str,
    rows: list[dict[str, str]],
    sessions_by_id: dict[str, dict[str, Any]],
    events_by_id: dict[str, dict[str, Any]],
    *,
    include_session_final: bool,
) -> dict[str, Any]:
    dest = _empty_reconciliation(grain, group_key)
    first = _first_row(rows)
    for column in ("thread_id", "github_repo", "workstream_label", "outcome_type", "attribution_confidence"):
        dest[column] = first.get(column, "")
    _merge_time(dest, {"first_event_at": min((row.get("timestamp", "") for row in rows if row.get("timestamp")), default="")})
    _merge_time(dest, {"last_event_at": max((row.get("timestamp", "") for row in rows if row.get("timestamp")), default="")})
    threads = {row.get("thread_id", "") for row in rows if row.get("thread_id")}
    segments = {row.get("session_segment_id", "") for row in rows if row.get("session_segment_id")}
    included_segments = [
        segment_id
        for segment_id in segments
        if safe_int(sessions_by_id.get(segment_id, {}).get("accounting_included"))
    ]
    event_rows = [events_by_id.get(str(row.get("event_id") or ""), {}) for row in rows]
    session_rows = [sessions_by_id.get(segment_id, {}) for segment_id in segments]
    warnings = _warning_flags(rows, session_rows)
    dest.update(
        {
            "token_event_count": len(rows),
            "thread_count": len(threads),
            "session_segment_count": len(segments),
            "distinct_turn_count": _distinct_turn_count(rows),
            "observed_event_sum_tokens": sum(safe_int(row.get("total_tokens")) for row in rows),
            "max_cumulative_tokens": _sum_thread_max_cumulative(rows),
            "cumulative_delta_tokens": sum(safe_int(row.get("cumulative_delta_tokens")) for row in event_rows),
            "unique_last_per_thread_turn_tokens": _unique_last_per_thread_turn_tokens(rows),
            "unique_last_per_session_turn_tokens": _unique_last_per_session_turn_tokens(rows),
            "repeated_last_usage_count": _repeated_usage_count(rows, "last_token_usage_hash"),
            "repeated_cumulative_count": _repeated_usage_count(rows, "total_token_usage_hash"),
            "cumulative_reset_count": sum(safe_int(row.get("cumulative_reset")) for row in event_rows),
            "missing_turn_id_count": sum(1 for row in rows if not row.get("turn_id")),
            "warning_flags": ";".join(sorted(warnings)),
        }
    )
    if include_session_final:
        dest["final_session_total_tokens"] = sum(
            safe_int(sessions_by_id.get(segment_id, {}).get("final_session_total_tokens"))
            for segment_id in included_segments
        )
    dest["final_thread_total_tokens"] = dest["max_cumulative_tokens"]
    dest["unique_last_per_turn_tokens"] = dest["unique_last_per_session_turn_tokens"]
    dest["deduped_turn_tokens"] = dest["unique_last_per_session_turn_tokens"]
    dest["session_segment_count_metric"] = dest["session_segment_count"]
    _set_factors(dest)
    return dest


def _empty_reconciliation(grain: str, group_key: str) -> dict[str, Any]:
    return {
        "grain": grain,
        "group_key": group_key or "(blank)",
        "period_start": "",
        "period_end": "",
        "thread_id": "",
        "github_repo": "",
        "workstream_label": "",
        "outcome_type": "",
        "attribution_confidence": "",
        "token_event_count": 0,
        "thread_count": 0,
        "session_segment_count": 0,
        "distinct_turn_count": 0,
        "observed_event_sum_tokens": 0,
        "max_cumulative_tokens": 0,
        "cumulative_delta_tokens": 0,
        "unique_last_per_thread_turn_tokens": 0,
        "unique_last_per_session_turn_tokens": 0,
        "unique_last_per_turn_tokens": 0,
        "deduped_turn_tokens": 0,
        "final_session_total_tokens": 0,
        "final_thread_total_tokens": 0,
        "repeated_last_usage_count": 0,
        "repeated_cumulative_count": 0,
        "session_segment_count_metric": 0,
        "cumulative_reset_count": 0,
        "missing_turn_id_count": 0,
        "inflation_factor_current_vs_max_cumulative": "",
        "inflation_factor_current_vs_delta": "",
        "warning_flags": set(),
    }


def _set_factors(row: dict[str, Any]) -> None:
    row["inflation_factor_current_vs_max_cumulative"] = _factor(
        safe_int(row.get("observed_event_sum_tokens")),
        safe_int(row.get("max_cumulative_tokens")),
    )
    row["inflation_factor_current_vs_delta"] = _factor(
        safe_int(row.get("observed_event_sum_tokens")),
        safe_int(row.get("cumulative_delta_tokens")),
    )


def _merge_time(dest: dict[str, Any], row: dict[str, Any]) -> None:
    first = row.get("first_event_at") or row.get("timestamp") or ""
    last = row.get("last_event_at") or row.get("timestamp") or ""
    if first and (not dest.get("first_event_at") or first < dest["first_event_at"]):
        dest["first_event_at"] = first
    if last and (not dest.get("last_event_at") or last > dest["last_event_at"]):
        dest["last_event_at"] = last


def _period(grain: str, timestamp: dt.datetime) -> tuple[str, str]:
    if grain == "day":
        start = timestamp.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + dt.timedelta(days=1)
    elif grain == "week":
        start = (timestamp - dt.timedelta(days=timestamp.weekday())).replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
        end = start + dt.timedelta(days=7)
    else:
        start = timestamp.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if start.month == 12:
            end = start.replace(year=start.year + 1, month=1)
        else:
            end = start.replace(month=start.month + 1)
    return _iso(start), _iso(end)


def _iso(value: dt.datetime) -> str:
    return value.astimezone(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _factor(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return ""
    return f"{numerator / denominator:.6f}"
