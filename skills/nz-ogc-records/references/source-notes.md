# Catalogue sources and verified behaviour

- Authentication: none
- Last verified: 2026-10-08

Verified with direct curl and the CLI on 8 October 2026. All HTTP calls use a
10 second timeout through the repo's stdlib `nzfetch` helper. No cache, login or
API key is required. The shared helper can use an already configured proxy;
this skill does not inspect or print proxy configuration.

| CLI name | Publisher | Dataset items endpoint | Observed unfiltered count |
|---|---|---|---:|
| auckland-council | Auckland Council | https://data-aucklandcouncil.opendata.arcgis.com/api/search/v1/collections/dataset/items | 171 |
| auckland-transport | Auckland Transport | https://data-atgis.opendata.arcgis.com/api/search/v1/collections/dataset/items | 14 |
| waka-kotahi | NZ Transport Agency Waka Kotahi | https://opendata-nzta.opendata.arcgis.com/api/search/v1/collections/dataset/items | 21 |
| niwa | NIWA | https://data-niwa.opendata.arcgis.com/api/search/v1/collections/dataset/items | 43 |
| data-govt-nz | data.govt.nz | https://catalogue.data.govt.nz/api/3/action/package_search | unavailable: bot challenge |

Counts are observations, not hard-coded runtime totals. Search uses OGC `q`,
`bbox` and `limit`. Get appends a URL-encoded record ID. These are ArcGIS Hub's
OGC Records search surfaces, not a full harvesting or general OGC client.
`features`, `numberMatched`, record `id`, `properties.title`, and the relevant
record property types are checked; malformed source responses are unavailable
with `error_category=schema_error`, never empty successful result sets.

Real GeoJSON responses supplied the fixtures in `tests/fixtures/`. Search
fixtures are the first two unfiltered results (`?limit=2`); `*-get.json` are
responses at the first search record's `links[rel=self].href`. Nonessential
ArcGIS administrative fields were removed; source dates, descriptions, licences,
URLs, coverage and links were retained. The Auckland Transport detail fixture
illustrates an item ID resolving to an ID ending `_0`.

`properties.url` provides service URLs. Explicit data/download links are also
included when available. Hub ZIP items have no distribution links in their
Records response; the CLI derives the ArcGIS item data endpoint for File
Geodatabase, CSV Collection and Shapefile ZIP records and marks it `derived`.
HEAD requests verified this endpoint for Council item
`3b8a6d1d29224763b41242a102d71fd2` (application/zip, 529,982,083 bytes) and Waka
Kotahi item `41e05dcdfcb749d390f7785543fb3b14` (application/zip, 1,525,639,765 bytes):
`https://www.arcgis.com/sharing/rest/content/items/{item-id}/data`.
The skill never retrieves a linked download or ArcGIS service.

Formats are catalogue types plus visible Hub download-format keys, not proof of
an available generated export. `licence_info` retains source licence prose,
including Council caveats. `modified` is an ArcGIS epoch-millisecond metadata
update; `updated_at` normalises it to UTC without asserting dataset freshness.
`time` is retained as `temporal_extent`. All captured sample `time` values were
null; no data date is inferred from the title, description or modification date.

CKAN is listed and probed via `package_search?q=*:*&rows=1`; search uses `q` and
`rows`, get uses `package_show?id=...`. Successful responses use standard CKAN
`result.results`, `count`, `resources`, `organization`, `license_title`/
`license_id` and `metadata_modified` (matching the existing `data-govt-nz` skill).
Direct curl and nzfetch returned a bot challenge, so the CKAN adapter has no
live parser fixture and is not claimed live-verified. Recheck if network access
changes. No CKAN spatial extension has been verified; bbox queries exclude it
with an explicit unsupported status. Prefer the existing `data-govt-nz` skill
for CKAN datastore queries.

Partial searches retain failed statuses, stable error codes and Retry-After on
429 responses. `catalogues` exits successfully after reporting probe results,
even if all are unavailable; its `ok` field shows whether any are usable.
Search exits 4 for a block/rate limit, 5 for an upstream outage, 6 for source
schema failure, or 7 for unsupported bbox when every selected catalogue fails.
Invalid CLI input exits 2. Get reports a JSON error with provenance on network
or parser failure. No pagination or distribution availability checks are hidden.
