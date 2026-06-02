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

    thread_rollups = _thread_rollups(session_rollups)
    reconciliation = _reconciliation(session_rollups, thread_rollups, event_accounting)
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
                **deltas,
            }
        )

        turn_key = row.get("turn_id") or row.get("event_id", "")
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

    unique_last = sum(safe_int(turn["unique_last_per_turn_tokens"]) for turn in turn_groups.values())
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


def _thread_rollups(session_rollups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in session_rollups:
        thread_id = str(row.get("thread_id") or "")
        dest = grouped.setdefault(
            thread_id,
            {
                "thread_id": thread_id,
                "github_repo": row.get("github_repo", ""),
                "workstream_label": row.get("workstream_label", ""),
                "outcome_type": row.get("outcome_type", ""),
                "attribution_confidence": row.get("attribution_confidence", ""),
                "first_event_at": row.get("first_event_at", ""),
                "last_event_at": row.get("last_event_at", ""),
                "token_event_count": 0,
                "distinct_turn_count": 0,
                "session_segment_count": 0,
                "included_session_segment_count": 0,
                "active_session_segment_count": 0,
                "archived_session_segment_count": 0,
                "active_archived_overlap": 0,
                "observed_event_sum_tokens": 0,
                "max_cumulative_tokens": 0,
                "final_session_total_tokens": 0,
                "final_thread_total_tokens": 0,
                "cumulative_delta_tokens": 0,
                "unique_last_per_turn_tokens": 0,
                "deduped_turn_tokens": 0,
                "repeated_last_usage_count": 0,
                "repeated_cumulative_count": 0,
                "cumulative_reset_count": 0,
                "missing_turn_id_count": 0,
                "warning_flags": set(),
            },
        )
        _merge_time(dest, row)
        dest["session_segment_count"] += 1
        dest["included_session_segment_count"] += safe_int(row.get("accounting_included"))
        dest["active_session_segment_count"] += safe_int(row.get("is_active_session"))
        dest["archived_session_segment_count"] += safe_int(row.get("is_archived_session"))
        for column in (
            "token_event_count",
            "distinct_turn_count",
            "observed_event_sum_tokens",
            "final_session_total_tokens",
            "cumulative_delta_tokens",
            "unique_last_per_turn_tokens",
            "deduped_turn_tokens",
            "repeated_last_usage_count",
            "repeated_cumulative_count",
            "cumulative_reset_count",
            "missing_turn_id_count",
        ):
            dest[column] += safe_int(row.get(column))
        dest["max_cumulative_tokens"] = max(
            safe_int(dest.get("max_cumulative_tokens")),
            safe_int(row.get("max_cumulative_tokens")),
        )
        if row.get("warning_flags"):
            dest["warning_flags"].update(str(row["warning_flags"]).split(";"))
    output = []
    for dest in grouped.values():
        dest["active_archived_overlap"] = (
            1
            if safe_int(dest.get("active_session_segment_count"))
            and safe_int(dest.get("archived_session_segment_count"))
            else 0
        )
        if dest["active_archived_overlap"]:
            dest["warning_flags"].add("active_archived_overlap")
        if safe_int(dest["session_segment_count"]) > 1:
            dest["warning_flags"].add("multi_segment_thread")
        dest["final_thread_total_tokens"] = dest["final_session_total_tokens"]
        dest["inflation_factor_current_vs_max_cumulative"] = _factor(
            safe_int(dest["observed_event_sum_tokens"]),
            safe_int(dest["max_cumulative_tokens"]),
        )
        dest["inflation_factor_current_vs_delta"] = _factor(
            safe_int(dest["observed_event_sum_tokens"]),
            safe_int(dest["cumulative_delta_tokens"]),
        )
        dest["warning_flags"] = ";".join(sorted(flag for flag in dest["warning_flags"] if flag))
        output.append(dest)
    return sorted(output, key=lambda row: (-safe_int(row["final_thread_total_tokens"]), row["thread_id"]))


def _reconciliation(
    session_rollups: list[dict[str, Any]],
    thread_rollups: list[dict[str, Any]],
    event_accounting: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    rows.extend(_session_based_reconciliation("thread", thread_rollups, ("thread_id",)))
    rows.extend(_session_based_reconciliation("repo", session_rollups, ("github_repo",)))
    rows.extend(_session_based_reconciliation("workstream", session_rollups, ("workstream_label",)))
    rows.extend(_session_based_reconciliation("outcome", session_rollups, ("outcome_type",)))
    rows.extend(
        _session_based_reconciliation(
            "attribution_confidence",
            session_rollups,
            ("attribution_confidence",),
        )
    )
    rows.extend(
        _session_based_reconciliation(
            "repo_workstream_outcome",
            session_rollups,
            ("github_repo", "workstream_label", "outcome_type", "attribution_confidence"),
        )
    )
    for grain in ("day", "week", "month"):
        rows.extend(_time_reconciliation(grain, event_accounting))
    return rows


def _session_based_reconciliation(
    grain: str,
    source_rows: list[dict[str, Any]],
    key_columns: tuple[str, ...],
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, ...], dict[str, Any]] = {}
    for row in source_rows:
        key = tuple(str(row.get(column) or "") for column in key_columns)
        dest = grouped.setdefault(key, _empty_reconciliation(grain, "|".join(key)))
        for column in ("thread_id", "github_repo", "workstream_label", "outcome_type", "attribution_confidence"):
            if not dest[column] and row.get(column):
                dest[column] = row.get(column)
        _merge_time(dest, row)
        _add_metric(dest, row)
        dest.setdefault("_threads", set()).add(row.get("thread_id", ""))
        dest.setdefault("_segments", set()).add(row.get("session_segment_id", ""))
    return _finalize_reconciliation(grouped.values())


def _time_reconciliation(grain: str, event_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in event_rows:
        ts = parse_time(row.get("timestamp"))
        if ts is None:
            continue
        start, end = _period(grain, ts)
        key = start
        dest = grouped.setdefault(key, _empty_reconciliation(grain, key))
        dest["period_start"] = start
        dest["period_end"] = end
        _merge_time(dest, row)
        _add_metric(dest, row)
        dest.setdefault("_threads", set()).add(row.get("thread_id", ""))
        dest.setdefault("_segments", set()).add(row.get("session_segment_id", ""))
    return _finalize_reconciliation(grouped.values())


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


def _add_metric(dest: dict[str, Any], row: dict[str, Any]) -> None:
    for column in (
        "token_event_count",
        "distinct_turn_count",
        "observed_event_sum_tokens",
        "cumulative_delta_tokens",
        "unique_last_per_turn_tokens",
        "deduped_turn_tokens",
        "final_session_total_tokens",
        "final_thread_total_tokens",
        "repeated_last_usage_count",
        "repeated_cumulative_count",
        "cumulative_reset_count",
        "missing_turn_id_count",
    ):
        dest[column] += safe_int(row.get(column))
    dest["max_cumulative_tokens"] += safe_int(row.get("max_cumulative_tokens"))
    if row.get("warning_flags"):
        dest["warning_flags"].update(str(row["warning_flags"]).split(";"))


def _finalize_reconciliation(rows) -> list[dict[str, Any]]:
    output = []
    for row in rows:
        threads = {item for item in row.pop("_threads", set()) if item}
        segments = {item for item in row.pop("_segments", set()) if item}
        row["thread_count"] = len(threads)
        row["session_segment_count"] = len(segments)
        row["session_segment_count_metric"] = len(segments)
        row["inflation_factor_current_vs_max_cumulative"] = _factor(
            safe_int(row["observed_event_sum_tokens"]),
            safe_int(row["max_cumulative_tokens"]),
        )
        row["inflation_factor_current_vs_delta"] = _factor(
            safe_int(row["observed_event_sum_tokens"]),
            safe_int(row["cumulative_delta_tokens"]),
        )
        row["warning_flags"] = ";".join(sorted(flag for flag in row["warning_flags"] if flag))
        output.append(row)
    return sorted(output, key=lambda item: (item["grain"], item["group_key"]))


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
