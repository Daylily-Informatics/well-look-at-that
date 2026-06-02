from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from cli_core_yo import output
from cli_core_yo.app import create_app, run
from cli_core_yo.registry import CommandRegistry
from cli_core_yo.runtime import get_context
from cli_core_yo.spec import CliSpec, CommandPolicy, PluginSpec, PolicySpec, XdgSpec

from well_look_at_that.model import DEFAULT_CODEX_HOME, DEFAULT_OUTPUT_ROOT
from well_look_at_that.runner import (
    allocate_value_run,
    backfill_run,
    plot_run,
    report_run,
    validate_run,
)

MUTATING_JSON = CommandPolicy(mutates_state=True, supports_json=True, runtime_guard="exempt")
READ_JSON = CommandPolicy(supports_json=True, runtime_guard="exempt")


def _emit(result: dict) -> None:
    if get_context().json_mode:
        output.emit_json(result)
        return
    output.success(f"{result.get('status', 'UNKNOWN')} run {result.get('run_id', '')}")
    if result.get("ledger_path"):
        output.detail(f"Ledger: {result['ledger_path']}")
    validation = result.get("validation") or {}
    if validation:
        output.detail(f"Token events: {validation.get('token_event_count', 0)}")
        output.detail(f"CSV files: {validation.get('csv_file_count', 0)}")
        output.detail(f"Redaction findings: {(validation.get('redaction_scan') or {}).get('finding_count', 0)}")


def backfill(
    codex_home: Annotated[
        Path,
        typer.Option("--codex-home", help="Codex home directory to inspect."),
    ] = DEFAULT_CODEX_HOME,
    output_root: Annotated[
        Path,
        typer.Option("--output-root", help="Report output root."),
    ] = DEFAULT_OUTPUT_ROOT,
    since: Annotated[str, typer.Option("--since", help="Window start such as 30d or 2026-01-01T00:00:00Z.")] = "30d",
    skip_github: Annotated[bool, typer.Option("--skip-github", help="Do not call gh for GitHub activity.")] = False,
    max_repos: Annotated[int, typer.Option("--max-repos", help="Maximum GitHub repos to query.")] = 120,
    repo_roots: Annotated[
        list[Path] | None,
        typer.Option("--repo-root", help="Explicit local repo/workspace roots for attribution."),
    ] = None,
    no_reports: Annotated[bool, typer.Option("--no-reports", help="Only collect data TSVs.")] = False,
    no_plots: Annotated[bool, typer.Option("--no-plots", help="Skip plot generation.")] = False,
) -> None:
    """Collect Codex token events and optional GitHub activity."""
    _emit(
        backfill_run(
            codex_home=codex_home,
            output_root=output_root,
            since_spec=since,
            skip_github=skip_github,
            max_repos=max_repos,
            repo_roots=repo_roots,
            no_reports=no_reports,
            no_plots=no_plots,
        )
    )


def run_incremental(
    codex_home: Annotated[Path, typer.Option("--codex-home")] = DEFAULT_CODEX_HOME,
    output_root: Annotated[Path, typer.Option("--output-root")] = DEFAULT_OUTPUT_ROOT,
    window: Annotated[str, typer.Option("--window")] = "30d",
    skip_github: Annotated[bool, typer.Option("--skip-github")] = False,
    max_repos: Annotated[int, typer.Option("--max-repos")] = 120,
    repo_roots: Annotated[list[Path] | None, typer.Option("--repo-root")] = None,
) -> None:
    """Run the rolling collection path for scheduled ongoing use."""
    _emit(
        backfill_run(
            codex_home=codex_home,
            output_root=output_root,
            since_spec=window,
            skip_github=skip_github,
            max_repos=max_repos,
            repo_roots=repo_roots,
        )
    )


def report(
    output_root: Annotated[Path, typer.Option("--output-root")] = DEFAULT_OUTPUT_ROOT,
    window: Annotated[str, typer.Option("--window")] = "30d",
) -> None:
    """Regenerate TSV and Markdown reports from existing TSV data."""
    _emit(report_run(output_root=output_root, window=window))


def plot(
    output_root: Annotated[Path, typer.Option("--output-root")] = DEFAULT_OUTPUT_ROOT,
    window: Annotated[str, typer.Option("--window")] = "30d",
    entitlements: Annotated[
        Path | None,
        typer.Option("--entitlements", help="Explicit token entitlement TSV for overlay plots."),
    ] = None,
) -> None:
    """Regenerate HTML plots from existing TSV data."""
    _emit(plot_run(output_root=output_root, window=window, entitlements=entitlements))


def allocate_value(
    output_root: Annotated[Path, typer.Option("--output-root")] = DEFAULT_OUTPUT_ROOT,
    window: Annotated[str, typer.Option("--window")] = "30d",
    entitlements: Annotated[
        Path,
        typer.Option("--entitlements", help="Explicit token entitlement TSV."),
    ] = DEFAULT_OUTPUT_ROOT / "config" / "token_entitlements.tsv",
) -> None:
    """Assign dollar value to event-grain token usage from explicit entitlements."""
    _emit(allocate_value_run(output_root=output_root, window=window, entitlements=entitlements))


def validate(
    output_root: Annotated[Path, typer.Option("--output-root")] = DEFAULT_OUTPUT_ROOT,
) -> None:
    """Validate TSV-only outputs and redaction scan results."""
    _emit(validate_run(output_root=output_root))


def register(registry: CommandRegistry, spec: CliSpec) -> None:
    registry.add_command(None, "backfill", backfill, help_text=backfill.__doc__ or "", policy=MUTATING_JSON)
    registry.add_command(
        None,
        "run-incremental",
        run_incremental,
        help_text=run_incremental.__doc__ or "",
        policy=MUTATING_JSON,
    )
    registry.add_command(None, "report", report, help_text=report.__doc__ or "", policy=MUTATING_JSON)
    registry.add_command(None, "plot", plot, help_text=plot.__doc__ or "", policy=MUTATING_JSON)
    registry.add_command(
        None,
        "allocate-value",
        allocate_value,
        help_text=allocate_value.__doc__ or "",
        policy=MUTATING_JSON,
    )
    registry.add_command(None, "validate", validate, help_text=validate.__doc__ or "", policy=READ_JSON)


spec = CliSpec(
    prog_name="well-look-at-that",
    app_display_name="well-look-at-that",
    dist_name="well-look-at-that",
    root_help="Codex token usage to GitHub outcome reporting.",
    xdg=XdgSpec(app_dir_name="well-look-at-that"),
    policy=PolicySpec(),
    plugins=PluginSpec(explicit=["well_look_at_that.cli.register"]),
)

app = create_app(spec)


def main() -> None:
    raise SystemExit(run(spec))
