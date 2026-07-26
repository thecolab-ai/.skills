# Source notes — WCC / GWRC ArcGIS open data

- Primary owner: Wellington City Council (GWRC via `--portal gwrc`)
- Primary source: https://data-wcc.opendata.arcgis.com/
- Declared outbound hosts: data-wcc.opendata.arcgis.com, data-gwrc.opendata.arcgis.com,
  www.arcgis.com, hub.arcgis.com, services.arcgis.com, services1.arcgis.com,
  services2.arcgis.com, gis.wcc.govt.nz, giswebprd.gw.govt.nz,
  mapping.gw.govt.nz, mapping1.gw.govt.nz, maps.gw.govt.nz, gis.wellingtonwater.co.nz,
  gis-snowflake-opendata-public-wcc-arcgis-prod.s3.ap-southeast-2.amazonaws.com
- Access mode: public-api
- Authentication: none
- Last verified: 2026-07-22

## Search: why org-scoped sharing search

The Hub portals front standard ArcGIS Online organisations. Three search surfaces
were tested on 2026-07-22:

- `data-wcc.opendata.arcgis.com/api/search/v1/...` — works for WCC but returns
  HTTP 500 (`CONT_0001`) on the GWRC hub.
- `.../api/v3/datasets?q=...` — responds on both hubs but searches the GLOBAL
  ArcGIS Hub catalogue (~227k datasets; a "Flood Hazard All" hit was a Canadian
  layer). Never use it unscoped.
- `https://www.arcgis.com/sharing/rest/search?q=<kw> orgid:<orgId>` — stable,
  works identically for both councils. This is what the CLI uses.

Org IDs resolved via `https://hub.arcgis.com/api/v3/domains/<hostname>`:
WCC `CPYspmTk3abe6d7i`, GWRC `RS7BXJAO6ksvblJm`. Item metadata resolves through
`https://www.arcgis.com/sharing/rest/content/items/<id>?f=json`.

## Layer queries

Feature/Map service layers answer standard ArcGIS REST `query` requests with
`f=geojson`, no key. Server page cap is 2000 records (`exceededTransferLimit`
surfaces as `truncated`). Count and object-ID modes use `f=json`; ordinary
feature mode remains GeoJSON. The CLI maps offset, ordering, geometry precision,
maximum allowable offset, and geometry suppression directly to ArcGIS REST.
Services live on `services.arcgis.com` /
`services1.arcgis.com` / `services2.arcgis.com` (Esri-hosted),
`gis.wcc.govt.nz`, `giswebprd.gw.govt.nz`, `mapping.gw.govt.nz`,
`mapping1.gw.govt.nz`, `maps.gw.govt.nz`, and `gis.wellingtonwater.co.nz`; the
CLI refuses any other host (exit 7). Note some
services do not start layer ids at 0 — the CLI reads the service's own layer
list when no `--layer-id` is given. Item ids must belong to the WCC or GWRC org
ids above. Direct service/layer URLs must use HTTPS and either an exact council
host or an Esri service path whose first segment is one of those org ids (plus
the verified Eagle Technologies tenant `XTtANUDT8Va4DLwI`, which serves the
MetService weather CAP and NZTA highway warning feeds used by NZ EM GIS users).
Every request pins redirects to its already-validated hostname and revalidates
the final service path after a redirect. Query strings, fragments, traversal
segments, extra path suffixes, ImageServer paths, foreign Esri tenants, and
host changes are rejected before returned content is trusted.

## Metadata and raw identify

`describe SERVICE [--layer-id N]` reads the standard ArcGIS service/layer JSON.
The normalized envelope preserves fields, aliases, types, field descriptions
and units when the publisher supplies them, domains, extent, spatial reference,
capabilities, geometry type, object-ID field, and record limits.

`identify SERVICE --point LON,LAT` calls a MapServer's standard `/identify`
operation with an explicit WGS84 (`EPSG:4326`) point, a small surrounding map
extent, display dimensions, tolerance, optional selected layer, and optional
geometry suppression. Results retain the upstream layer identifiers,
attributes, geometry type, and geometry. This raw primitive is not a hazard
assessment: interpretation remains with the caller. Non-finite or out-of-range
WGS84 points and bounding boxes are rejected before any request.

Catalogue search sends ArcGIS `start` unchanged and returns the upstream
`nextStart` cursor as `next_start`. Item metadata is accepted only for the WCC
or GWRC organisation IDs. The raw item `url` is preserved for Web Maps,
applications, documents, and services; only Feature Service and Map Service
items expose `service_url`, which must independently pass the same exact host,
tenant, and service-path checks before use. Empty search, query, and identify
result lists remain explicit empty results. Empty or implausible service/layer
metadata and other malformed response shapes produce structured
`malformed_response` errors instead of invented rows.

