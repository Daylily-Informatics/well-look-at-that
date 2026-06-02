from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from well_look_at_that.model import GITHUB_EVENT_COLUMNS, isoformat, parse_time, sha1_text
from well_look_at_that.redaction import redact_text
from well_look_at_that.tsv import read_tsv, write_tsv


def _gh_json(args: list[str], *, timeout: int = 60) -> Any:
    if shutil.which("gh") is None:
        raise RuntimeError("GitHub collection requires the gh CLI, but gh is not on PATH.")
    result = subprocess.run(
        ["gh", *args],
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args)} failed: {result.stderr.strip()}")
    return json.loads(result.stdout or "[]")


def _repo_names(output_root: Path, max_repos: int) -> list[str]:
    rows = read_tsv(output_root / "data" / "codex_threads.tsv")
    repos = sorted({row.get("github_repo", "") for row in rows if row.get("github_repo")})
    return repos[:max_repos]


def _actor(login_obj: Any) -> str:
    if isinstance(login_obj, dict):
        return str(login_obj.get("login") or "")
    return ""


def collect_github(
    *,
    output_root: Path,
    since,
    run_id: str,
    max_repos: int = 120,
) -> dict[str, Any]:
    repos = _repo_names(output_root, max_repos)
    rows: list[dict[str, Any]] = []
    since_iso = isoformat(since)
    _gh_json(["auth", "status"], timeout=20)
    for repo in repos:
        commits = _gh_json(
            ["api", f"repos/{repo}/commits", "--paginate", "-f", f"since={since_iso}"],
            timeout=90,
        )
        if isinstance(commits, dict):
            commits = [commits]
        for item in commits:
            sha = str(item.get("sha") or "")
            timestamp = (
                (item.get("commit") or {}).get("author") or {}
            ).get("date") or ""
            rows.append(
                {
                    "github_event_id": sha1_text(f"{repo}:commit:{sha}"),
                    "repo": repo,
                    "event_kind": "commit",
                    "artifact_type": "commit",
                    "artifact_id": sha[:12],
                    "timestamp": isoformat(parse_time(timestamp)),
                    "actor": _actor(item.get("author")) or str(((item.get("commit") or {}).get("author") or {}).get("name") or ""),
                    "sha": sha,
                    "branch": "",
                    "title": redact_text(str(((item.get("commit") or {}).get("message") or "").splitlines()[0])),
                    "state": "",
                    "merged": "",
                    "url": str(item.get("html_url") or ""),
                    "labels": "",
                    "file_path": "",
                    "additions": "",
                    "deletions": "",
                    "inserted_by_run": run_id,
                }
            )

        pulls = _gh_json(
            ["api", f"repos/{repo}/pulls", "--paginate", "-f", "state=all", "-f", "sort=updated", "-f", "direction=desc"],
            timeout=90,
        )
        if isinstance(pulls, dict):
            pulls = [pulls]
        for item in pulls:
            updated = parse_time(item.get("updated_at"))
            if updated is None or updated < since:
                continue
            number = str(item.get("number") or "")
            rows.append(
                {
                    "github_event_id": sha1_text(f"{repo}:pull:{number}:{item.get('updated_at')}"),
                    "repo": repo,
                    "event_kind": "pull_request",
                    "artifact_type": "pull_request",
                    "artifact_id": number,
                    "timestamp": isoformat(updated),
                    "actor": _actor(item.get("user")),
                    "sha": str(((item.get("head") or {}).get("sha")) or ""),
                    "branch": str(((item.get("head") or {}).get("ref")) or ""),
                    "title": redact_text(str(item.get("title") or "")),
                    "state": str(item.get("state") or ""),
                    "merged": "1" if item.get("merged_at") else "0",
                    "url": str(item.get("html_url") or ""),
                    "labels": ",".join(sorted(str(label.get("name") or "") for label in item.get("labels") or [])),
                    "file_path": "",
                    "additions": str(item.get("additions") or ""),
                    "deletions": str(item.get("deletions") or ""),
                    "inserted_by_run": run_id,
                }
            )

        issues = _gh_json(
            ["api", f"repos/{repo}/issues", "--paginate", "-f", "state=all", "-f", "sort=updated", "-f", "direction=desc"],
            timeout=90,
        )
        if isinstance(issues, dict):
            issues = [issues]
        for item in issues:
            if "pull_request" in item:
                continue
            updated = parse_time(item.get("updated_at"))
            if updated is None or updated < since:
                continue
            number = str(item.get("number") or "")
            rows.append(
                {
                    "github_event_id": sha1_text(f"{repo}:issue:{number}:{item.get('updated_at')}"),
                    "repo": repo,
                    "event_kind": "issue",
                    "artifact_type": "issue",
                    "artifact_id": number,
                    "timestamp": isoformat(updated),
                    "actor": _actor(item.get("user")),
                    "sha": "",
                    "branch": "",
                    "title": redact_text(str(item.get("title") or "")),
                    "state": str(item.get("state") or ""),
                    "merged": "",
                    "url": str(item.get("html_url") or ""),
                    "labels": ",".join(sorted(str(label.get("name") or "") for label in item.get("labels") or [])),
                    "file_path": "",
                    "additions": "",
                    "deletions": "",
                    "inserted_by_run": run_id,
                }
            )

    write_tsv(output_root / "data" / "github_events.tsv", rows, GITHUB_EVENT_COLUMNS)
    return {"github_repos_seen": len(repos), "github_events_written": len(rows)}
