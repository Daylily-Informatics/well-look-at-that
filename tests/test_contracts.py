from __future__ import annotations

import importlib.metadata
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from tests.test_codex_collect import THREAD_ID, _write_jsonl

from well_look_at_that.collectors.github import collect_github
from well_look_at_that.model import parse_github_repo, parse_window
from well_look_at_that.redaction import redact_text, scan_paths
from well_look_at_that.runner import backfill_run
from well_look_at_that.tsv import read_tsv, write_tsv
from well_look_at_that.value import allocate_value


def test_console_scripts_include_full_name_and_wlat_alias() -> None:
    scripts = importlib.metadata.entry_points(group="console_scripts")
    names = {script.name for script in scripts if script.value == "well_look_at_that.cli:main"}
    assert {"well-look-at-that", "wlat"} <= names


def test_tsv_writer_rejects_csv_paths(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="CSV outputs are not supported"):
        write_tsv(tmp_path / "bad.csv", [], ["a"])


def test_tsv_writer_redacts_secret_like_cells(tmp_path: Path) -> None:
    path = tmp_path / "safe.tsv"
    write_tsv(
        path,
        [{"note": "ghp_abcdefghijklmnopqrstuvwxyz123456"}],
        ["note"],
    )
    rows = read_tsv(path)
    assert rows[0]["note"] == "[REDACTED:github_token]"


def test_time_and_repo_parsers_are_explicit() -> None:
    assert parse_window("2026-01-01T00:00:00Z").isoformat().startswith("2026-01-01")
    assert parse_github_repo("git@github.com:Daylily-Informatics/well-look-at-that.git") == (
        "Daylily-Informatics/well-look-at-that"
    )


def test_redaction_scan_flags_secret_like_outputs(tmp_path: Path) -> None:
    path = tmp_path / "report.md"
    path.write_text("ghp_abcdefghijklmnopqrstuvwxyz123456\n", encoding="utf-8")
    assert "[REDACTED:github_token]" in redact_text(path.read_text(encoding="utf-8"))
    scan = scan_paths([path])
    assert scan["finding_count"] == 1


def test_value_allocation_requires_explicit_entitlements(tmp_path: Path) -> None:
    output_root = tmp_path / "out"
    write_tsv(
        output_root / "data" / "codex_token_events.tsv",
        [
            {
                "event_id": "e1",
                "thread_id": "t1",
                "timestamp": "2026-06-01T00:01:00Z",
                "total_tokens": "7",
            }
        ],
        ["event_id", "thread_id", "timestamp", "total_tokens"],
    )
    with pytest.raises(FileNotFoundError, match="Entitlement TSV does not exist"):
        allocate_value(
            output_root=output_root,
            entitlements=output_root / "missing.tsv",
            since=parse_window("2026-01-01T00:00:00Z"),
            run_id="20260602T000000Z",
        )


def test_github_collector_requires_gh(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    output_root = tmp_path / "out"
    write_tsv(
        output_root / "data" / "codex_threads.tsv",
        [{"thread_id": "t1", "github_repo": "Daylily-Informatics/example"}],
        ["thread_id", "github_repo"],
    )
    monkeypatch.setattr(shutil, "which", lambda _: None)
    with pytest.raises(RuntimeError, match="requires the gh CLI"):
        collect_github(
            output_root=output_root,
            since=parse_window("2026-01-01T00:00:00Z"),
            run_id="20260602T000000Z",
        )


def test_github_collector_accepts_plain_text_auth_status(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "out"
    write_tsv(
        output_root / "data" / "codex_threads.tsv",
        [],
        ["thread_id", "github_repo"],
    )
    monkeypatch.setattr(shutil, "which", lambda _: "/usr/bin/gh")

    def fake_run(*args, **kwargs):
        assert args[0] == ["gh", "auth", "status"]
        return SimpleNamespace(returncode=0, stdout="Logged in to github.com\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    counts = collect_github(
        output_root=output_root,
        since=parse_window("2026-01-01T00:00:00Z"),
        run_id="20260602T000000Z",
    )
    assert counts == {"github_repos_seen": 0, "github_events_written": 0}


def test_github_collector_uses_get_for_fielded_api_calls(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "out"
    write_tsv(
        output_root / "data" / "codex_threads.tsv",
        [{"thread_id": "t1", "github_repo": "Daylily-Informatics/example"}],
        ["thread_id", "github_repo"],
    )
    monkeypatch.setattr(shutil, "which", lambda _: "/usr/bin/gh")
    calls: list[list[str]] = []

    def fake_run(args, **kwargs):
        calls.append(args)
        if args == ["gh", "auth", "status"]:
            return SimpleNamespace(returncode=0, stdout="Logged in to github.com\n", stderr="")
        assert args[:3] == ["gh", "api", "--method"]
        assert args[3] == "GET"
        return SimpleNamespace(returncode=0, stdout="[]", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    counts = collect_github(
        output_root=output_root,
        since=parse_window("2026-01-01T00:00:00Z"),
        run_id="20260602T000000Z",
    )
    assert counts == {"github_repos_seen": 1, "github_events_written": 0}
    assert len([call for call in calls if call[:2] == ["gh", "api"]]) == 3


def test_backfill_run_creates_reports_plots_and_ledger(tmp_path: Path) -> None:
    repo = tmp_path / "projects" / "repo"
    repo.mkdir(parents=True)
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
                    "info": {
                        "last_token_usage": {
                            "input_tokens": 1,
                            "cached_input_tokens": 1,
                            "output_tokens": 1,
                            "reasoning_output_tokens": 1,
                            "total_tokens": 4,
                        },
                        "total_token_usage": {"total_tokens": 4},
                    },
                    "rate_limits": {},
                },
            },
        ],
    )

    output_root = tmp_path / "reports"
    result = backfill_run(
        codex_home=codex_home,
        output_root=output_root,
        since_spec="2026-01-01T00:00:00Z",
        skip_github=True,
        max_repos=10,
        repo_roots=[tmp_path / "projects"],
    )

    assert result["status"] == "SUCCESS"
    assert Path(result["ledger_path"]).exists()
    assert read_tsv(output_root / "data" / "codex_token_events.tsv")[0]["total_tokens"] == "4"
    assert (output_root / "reports" / "latest_2026-01-01T00:00:00Z_summary.md").exists()
    assert (output_root / "plots" / "latest_2026-01-01T00:00:00Z_token_event_raster.html").exists()
