from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

SECRET_PATTERNS = [
    ("github_token", re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}")),
    ("openai_key", re.compile(r"sk-[A-Za-z0-9]{20,}")),
    ("slack_token", re.compile(r"xox[baprs]-[A-Za-z0-9-]{20,}")),
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    (
        "secret_assignment",
        re.compile(r"(?i)(password|passwd|secret|token|api[_-]?key)\s*[:=]\s*['\"]?[^,'\"\s]{8,}"),
    ),
]


def redact_text(text: str) -> str:
    redacted = text
    for label, pattern in SECRET_PATTERNS:
        redacted = pattern.sub(f"[REDACTED:{label}]", redacted)
    return redacted


def scan_paths(paths: Iterable[Path]) -> dict[str, object]:
    findings: list[dict[str, object]] = []
    files_scanned = 0
    for path in paths:
        if not path.exists() or path.is_dir():
            continue
        if path.suffix.lower() not in {".tsv", ".md", ".html", ".svg", ".json"}:
            continue
        files_scanned += 1
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line_number, line in enumerate(lines, 1):
            for label, pattern in SECRET_PATTERNS:
                if pattern.search(line):
                    findings.append(
                        {
                            "path": str(path),
                            "line": line_number,
                            "pattern": label,
                        }
                    )
    return {
        "files_scanned": files_scanned,
        "finding_count": len(findings),
        "findings": findings,
    }
