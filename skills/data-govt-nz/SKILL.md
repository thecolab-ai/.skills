---
name: data-govt-nz
description: Search and inspect New Zealand Government open-data catalogue datasets, organisations, resources, and datastore records through the public CKAN API at catalogue.data.govt.nz. Use when the task involves finding NZ public datasets, agencies, downloadable resources, CSV/API links, metadata, or data.govt.nz catalogue records. Read-only and no API key required.
---

# data.govt.nz Catalogue

## Goal

Query New Zealand's public open-data catalogue through a deterministic no-login CLI backed by the CKAN API.

## Use this when

- A user asks what public NZ datasets exist for a topic
- A workflow needs dataset metadata, organisations, resource URLs, or formats
- A user has a data.govt.nz dataset ID/name and wants details
- A workflow needs a small preview from a CKAN datastore resource

## Do not use this for

- Authenticated agency portals or non-public datasets
- Bulk mirroring the entire catalogue
- Treating catalogue metadata as authoritative source data without checking the linked source resource

## CLI

```bash
python3 skills/data-govt-nz/scripts/cli.py search "water quality" --json
python3 skills/data-govt-nz/scripts/cli.py dataset waterpoint --json
python3 skills/data-govt-nz/scripts/cli.py orgs --limit 20
python3 skills/data-govt-nz/scripts/cli.py resource <resource-id> --limit 5 --json
```

Commands:

- `search QUERY [--limit N] [--json]` - catalogue dataset search
- `dataset ID_OR_NAME [--json]` - full dataset/package metadata
- `orgs [--limit N] [--json]` - list catalogue organisations
- `resource RESOURCE_ID [--limit N] [--json]` - datastore preview when available

## Resources

- CLI: `scripts/cli.py`
- Smoke test: `scripts/smoke_test.py`
- API notes: `references/api-notes.md`
