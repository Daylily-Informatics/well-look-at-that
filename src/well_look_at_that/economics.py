from __future__ import annotations

import datetime as dt
from collections import defaultdict
from pathlib import Path
from typing import Any

from well_look_at_that.accounting import accounting_snapshot, load_raw_token_events
from well_look_at_that.model import (
    ATTRIBUTION_DIAGNOSTIC_COLUMNS,
    ECONOMIC_COST_SCENARIO_COLUMNS,
    ECONOMIC_READINESS_COLUMNS,
    ECONOMIC_USAGE_COLUMNS,
    REPO_ATTRIBUTION_EVIDENCE_COLUMNS,
    UNATTRIBUTED_SESSION_COLUMNS,
    UNATTRIBUTED_THREAD_COLUMNS,
    WINDOW_BOUNDARY_DIAGNOSTIC_COLUMNS,
    isoformat,
    parse_time,
    safe_int,
)
from well_look_at_that.tsv import read_tsv, write_tsv

PRICE_EXAMPLE = """currency: USD
purchased_usd_per_credit: 0.04
subscription:
  plan_name: ChatGPT Pro
  monthly_usd: 200.00
  included_usage_basis: unknown_from_local_data
  allocation_method: internal_subscription_period_cost
models:
  GPT-5.5:
    input_credits_per_1m: 125
    cached_input_credits_per_1m: 12.50
    output_credits_per_1m: 750
  GPT-5.4:
    input_credits_per_1m: 62.50
    cached_input_credits_per_1m: 6.250
    output_credits_per_1m: 375
  GPT-5.4-Mini:
    input_credits_per_1m: 18.75
    cached_input_credits_per_1m: 1.875
    output_credits_per_1m: 113
  GPT-5.3-Codex:
    input_credits_per_1m: 43.75
    cached_input_credits_per_1m: 4.375
    output_credits_per_1m: 350
  GPT-5.2:
    input_credits_per_1m: 43.75
    cached_input_credits_per_1m: 4.375
    output_credits_per_1m: 350
  GPT-5.3-Codex-Spark:
    research_preview: true
"""


def generate_economic_outputs(
    *,
    output_root: Path,
    since,
    window_label: str,
    run_id: str,
    price_config: Path | None = None,
) -> dict[str, Any]:
    output_root = output_root.expanduser()
    accounting = accounting_snapshot(output_root, since)
    raw_rows = load_raw_token_events(output_root)
    period_raw = [row for row in raw_rows if _in_window(parse_time(row.get("timestamp")), since, None)]
    period_events = accounting["event_accounting"]
    diagnostics = accounting.get("window_boundary_diagnostics", [])
    report_root = output_root / "reports"
    data_root = output_root / "data"
    config_root = output_root / "config"
    config_root.mkdir(parents=True, exist_ok=True)

    write_tsv(data_root / "window_boundary_diagnostics.tsv", diagnostics, WINDOW_BOUNDARY_DIAGNOSTIC_COLUMNS)
    (data_root / "README_accounting.md").write_text(
        _accounting_readme(window_label=window_label, run_id=run_id, diagnostics=diagnostics),
        encoding="utf-8",
    )
    (config_root / "economic_price_scenarios.example.yml").write_text(PRICE_EXAMPLE, encoding="utf-8")

    event_by_id = {row.get("event_id", ""): row for row in period_events}
    boundary_by_event = {
        row.get("first_in_window_event_id", ""): safe_int(row.get("period_boundary_uncertain_tokens"))
        for row in diagnostics
    }
    tables = _economic_tables(
        period_raw=period_raw,
        event_by_id=event_by_id,
        boundary_by_event=boundary_by_event,
        since=since,
    )
    for slug, rows in tables.items():
        write_tsv(report_root / f"economic_token_usage_by_{slug}.tsv", rows, ECONOMIC_USAGE_COLUMNS)
        write_tsv(report_root / f"latest_{window_label}_economic_token_usage_by_{slug}.tsv", rows, ECONOMIC_USAGE_COLUMNS)

    readiness = _economic_readiness(tables)
    write_tsv(report_root / "economic_readiness.tsv", readiness, ECONOMIC_READINESS_COLUMNS)
    write_tsv(report_root / f"latest_{window_label}_economic_readiness.tsv", readiness, ECONOMIC_READINESS_COLUMNS)
    (report_root / "economic_readiness.md").write_text(_readiness_markdown(readiness), encoding="utf-8")
    (report_root / f"latest_{window_label}_economic_readiness.md").write_text(_readiness_markdown(readiness), encoding="utf-8")

    attribution = _attribution_outputs(output_root, period_raw, event_by_id, since)
    write_tsv(data_root / "token_attribution_diagnostics.tsv", attribution["diagnostics"], ATTRIBUTION_DIAGNOSTIC_COLUMNS)
    write_tsv(data_root / "unattributed_threads.tsv", attribution["threads"], UNATTRIBUTED_THREAD_COLUMNS)
    write_tsv(data_root / "unattributed_sessions.tsv", attribution["sessions"], UNATTRIBUTED_SESSION_COLUMNS)
    write_tsv(data_root / "repo_attribution_evidence.tsv", attribution["repo_evidence"], REPO_ATTRIBUTION_EVIDENCE_COLUMNS)

    cost_rows: list[dict[str, Any]] = []
    if price_config is not None:
        price_config = price_config.expanduser()
        if not price_config.exists():
            raise FileNotFoundError(f"Price config does not exist: {price_config}")
        pricing = _parse_price_config(price_config)
        cost_rows = _cost_rows(period_raw, event_by_id, pricing, since)
        write_tsv(report_root / "economic_cost_scenarios.tsv", cost_rows, ECONOMIC_COST_SCENARIO_COLUMNS)
        write_tsv(report_root / f"latest_{window_label}_economic_cost_scenarios.tsv", cost_rows, ECONOMIC_COST_SCENARIO_COLUMNS)
        (report_root / "economic_cost_scenarios.md").write_text(_cost_markdown(cost_rows, price_config), encoding="utf-8")
        (report_root / f"latest_{window_label}_economic_cost_scenarios.md").write_text(_cost_markdown(cost_rows, price_config), encoding="utf-8")

    return {
        "economic_usage_tables": len(tables),
        "economic_readiness_rows": len(readiness),
        "window_boundary_diagnostic_rows": len(diagnostics),
        "attribution_diagnostic_rows": len(attribution["diagnostics"]),
        "economic_cost_rows": len(cost_rows),
    }


