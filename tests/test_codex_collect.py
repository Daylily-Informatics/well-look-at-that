from __future__ import annotations

import json
import subprocess
from pathlib import Path

from well_look_at_that.collectors.codex import collect_codex
from well_look_at_that.model import parse_window
from well_look_at_that.tsv import read_tsv

THREAD_ID = "019f0000-0000-7000-8000-000000000001"


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def test_collect_codex_writes_event_grain_tsv(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "remote", "add", "origin", "git@github.com:Daylily-Informatics/example.git"], cwd=repo, check=True)

    codex_home = tmp_path / ".codex"
    session = codex_home / "sessions" / "2026" / "06" / "01" / f"rollout-2026-06-01T00-00-00-{THREAD_ID}.jsonl"
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
                        "last_token_usage": {
                            "input_tokens": 10,
                            "cached_input_tokens": 2,
                            "output_tokens": 3,
                            "reasoning_output_tokens": 4,
                            "total_tokens": 19,
                        },
                        "total_token_usage": {"total_tokens": 19},
                        "model_context_window": 200000,
                    },
                    "rate_limits": {"plan_type": "plus", "credits": {"balance": 12.5}},
                },
            },
        ],
    )

    output_root = tmp_path / "out"
    result = collect_codex(
        codex_home=codex_home,
        output_root=output_root,
        since=parse_window("2026-01-01T00:00:00Z"),
        run_id="20260602T000000Z",
    )

    assert result["counts"]["token_events_written"] == 1
    events = read_tsv(output_root / "data" / "codex_token_events.tsv")
    assert len(events) == 1
    assert events[0]["thread_id"] == THREAD_ID
    assert events[0]["github_repo"] == "Daylily-Informatics/example"
    assert events[0]["total_tokens"] == "19"
    assert not list(output_root.glob("**/*.csv"))
