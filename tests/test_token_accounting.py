from __future__ import annotations

import subprocess
from pathlib import Path

from tests.test_codex_collect import THREAD_ID, _write_jsonl

from well_look_at_that.accounting import build_accounting
from well_look_at_that.collectors.codex import collect_codex
from well_look_at_that.model import parse_window
from well_look_at_that.tsv import read_tsv


def _row(
    *,
    event_id: str,
    segment: str = "seg-1",
    thread: str = "thread-1",
    turn: str = "turn-1",
    line: int = 1,
    total: int = 10,
    cumulative: int = 10,
    source_path: str = "/tmp/codex/sessions/a.jsonl",
    active: int = 1,
    archived: int = 0,
    payload_hash: str | None = None,
) -> dict[str, str]:
    payload_hash = payload_hash or f"payload-{event_id}"
    return {
        "event_id": event_id,
        "thread_id": thread,
        "turn_id": turn,
        "timestamp": f"2026-06-01T00:00:{line:02d}Z",
        "source_path": source_path,
        "rollout_path": source_path,
        "line_number": str(line),
        "session_segment_id": segment,
        "input_tokens": str(total),
        "cached_input_tokens": "0",
        "output_tokens": "0",
        "reasoning_output_tokens": "0",
        "total_tokens": str(total),
        "cumulative_input_tokens": str(cumulative),
        "cumulative_cached_input_tokens": "0",
        "cumulative_output_tokens": "0",
        "cumulative_reasoning_output_tokens": "0",
        "cumulative_total_tokens": str(cumulative),
        "last_token_usage_hash": f"last-{total}",
        "total_token_usage_hash": f"cum-{cumulative}",
        "token_count_payload_hash": payload_hash,
        "content_event_hash": f"content-{event_id}",
        "is_active_session": str(active),
        "is_archived_session": str(archived),
        "missing_last_token_usage": "0",
        "missing_total_token_usage": "0",
        "github_repo": "Daylily-Informatics/example",
        "workstream_label": "example",
        "outcome_type": "feature",
        "attribution_confidence": "strong",
    }


def test_repeated_last_and_cumulative_are_diagnostic_not_accounting() -> None:
    rows = [
        _row(event_id="e1", line=1, total=10, cumulative=10, payload_hash="same"),
        _row(event_id="e2", line=2, total=10, cumulative=10, payload_hash="same"),
        _row(event_id="e3", line=3, total=10, cumulative=10, payload_hash="same"),
    ]
    accounting = build_accounting(rows)
    session = accounting["session_rollups"][0]

    assert len(accounting["event_accounting"]) == 3
    assert session["observed_event_sum_tokens"] == 30
    assert session["final_session_total_tokens"] == 10
    assert session["cumulative_delta_tokens"] == 10
    assert session["unique_last_per_session_turn_tokens"] == 10
    assert session["unique_last_per_turn_tokens"] == 10
    assert session["repeated_last_usage_count"] == 2
    assert session["repeated_cumulative_count"] == 2
    thread = accounting["thread_rollups"][0]
    assert thread["unique_last_per_thread_turn_tokens"] == 10
    assert thread["unique_last_per_session_turn_tokens"] == 10
    assert thread["repeated_last_usage_count"] == 2


def test_missing_turn_id_keeps_event_grain_for_turn_estimate() -> None:
    rows = [
        _row(event_id="e1", turn="", line=1, total=5, cumulative=5),
        _row(event_id="e2", turn="", line=2, total=5, cumulative=10),
    ]
    accounting = build_accounting(rows)
    session = accounting["session_rollups"][0]

    assert session["missing_turn_id_count"] == 2
    assert session["unique_last_per_session_turn_tokens"] == 10
    assert session["unique_last_per_turn_tokens"] == 10
    assert accounting["thread_rollups"][0]["unique_last_per_thread_turn_tokens"] == 10
    assert len(accounting["turn_estimates"]) == 2


def test_cumulative_reset_starts_new_delta_span() -> None:
    rows = [
        _row(event_id="e1", line=1, total=100, cumulative=100),
        _row(event_id="e2", line=2, total=20, cumulative=120),
        _row(event_id="e3", line=3, total=5, cumulative=5),
        _row(event_id="e4", line=4, total=15, cumulative=20),
    ]
    session = build_accounting(rows)["session_rollups"][0]

    assert session["cumulative_reset_count"] == 1
    assert session["cumulative_delta_tokens"] == 140
    assert "cumulative_reset" in session["warning_flags"]


def test_duplicate_active_archived_segment_is_excluded_from_primary_accounting() -> None:
    active_path = "/tmp/codex/sessions/thread.jsonl"
    archived_path = "/tmp/codex/archived_sessions/thread.jsonl"
    rows = [
        _row(
            event_id="active",
            segment="active-seg",
            thread="thread-1",
            source_path=active_path,
            active=1,
            archived=0,
            payload_hash="same-payload",
        ),
        _row(
            event_id="archived",
            segment="archived-seg",
            thread="thread-1",
            source_path=archived_path,
            active=0,
            archived=1,
            payload_hash="same-payload",
        ),
    ]
    accounting = build_accounting(rows)
    sessions = {row["session_segment_id"]: row for row in accounting["session_rollups"]}
    thread = accounting["thread_rollups"][0]

    assert sessions["active-seg"]["accounting_included"] == 1
    assert sessions["archived-seg"]["accounting_included"] == 0
    assert sessions["archived-seg"]["duplicate_segment_of"] == "active-seg"
    assert thread["session_segment_count"] == 2
    assert thread["included_session_segment_count"] == 1
    assert thread["excluded_duplicate_session_segment_count"] == 1
    assert thread["active_archived_overlap"] == 1
    assert thread["final_thread_total_tokens"] == 10