def _in_window(timestamp, since, until=None) -> bool:
    if timestamp is None:
        return False
    if since is not None and timestamp < since:
        return False
    if until is not None and timestamp >= until:
        return False
    return True


def _economic_tables(
    *,
    period_raw: list[dict[str, str]],
    event_by_id: dict[str, dict[str, Any]],
    boundary_by_event: dict[str, int],
    since,
) -> dict[str, list[dict[str, Any]]]:
    return {
        "day": _usage_rows("day", period_raw, event_by_id, boundary_by_event, _day_key, since),
        "week": _usage_rows("week", period_raw, event_by_id, boundary_by_event, _week_key, since),
        "month": _usage_rows("month", period_raw, event_by_id, boundary_by_event, _month_key, since),
        "repo": _usage_rows("repo", period_raw, event_by_id, boundary_by_event, lambda row: row.get("github_repo") or "(no github repo)", since),
        "workstream": _usage_rows("workstream", period_raw, event_by_id, boundary_by_event, lambda row: row.get("workstream_label") or "unknown", since),
        "outcome": _usage_rows("outcome", period_raw, event_by_id, boundary_by_event, lambda row: row.get("outcome_type") or "unknown", since),
        "repo_workstream_outcome": _usage_rows(
            "repo_workstream_outcome",
            period_raw,
            event_by_id,
            boundary_by_event,
            lambda row: "|".join(
                [
                    row.get("github_repo") or "(no github repo)",
                    row.get("workstream_label") or "unknown",
                    row.get("outcome_type") or "unknown",
                ]
            ),
            since,
        ),
    }


