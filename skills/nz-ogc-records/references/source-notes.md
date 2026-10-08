# Catalogue sources and verified behaviour

- Authentication: none
- Last verified: 2026-10-08

All HTTP calls use a 10 second timeout through the repo's stdlib `nzfetch` helper.
No cache, login or API key is required. Keep nzfetch's configured proxy fallback
for blocked requests; this skill does not inspect or print proxy configuration.

| CLI name | Publisher | Dataset items endpoint | Observed unfiltered count |
|---|---|---|---:|
| auckland-council | Auckland Council | https://data-aucklandcouncil.opendata.arcgis.com/api/search/v1/collections/dataset/items | 171 |
| auckland-transport | Auckland Transport | https://data-atgis.opendata.arcgis.com/api/search/v1/collections/dataset/items | 14 |
| waka-kotahi | NZ Transport Agency Waka Kotahi | https://opendata-nzta.opendata.arcgis.com/api/search/v1/collections/dataset/items | 21 |
| niwa | Earth Sciences New Zealand (NIWA) | https://data-niwa.opendata.arcgis.com/api/search/v1/collections/dataset/items | 43 |
| data-govt-nz | data.govt.nz | https://catalogue.data.govt.nz/api/3/action/package_search | 32884 (NZ network) |

Counts are observations on 8 October 2026, not hard-coded runtime totals.
CKAN search/get was verified live from an NZ network on that date. Some overseas
networks receive an Incapsula bot challenge, reported as `blocked` (exit 4);
nzfetch proxy fallback applies. Health remains degraded because access varies
by network. CKAN parser fixtures are synthetic and are not live captures.

The NIWA catalogue HTML still has the title "National Institute of Water and
Atmospheric Research". The [current owner's announcement](https://earthsciences.nz/about-us)
confirms NIWA and GNS Science merged on 1 July 2025. Catalogue provenance uses
Earth Sciences New Zealand (NIWA); record-level upstream `source` is preserved.

Search uses Hub `q`, `bbox`, `limit`, and CKAN `q`, `rows`, `ext_bbox`. Both
filter upstream by coverage intersection, not containment. Broad national
coverage can intersect a small box. Live checks returned three Waka Kotahi traffic
records for Fiordland `166,-47.5,166.5,-47`. CKAN water counts from an NZ network
were 4503 without bbox versus 1025 for `174,-37,175,-36`.
Get uses a URL-encoded record ID.
One bounded page is returned; `next_urls` exposes Hub next links or CKAN's next
`start=rows` URL, retaining the query/bbox. No hidden pagination occurs.

OGC `features`, `numberMatched`, record `id`, `properties.title`, property types
and geometry shape are checked. CKAN validates `success`, `result.results`,
`count`, `resources`, `organization`, and parses `spatial` JSON into coverage
geometry. Missing or blank/whitespace-only coverage and timestamps are absent.
Malformed coverage on search is isolated to the record: geometry becomes null,
`geometry_warning` explains the omission, and catalogue/meta warnings identify
the record. Other records and pagination remain available. Get keeps malformed
coverage as `schema_failure` (6). Other malformed responses and invalid JSON
are `schema_failure` (6), never empty successful datasets.
Get HTTP 404/410 means `invalid_input` (2); the same
HTTP status on a collection/search endpoint means `upstream_unavailable` (5).

Fixture provenance and licences: OGC factual metadata captured 2026-10-08 from
the endpoints above; descriptions, snippets and licence prose are synthetic
HTML parser examples in every fixture. CC BY 4.0 attribution belongs to Auckland
Council (`3b8a6d1d29224763b41242a102d71fd2`, `017febe483a14ba99108215cc1a3804c`),
Auckland Transport (`eeb0839fbd594c9e87189df5c84c2543` / `_0`,
`75bbb3afce054ee9a2826fd89c18e4bf`), and NZ Transport Agency Waka Kotahi
(`41e05dcdfcb749d390f7785543fb3b14`, `d682a0a23eae45dcbe8bffcb04b5a64f`).
NIWA / Earth Sciences New Zealand metadata (`3a1d7ee29dac42e3ba6ec4efeeafbacf`,
`a2582b1eb3584237a3b50418f379ca84`) states CC BY-NC 4.0; substantive descriptions
and bespoke terms have been replaced with synthetic prose, retaining only
factual fields and the NonCommercial parser marker. CC licences are source data
licences, separate from this repository's MIT code licence. Search examples
retain their source self/next links. Detail examples use the first search record;
AT illustrates item-to-layer `_0` resolution. `data-govt-nz.json` and
`data-govt-nz-get.json` are entirely synthetic CKAN responses, clearly marked
inside each file; their counts, publishers, IDs, resources and geometry are
examples and were never claimed as observed datasets.
They cover valid and blank spatial strings, absent organisation/licence fields,
blank resource dates and a populated resource modification timestamp. The detail
fixture matches the blank-coverage search record.

`properties.url` and explicit data/download links supply distributions. For
Hub ZIP records without links, the CLI derives the ArcGIS item data endpoint
for File Geodatabase, CSV Collection and Shapefile and marks it `derived`:
`https://www.arcgis.com/sharing/rest/content/items/{item-id}/data`.
Original HEAD checks verified Council `3b8a6d1d29224763b41242a102d71fd2` and
Waka Kotahi `41e05dcdfcb749d390f7785543fb3b14` as application/zip. The CLI never
fetches linked services or downloads; their hosts are outside its outbound list.

Formats are catalogue types plus visible Hub download keys, not guaranteed
exports. Hub licence markers `custom`, `none`, and empty are unstated: use up to
300 plain-text characters of `licenseInfo`, truncating at a word boundary and
appending an ellipsis when needed, or omit `licence`. `licence_info`
retains complete live source prose. Unknown `licence`/`latest_data` are omitted
from meta, records and distributions. `updated_at` describes catalogue metadata
modification, normalised to UTC Z (naive CKAN dates are interpreted as UTC), not
data vintage. `time` is retained as `temporal_extent`. `latest_data` is emitted
only if explicitly provided by the source, preserving source precision.

Partial search/catalogues results retain failure statuses and warnings. If all
catalogues fail, both commands emit the error envelope and exit non-zero.
Mixed failures use fixed precedence 6 > 4 > 5 > 7; any schema failure therefore
wins, followed by blocked/rate limited, upstream unavailable and unsupported.
Rate limits preserve upstream Retry-After in status rows and aggregate errors.
Get failures use the same error envelope, even for `--format geojson`.
Invalid CLI input exits 2. Prefer `data-govt-nz` for CKAN datastore queries.
