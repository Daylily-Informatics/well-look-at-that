# wlat Examples

All tabular examples are TSV. Do not convert these examples to CSV.

## January 2026 Forward Backfill

```console
wlat backfill \
  --since 2026-01-01T00:00:00Z \
  --accounting-mode full-history-delta \
  --codex-home /Users/jmajor/.codex \
  --output-root /Users/jmajor/Downloads/wlat-v2.2 \
  --repo-root /Users/jmajor/projects \
  --repo-root /Users/jmajor/IGNORE-THIS
```

Validate the generated bundle:

```console
wlat validate --output-root /Users/jmajor/Downloads/wlat-v2.2
```

Package the generated bundle without macOS AppleDouble files:

```console
COPYFILE_DISABLE=1 tar --exclude='._*' -czf /Users/jmajor/Downloads/wlat-v2.2.tgz -C /Users/jmajor/Downloads wlat-v2.2
```

## Period-Correct 28-Day Economic Bundle

```console
wlat backfill \
  --last-days 28 \
  --accounting-mode full-history-delta \
  --economic-inputs \
  --economic-readiness \
  --price-config /Users/jmajor/Downloads/wlat-v2.2-28d/config/token_prices.yml \
  --codex-home /Users/jmajor/.codex \
  --output-root /Users/jmajor/Downloads/wlat-v2.2-28d \
  --repo-root /Users/jmajor/projects \
  --repo-root /Users/jmajor/IGNORE-THIS
```

The reporting window is applied after full-history event deltas are computed. `final_session_total_tokens` is not a period total; use `period_cumulative_delta_tokens` for economic analysis.

Create a clean share bundle:

```console
COPYFILE_DISABLE=1 tar --exclude='._*' -czf /Users/jmajor/Downloads/wlat-v2.2-28d.tgz -C /Users/jmajor/Downloads wlat-v2.2-28d
```

## Entitlement Overlay Example

Use `token_entitlements.example.tsv` as a shape example only. Replace the amounts, token allocations, source, confidence, and evidence path with explicit records before using value allocation or entitlement overlays.

```console
wlat allocate-value \
  --window 30d \
  --output-root /Users/jmajor/Downloads/wlat-v2.2 \
  --entitlements examples/token_entitlements.example.tsv
```

## Purchased Credit Price Config

Use `token_prices.example.yml` as the shape for cost scenarios. The example uses explicit evidence: purchased credits at `$0.04/credit`, ChatGPT Pro at `$200/month`, and Codex rate-card credits per 1M tokens. Subscription allocation is internal scenario modeling, not an official included-token price.