def _usage_rows(grain: str, raw_rows, event_by_id, boundary_by_event, key_fn, since) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in raw_rows:
        grouped[str(key_fn(row) or "")].append(row)
    rows = []
    for group_key, group_rows in sorted(grouped.items()):
        first = sorted(group_rows, key=lambda row: row.get("timestamp", ""))[0] if group_rows else {}
        period_delta = sum(safe_int(event_by_id.get(row.get("event_id", ""), {}).get("cumulative_delta_tokens")) for row in group_rows)
        uncertain = sum(safe_int(boundary_by_event.get(row.get("event_id", ""))) for row in group_rows)
        strong = derived = unknown = 0
        for row in group_rows:
            event_tokens = safe_int(event_by_id.get(row.get("event_id", ""), {}).get("cumulative_delta_tokens"))
            confidence = (row.get("attribution_confidence") or "").lower()
            if confidence == "strong" and row.get("github_repo"):
                strong += event_tokens
            elif confidence in {"medium", "derived"}:
                derived += event_tokens
            else:
                unknown += event_tokens
        start, end = _period_bounds(grain, group_key, group_rows, since)
        rows.append(
            {
                "period_start": start,
                "period_end": end,
                "grain": grain,
                "group_key": group_key or "(blank)",
                "github_repo": first.get("github_repo", ""),
                "workstream_label": first.get("workstream_label", ""),
                "outcome_type": first.get("outcome_type", ""),
                "period_cumulative_delta_tokens": period_delta,
                "period_delta_low_tokens": max(0, period_delta - uncertain),
                "period_delta_base_tokens": period_delta,
                "period_delta_high_tokens": period_delta,
                "period_uncertainty_pct": _pct(uncertain, period_delta),
                "observed_event_sum_tokens": sum(safe_int(row.get("total_tokens")) for row in group_rows),
                "token_event_count": len(group_rows),
                "distinct_turn_count": len({(row.get("thread_id"), row.get("turn_id")) for row in group_rows if row.get("turn_id")}),
                "session_segment_count": len({row.get("session_segment_id") for row in group_rows if row.get("session_segment_id")}),
                "strong_attribution_tokens": strong,
                "derived_attribution_tokens": derived,
                "unknown_attribution_tokens": unknown,
                "strong_attribution_share": _share(strong, period_delta),
                "unknown_attribution_share": _share(unknown, period_delta),
                "boundary_uncertain_tokens": uncertain,
                "boundary_uncertain_share": _share(uncertain, period_delta),
                "recommended_analysis_use": _recommended_use(grain, period_delta, uncertain, strong, unknown),
            }
        )
    return rows


def _attribution_outputs(output_root: Path, period_raw, event_by_id, since) -> dict[str, list[dict[str, Any]]]:
    diagnostics = _usage_rows(
        "attribution_confidence",
        period_raw,
        event_by_id,
        {},
        lambda row: row.get("attribution_confidence") or "unknown",
        since,
    )
    attr_rows = [
        {
            "grain": row["grain"],
            "group_key": row["group_key"],
            "github_repo": row["github_repo"],
            "workstream_label": row["workstream_label"],
            "outcome_type": row["outcome_type"],
            "attribution_confidence": row["group_key"],
            "repo_attribution_method": "git_origin_url" if row["github_repo"] else "cwd_workspace",
            "repo_attribution_confidence": row["group_key"],
            "period_cumulative_delta_tokens": row["period_cumulative_delta_tokens"],
            "token_event_count": row["token_event_count"],
            "strong_attribution_share": row["strong_attribution_share"],
            "unknown_attribution_share": row["unknown_attribution_share"],
            "evidence_path": str(output_root / "data" / "raw_token_events.tsv"),
        }
        for row in diagnostics
    ]
    thread_groups: dict[str, dict[str, Any]] = {}
    session_groups: dict[str, dict[str, Any]] = {}
    for row in period_raw:
        tokens = safe_int(event_by_id.get(row.get("event_id", ""), {}).get("cumulative_delta_tokens"))
        if row.get("github_repo") and row.get("attribution_confidence") == "strong":
            continue
        thread = thread_groups.setdefault(
            row.get("thread_id", ""),
            {
                "thread_id": row.get("thread_id", ""),
                "cwd": row.get("cwd", ""),
                "repo_root": row.get("repo_root", ""),
                "github_repo": row.get("github_repo", ""),
                "workstream_label": row.get("workstream_label", ""),
                "outcome_type": row.get("outcome_type", ""),
                "attribution_confidence": row.get("attribution_confidence", ""),
                "period_cumulative_delta_tokens": 0,
                "token_event_count": 0,
                "evidence_paths": row.get("evidence_path", ""),
            },
        )
        thread["period_cumulative_delta_tokens"] += tokens
        thread["token_event_count"] += 1
        session = session_groups.setdefault(
            row.get("session_segment_id", ""),
            {
                "session_segment_id": row.get("session_segment_id", ""),
                "thread_id": row.get("thread_id", ""),
                "source_path": row.get("source_path", ""),
                "cwd": row.get("cwd", ""),
                "repo_root": row.get("repo_root", ""),
                "github_repo": row.get("github_repo", ""),
                "workstream_label": row.get("workstream_label", ""),
                "outcome_type": row.get("outcome_type", ""),
                "attribution_confidence": row.get("attribution_confidence", ""),
                "period_cumulative_delta_tokens": 0,
                "token_event_count": 0,
                "evidence_path": row.get("evidence_path", ""),
            },
        )
        session["period_cumulative_delta_tokens"] += tokens
        session["token_event_count"] += 1
    threads = read_tsv(output_root / "data" / "codex_threads.tsv")
    repo_evidence = [
        {
            "thread_id": row.get("thread_id", ""),
            "cwd": row.get("cwd", ""),
            "repo_root": row.get("repo_root", ""),
            "github_repo": row.get("github_repo", ""),
            "git_origin_url": row.get("git_origin_url", ""),
            "git_branch": row.get("git_branch", ""),
            "git_sha": row.get("git_sha", ""),
            "attribution_confidence": row.get("attribution_confidence", ""),
            "repo_attribution_method": "git_origin_url" if row.get("github_repo") else ("local_git_root" if row.get("repo_root") else "cwd_workspace"),
            "evidence_paths": row.get("evidence_paths", ""),
        }
        for row in threads
    ]
    return {
        "diagnostics": attr_rows,
        "threads": sorted(thread_groups.values(), key=lambda row: -safe_int(row["period_cumulative_delta_tokens"])),
        "sessions": sorted(session_groups.values(), key=lambda row: -safe_int(row["period_cumulative_delta_tokens"])),
        "repo_evidence": repo_evidence,
    }


