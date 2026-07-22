# Source notes — WCC / GWRC ArcGIS open data

- Primary owner: Wellington City Council (GWRC via `--portal gwrc`)
- Primary source: https://data-wcc.opendata.arcgis.com/
- Declared outbound hosts: data-wcc.opendata.arcgis.com, data-gwrc.opendata.arcgis.com,
  www.arcgis.com, hub.arcgis.com, services.arcgis.com, services1.arcgis.com,
  services2.arcgis.com, gis.wcc.govt.nz, giswebprd.gw.govt.nz,
  mapping.gw.govt.nz, maps.gw.govt.nz,
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
surfaces as `truncated`). Services live on `services.arcgis.com` /
`services1.arcgis.com` / `services2.arcgis.com` (Esri-hosted),
`gis.wcc.govt.nz`, `giswebprd.gw.govt.nz`, `mapping.gw.govt.nz`, and
`maps.gw.govt.nz`; the CLI refuses any other host (exit 7). Note some
services do not start layer ids at 0 — the CLI reads the service's own layer
list when no `--layer-id` is given. Item ids must belong to the WCC or GWRC org
ids above. Direct service/layer URLs must use HTTPS and either an exact council
host or an Esri service path whose first segment is one of those org ids (plus
GWRC's verified legacy tenant `XTtANUDT8Va4DLwI`). Every request pins redirects
to its already-validated hostname.

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
