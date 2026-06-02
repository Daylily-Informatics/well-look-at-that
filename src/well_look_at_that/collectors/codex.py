from __future__ import annotations

import json
import sqlite3
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

from well_look_at_that.model import (
    RAW_TOKEN_EVENT_COLUMNS,
    THREAD_COLUMNS,
    TOKEN_EVENT_COLUMNS,
    infer_outcome_type,
    isoformat,
    parse_github_repo,
    parse_time,
    safe_float,
    safe_int,
    sha1_text,
    workstream_label,
)
from well_look_at_that.tsv import write_tsv


def _session_paths(codex_home: Path) -> list[Path]:
    candidates: list[Path] = []
    for name in ("sessions", "archived_sessions"):
        root = codex_home / name
        if root.exists():
            candidates.extend(root.glob("**/*.jsonl"))
    return sorted(path for path in candidates if path.is_file())


def _infer_thread_id_from_path(path: Path) -> str:
    stem = path.stem
    for part in stem.split("-"):
        if len(part) == 36 and part.count("-") == 4:
            return part
    text = str(path)
    marker = "019"
    start = text.find(marker)
    if start >= 0:
        candidate = text[start : start + 36]
        if len(candidate) == 36 and candidate.count("-") == 4:
            return candidate
    return ""


def _json_hash(value: Any) -> str:
    if value in (None, ""):
        return ""
    text = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return sha1_text(text)


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _session_segment_id(thread_id: str, path: Path) -> str:
    return sha1_text(f"{thread_id}\t{path}")


def _git_value(cwd: str | Path, args: list[str]) -> str:
    if not cwd:
        return ""
    path = Path(cwd).expanduser()
    if not path.exists() or not path.is_dir():
        return ""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=path,
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _explicit_repo_base(cwd: str, repo_roots: list[Path]) -> Path | None:
    if not cwd or not repo_roots:
        return None
    cwd_path = Path(cwd).expanduser()
    roots = [root.expanduser() for root in repo_roots]
    for candidate in (cwd_path, *cwd_path.parents):
        if not any(candidate == root or _is_relative_to(candidate, root) for root in roots):
            continue
        if (candidate / ".git").exists():
            return candidate
    return None


def _repo_info(cwd: str, repo_roots: list[Path] | None = None) -> dict[str, str]:
    roots = repo_roots or []
    repo_root = _git_value(cwd, ["rev-parse", "--show-toplevel"])
    git_cwd = Path(repo_root) if repo_root else _explicit_repo_base(cwd, roots)
    if git_cwd is None:
        git_cwd = Path(cwd).expanduser() if cwd else Path()
    if not repo_root and git_cwd:
        repo_root = _git_value(git_cwd, ["rev-parse", "--show-toplevel"])
    git_origin = _git_value(git_cwd, ["config", "--get", "remote.origin.url"])
    git_branch = _git_value(git_cwd, ["rev-parse", "--abbrev-ref", "HEAD"])
    git_sha = _git_value(git_cwd, ["rev-parse", "HEAD"])
    github_repo = parse_github_repo(git_origin)
    return {
        "repo_root": repo_root,
        "git_origin_url": git_origin,
        "git_branch": "" if git_branch == "HEAD" else git_branch,
        "git_sha": git_sha,
        "github_repo": github_repo,
    }


def _row_get(row: sqlite3.Row, *names: str) -> Any:
    keys = set(row.keys())
    for name in names:
        if name in keys:
            return row[name]
    return ""