def _economic_readiness(tables: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    aggregate = _aggregate_usage([row for rows in tables.values() for row in rows if row.get("grain") == "day"])
    rows = []
    rows.append(_readiness_row("aggregate_28d_economics", aggregate, require_attribution=False))
    rows.append(_readiness_row("repo_level_economics", _aggregate_usage(tables.get("repo", [])), require_attribution=True))
    rows.append(_readiness_row("workstream_level_economics", _aggregate_usage(tables.get("workstream", [])), require_attribution=True))
    rows.append(_readiness_row("outcome_level_economics", _aggregate_usage(tables.get("outcome", [])), require_attribution=True))
    rows.append(_readiness_row("day_week_month_trend_economics", aggregate, require_attribution=False))
    chargeback = _readiness_row("chargeback_invoicing_readiness", _aggregate_usage(tables.get("repo", [])), require_attribution=True)
    if chargeback["ready_status"] == "PASS":
        chargeback["ready_status"] = "FAIL"
        chargeback["primary_blocker"] = "chargeback requires explicit validation of accounting, attribution, pricing, and policy"
    rows.append(chargeback)
    return rows


def _aggregate_usage(rows: list[dict[str, Any]]) -> dict[str, int]:
    total = sum(safe_int(row.get("period_cumulative_delta_tokens")) for row in rows)
    return {
        "total": total,
        "uncertain": sum(safe_int(row.get("boundary_uncertain_tokens")) for row in rows),
        "strong": sum(safe_int(row.get("strong_attribution_tokens")) for row in rows),
        "derived": sum(safe_int(row.get("derived_attribution_tokens")) for row in rows),
        "unknown": sum(safe_int(row.get("unknown_attribution_tokens")) for row in rows),
    }


def _readiness_row(level: str, totals: dict[str, int], *, require_attribution: bool) -> dict[str, Any]:
    uncertainty = _pct_float(totals["uncertain"], totals["total"])
    strong_share = _pct_float(totals["strong"], totals["total"])
    unknown_share = _pct_float(totals["unknown"], totals["total"])
    status = "PASS"
    blocker = ""
    if uncertainty > 8:
        status = "CAUTION"
        blocker = "period boundary uncertainty exceeds 8 percent"
    if require_attribution and strong_share < 80:
        status = "CAUTION" if status == "PASS" else "FAIL"
        blocker = "strong attribution share below 80 percent"
    if level == "chargeback_invoicing_readiness":
        status = "FAIL"
        blocker = blocker or "chargeback requires explicit accounting, attribution, pricing, and policy approval"
    return {
        "analysis_level": level,
        "ready_status": status,
        "primary_blocker": blocker,
        "period_uncertainty_pct": f"{uncertainty:.6f}",
        "unattributed_token_share": f"{unknown_share:.6f}",
        "strong_attribution_token_share": f"{strong_share:.6f}",
        "derived_attribution_token_share": _pct(totals["derived"], totals["total"]),
        "boundary_uncertain_token_share": _pct(totals["uncertain"], totals["total"]),
        "recommended_use": "directional internal analysis" if status != "FAIL" else "not recommended",
        "not_recommended_use": "chargeback or billing-grade claims",
    }


def _parse_price_config(path: Path) -> dict[str, Any]:
    pricing: dict[str, Any] = {"models": {}}
    current_model = ""
    in_models = False
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip() or raw.strip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()
        if line == "models:":
            in_models = True
            continue
        if ":" not in line:
            continue
        key, value = [part.strip() for part in line.split(":", 1)]
        if in_models and indent == 2:
            current_model = key
            pricing["models"][current_model] = {}
            continue
        if in_models and current_model and indent >= 4:
            pricing["models"][current_model][key] = _number_or_text(value)
        elif not in_models:
            pricing[key] = _number_or_text(value)
    return pricing


def _cost_rows(period_raw, event_by_id, pricing: dict[str, Any], since) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in period_raw:
        key = (
            "|".join([row.get("github_repo") or "(no github repo)", row.get("workstream_label") or "unknown", row.get("outcome_type") or "unknown"]),
            row.get("model") or "model_unknown",
        )
        grouped[key].append(row)
    usd_per_credit = float(pricing.get("purchased_usd_per_credit") or 0)
    model_rates = {str(model).lower(): rates for model, rates in pricing.get("models", {}).items()}
    output = []
    for (group_key, model), rows in sorted(grouped.items()):
        rates = model_rates.get(model.lower(), {})
        event_rows = [event_by_id.get(row.get("event_id", ""), {}) for row in rows]
        input_tokens = sum(safe_int(row.get("delta_input_tokens")) for row in event_rows)
        cached_tokens = sum(safe_int(row.get("delta_cached_input_tokens")) for row in event_rows)
        output_tokens = sum(safe_int(row.get("delta_output_tokens")) + safe_int(row.get("delta_reasoning_output_tokens")) for row in event_rows)
        period_tokens = sum(safe_int(row.get("cumulative_delta_tokens")) for row in event_rows)
        caveat = ""
        credits = 0.0
        if model == "model_unknown":
            caveat = "model missing; per-model pricing skipped"
        elif rates.get("research_preview"):
            caveat = "research preview model has no final rate"
        elif not rates:
            caveat = "model not found in price config"
        elif not usd_per_credit:
            caveat = "missing purchased_usd_per_credit"
        else:
            credits = (
                input_tokens / 1_000_000 * float(rates.get("input_credits_per_1m") or 0)
                + cached_tokens / 1_000_000 * float(rates.get("cached_input_credits_per_1m") or 0)
                + output_tokens / 1_000_000 * float(rates.get("output_credits_per_1m") or 0)
            )
        output.append(
            {
                "period_start": isoformat(since),
                "period_end": "",
                "grain": "repo_workstream_outcome",
                "group_key": group_key,
                "scenario": "purchased_credit_cost",
                "pricing_basis": "codex_rate_card_credits_per_1m_tokens",
                "model": model,
                "period_cumulative_delta_tokens": period_tokens,
                "input_tokens": input_tokens,
                "cached_input_tokens": cached_tokens,
                "output_tokens": output_tokens,
                "reasoning_output_tokens": sum(safe_int(row.get("delta_reasoning_output_tokens")) for row in event_rows),
                "credits": f"{credits:.6f}" if credits else "",
                "usd": f"{credits * usd_per_credit:.6f}" if credits and usd_per_credit else "",
                "caveat": caveat,
            }
        )
    return output


def _period_bounds(grain: str, group_key: str, rows: list[dict[str, str]], since) -> tuple[str, str]:
    if grain in {"day", "week", "month"} and rows:
        ts = parse_time(rows[0].get("timestamp"))
        if ts is None:
            return isoformat(since), ""
        if grain == "day":
            start = ts.replace(hour=0, minute=0, second=0, microsecond=0)
            return isoformat(start), isoformat(start + dt.timedelta(days=1))
        if grain == "week":
            start = (ts - dt.timedelta(days=ts.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
            return isoformat(start), isoformat(start + dt.timedelta(days=7))
        start = ts.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = start.replace(year=start.year + 1, month=1) if start.month == 12 else start.replace(month=start.month + 1)
        return isoformat(start), isoformat(end)
    return isoformat(since), ""


def _day_key(row: dict[str, str]) -> str:
    return (row.get("timestamp") or "")[:10]


def _week_key(row: dict[str, str]) -> str:
    ts = parse_time(row.get("timestamp"))
    if ts is None:
        return ""
    return isoformat((ts - dt.timedelta(days=ts.weekday())).replace(hour=0, minute=0, second=0, microsecond=0))[:10]


def _month_key(row: dict[str, str]) -> str:
    return (row.get("timestamp") or "")[:7]


def _recommended_use(grain: str, total: int, uncertain: int, strong: int, unknown: int) -> str:
    if total <= 0:
        return "no usage"
    if _pct_float(uncertain, total) > 8:
        return "directional only; boundary uncertainty above threshold"
    if grain in {"repo", "workstream", "outcome", "repo_workstream_outcome"} and _pct_float(strong, total) < 80:
        return "directional only; attribution below threshold"
    if unknown:
        return "directional internal analysis"
    return "aggregate economic analysis"


def _accounting_readme(*, window_label: str, run_id: str, diagnostics: list[dict[str, Any]]) -> str:
    uncertain = sum(safe_int(row.get("period_boundary_uncertain_tokens")) for row in diagnostics)
    base = sum(safe_int(row.get("period_delta_base_tokens")) for row in diagnostics)
    return "\n".join(
        [
            "# WLAT Accounting Notes",
            "",
            f"- Run: `{run_id}`",
            f"- Window: `{window_label}`",
            "- Raw grain: one Codex `token_count` event.",
            "- Accounting grain: event deltas computed from full available session segment history before report-window filtering.",
            "- Primary period basis: `period_cumulative_delta_tokens`.",
            "- `observed_event_sum_tokens` is diagnostic and can be inflated by repeated events.",
            "- `final_session_total_tokens` is a lifetime/intersecting-session metric, not period usage.",
            f"- Boundary uncertain tokens: {uncertain:,}",
            f"- Boundary uncertainty percent: {_pct(uncertain, base)}",
            "- Pro subscription allocation is an internal scenario, not an official included-token price.",
        ]
    ) + "\n"


def _readiness_markdown(rows: list[dict[str, Any]]) -> str:
    lines = ["# Economic Readiness", ""]
    for row in rows:
        lines.append(
            f"- `{row['analysis_level']}`: `{row['ready_status']}`; "
            f"uncertainty `{row['period_uncertainty_pct']}%`; "
            f"strong attribution `{row['strong_attribution_token_share']}%`; "
            f"blocker `{row['primary_blocker']}`"
        )
    return "\n".join(lines) + "\n"


def _cost_markdown(rows: list[dict[str, Any]], price_config: Path) -> str:
    total = sum(float(row.get("usd") or 0) for row in rows)
    caveats = sorted({row.get("caveat", "") for row in rows if row.get("caveat")})
    lines = [
        "# Economic Cost Scenarios",
        "",
        f"- Price config: `{price_config}`",
        f"- Purchased-credit scenario total USD: `{total:.6f}`",
        "- Pricing source: explicit config derived from user-provided invoices and Codex rate card.",
        "- Subscription allocation is internal scenario modeling, not official included-token pricing.",
    ]
    if caveats:
        lines.extend(["", "## Caveats", ""])
        lines.extend(f"- {caveat}" for caveat in caveats)
    return "\n".join(lines) + "\n"


def _number_or_text(value: str) -> Any:
    value = value.strip().strip('"').strip("'")
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    try:
        return float(value)
    except ValueError:
        return value


def _share(numerator: int, denominator: int) -> str:
    return _pct(numerator, denominator)


def _pct(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "0.000000"
    return f"{(numerator / denominator) * 100:.6f}"


def _pct_float(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return (numerator / denominator) * 100
