---
name: rbnz-data
description: Discover and fetch Reserve Bank of New Zealand public statistics datasets through data.govt.nz CKAN and browser-compatible rbnz.govt.nz public file/chart endpoints. Use when the task involves RBNZ exchange rates, wholesale interest rates, OCR/key graphs, retail mortgage/deposit rate charts, dataset metadata, resource URLs, downloadable XLSX series, or JSON chart-cache previews. Read-only; no authentication required.
---

# RBNZ Data

## Goal

Find RBNZ public statistics datasets/resources through the data.govt.nz catalogue, then fetch official rbnz.govt.nz public XLSX/chart endpoints using browser-compatible request headers.

## CLI

```bash
python3 skills/rbnz-data/scripts/cli.py search "interest rates" --json
python3 skills/rbnz-data/scripts/cli.py dataset exchange-rates --json
python3 skills/rbnz-data/scripts/cli.py exchange-rates --limit 3 --json
python3 skills/rbnz-data/scripts/cli.py download exchange-rates --match daily --preview
python3 skills/rbnz-data/scripts/cli.py chart retail-rates --limit 5 --json
```

Commands:

- `search QUERY [--limit N] [--json]` - RBNZ-only data.govt.nz catalogue search
- `dataset ID_OR_NAME [--json]` - package metadata and resource URLs
- `exchange-rates [--limit N] [--json]` - small CKAN datastore preview for the RBNZ exchange-rates resource where available
- `download DATASET [--match TEXT] [--preview] [--output PATH] [--json]` - fetch a matching official RBNZ public XLSX resource and optionally preview worksheet rows
- `chart {twi,retail-rates}` - fetch public RBNZ chart-cache JSON used on the Statistics page

## Resources

- CLI: `scripts/cli.py`
- Smoke test: `scripts/smoke_test.py`
- API notes: `references/api-notes.md`
