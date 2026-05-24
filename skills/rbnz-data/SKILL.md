---
name: rbnz-data
description: Discover Reserve Bank of New Zealand public statistics datasets and resources through the data.govt.nz CKAN catalogue, including exchange-rate, wholesale-interest-rate, OCR/key-graph, lending, banking, and monetary datasets. Use when the task involves finding RBNZ dataset metadata, resource URLs, downloadable series, or datastore previews. Read-only; no authentication required for catalogue access.
---

# RBNZ Data

## Goal

Find RBNZ public statistics datasets/resources reliably through the data.govt.nz catalogue when direct rbnz.govt.nz downloads are protected by Cloudflare.

## CLI

```bash
python3 skills/rbnz-data/scripts/cli.py search "interest rates" --json
python3 skills/rbnz-data/scripts/cli.py dataset exchange-rates --json
python3 skills/rbnz-data/scripts/cli.py exchange-rates --limit 3 --json
```

Commands:

- `search QUERY [--limit N] [--json]` - RBNZ-only data.govt.nz catalogue search
- `dataset ID_OR_NAME [--json]` - package metadata and resource URLs
- `exchange-rates [--limit N] [--json]` - small CKAN datastore preview for the RBNZ exchange-rates resource where available

## Resources

- CLI: `scripts/cli.py`
- Smoke test: `scripts/smoke_test.py`
- API notes: `references/api-notes.md`
