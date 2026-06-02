from __future__ import annotations

from pathlib import Path
from typing import Any

from well_look_at_that.accounting import accounting_snapshot
from well_look_at_that.model import VALUE_ALLOCATION_COLUMNS, parse_time, safe_int
from well_look_at_that.tsv import read_tsv, write_tsv


def _money(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def allocate_value(*, output_root: Path, entitlements: Path, since, run_id: str) -> dict[str, Any]:
    output_root = output_root.expanduser()
    entitlements = entitlements.expanduser()
    if not entitlements.exists():
        raise FileNotFoundError(f"Entitlement TSV does not exist: {entitlements}")
    entitlement_rows = read_tsv(entitlements)
    if not entitlement_rows:
        raise RuntimeError(f"Entitlement TSV is empty: {entitlements}")
    events = accounting_snapshot(output_root, since)["event_accounting"]
    allocations: list[dict[str, Any]] = []
    counters: dict[int, int] = {}

    for event in sorted(events, key=lambda row: row.get("timestamp", "")):
        ts = parse_time(event.get("timestamp"))
        if ts is None:
            continue
        window_index = None
        for idx, row in enumerate(entitlement_rows):
            start = parse_time(row.get("window_start"))
            end = parse_time(row.get("window_end"))
            if start and end and start <= ts < end:
                window_index = idx
                break
        tokens = safe_int(event.get("cumulative_delta_tokens"))
        if window_index is None:
            allocations.append(_allocation(event, tokens, "unpriced", 0.0, "", "missing_entitlement", "", run_id))
            continue
        entitlement = entitlement_rows[window_index]
        counters[window_index] = counters.get(window_index, 0) + tokens
        consumed = counters[window_index]
        base_tokens = safe_int(entitlement.get("base_subscription_tokens"))
        purchased_tokens = safe_int(entitlement.get("purchased_tokens"))
        source = str(entitlement.get("source") or "")
        confidence = str(entitlement.get("confidence") or "manual")
        evidence_path = str(entitlement.get("evidence_path") or entitlements)
        base_usd = _money(entitlement.get("base_subscription_usd"))
        purchased_usd = _money(entitlement.get("purchased_usd"))
        if consumed <= base_tokens and base_tokens and base_usd is not None:
            unit = base_usd / base_tokens
            allocations.append(_allocation(event, tokens, "base_subscription", tokens * unit, source, confidence, evidence_path, run_id, unit))
        elif consumed <= base_tokens + purchased_tokens and purchased_tokens and purchased_usd is not None:
            unit = purchased_usd / purchased_tokens
            allocations.append(_allocation(event, tokens, "purchased_tokens", tokens * unit, source, confidence, evidence_path, run_id, unit))
        else:
            allocations.append(_allocation(event, tokens, "unpriced", 0.0, source, "missing_unit_price_or_allocation", evidence_path, run_id))

    write_tsv(output_root / "data" / "token_value_allocations.tsv", allocations, VALUE_ALLOCATION_COLUMNS)
    rollups: dict[str, dict[str, Any]] = {}
    for row in allocations:
        key = str(row["funding_source"])
        dest = rollups.setdefault(
            key,
            {"funding_source": key, "event_count": 0, "allocated_tokens": 0, "allocated_usd": 0.0},
        )
        dest["event_count"] += 1
        dest["allocated_tokens"] += safe_int(row.get("allocated_tokens"))
        dest["allocated_usd"] += float(row.get("allocated_usd") or 0.0)
    write_tsv(
        output_root / "reports" / f"{run_id}_token_value_rollups.tsv",
        list(rollups.values()),
        ["funding_source", "event_count", "allocated_tokens", "allocated_usd"],
    )
    write_tsv(
        output_root / "reports" / "latest_token_value_rollups.tsv",
        list(rollups.values()),
        ["funding_source", "event_count", "allocated_tokens", "allocated_usd"],
    )
    return {"value_allocations_written": len(allocations), "value_rollup_rows": len(rollups)}


def _allocation(
    event: dict[str, str],
    tokens: int,
    funding_source: str,
    allocated_usd: float,
    source: str,
    confidence: str,
    evidence_path: str,
    run_id: str,
    unit: float = 0.0,
) -> dict[str, Any]:
    return {
        "event_id": event.get("event_id", ""),
        "session_segment_id": event.get("session_segment_id", ""),
        "thread_id": event.get("thread_id", ""),
        "timestamp": event.get("timestamp", ""),
        "accounting_basis": "cumulative_delta_tokens",
        "total_tokens": tokens,
        "funding_source": funding_source,
        "allocated_tokens": tokens,
        "allocated_usd": f"{allocated_usd:.6f}",
        "unit_usd_per_token": f"{unit:.12f}" if unit else "",
        "entitlement_source": source,
        "confidence": confidence,
        "evidence_path": evidence_path,
        "inserted_by_run": run_id,
    }