Field selection and ordering use a strict identifier grammar. Identifiers begin
with a letter or underscore and continue with letters, digits, or underscores.
Qualified identifiers may contain dots only between non-empty valid segments.
Order clauses add at most one `ASC` or `DESC` direction. Semicolons, empty
fields, trailing dots, malformed directions, and other SQL-like syntax are
rejected by the parser, whose failures use the same JSON error envelope as
runtime validation.

### Verified hazard/climate services (WCC-EM GIS overview, 2026-07-24)

- `mapping1.gw.govt.nz/arcgis/rest/services/Hazards/Sea_Level_Rise/MapServer` —
  GWRC/NIWA sea level rise grids (1–5 m above MHWS10)
- `mapping1.gw.govt.nz/arcgis/rest/services/Hazards/Storm_Surge/MapServer` —
  1% AEP storm-tide flooding with 0.5/1.0/1.5 m SLR increments
- `mapping1.gw.govt.nz/arcgis/rest/services/GW/Flood_Hazards_Areas/MapServer` —
  layer 0 GWRC-maintained watercourses (RMA classification), 1 river corridor,
  2 1% AEP flood hazard extent (Wellington Water), 3 1% AEP flood hazard
  extent, 4 0.23% AEP flood hazard extent. Verified 2026-07-26: the service
  publishes AEP-labelled extents (1% ≈ 100-year, 0.23% ≈ 400-year) and there
  is **no 50-year layer**, contrary to the source spreadsheet's
  "50, 100 and 400 year" description — cite the AEP labels, not return periods
  the service does not expose
- `mapping1.gw.govt.nz/arcgis/rest/services/GW/Emergencies_P/MapServer` — layer 10
  liquefaction potential, 11 earthquake slope failure, 21 landslide lines,
  23 tsunami evacuation zones (2019)
- `mapping1.gw.govt.nz/arcgis/rest/services/ClimateChange/Modelled_Climate_Change/MapServer`
  — 26 NIWA modelled climate-change layers (wind, temperature, rainfall, PED,
  soil moisture, GDD, snow days, solar, humidity)
- `gis.wellingtonwater.co.nz/server1/rest/services/Modelling/WCC100yrCC2025FloodDepths_FB/MapServer`
  — Wellington Water combined stormwater flood depths, 100yr ARI + climate change

## Pōneke Travel Insights transport sensors

The Transport Sensors dataset (item `ad1935dad4344b518b6325d85d4fbda6`; layer at
`gis.wcc.govt.nz/.../Transportation/Transport_Sensors/FeatureServer/0`) carries
countline geometry only. The counts live in a public S3 bucket referenced from
the item description:

- `transport_sensors/countline_meta_info/csv/countline_meta_info.csv` (~43 KB):
  VIEWPOINT_ID, COUNTLINE_ID, NAME, start/end lat-long, directions, EARLIEST,
  LATEST.
- `transport_sensors/countline_mobility/csv/<YYYY>/<MM>/countline_mobility_<YYYY>_<MM>.csv`
  (~12–14 MB/month): COUNTLINE_ID, COUNTLINE_DATE, COUNTLINE_HOUR,
  DIRECTION_COUNT, COUNTLINE_TRANSPORT_CLASS (Pedestrian, Car, Cyclist, …),
  DIRECTION. Parquet twins exist beside each CSV.

WCC documents a refresh of "no less than once per calendar month"; in practice
the current-month file updated daily during verification (newest day = yesterday).
The bucket allows anonymous ListObjectsV2, but the CLI derives the newest month
from the metadata's LATEST column and falls back one month on a missing file
rather than listing the bucket.

Mobility files omit rows when a countline/class did not report on a date. The CLI
must not turn that absence into a measured zero: it emits `latest_date_count: null`,
`stale: true`, `latest_observed_date`, and the metadata's `LATEST` date. A numeric
zero is reserved for a row that was actually present and summed to zero.

Upstream data source is VivaCity Labs sensors; WCC contact for the dataset is
digitalinnovation@wcc.govt.nz.

## Stability and licence

- Everything used is anonymous, keyless, and served from Esri/AWS
  infrastructure the councils already depend on for their public portals.
- Licence: CC BY 4.0. Attribute "Wellington City Council" or "Greater Wellington
  Regional Council" per item owner.
- Sensor counts are statistical, sensor-derived, and occasionally revised;
  they are not a safety-critical people counter.
