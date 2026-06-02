# wlat Examples

All tabular examples are TSV. Do not convert these examples to CSV.

## January 2026 Forward Backfill

```console
wlat backfill \
  --since 2026-01-01T00:00:00Z \
  --codex-home /Users/jmajor/.codex \
  --output-root /Users/jmajor/Downloads/wlat-v2.1 \
  --repo-root /Users/jmajor/projects \
  --repo-root /Users/jmajor/IGNORE-THIS
```

Validate the generated bundle:

```console
wlat validate --output-root /Users/jmajor/Downloads/wlat-v2.1
```

Package the generated bundle without macOS AppleDouble files:

```console
COPYFILE_DISABLE=1 tar --exclude='._*' -czf /Users/jmajor/Downloads/wlat-v2.1.tgz -C /Users/jmajor/Downloads wlat-v2.1
```

## Entitlement Overlay Example

Use `token_entitlements.example.tsv` as a shape example only. Replace the amounts, token allocations, source, confidence, and evidence path with explicit records before using value allocation or entitlement overlays.

```console
wlat allocate-value \
  --window 30d \
  --output-root /Users/jmajor/Downloads/wlat-v2.1 \
  --entitlements examples/token_entitlements.example.tsv
```
