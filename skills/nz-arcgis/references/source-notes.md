# Source notes

Primary source: https://services1.arcgis.com/n4yPwebTjJCmXB6W/arcgis/rest/services

Authentication: none

Last verified: 2026-10-08

Outbound hosts and exact roots:

- akl: https://services1.arcgis.com/n4yPwebTjJCmXB6W/arcgis/rest/services, https://tiledimageservices1.arcgis.com/n4yPwebTjJCmXB6W/arcgis/rest/services, https://mapspublic.aucklandcouncil.govt.nz/arcgis/rest/services, https://mapspublic.aucklandcouncil.govt.nz/arcgis3/rest/services, https://mapspublic.aklc.govt.nz/arcgis/rest/services, https://services-ap1.arcgis.com/9R0qvCUXav3QPG1F/arcgis/rest/services, https://services-ap1.arcgis.com/amvJtxbPQBZ5mG81/arcgis/rest/services
- at: https://services2.arcgis.com/JkPEgZJGxhSjYOo0/arcgis/rest/services, https://mahere.at.govt.nz/server/rest/services
- nzta: https://services.arcgis.com/CXBb7LAjgIIdcsPt/arcgis/rest/services, https://services1.arcgis.com/1lLaMWUudPsf6JuN/arcgis/rest/services
- linz: https://services.arcgis.com/xdsHIIxuCWByZiCB/arcgis/rest/services
- doc: https://services1.arcgis.com/3JjYDyG3oajxU6HO/arcgis/rest/services, https://seasketch.doc.govt.nz/arcgis/rest/services
- stats: https://services2.arcgis.com/vKb0s8tBIA3bdocZ/arcgis/rest/services
- watercare: https://wslgis.water.co.nz/arcgis/rest/services, https://services5.arcgis.com/PnnKqtqi3qfxnaPc/arcgis/rest/services
- vector: https://services6.arcgis.com/8RWEO35G1ALMME0I/arcgis/rest/services
- wcc: https://services1.arcgis.com/CPYspmTk3abe6d7i/arcgis/rest/services, https://gis.wcc.govt.nz/arcgis/rest/services
- gwrc: https://services2.arcgis.com/RS7BXJAO6ksvblJm/arcgis/rest/services, https://mapping.gw.govt.nz/arcgis/rest/services, https://mapping1.gw.govt.nz/arcgis/rest/services
- niwa: https://services3.arcgis.com/fp1tibNcN9mbExhG/arcgis/rest/services
- ccc: https://gis.ccc.govt.nz/server/rest/services
- gns: https://gis.gns.cri.nz/server/rest/services
- herenga: https://maps.herengaanuku.govt.nz/maps/rest/services
- mfe: https://arcgis.mfe.govt.nz/server1/rest/services
- moe: https://services9.arcgis.com/ygJ1AFEQ1sNGJz4H/arcgis/rest/services
- health: https://services2.arcgis.com/9V7Qc4NIcvZBm0io/arcgis/rest/services
- mbie: https://services-ap1.arcgis.com/0380iqO8xVVhk66v/arcgis/rest/services

The runtime registry, `orgs.json`, permits exact HTTPS host/path pairs. ArcGIS Online roots include the tenant ID; Enterprise roots include the specific REST services path. It deliberately does not trust all tenants on an ArcGIS host. Public service discovery includes MapServer, FeatureServer and ImageServer, while feature commands require a numeric MapServer/FeatureServer layer.

## Verification, 8 October 2026

`verification.json` records real `?f=json` services-directory responses, root service counts, folders and failures. All requested Auckland Council, AT, NZTA, LINZ, DOC, Stats NZ, Watercare and Vector publishers responded, as did WCC and GWRC's current hosted tenants. Auckland Council's tiled image root responded with an empty services list; that proves its public directory route is live, not that every imagery service is exposed or queryable.

Additional routes come from publisher-labelled catalogue endpoints and were accepted only after a live directory response: NIWA, Christchurch City Council, GNS Science, Herenga ā Nuku, DOC SeaSketch, Watercare's Central Interceptor tenant, Council validated landslides and AEM, NZTA's camera tenant, MfE, Ministry of Education, Ministry of Health, MBIE/NZGD.

These candidates failed and are **absent from the runtime registry**:

- `services.arcgis.com/RS7BXJAO6ksvblJm/arcgis/rest/services`: ArcGIS 400 Invalid URL. GWRC works on `services2.arcgis.com`.
- `giswebprd.gw.govt.nz/arcgis/rest/services` and `maps.gw.govt.nz/portal/rest/services`: DNS resolution failed.
- `gis.wellingtonwater.co.nz/server1/rest/services`: HTTP 403. Wellington Water is excluded; this does not imply that its individual services are gone.

