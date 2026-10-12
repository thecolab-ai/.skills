---
name: mfe-data-service
description: "Search the Ministry for the Environment Koordinates catalogue and read one layer's metadata, field names, feature count and licence. Use for public MfE layers such as land use, ecosystem services or river environment classifications. Refuses a layer unless license.type is an open Creative Commons Attribution licence. Does not query features, call the keyed query service, or read waste-data exports."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "public-data"
  thecolab.source_owner: "Ministry for the Environment"
  thecolab.source_type: "official"
  thecolab.auth: "none"
  thecolab.access_mode: "public-api"
  thecolab.data_class: "public"
  thecolab.writes: "false"
  thecolab.browser: "false"
  thecolab.risk: "low"
  thecolab.cache_ttl: "24h"
  thecolab.schema_version: "1"
  thecolab.skill_type: "public-api"
  thecolab.pack: "nz-public-data"
  thecolab.source_url: "https://data.mfe.govt.nz/services/api/v1/data/"
  thecolab.allowed_domains: "data.mfe.govt.nz"
  thecolab.last_verified: "2026-10-12"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# MfE Data Service

Search the public Ministry for the Environment catalogue on `data.mfe.govt.nz` and read one layer document. This is catalogue metadata only: titles, field names, feature counts and the layer licence. It does not download features or call a query endpoint.

## CLI

```bash
python3 skills/mfe-data-service/scripts/cli.py search flood --limit 1 --json
python3 skills/mfe-data-service/scripts/cli.py layer 117733 --json
```

Commands:

- `search QUERY [--limit N] [--json]` — one `GET /services/api/v1/data/?q=&page_size=N`. `N` is 1 to 20. The response is one JSON list. Further pages are announced in the HTTP `Link` header with `rel="page-next"` and `rel="page-last"` (also `rel="next"` / `rel="last"`). The command does not request the next page. `truncated` is true when that next relation is present or the list is longer than `--limit`. Sort-only relations, including an empty catalogue page, stay `truncated` false. Same-host targets under `/services/api/v1/data/` are copied to `page.next` and `page.last`. Off-host, userinfo, and query-service targets are omitted.
- `layer ID [--json]` — `GET /services/api/v1/layers/{id}/`. Returns field names, `feature_count` and the licence. A layer is returned only when `license.type` is `cc-by` for a known Creative Commons Attribution version.

`--json` prints a `meta` / `results` envelope. Search JSON also includes `truncated`, and `page.next` / `page.last` when those Link targets are official catalogue URLs. `meta.latest_data` is the source `published_at` timestamp when that value is stated, not the land-use or observation year in a title. `meta.licence` is set on a layer only after the licence gate passes. Search results omit a catalogue-wide licence because each layer states its own.

When `truncated` is true, human output includes `More catalogue rows exist; this command does not page further.`

Exit codes follow `docs/contracts.md`: 2 invalid input, 4 rate limit or block, 5 timeout or HTTP 5xx, 6 malformed catalogue JSON, 7 closed licence, missing licence, off-host redirect, or unsupported path. An empty search is an empty `results` array. A missing or non-attribution licence is a refusal, not an assumed Creative Commons Attribution licence.

There is no URL argument. Requests stay on `https://data.mfe.govt.nz`. Thumbnail and service links inside a document are not requested.

## Resources

- CLI: `scripts/cli.py`
- Contract test: `scripts/test_contract.py`
- Smoke test: `scripts/smoke_test.py`
- Source notes: `references/source-notes.md`
