from __future__ import annotations

import datetime as dt
import hashlib
import os
import re
from pathlib import Path
from typing import Any

UTC = dt.timezone.utc

DEFAULT_CODEX_HOME = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
DEFAULT_OUTPUT_ROOT = DEFAULT_CODEX_HOME / "docs" / "codex-github-outcomes"

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
    "thread_id",
    "turn_id",
    "timestamp",
    "rollout_path",
    "line_number",
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
    "thread_id",
    "timestamp",
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
