from __future__ import annotations

import inspect
from pathlib import Path

from typer.testing import CliRunner

from well_look_at_that.cli import app, spec
from well_look_at_that.model import THREAD_COLUMNS, TOKEN_EVENT_COLUMNS, parse_window
from well_look_at_that.plots import generate_plots
from well_look_at_that.reports import generate_reports, validate_outputs
from well_look_at_that.tsv import read_tsv, write_tsv
from well_look_at_that.value import allocate_value


def _seed_output(output_root: Path) -> None:
    write_tsv(
        output_root / "data" / "codex_threads.tsv",
        [
            {
                "thread_id": "t1",
                "created_at": "2026-06-01T00:00:00Z",
                "updated_at": "2026-06-01T00:10:00Z",
                "github_repo": "Daylily-Informatics/example",
                "workstream_label": "example",
                "outcome_type": "feature",
                "attribution_confidence": "strong",
            }
        ],
        THREAD_COLUMNS,
    )
    write_tsv(
        output_root / "data" / "codex_token_events.tsv",
        [
            {
                "event_id": "e1",
                "thread_id": "t1",
                "timestamp": "2026-06-01T00:01:00Z",
                "total_tokens": 100,
                "input_tokens": 40,
                "cached_input_tokens": 10,
                "output_tokens": 30,
                "reasoning_output_tokens": 20,
                "github_repo": "Daylily-Informatics/example",
                "workstream_label": "example",
                "outcome_type": "feature",
                "attribution_confidence": "strong",
            },
            {
                "event_id": "e2",
                "thread_id": "t1",
                "timestamp": "2026-06-01T01:01:00Z",
                "total_tokens": 50,
                "input_tokens": 20,
                "cached_input_tokens": 5,
                "output_tokens": 15,
                "reasoning_output_tokens": 10,
                "github_repo": "Daylily-Informatics/example",
                "workstream_label": "example",
                "outcome_type": "feature",
                "attribution_confidence": "strong",
            },
        ],
        TOKEN_EVENT_COLUMNS,
    )


def test_reports_plots_and_value_use_tsv(tmp_path: Path) -> None:
    output_root = tmp_path / "out"
    _seed_output(output_root)
    since = parse_window("2026-01-01T00:00:00Z")
    report_counts = generate_reports(
        output_root=output_root,
        since=since,
        window_label="30d",
        run_id="20260602T000000Z",
    )
    plot_counts = generate_plots(
        output_root=output_root,
        since=since,
        window_label="30d",
        run_id="20260602T000000Z",
    )
    entitlements = output_root / "config" / "token_entitlements.tsv"
    write_tsv(
        entitlements,
        [
            {
                "window_start": "2026-06-01T00:00:00Z",
                "window_end": "2026-06-02T00:00:00Z",
                "base_subscription_usd": "20",
                "base_subscription_tokens": "100",
                "purchased_usd": "5",
                "purchased_tokens": "100",
                "source": "test",
                "confidence": "manual",
                "evidence_path": str(entitlements),
            }
        ],
        [
            "window_start",
            "window_end",
            "base_subscription_usd",
            "base_subscription_tokens",
            "purchased_usd",
            "purchased_tokens",
            "source",
            "confidence",
            "evidence_path",
        ],
    )
    value_counts = allocate_value(
        output_root=output_root,
        entitlements=entitlements,
        since=since,
        run_id="20260602T000000Z",
    )
    validation = validate_outputs(output_root=output_root, run_id="20260602T000000Z")

    assert report_counts["report_token_events"] == 2
    assert plot_counts["plot_count"] == 5
    assert value_counts["value_allocations_written"] == 2
    assert validation["status"] == "SUCCESS"
    assert read_tsv(output_root / "data" / "token_value_allocations.tsv")[1]["funding_source"] == "purchased_tokens"
    assert not list(output_root.glob("**/*.csv"))


def test_cli_registry_exposes_expected_commands() -> None:
    registry = app._cli_core_yo_registry
    assert spec.policy.profile == "platform-v2"
    for command in ("backfill", "run-incremental", "report", "plot", "allocate-value", "validate"):
        assert registry.resolve_command_args([command]) is not None


def test_cli_version_json() -> None:
    result = CliRunner().invoke(app, ["--json", "version"])
    assert result.exit_code == 0
    assert "well-look-at-that" in result.stdout


def test_cli_backfill_exposes_repo_roots_parameter() -> None:
    command = app._cli_core_yo_registry.get_command("backfill")
    assert command is not None
    assert "repo_roots" in inspect.signature(command.callback).parameters
