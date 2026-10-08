# Sources, access and parser notes

- Authentication: none
- Last verified: 2026-10-08

Verified 8 October 2026 using catalogue searches (`NIWA hydrometric`, `river maps`,
`flood plains`, `fish passage`) and real unauthenticated HTTP requests. Catalogue
rows: S1057, S0128, S0127, S1056 and S1297. Earlier counts are discovery evidence,
not constants in the implementation. All fixtures contain synthetic values in
observed response shapes; no third-party datasets are bundled.

## DataHub: hourly hydrometric data and regional flood maps

- Hourly landing/catalogue: <https://data.niwa.co.nz/products/hydro-data-hourly>
- Flood landing/catalogue: <https://data.niwa.co.nz/products/100-year-flood-maps>
- API documentation: <https://data.niwa.co.nz/pages/datahub-api-information>
- Authenticated files: <https://d17fc0a885.execute-api.ap-southeast-2.amazonaws.com/dev/api/data-files>
- Data licences: <https://data.niwa.co.nz/pages/data-licences-explained>
- Non-commercial terms: <https://data.niwa.co.nz/pages/license/non-commercial>

The catalogue originally points to `store.niwa.co.nz`, which did not resolve in
this verification environment. The working official `data.niwa.co.nz` pages
expose public catalogue props, even though file downloads are account-gated.
`robots.txt` on the working host allows `/`. No account/login paths are queried.
The documented API requires customer identification and authorisation for **all**
requests. A bare GET returned HTTP 401. The CLI accepts no keys and does not
request account files or signed download URLs. `flow` returns exit 4 describing
this known gate, without issuing a credentialed request or claiming to fetch data.

Public listing schema: an `astro-island` whose component URL contains
`SubcategoriesMain.` has JSON-encoded `products`, `total` and `page` props.
Astro encodes ordinary values as `[0, value]`, arrays as `[1, items]` and Date
objects as `[3, ISO timestamp]`. Read only the public catalogue fields, ignoring
settings/account props. Each product has `id`, `productRef`, `metadata`, with
`title`, `description`, `geojson`, `region`, `version`, `dateMin`, `dateMax`,
`updatedAt`, `keywords`, `image` and `specifications` fields. The parser fails
if the source markup, pagination or station-ID description changes.

Verified pagination: `?page=1`, `?page=2`; regional filter: `?region=Auckland`.
The hourly catalogue returned 38 distinct station IDs/flow series, 24 on page 1
and 14 on page 2. The newest stated series end was 2026-05-07, while catalogue
metadata updates were in July 2026. Series dates are coverage, not live readings.
Each result preserves its page URL and series `dateMax` as `latest_data`.
Public hourly metadata does not establish permission to redistribute observations;
DataHub's non-commercial option restricts redistribution/rehosting.

The Auckland flood catalogue returned four climate scenario listings. Each
contains a **coverage bounding rectangle**. GeoJSON from `flood-hazard` represents
these product footprints only, with `geometry_role=product_coverage_bbox` and
`hazard_values_available=false`; it cannot establish inundation or safety for a
property. The actual products are regional ZIPs containing 4 m maximum depth
and depth–velocity GeoTIFFs for a 1% AEP scenario, under current/future climate.
The official product notes describe LiDAR availability as of December 2024.
Flood `latest_data` means catalogue `updatedAt`, not the date of a flood event.
The product offers CC BY-NC 4.0 for non-commercial use; separate commercial
restricted terms apply. Never convert coverage polygons into claimed flood extents.

Station `--region` queries the public NIWA WFS `niwa:regional_council_gen`
layer and uses local point-in-polygon tests with holes. Its label field is
`regc2013_n` (e.g. `Canterbury Region`); it represents generalised 2013 council
boundaries, not current cadastral boundaries. Metadata records the boundary
query URL. Points exactly on generalised boundary edges may be classified
imprecisely; use a bbox for an explicit geographic window.

## NZ River Maps predictions

Official source: <https://shiny.niwa.co.nz/nzrivermaps/>