def _load_state_threads(
    codex_home: Path,
    since,
    repo_roots: list[Path],
) -> dict[str, dict[str, Any]]:
    state_db = codex_home / "state_5.sqlite"
    if not state_db.exists():
        return {}
    threads: dict[str, dict[str, Any]] = {}
    conn = sqlite3.connect(state_db)
    conn.row_factory = sqlite3.Row
    try:
        tables = {
            row["name"]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if "threads" not in tables:
            return {}
        for row in conn.execute("SELECT * FROM threads"):
            thread_id = str(_row_get(row, "thread_id", "id"))
            if not thread_id:
                continue
            updated = parse_time(_row_get(row, "updated_at", "updatedAt"))
            created = parse_time(_row_get(row, "created_at", "createdAt"))
            if updated and updated < since:
                continue
            cwd = str(_row_get(row, "cwd"))
            repo = _repo_info(cwd, repo_roots)
            github_repo = str(_row_get(row, "github_repo", "githubRepo")) or repo["github_repo"]
            branch = str(_row_get(row, "git_branch", "gitBranch")) or repo["git_branch"]
            title = str(_row_get(row, "title"))
            preview = str(_row_get(row, "preview"))
            workstream = workstream_label(github_repo, cwd, branch, title)
            threads[thread_id] = {
                "thread_id": thread_id,
                "created_at": isoformat(created),
                "updated_at": isoformat(updated),
                "rollout_path": str(_row_get(row, "rollout_path", "rolloutPath")),
                "cwd": cwd,
                "session_cwd": "",
                "repo_root": str(_row_get(row, "repo_root", "repoRoot")) or repo["repo_root"],
                "github_repo": github_repo,
                "git_origin_url": str(_row_get(row, "git_origin_url", "gitOriginUrl"))
                or repo["git_origin_url"],
                "git_branch": branch,
                "git_sha": str(_row_get(row, "git_sha", "gitSha")) or repo["git_sha"],
                "source": str(_row_get(row, "source")),
                "thread_source": str(_row_get(row, "thread_source", "threadSource")),
                "model": str(_row_get(row, "model")),
                "reasoning_effort": str(_row_get(row, "reasoning_effort", "reasoningEffort")),
                "title": title,
                "preview": preview,
                "tokens_used": safe_int(_row_get(row, "tokens_used", "tokensUsed")),
                "event_count": 0,
                "first_token_event_at": "",
                "last_token_event_at": "",
                "workstream_label": workstream,
                "outcome_type": infer_outcome_type(" ".join([title, preview, branch, workstream])),
                "attribution_confidence": "strong" if github_repo else ("derived" if cwd else "weak"),
                "evidence_paths": str(state_db),
                "updated_by_run": "",
            }
    finally:
        conn.close()
    return threads


def _thread_from_session(
    thread_id: str,
    path: Path,
    timestamp: str,
    session_meta: dict[str, Any],
    run_id: str,
    repo_roots: list[Path],
) -> dict[str, Any]:
    cwd = str(session_meta.get("cwd") or "")
    repo = _repo_info(cwd, repo_roots)
    title = str(session_meta.get("title") or "")
    branch = repo["git_branch"]
    github_repo = repo["github_repo"]
    workstream = workstream_label(github_repo, cwd, branch, title)
    created = parse_time(session_meta.get("timestamp")) or parse_time(timestamp)
    return {
        "thread_id": thread_id,
        "created_at": isoformat(created),
        "updated_at": isoformat(created),
        "rollout_path": str(path),
        "cwd": cwd,
        "session_cwd": cwd,
        "repo_root": repo["repo_root"],
        "github_repo": github_repo,
        "git_origin_url": repo["git_origin_url"],
        "git_branch": branch,
        "git_sha": repo["git_sha"],
        "source": str(session_meta.get("source") or ""),
        "thread_source": str(session_meta.get("thread_source") or ""),
        "model": str(session_meta.get("model") or ""),
        "reasoning_effort": str(session_meta.get("reasoning_effort") or ""),
        "title": title,
        "preview": "",
        "tokens_used": 0,
        "event_count": 0,
        "first_token_event_at": "",
        "last_token_event_at": "",
        "workstream_label": workstream,
        "outcome_type": infer_outcome_type(" ".join([title, branch, workstream])),
        "attribution_confidence": "strong" if github_repo else ("derived" if cwd else "weak"),
        "evidence_paths": str(path),
        "updated_by_run": run_id,
    }


def collect_codex(
    *,
    codex_home: Path,
    output_root: Path,
    since,
    run_id: str,
    repo_roots: list[Path] | None = None,
) -> dict[str, Any]:
    codex_home = codex_home.expanduser()
    output_root = output_root.expanduser()
    if not codex_home.exists():
        raise FileNotFoundError(f"Codex home does not exist: {codex_home}")

    paths = _session_paths(codex_home)
    if not paths:
        raise RuntimeError(f"No Codex session JSONL files found under {codex_home}")

    explicit_roots = [root.expanduser() for root in (repo_roots or [])]
    missing_roots = [str(root) for root in explicit_roots if not root.exists()]
    if missing_roots:
        raise FileNotFoundError(f"Explicit repo roots do not exist: {', '.join(missing_roots)}")

    threads = _load_state_threads(codex_home, since, explicit_roots)
    counts = Counter({"jsonl_files_seen": len(paths), "state_threads_loaded": len(threads)})
    events: list[dict[str, Any]] = []

    for path in paths:
        inferred_thread_id = _infer_thread_id_from_path(path)
        current_thread_id = inferred_thread_id
        current_turn_id = ""
        session_meta: dict[str, Any] = {}
        try:
            handle = path.open("r", encoding="utf-8")
        except OSError:
            counts["jsonl_files_unreadable"] += 1
            continue
        with handle:
            for line_number, line in enumerate(handle, 1):
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    counts["json_decode_errors"] += 1
                    continue

                record_type = record.get("type")
                payload = record.get("payload") or {}
                if isinstance(payload, dict):
                    current_turn_id = str(payload.get("turn_id") or payload.get("turnId") or current_turn_id)

                if record_type == "session_meta":
                    session_meta = payload if isinstance(payload, dict) else {}
                    current_thread_id = str(session_meta.get("id") or current_thread_id)
                    if current_thread_id:
                        thread = threads.get(current_thread_id) or _thread_from_session(
                            current_thread_id,
                            path,
                            str(record.get("timestamp") or ""),
                            session_meta,
                            run_id,
                            explicit_roots,
                        )
                        thread["session_cwd"] = str(session_meta.get("cwd") or thread.get("session_cwd") or "")
                        thread["rollout_path"] = thread.get("rollout_path") or str(path)
                        thread["evidence_paths"] = ";".join(
                            sorted({p for p in [str(thread.get("evidence_paths") or ""), str(path)] if p})
                        )
                        thread["updated_by_run"] = run_id
                        threads[current_thread_id] = thread
                    continue

                if record_type != "event_msg" or not isinstance(payload, dict):
                    continue
                if payload.get("type") != "token_count":
                    continue
                ts = parse_time(record.get("timestamp"))
                if ts is None:
                    counts["token_events_missing_timestamp"] += 1
                    continue
                if ts < since:
                    continue
                thread_id = current_thread_id or inferred_thread_id
                if not thread_id:
                    counts["token_events_missing_thread"] += 1
                    continue
                if thread_id not in threads:
                    threads[thread_id] = _thread_from_session(
                        thread_id,
                        path,
                        str(record.get("timestamp") or ""),
                        session_meta,
                        run_id,
                        explicit_roots,
                    )
                thread = threads[thread_id]
                info = payload.get("info") or {}
                last = info.get("last_token_usage") or {}
                cumulative = info.get("total_token_usage") or {}
                rate_limits = payload.get("rate_limits") or {}
                primary = rate_limits.get("primary") or {}
                secondary = rate_limits.get("secondary") or {}
                credits = rate_limits.get("credits")
                credits = credits if isinstance(credits, dict) else {}
                raw_event_id = str(
                    record.get("id")
                    or record.get("event_id")
                    or record.get("eventId")
                    or payload.get("id")
                    or payload.get("event_id")
                    or payload.get("eventId")
                    or ""
                )
                event_id = sha1_text(f"{path}:{line_number}:{record.get('timestamp')}:{thread_id}")
                segment_id = _session_segment_id(thread_id, path)
                is_active = 1 if _is_under(path, codex_home / "sessions") else 0
                is_archived = 1 if _is_under(path, codex_home / "archived_sessions") else 0
                event = {
                    "event_id": event_id,
                    "raw_event_id": raw_event_id,
                    "thread_id": thread_id,
                    "turn_id": current_turn_id,
                    "timestamp": isoformat(ts),
                    "source_path": str(path),
                    "rollout_path": str(path),
                    "line_number": line_number,
                    "session_segment_id": segment_id,
                    "input_tokens": safe_int(last.get("input_tokens")),
                    "cached_input_tokens": safe_int(last.get("cached_input_tokens")),
                    "output_tokens": safe_int(last.get("output_tokens")),
                    "reasoning_output_tokens": safe_int(last.get("reasoning_output_tokens")),
                    "total_tokens": safe_int(last.get("total_tokens")),
                    "cumulative_input_tokens": safe_int(cumulative.get("input_tokens")),
                    "cumulative_cached_input_tokens": safe_int(cumulative.get("cached_input_tokens")),
                    "cumulative_output_tokens": safe_int(cumulative.get("output_tokens")),
                    "cumulative_reasoning_output_tokens": safe_int(
                        cumulative.get("reasoning_output_tokens")
                    ),
                    "cumulative_total_tokens": safe_int(cumulative.get("total_tokens")),
                    "last_token_usage_hash": _json_hash(last) if last else "",
                    "total_token_usage_hash": _json_hash(cumulative) if cumulative else "",
                    "token_count_payload_hash": _json_hash(payload),
                    "content_event_hash": _json_hash(
                        {
                            "thread_id": thread_id,
                            "turn_id": current_turn_id,
                            "last_token_usage": last,
                            "total_token_usage": cumulative,
                        }
                    ),
                    "is_active_session": is_active,
                    "is_archived_session": is_archived,
                    "missing_last_token_usage": 0 if last else 1,
                    "missing_total_token_usage": 0 if cumulative else 1,
                    "accounting_included": 1,
                    "duplicate_segment_of": "",
                    "model_context_window": safe_int(info.get("model_context_window")),
                    "primary_used_percent": safe_float(primary.get("used_percent")),
                    "primary_window_minutes": safe_int(primary.get("window_minutes")),
                    "primary_resets_at": isoformat(parse_time(primary.get("resets_at"))),
                    "secondary_used_percent": safe_float(secondary.get("used_percent")),
                    "secondary_window_minutes": safe_int(secondary.get("window_minutes")),
                    "secondary_resets_at": isoformat(parse_time(secondary.get("resets_at"))),
                    "credits_has_credits": 1 if credits.get("has_credits") is True else 0,
                    "credits_unlimited": 1 if credits.get("unlimited") is True else 0,
                    "credits_balance": "" if credits.get("balance") is None else str(credits.get("balance")),
                    "plan_type": str(rate_limits.get("plan_type") or ""),
                    "rate_limit_reached_type": str(rate_limits.get("rate_limit_reached_type") or ""),
                    "cwd": str(thread.get("cwd") or thread.get("session_cwd") or ""),
                    "repo_root": str(thread.get("repo_root") or ""),
                    "github_repo": str(thread.get("github_repo") or ""),
                    "git_origin_url": str(thread.get("git_origin_url") or ""),
                    "git_branch": str(thread.get("git_branch") or ""),
                    "git_sha": str(thread.get("git_sha") or ""),
                    "workstream_label": str(thread.get("workstream_label") or "unknown"),
                    "outcome_type": str(thread.get("outcome_type") or "unknown"),
                    "attribution_confidence": str(thread.get("attribution_confidence") or "weak"),
                    "evidence_path": f"{path}:{line_number}",
                    "sensitivity_notes": "raw prompt and command text excluded",
                    "inserted_by_run": run_id,
                }
                events.append(event)
                counts["token_events_extracted"] += 1
                thread["event_count"] = safe_int(thread.get("event_count")) + 1
                first = parse_time(thread.get("first_token_event_at"))
                last_seen = parse_time(thread.get("last_token_event_at"))
                if first is None or ts < first:
                    thread["first_token_event_at"] = isoformat(ts)
                if last_seen is None or ts > last_seen:
                    thread["last_token_event_at"] = isoformat(ts)
                    thread["updated_at"] = isoformat(ts)
                thread["updated_by_run"] = run_id

    thread_rows = list(threads.values())
    write_tsv(output_root / "data" / "codex_threads.tsv", thread_rows, THREAD_COLUMNS)
    write_tsv(output_root / "data" / "raw_token_events.tsv", events, RAW_TOKEN_EVENT_COLUMNS)
    write_tsv(output_root / "data" / "codex_token_events.tsv", events, TOKEN_EVENT_COLUMNS)
    counts["threads_written"] = len(thread_rows)
    counts["raw_token_events_written"] = len(events)
    counts["token_events_written"] = len(events)
    return {"counts": dict(counts), "threads": thread_rows, "events": events}