The existing `wcc-arcgis-nz` skill remains unchanged, including its wider legacy/Eagle routes. No global ArcGIS sharing search is used here.

## Curated selection

`layers-auckland.json` is generated from `skills/nz-data-catalogue/data/catalogue.json.gz` (derived from `akl-catalogue-v4.json`), from non-duplicate A/B catalogue rows marked `Covers Auckland: yes`. It contains 167 unique FeatureServer/MapServer layer URLs with live metadata checks; repeated URLs merge problem tags and caveats. National layers covering Auckland are included. Each record retains the catalogue ID, licence and caveat, source URL, publisher, probe date and published edit timestamp where available. The original catalogue freshness label is separate (`catalogue_latest_data`).

`curation-exclusions.json` records omitted candidates. These include non-layer tile URLs and private/third-party/other unverified tenants. Tiled PC78/PC120 maps and scene/raster services are not feature extracts. An accessible directory does not establish a universal licence, source completeness or authority for every record: retain layer-specific caveats and unknown licences as absent fields, with placeholder text in `licence_note`. Curated `retrieved_at` and `verified_at` retain the actual metadata probe time. Catalogue envelope retrieval time is its maximum verified probe timestamp. `orgs` uses the repository registry URL and the maximum applicable timestamp in `verification.json`; it makes no network request. NEMA is excluded because the only selected layer requires permission for public release.

## Bounds and output

- Read-only GET; default 10-second request timeout, `--timeout` 1–60 for describe/count/query. Every command has a 55-second monotonic deadline (within the common runner’s 60-second cap), checked before requests and while reading, 32 MiB per response and 64 MiB aggregate response bytes. Redirects are refused; no authentication endpoints or credential configuration are used.
- Discovery traverses two folder levels and at most 50 directory requests (40 default). Search adds at most 50 service listings (20 default). `failed_directories` and `failed_services` retain source URL, standard error type and message. Failures mark coverage truncated and preserve collected results; all roots failing raises an error. Unsafe routes remain fatal.
- Object-ID selection uses the original where/bbox without reprojection and is capped at 32 MiB independently of the requested feature limit. `matched_count` reports the returned ID selection size; server-truncated ID selections are marked incomplete. IDs are sorted, limited, and fetched in batches of at most 200, with URLs below 8 KB. Returned IDs are checked against requested IDs. Reprojection omissions mark `incomplete`, `truncated` and `missing_object_ids_count`, even when the server says no more rows. Layers without OIDs use up to 50 offset pages and a count cross-check, with an unordered warning.
- Feature limits are at most 10,000; truncation is based on selected IDs/count, missing rows or resource limits. Tables reject bbox filtering with an actionable input error; use `--where`. Bbox filtering uses intersects; coordinates may extend beyond the requested envelope. Enterprise MapServer layers need small bboxes and may require a longer timeout.
- JSON success is `{"meta": {...}, "results": [...]}`; errors on stdout have empty results and standard `error.code/type/message`, with optional Retry-After. GeoJSON is a WGS84 FeatureCollection with `meta`. Query bounds and completeness are top-level fields. CSV contains attributes and provenance; geometry is not requested. Formula-like strings are prefixed with an apostrophe.
- `latest_data` is editingInfo.lastEditDate converted from epoch milliseconds to UTC, not an observation timestamp. Unknown licences are omitted. Human curated, describe and query output shows licence and caveats, including non-commercial, CC BY-ND and NZTA commercial-restriction terms.
- The terms filter excludes internal use, public-release permission gates, data-sharing agreements and viewer-only restrictions. Physical road-height restrictions and explicit BY-ND commercial download pricing do not imply a public-release permission gate. The tag table is in `layers-auckland.md` and JSON `tags`.

## Captured fixtures

Contains data from Auckland Transport and Auckland Council (Healthy Waters), CC BY 4.0, captured 8 Oct 2026, trimmed. Synthetic failure/paging examples are identified in the test code.

Files in `tests/fixtures/` were captured from public metadata, service directories, count queries and five-feature WGS84 bbox queries on `PJ_Roadworks_MS/FeatureServer/0` and `Stormwater_Pipe/FeatureServer/0`. Count snapshots are 2,449 and 315,956; live tests assert positive counts rather than permanent equality. Feature samples are trimmed to public asset/worksite attributes and retain the real geometry and object IDs. `PrincipalOrganisation` is omitted from both roadworks feature fixtures to avoid retaining personal applicant names. `scripts/fixture_checks.py` tests these fixtures, paging, rejection before network access, provenance, CSV and curated filtering; it is called by both contract and smoke runners.
