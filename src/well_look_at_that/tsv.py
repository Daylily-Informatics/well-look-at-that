from __future__ import annotations

import csv
from collections.abc import Iterable
from pathlib import Path
from typing import Any


def require_tsv_path(path: Path) -> None:
    if path.suffix.lower() == ".csv":
        raise ValueError(f"CSV outputs are not supported: {path}")
    if path.suffix.lower() != ".tsv":
        raise ValueError(f"Tabular outputs must use .tsv: {path}")


def write_tsv(path: Path, rows: Iterable[dict[str, Any]], fieldnames: list[str]) -> None:
    require_tsv_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
            delimiter="\t",
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({key: "" if row.get(key) is None else row.get(key) for key in fieldnames})


def append_tsv(path: Path, rows: Iterable[dict[str, Any]], fieldnames: list[str]) -> None:
    require_tsv_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists() and path.stat().st_size > 0
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
            delimiter="\t",
            extrasaction="ignore",
            lineterminator="\n",
        )
        if not exists:
            writer.writeheader()
        for row in rows:
            writer.writerow({key: "" if row.get(key) is None else row.get(key) for key in fieldnames})


def read_tsv(path: Path) -> list[dict[str, str]]:
    require_tsv_path(path)
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))
