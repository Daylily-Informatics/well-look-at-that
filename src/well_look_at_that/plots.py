from __future__ import annotations

import html
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

from well_look_at_that.model import parse_time, safe_int
from well_look_at_that.tsv import read_tsv


def _events(output_root: Path, since) -> list[dict[str, str]]:
    rows = read_tsv(output_root / "data" / "codex_token_events.tsv")
    return [row for row in rows if (parse_time(row.get("timestamp")) or since) >= since]


def _html_doc(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{html.escape(title)}</title>
<style>
body {{ font-family: ui-sans-serif, system-ui, -apple-system, sans-serif; margin: 24px; color: #1f2933; }}
h1 {{ font-size: 22px; margin: 0 0 12px; }}
.note {{ color: #52606d; font-size: 13px; margin: 8px 0 18px; }}
svg {{ max-width: 100%; height: auto; border: 1px solid #d9e2ec; background: #fff; }}
.axis {{ fill: #52606d; font-size: 11px; }}
.label {{ fill: #323f4b; font-size: 11px; }}
.grid {{ stroke: #e4e7eb; stroke-width: 1; }}
</style>
</head>
<body>
{body}
</body>
</html>
"""


def generate_plots(*, output_root: Path, since, window_label: str, run_id: str, entitlements: Path | None = None) -> dict[str, Any]:
    output_root = output_root.expanduser()
    events = _events(output_root, since)
    plot_root = output_root / "plots"
    plot_root.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "token_event_raster": _write_pair(plot_root, run_id, window_label, "token_event_raster", _token_event_raster(events)),
        "token_mix_stacked_area": _write_pair(plot_root, run_id, window_label, "token_mix_stacked_area", _token_mix(events)),
        "repo_outcome_heatmap": _write_pair(plot_root, run_id, window_label, "repo_outcome_heatmap", _heatmap(events)),
        "top_threads_sparklines": _write_pair(plot_root, run_id, window_label, "top_threads_sparklines", _sparklines(events)),
        "cumulative_burnup_entitlements": _write_pair(
            plot_root,
            run_id,
            window_label,
            "cumulative_burnup_entitlements",
            _burnup(events, entitlements),
        ),
    }
    return {"plot_count": len(artifacts), "plots": artifacts}


def _write_pair(plot_root: Path, run_id: str, window_label: str, slug: str, content: str) -> str:
    timestamped = plot_root / f"{run_id}_{window_label}_{slug}.html"
    latest = plot_root / f"latest_{window_label}_{slug}.html"
    timestamped.write_text(content, encoding="utf-8")
    latest.write_text(content, encoding="utf-8")
    return str(latest)


def _time_extent(events: list[dict[str, str]]):
    times = [parse_time(row.get("timestamp")) for row in events]
    times = [item for item in times if item is not None]
    if not times:
        return None, None
    return min(times), max(times)


def _x(ts, start, end, width: int) -> float:
    if ts is None or start is None or end is None or start == end:
        return 0
    span = (end - start).total_seconds() or 1
    return ((ts - start).total_seconds() / span) * width


def _color(tokens: int) -> str:
    if tokens <= 0:
        return "#d9e2ec"
    intensity = min(1.0, math.log10(tokens + 1) / 5.0)
    red = int(44 + intensity * 190)
    green = int(123 - intensity * 54)
    blue = int(182 - intensity * 120)
    return f"#{red:02x}{green:02x}{blue:02x}"


def _token_event_raster(events: list[dict[str, str]]) -> str:
    start, end = _time_extent(events)
    lane_names = sorted({row.get("github_repo") or row.get("workstream_label") or "(unknown)" for row in events})
    lane_map = {name: idx for idx, name in enumerate(lane_names)}
    width = 1400
    height = max(180, 24 * max(1, len(lane_names)) + 60)
    rects = []
    for row in events:
        lane = lane_map.get(row.get("github_repo") or row.get("workstream_label") or "(unknown)", 0)
        x = _x(parse_time(row.get("timestamp")), start, end, width - 220) + 190
        y = 36 + lane * 22
        tokens = safe_int(row.get("total_tokens"))
        rects.append(
            f'<rect x="{x:.1f}" y="{y}" width="2" height="14" fill="{_color(tokens)}"><title>{html.escape(row.get("thread_id", ""))} {tokens} tokens</title></rect>'
        )
    labels = [
        f'<text class="label" x="8" y="{47 + idx * 22}">{html.escape(name[:30])}</text>'
        for name, idx in lane_map.items()
    ]
    svg = f'<svg viewBox="0 0 {width} {height}" role="img">{"".join(labels)}{"".join(rects)}</svg>'
    return _html_doc(
        "Token Event Raster",
        f"<h1>Token Event Raster</h1><p class=\"note\">One mark per token_count event. Color is log-scaled total tokens.</p>{svg}",
    )


def _hour_key(timestamp: str) -> str:
    ts = parse_time(timestamp)
    if ts is None:
        return ""
    return ts.replace(minute=0, second=0, microsecond=0).isoformat().replace("+00:00", "Z")


def _token_mix(events: list[dict[str, str]]) -> str:
    buckets: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for row in events:
        key = _hour_key(row.get("timestamp", ""))
        if not key:
            continue
        for col in ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_output_tokens"):
            buckets[key][col] += safe_int(row.get(col))
    keys = sorted(buckets)
    width = 1400
    height = 460
    max_total = max((sum(buckets[key].values()) for key in keys), default=1)
    bar_w = max(1, (width - 120) / max(1, len(keys)))
    colors = {
        "input_tokens": "#2f80ed",
        "cached_input_tokens": "#27ae60",
        "output_tokens": "#f2994a",
        "reasoning_output_tokens": "#9b51e0",
    }
    bars = []
    for idx, key in enumerate(keys):
        x = 70 + idx * bar_w
        y_base = height - 60
        for col in colors:
            value = buckets[key][col]
            h = (value / max_total) * (height - 120)
            y_base -= h
            bars.append(f'<rect x="{x:.1f}" y="{y_base:.1f}" width="{max(1, bar_w - 1):.1f}" height="{h:.1f}" fill="{colors[col]}"><title>{html.escape(key)} {col}: {value}</title></rect>')
    legend = " ".join(f'<span style="color:{color}">{html.escape(col)}</span>' for col, color in colors.items())
    svg = f'<svg viewBox="0 0 {width} {height}" role="img"><line class="grid" x1="70" y1="{height-60}" x2="{width-30}" y2="{height-60}"/>{"".join(bars)}</svg>'
    return _html_doc("Token Mix Stacked Area", f"<h1>Token Mix Stacked Area</h1><p class=\"note\">Hourly stacked token mix. {legend}</p>{svg}")


def _heatmap(events: list[dict[str, str]]) -> str:
    repos = sorted({row.get("github_repo") or "(no github repo)" for row in events})
    days = sorted({(row.get("timestamp") or "")[:10] for row in events if row.get("timestamp")})
    totals: dict[tuple[str, str], int] = defaultdict(int)
    for row in events:
        totals[(row.get("github_repo") or "(no github repo)", (row.get("timestamp") or "")[:10])] += safe_int(row.get("total_tokens"))
    width = max(700, 160 + 44 * max(1, len(days)))
    height = max(180, 56 + 24 * max(1, len(repos)))
    max_tokens = max(totals.values(), default=1)
    cells = []
    for y_idx, repo in enumerate(repos):
        cells.append(f'<text class="label" x="8" y="{68 + y_idx * 24}">{html.escape(repo[:28])}</text>')
        for x_idx, day in enumerate(days):
            value = totals[(repo, day)]
            opacity = 0.12 + 0.88 * (math.log10(value + 1) / math.log10(max_tokens + 1))
            cells.append(f'<rect x="{150 + x_idx * 44}" y="{52 + y_idx * 24}" width="40" height="20" fill="#2f80ed" opacity="{opacity:.3f}"><title>{html.escape(repo)} {day}: {value} tokens</title></rect>')
    for x_idx, day in enumerate(days):
        cells.append(f'<text class="axis" x="{150 + x_idx * 44}" y="42" transform="rotate(-35 {150 + x_idx * 44},42)">{html.escape(day)}</text>')
    svg = f'<svg viewBox="0 0 {width} {height}" role="img">{"".join(cells)}</svg>'
    return _html_doc("Repo Outcome Heatmap", f"<h1>Repo Outcome Heatmap</h1><p class=\"note\">Repo by day token intensity. Empty GitHub attribution is shown as no github repo.</p>{svg}")


def _sparklines(events: list[dict[str, str]]) -> str:
    by_thread: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in events:
        by_thread[row.get("thread_id") or "unknown"].append(row)
    ranked = sorted(by_thread.items(), key=lambda item: -sum(safe_int(row.get("total_tokens")) for row in item[1]))[:40]
    width = 1400
    height = max(140, 34 * max(1, len(ranked)) + 40)
    start, end = _time_extent(events)
    marks = []
    for idx, (thread_id, rows) in enumerate(ranked):
        y = 34 + idx * 30
        total = sum(safe_int(row.get("total_tokens")) for row in rows)
        label = f"{thread_id[:8]} {total:,}"
        marks.append(f'<text class="label" x="8" y="{y + 10}">{html.escape(label)}</text>')
        marks.append(f'<line class="grid" x1="170" y1="{y+5}" x2="{width-30}" y2="{y+5}"/>')
        for row in rows:
            x = _x(parse_time(row.get("timestamp")), start, end, width - 220) + 190
            h = 4 + min(20, math.log10(safe_int(row.get("total_tokens")) + 1) * 4)
            marks.append(f'<rect x="{x:.1f}" y="{y + 5 - h:.1f}" width="3" height="{h:.1f}" fill="{_color(safe_int(row.get("total_tokens")))}"><title>{html.escape(row.get("timestamp", ""))} {safe_int(row.get("total_tokens"))} tokens</title></rect>')
    svg = f'<svg viewBox="0 0 {width} {height}" role="img">{"".join(marks)}</svg>'
    return _html_doc("Top Threads Sparklines", f"<h1>Top Threads Sparklines</h1><p class=\"note\">Top threads by tokens, with burst marks at event grain.</p>{svg}")


def _burnup(events: list[dict[str, str]], entitlements: Path | None) -> str:
    sorted_events = sorted(events, key=lambda row: row.get("timestamp", ""))
    start, end = _time_extent(sorted_events)
    width = 1400
    height = 460
    cumulative = []
    total = 0
    for row in sorted_events:
        total += safe_int(row.get("total_tokens"))
        cumulative.append((parse_time(row.get("timestamp")), total))
    entitlement_rows = read_tsv(entitlements.expanduser()) if entitlements and entitlements.exists() else []
    max_y = max([total, *[safe_int(row.get("base_subscription_tokens")) + safe_int(row.get("purchased_tokens")) for row in entitlement_rows], 1])
    points = []
    for ts, value in cumulative:
        x = _x(ts, start, end, width - 140) + 70
        y = height - 60 - (value / max_y) * (height - 120)
        points.append(f"{x:.1f},{y:.1f}")
    overlays = []
    for row in entitlement_rows:
        base = safe_int(row.get("base_subscription_tokens"))
        purchased = safe_int(row.get("purchased_tokens"))
        if base:
            y = height - 60 - (base / max_y) * (height - 120)
            overlays.append(f'<line x1="70" y1="{y:.1f}" x2="{width-30}" y2="{y:.1f}" stroke="#27ae60" stroke-width="2"><title>base subscription {base} tokens</title></line>')
        if base and purchased:
            y = height - 60 - ((base + purchased) / max_y) * (height - 120)
            overlays.append(f'<line x1="70" y1="{y:.1f}" x2="{width-30}" y2="{y:.1f}" stroke="#f2994a" stroke-width="2"><title>base plus purchased {base + purchased} tokens</title></line>')
    note = "Entitlement overlays require explicit token_entitlements.tsv rows."
    if entitlement_rows:
        note = "Green line is base subscription allocation; orange line is base plus purchased allocation."
    svg = f'<svg viewBox="0 0 {width} {height}" role="img"><line class="grid" x1="70" y1="{height-60}" x2="{width-30}" y2="{height-60}"/>{"".join(overlays)}<polyline fill="none" stroke="#2f80ed" stroke-width="2" points="{" ".join(points)}"/></svg>'
    return _html_doc("Cumulative Burnup Entitlements", f"<h1>Cumulative Burnup Entitlements</h1><p class=\"note\">{html.escape(note)}</p>{svg}")