The app grants CC Attribution 3.0 NZ unless a metric states different terms.
It provides static national model estimates on RECv2.4. The CLI retrieves map
values through the same public read-only Shiny/SockJS interface used by its web
client, without a browser or external dependencies. The opt-in `rivers` command
drives NIWA's Shiny app by imitating a browser session; invoke it only when
River Maps predictions are explicitly requested. `sources` lists this method
without opening a session. No stable REST prediction
API is advertised. `robots.txt` returned 404; the source explicitly offers
research downloads. No CAPTCHA, login or access challenge is bypassed.

`scripts/rivermaps.py` implements public XHR polling under `__sockjs__`, opening
one ephemeral session per query. POSTs contain application query inputs only;
they do not modify source records or accounts. Long polls have a timeout of up
to 30 s and retry once on timeout, capped by the remaining 50 s query deadline.
Other calls have a 10 s timeout. The query checks the deadline between requests,
plus a best-effort 2 s
session close. Configured shared HTTP retries can extend elapsed time; smoke
probes enforce a 70 s subprocess limit. Session/config
identifiers are discarded and are never returned as source URLs or stored.

Observed protocol: SockJS `o` opens; `a[...]` contains multiplex `0|m|` JSON
messages. Initialise the visible map and hydrology selectors. Provide initial map bounds/zoom and wait for the initial map to finish
before sending `SelectedVariable`, `ActionUpdate`, zoom and map bounds. Ignore
stale national-map frames until the requested view has a different stream-order
visibility threshold. Hydrology choices: Mean Flow, Median flow, MALF, 1 in 5 year low
flow, FRE3, February flow seasonality and Month lowest mean flow. Read the
selected metric description and Leaflet `addPolylines` calls for `MapLines`.
Reach IDs, nested longitude/latitude arrays and prediction tooltips must agree.
Values are rounded **displayed** values (month names remain strings for
Month lowest mean flow); obtain the app's CSV and metadata
exports manually if full precision is needed. NA predictions remain null.

Reaches are filtered by local geometry bounding-box intersection and ranked
by approximate equirectangular point-to-segment distance, suitable for the
small NZ search window. `--radius-km` defines a box half-size, not a circular
radius. The source uses zoom-dependent stream-order thresholds; inspect
`meta.visibility` and `meta.truncated`. No nearest-reach guarantee is made
outside the returned visible network. App errors, timeouts and schema changes
remain failures, not empty successes. No `latest_data` is inferred: metric
periods vary and the UI does not state a single dataset update date.

## Fish Passage Assessment Tool

- Web tool: <https://fishpassage.niwa.co.nz/>
- Verified WFS: <https://geoserver.niwa.co.nz/fpat/wfs>
- Layer: `fpat:fpat_surveys`, WFS 2.0.0, `outputFormat=application/json`
- Full CSV discovery route (not downloaded by this CLI):
  <https://s3-ap-southeast-2.amazonaws.com/prod.fishpassage.niwa/fpat_survey_responses.csv>

Use bounded WFS instead of the large bulk CSV. `geoserver` robots returned 404.
The catalogue identifies CC BY 4.0, with attribution to NIWA/ESNZ and original
survey contributors. The verified national WFS count was 152,761 surveys;
6034 matched bbox `174.6,-37,174.9,-36.7`. Counts change with source maintenance.

Explicit CRS `urn:ogc:def:crs:OGC:1.3:CRS84` ensures longitude/latitude ordering
for `srsName` and bbox. Paging includes `sortBy=id`; this is essential for the
backing view, which returned HTTP 400 for `startIndex` without an explicit sort.
`numberMatched`, `numberReturned`, `features`, `totalFeatures`, `timeStamp` and
`crs` form the observed GeoJSON response. `timeStamp` is a response timestamp,
not the latest survey date. Point properties include `id`, `structure_type`,
`survey_response_id`, `recorded_date`, `nzsegment`, `risk_class_num`,
`risk_class_str`, `max_risk`, `priority`, `historical`, `manual_assessment` and
`asset_owner`. Sentinel/historical dates such as 1899-12-31 occur upstream and
are preserved. Fish passage risk classes do not measure hydraulic conveyance.

## Other skills

`lawa-nz` handles LAWA/council observations; `gwrc-hilltop-nz` covers Wellington
Hilltop observations. `niwa-coastal-nz` covers NIWA coastal ArcGIS layers.
Council flood extents belong with the regional/`nz-arcgis` connectors; no council
hazard data is silently substituted for NIWA's regional raster products.
