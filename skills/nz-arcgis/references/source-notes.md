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
- nema: https://services5.arcgis.com/cJn6oR1QqErYBL5d/arcgis/rest/services

The runtime registry, `orgs.json`, permits exact HTTPS host/path pairs. ArcGIS Online roots include the tenant ID; Enterprise roots include the specific REST services path. It deliberately does not trust all tenants on an ArcGIS host. Public service discovery includes MapServer, FeatureServer and ImageServer, while feature commands require a numeric MapServer/FeatureServer layer.

## Verification, 8 October 2026

`verification.json` records real `?f=json` services-directory responses, root service counts, folders and failures. All requested Auckland Council, AT, NZTA, LINZ, DOC, Stats NZ, Watercare and Vector publishers responded, as did WCC and GWRC's current hosted tenants. Auckland Council's tiled image root responded with an empty services list; that proves its public directory route is live, not that every imagery service is exposed or queryable.

Additional routes come from publisher-labelled catalogue endpoints and were accepted only after a live directory response: NIWA, Christchurch City Council, GNS Science, Herenga ā Nuku, DOC SeaSketch, Watercare's Central Interceptor tenant, Council validated landslides and AEM, NZTA's camera tenant, MfE, Ministry of Education, Ministry of Health, MBIE/NZGD and NEMA.

These candidates failed and are **absent from the runtime registry**:

- `services.arcgis.com/RS7BXJAO6ksvblJm/arcgis/rest/services`: ArcGIS 400 Invalid URL. GWRC works on `services2.arcgis.com`.
- `giswebprd.gw.govt.nz/arcgis/rest/services` and `maps.gw.govt.nz/portal/rest/services`: DNS resolution failed.
- `gis.wellingtonwater.co.nz/server1/rest/services`: HTTP 403. Wellington Water is excluded; this does not imply that its individual services are gone.

The existing `wcc-arcgis-nz` skill remains unchanged, including its wider legacy/Eagle routes. No global ArcGIS sharing search is used here.

## Curated selection

`layers-auckland.json` is generated from non-duplicate A/B catalogue rows marked `Covers Auckland: yes`. It contains 177 unique FeatureServer/MapServer layer URLs with live metadata checks; repeated URLs merge problem tags and caveats. National layers covering Auckland are included. Each record retains the catalogue ID, licence and caveat, source URL, publisher, probe date and published edit timestamp where available. The original catalogue freshness label is separate (`catalogue_latest_data`).

`curation-exclusions.json` records 22 omitted candidates. These include non-layer tile URLs and private/third-party/other unverified tenants. Tiled PC78/PC120 maps and scene/raster services are not feature extracts. An accessible directory does not establish a universal licence, source completeness or authority for every record: retain layer-specific caveats and null licences when unknown. A curated `retrieved_at` is the time the bundled catalogue record is returned; `verified_at` identifies the actual metadata probe.

## Bounds and output

- Every HTTP request is GET, timeout 10 seconds, response cap 32 MiB. Redirects are refused before a second connection, including redirects within a shared ArcGIS host to a different tenant. The client does not access authentication endpoints or read credential configuration.
- Discovery traverses at most two folder levels, at most 50 directory requests (40 by default), and reports pending directories. Root indices are visible in `orgs`.
- Search has a separate maximum of 50 layer-listing requests (20 by default). It examines service-name matches first and clearly marks partial coverage. Public directories can list private folders/services: discovery reports these in `inaccessible_directories`/`inaccessible_services`, retains accessible results and marks coverage truncated. Direct layer commands still fail on a gated source; no authentication attempt is made.
- Query pages contain at most 1,000 features, at most 20 page requests and at most 10,000 features overall. With no server pagination support it returns one page. A repeated object ID fails closed. The object-ID field is automatically added to a restricted field selection so duplicate detection stays effective.
- `truncated` is conservative when the requested limit is reached; it does not claim that an exact-size selection has more records. Use `count` on the same where/bbox to distinguish these cases. Bbox uses intersects, so feature coordinates can extend beyond the requested envelope.
- GeoJSON is requested from the server with outSR=4326; no local geometry reprojection or simplification is performed. Servers that lack GeoJSON support return a clear upstream error. CSV carries attributes and provenance, not a geometry encoding. `--json --format csv` retains pagination/truncation in its envelope.
- JSON envelopes carry provenance rather than modifying upstream feature properties. `latest_data` is editingInfo.lastEditDate converted from epoch milliseconds to ISO 8601 UTC; it is not an observation timestamp. Licence text is drawn from the supplied catalogue for matching curated layers, otherwise null.

## Captured fixtures

Files in `tests/fixtures/` were captured from public metadata, service directories, count queries and five-feature WGS84 bbox queries on `PJ_Roadworks_MS/FeatureServer/0` and `Stormwater_Pipe/FeatureServer/0`. Count snapshots are 2,449 and 315,956; live tests assert positive counts rather than permanent equality. Feature samples are trimmed to public asset/worksite attributes and retain the real geometry and object IDs. `scripts/fixture_checks.py` tests these fixtures, paging, rejection before network access, provenance, CSV and curated filtering; it is called by both contract and smoke runners.
