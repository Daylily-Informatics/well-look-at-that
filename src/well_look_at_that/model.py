from __future__ import annotations

import datetime as dt
import hashlib
import os
import re
from pathlib import Path
from typing import Any

UTC = dt.UTC

DEFAULT_CODEX_HOME = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
DEFAULT_OUTPUT_ROOT = DEFAULT_CODEX_HOME / "docs" / "codex-github-outcomes"
DEFAULT_REPO_ROOTS: tuple[Path, ...] = ()

OUTCOME_TYPES = (
    "feature",
    "capability",
    "improvement",
    "bugfix",
    "docs",
    "tests",
    "release",
    "infra",
    "workflow",
    "review",
    "planning",
    "investigation",
    "ops",
    "unknown",
)

TOKEN_EVENT_COLUMNS = [
    "event_id",
    "raw_event_id",
    "thread_id",
    "turn_id",
    "timestamp",
    "source_path",
    "rollout_path",
    "line_number",
    "session_segment_id",
    "input_tokens",
    "cached_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "total_tokens",
    "cumulative_input_tokens",
    "cumulative_cached_input_tokens",
    "cumulative_output_tokens",
    "cumulative_reasoning_output_tokens",
    "cumulative_total_tokens",
    "last_token_usage_hash",
    "total_token_usage_hash",
    "token_count_payload_hash",
    "content_event_hash",
    "is_active_session",
    "is_archived_session",
    "missing_last_token_usage",
    "missing_total_token_usage",
    "accounting_included",
    "duplicate_segment_of",
    "model_context_window",
    "primary_used_percent",
    "primary_window_minutes",
    "primary_resets_at",
    "secondary_used_percent",
    "secondary_window_minutes",
    "secondary_resets_at",
    "credits_has_credits",
    "credits_unlimited",
    "credits_balance",
    "plan_type",
    "rate_limit_reached_type",
    "cwd",
    "repo_root",
    "github_repo",
    "git_origin_url",
    "git_branch",
    "git_sha",
    "workstream_label",
    "outcome_type",
    "attribution_confidence",
    "evidence_path",
    "sensitivity_notes",
    "inserted_by_run",
]

RAW_TOKEN_EVENT_COLUMNS = TOKEN_EVENT_COLUMNS

TOKEN_TURN_ESTIMATE_COLUMNS = [
    "session_segment_id",
    "thread_id",
    "turn_id",
    "turn_group_key",
    "github_repo",
    "workstream_label",
    "outcome_type",
    "attribution_confidence",
    "first_event_at",
    "last_event_at",
    "token_event_count",
    "observed_event_sum_tokens",
    "unique_last_per_thread_turn_tokens",
    "unique_last_per_session_turn_tokens",
    "unique_last_per_turn_tokens",
    "deduped_turn_tokens",
    "repeated_last_usage_count",
    "missing_turn_id_count",
]

TOKEN_SESSION_ROLLUP_COLUMNS = [
    "session_segment_id",
    "thread_id",
    "source_path",
    "rollout_path",
    "is_active_session",
    "is_archived_session",
    "accounting_included",
    "duplicate_segment_of",
    "github_repo",
    "workstream_label",
    "outcome_type",
    "attribution_confidence",
    "first_event_at",
    "last_event_at",
    "token_event_count",
    "distinct_turn_count",
    "observed_event_sum_tokens",
    "max_cumulative_tokens",
    "final_session_total_tokens",
    "cumulative_delta_tokens",
    "unique_last_per_session_turn_tokens",
    "unique_last_per_turn_tokens",
    "deduped_turn_tokens",
    "repeated_last_usage_count",
    "repeated_cumulative_count",
    "cumulative_reset_count",
    "missing_turn_id_count",
    "zero_cumulative_event_count",
    "inflation_factor_current_vs_max_cumulative",
    "inflation_factor_current_vs_delta",
    "warning_flags",
]

TOKEN_THREAD_ROLLUP_COLUMNS = [
    "thread_id",
    "github_repo",
    "workstream_label",
    "outcome_type",
    "attribution_confidence",
    "first_event_at",
    "last_event_at",
    "token_event_count",
    "distinct_turn_count",
    "session_segment_count",
    "included_session_segment_count",
    "excluded_duplicate_session_segment_count",
    "active_session_segment_count",
    "archived_session_segment_count",
    "active_archived_overlap",
    "observed_event_sum_tokens",
    "max_cumulative_tokens",
    "final_session_total_tokens",
    "final_thread_total_tokens",
    "cumulative_delta_tokens",
    "unique_last_per_thread_turn_tokens",
    "unique_last_per_session_turn_tokens",
    "unique_last_per_turn_tokens",
    "deduped_turn_tokens",
    "repeated_last_usage_count",
    "repeated_cumulative_count",
    "cumulative_reset_count",
    "missing_turn_id_count",
    "inflation_factor_current_vs_max_cumulative",
    "inflation_factor_current_vs_delta",
    "warning_flags",
]

TOKEN_ACCOUNTING_RECONCILIATION_COLUMNS = [
    "grain",
    "group_key",
    "period_start",
    "period_end",
    "thread_id",
    "github_repo",
    "workstream_label",
    "outcome_type",
    "attribution_confidence",
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
    "session_segment_count_metric",
    "cumulative_reset_count",
    "missing_turn_id_count",
    "inflation_factor_current_vs_max_cumulative",
    "inflation_factor_current_vs_delta",
    "warning_flags",
]

