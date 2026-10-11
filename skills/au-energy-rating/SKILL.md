---
name: au-energy-rating
description: "Look up Australian and New Zealand Energy Rating labelled appliance registrations from the Australian Government data.gov.au CKAN package. Use for package metadata, resource names, the stated licence, and a short datastore preview of air conditioners, whitegoods, televisions, monitors, pool pumps, lamps or commercial ice-makers. Read-only, no API key, and it does not download the large CSV files."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "public-data"
  thecolab.source_owner: "Australian Government Department of Climate Change, Energy, the Environment and Water"
  thecolab.source_type: "official"
  thecolab.auth: "none"
  thecolab.access_mode: "public-api"
  thecolab.data_class: "public"
  thecolab.writes: "false"
  thecolab.browser: "false"
  thecolab.risk: "low"
  thecolab.cache_ttl: "none"
  thecolab.schema_version: "1"
  thecolab.skill_type: "public-api"
  thecolab.pack: "nz-public-data"
  thecolab.source_url: "https://data.gov.au/data/api/3/action/package_show?id=559708e5-480e-4f94-8429-c49571e82761"
  thecolab.allowed_domains: "data.gov.au"
  thecolab.last_verified: "2026-10-12"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# Australian Energy Rating registrations

Use the stdlib Python CLI in `scripts/cli.py` to read the public Energy Rating
CKAN package on data.gov.au. Suppliers register labelled appliances sold in
Australia and New Zealand. The CLI is read-only and does not take an API key.

## Workflow

1. Run `package` and read the licence, organisation and resource list.
2. Copy a resource whose line says `datastore` (JSON `datastore_active: true`).
3. Run `preview` with that lowercase UUID and a small `--limit`.

```bash
python3 skills/au-energy-rating/scripts/cli.py package --json
python3 skills/au-energy-rating/scripts/cli.py preview 0973a476-eb0c-45e6-9a18-054f74307843 --limit 1 --json
```

## Commands and output

- `package` returns one result for package `559708e5-480e-4f94-8429-c49571e82761`
  (`energy-rating-for-household-appliances`): title, organisation, notes, the
  licence text and URL as published, `metadata_modified`, and each resource's
  id, collapsed name, format, datastore flag, size and `last_modified`.
  Resource names keep their visible tokens; CKAN's long space padding is
  collapsed. CSV and dictionary download URLs are omitted.
- `preview RESOURCE_ID [--limit N]` checks that id against the same package,
  then calls CKAN `datastore_search`. `N` is an integer from 1 to 20 and
  defaults to 5. `results` is the source records, unchanged, including null and
  `N/A`. `meta` also carries the package licence URL, resource id, collapsed
  resource name, `limit` and `total`. `total` is the source count, usually
  larger than the preview. There is no offset and no CSV download.

Every data command accepts `--json` and returns `{"meta": {...}, "results": [...]}`.
`meta` includes `source_url`, `publisher`, `retrieved_at`, and `licence` plus
`latest_data` when the source states them. `latest_data` is the package
`metadata_modified` or the resource `last_modified`, copied as published
(no timezone is added). `retrieved_at` is the UTC time of the call.
Errors use the same `meta`, an empty `results` array, and `error.code`,
`error.type` and `error.message`. HTTP 429 keeps `error.retry_after` when the
source sends a short `Retry-After` header.

Exit codes: 2 invalid input, 4 rate limit, 5 timeout or HTTP 503/5xx, 6 non-JSON,
truncated JSON or a schema change, 7 a request or redirect outside
`https://data.gov.au`. A datastore total of 0 is an empty `results` array, not
invented rows. A URL, a non-UUID, or a `--limit` outside 1..20 is rejected
before any network call. Inactive resources, including the DOCX data
dictionaries, are rejected instead of downloaded.

Read `references/source-notes.md` for the licence, timestamps and bounds, and
`references/api-notes.md` for the CKAN actions. Run `scripts/test_contract.py`
and `scripts/smoke_test.py` after a change.