def test_multi_segment_thread_keeps_thread_max_diagnostic_separate() -> None:
    rows = [
        _row(
            event_id="s1-e1",
            segment="seg-1",
            line=1,
            total=100,
            cumulative=100,
            source_path="/tmp/codex/archived_sessions/a.jsonl",
            active=0,
            archived=1,
            payload_hash="seg1",
        ),
        _row(
            event_id="s2-e1",
            segment="seg-2",
            line=2,
            total=50,
            cumulative=50,
            source_path="/tmp/codex/archived_sessions/b.jsonl",
            active=0,
            archived=1,
            payload_hash="seg2",
        ),
    ]
    accounting = build_accounting(rows)
    thread = accounting["thread_rollups"][0]
    thread_reconciliation = [row for row in accounting["reconciliation"] if row["grain"] == "thread"][0]

    assert thread["session_segment_count"] == 2
    assert thread["final_session_total_tokens"] == 150
    assert thread["cumulative_delta_tokens"] == 150
    assert thread["final_thread_total_tokens"] == 100
    assert thread["max_cumulative_tokens"] == 100
    assert thread_reconciliation["session_segment_count"] == 2
    assert thread_reconciliation["final_thread_total_tokens"] == 100


def test_method_d_is_thread_turn_scoped_not_session_turn_scoped() -> None:
    rows = [
        _row(
            event_id="s1-e1",
            segment="seg-1",
            thread="thread-1",
            turn="turn-same",
            line=1,
            total=10,
            cumulative=10,
            source_path="/tmp/codex/archived_sessions/a.jsonl",
            payload_hash="seg1",
        ),
        _row(
            event_id="s2-e1",
            segment="seg-2",
            thread="thread-1",
            turn="turn-same",
            line=2,
            total=10,
            cumulative=10,
            source_path="/tmp/codex/archived_sessions/b.jsonl",
            payload_hash="seg2",
        ),
    ]
    thread = build_accounting(rows)["thread_rollups"][0]

    assert thread["distinct_turn_count"] == 1
    assert thread["unique_last_per_thread_turn_tokens"] == 10
    assert thread["unique_last_per_session_turn_tokens"] == 20
    assert thread["unique_last_per_turn_tokens"] == 20
    assert thread["repeated_last_usage_count"] == 1
    assert thread["repeated_cumulative_count"] == 1


def test_time_reconciliation_populates_event_counts_and_deltas() -> None:
    rows = [
        _row(event_id="d1-e1", line=1, total=10, cumulative=10),
        _row(event_id="d1-e2", line=2, total=5, cumulative=15),
        {
            **_row(event_id="d2-e1", line=3, total=15, cumulative=30),
            "timestamp": "2026-06-02T00:00:03Z",
        },
    ]
    accounting = build_accounting(rows)
    event_count = len(accounting["event_accounting"])
    delta_total = sum(row["cumulative_delta_tokens"] for row in accounting["event_accounting"])

    for grain in ("day", "week", "month"):
        grain_rows = [row for row in accounting["reconciliation"] if row["grain"] == grain]
        assert sum(row["token_event_count"] for row in grain_rows) == event_count
        assert sum(row["cumulative_delta_tokens"] for row in grain_rows) == delta_total


def test_collector_writes_raw_event_metadata_and_compatibility_tsv(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "git@github.com:Daylily-Informatics/example.git"],
        cwd=repo,
        check=True,
    )
    codex_home = tmp_path / ".codex"
    session = codex_home / "sessions" / "2026" / "06" / "01" / f"rollout-{THREAD_ID}.jsonl"
    _write_jsonl(
        session,
        [
            {
                "type": "session_meta",
                "timestamp": "2026-06-01T00:00:00Z",
                "payload": {"id": THREAD_ID, "cwd": str(repo), "model": "gpt-test"},
            },
            {
                "type": "event_msg",
                "timestamp": "2026-06-01T00:01:00Z",
                "payload": {
                    "type": "token_count",
                    "turn_id": "turn-1",
                    "info": {
                        "last_token_usage": {"input_tokens": 7, "total_tokens": 7},
                        "total_token_usage": {"input_tokens": 7, "total_tokens": 7},
                    },
                    "rate_limits": {},
                },
            },
            {
                "type": "event_msg",
                "timestamp": "2026-06-01T00:02:00Z",
                "payload": {"type": "token_count", "info": {}, "rate_limits": {}},
            },
        ],
    )

    output_root = tmp_path / "out"
    collect_codex(
        codex_home=codex_home,
        output_root=output_root,
        since=parse_window("2026-01-01T00:00:00Z"),
        run_id="20260602T000000Z",
    )
    raw_rows = read_tsv(output_root / "data" / "raw_token_events.tsv")
    compat_rows = read_tsv(output_root / "data" / "codex_token_events.tsv")

    assert len(raw_rows) == 2
    assert len(compat_rows) == 2
    assert raw_rows[0]["source_path"] == str(session)
    assert raw_rows[0]["session_segment_id"]
    assert raw_rows[0]["last_token_usage_hash"]
    assert raw_rows[0]["total_token_usage_hash"]
    assert raw_rows[0]["token_count_payload_hash"]
    assert raw_rows[0]["is_active_session"] == "1"
    assert raw_rows[0]["is_archived_session"] == "0"
    assert raw_rows[1]["missing_last_token_usage"] == "1"
    assert raw_rows[1]["missing_total_token_usage"] == "1"