TOKEN_EVENT_ACCOUNTING_COLUMNS = [
    "event_id",
    "session_segment_id",
    "thread_id",
    "turn_id",
    "timestamp",
    "line_number",
    "github_repo",
    "workstream_label",
    "outcome_type",
    "attribution_confidence",
    "observed_event_sum_tokens",
    "cumulative_delta_tokens",
    "delta_input_tokens",
    "delta_cached_input_tokens",
    "delta_output_tokens",
    "delta_reasoning_output_tokens",
    "last_token_usage_hash",
    "total_token_usage_hash",
    "accounting_included",
    "cumulative_reset",
    "warning_flags",
]

THREAD_COLUMNS = [
    "thread_id",
    "created_at",
    "updated_at",
    "rollout_path",
    "cwd",
    "session_cwd",
    "repo_root",
    "github_repo",
    "git_origin_url",
    "git_branch",
    "git_sha",
    "source",
    "thread_source",
    "model",
    "reasoning_effort",
    "title",
    "preview",
    "tokens_used",
    "event_count",
    "first_token_event_at",
    "last_token_event_at",
    "workstream_label",
    "outcome_type",
    "attribution_confidence",
    "evidence_paths",
    "updated_by_run",
]

GITHUB_EVENT_COLUMNS = [
    "github_event_id",
    "repo",
    "event_kind",
    "artifact_type",
    "artifact_id",
    "timestamp",
    "actor",
    "sha",
    "branch",
    "title",
    "state",
    "merged",
    "url",
    "labels",
    "file_path",
    "additions",
    "deletions",
    "inserted_by_run",
]

VALUE_ALLOCATION_COLUMNS = [
    "event_id",
    "session_segment_id",
    "thread_id",
    "timestamp",
    "accounting_basis",
    "total_tokens",
    "funding_source",
    "allocated_tokens",
    "allocated_usd",
    "unit_usd_per_token",
    "entitlement_source",
    "confidence",
    "evidence_path",
    "inserted_by_run",
]


def utc_now() -> dt.datetime:
    return dt.datetime.now(UTC)


def run_id_now() -> str:
    return utc_now().strftime("%Y%m%dT%H%M%SZ")


def parse_time(value: Any) -> dt.datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        raw = float(value)
        if raw > 10_000_000_000:
            raw = raw / 1000.0
        return dt.datetime.fromtimestamp(raw, UTC)
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def isoformat(value: dt.datetime | None) -> str:
    if value is None:
        return ""
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_window(spec: str, *, now: dt.datetime | None = None) -> dt.datetime:
    now = now or utc_now()
    text = spec.strip().lower()
    match = re.fullmatch(r"(\d+)([dhm])", text)
    if match:
        amount = int(match.group(1))
        unit = match.group(2)
        if unit == "d":
            return now - dt.timedelta(days=amount)
        if unit == "h":
            return now - dt.timedelta(hours=amount)
        return now - dt.timedelta(minutes=amount)
    parsed = parse_time(spec)
    if parsed is None:
        raise ValueError(f"Invalid time/window value: {spec!r}")
    return parsed


def window_label(spec: str) -> str:
    return spec.strip().replace(" ", "_").replace("/", "_")


def safe_int(value: Any, default: int = 0) -> int:
    if value in (None, ""):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_float(value: Any) -> str:
    if value in (None, ""):
        return ""
    try:
        return str(float(value))
    except (TypeError, ValueError):
        return ""


def sha1_text(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8"), usedforsecurity=False).hexdigest()


def parse_github_repo(origin: str | None) -> str:
    if not origin:
        return ""
    text = origin.strip()
    match = re.search(r"github\.com[:/]([^/\s]+)/([^/\s]+?)(?:\.git)?$", text)
    if not match:
        return ""
    return f"{match.group(1)}/{match.group(2)}"


def infer_outcome_type(text: str) -> str:
    lower = text.lower()
    keyword_map = {
        "docs": ("doc", "readme", "writeup", "report"),
        "tests": ("test", "pytest", "coverage"),
        "bugfix": ("bug", "fix", "repair", "regression"),
        "release": ("release", "tag", "publish", "version"),
        "infra": ("aws", "deploy", "cluster", "s3", "cloudfront", "terraform"),
        "workflow": ("workflow", "snakemake", "pipeline", "automation"),
        "review": ("review", "pr", "pull request"),
        "planning": ("plan", "ledger", "roadmap"),
        "investigation": ("debug", "triage", "inspect", "forensic"),
        "ops": ("ops", "monitor", "status", "backup"),
        "feature": ("feature", "capability", "add "),
        "improvement": ("improve", "refactor", "cleanup", "polish"),
    }
    for outcome, needles in keyword_map.items():
        if any(needle in lower for needle in needles):
            return outcome
    return "unknown"


def workstream_label(github_repo: str, cwd: str, branch: str, title: str = "") -> str:
    if github_repo:
        return github_repo.split("/", 1)[1]
    if cwd:
        return Path(cwd).name or cwd
    if branch:
        return branch
    if title:
        return title[:48]
    return "unknown"


def ensure_output_dirs(output_root: Path) -> None:
    for name in ("config", "data", "reports", "plots", "runs"):
        (output_root / name).mkdir(parents=True, exist_ok=True)
