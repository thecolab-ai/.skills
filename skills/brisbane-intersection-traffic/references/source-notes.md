# Source notes

- Primary owner: Brisbane City Council
- Primary source: https://data.brisbane.qld.gov.au/
- Data licence: CC BY 4.0, read separately for each dataset below
- Declared outbound hosts: data.brisbane.qld.gov.au
- Access mode: public-api
- Authentication: none
- Last verified: 2026-10-11

The skill reads two keyless explore v2.1 record endpoints and no other
Brisbane dataset. Volume rows are real-time SCATS detector readings.
Signal rows are the council's signal point reference. Not every signal in
the Brisbane area is operated by Brisbane City Council; both descriptions
limit the data to council-operated sites.

## Volumes

- Dataset: `traffic-data-at-intersection`
- Records: `https://data.brisbane.qld.gov.au/api/explore/v2.1/catalog/datasets/traffic-data-at-intersection/records`
- Metadata read 2026-10-11: `metas.default.license` was `CC BY 4.0` and `license_url` was `https://creativecommons.org/licenses/by/4.0/`
- Publisher: Brisbane City Council
- Attribution stated by the dataset: © Brisbane City Council 2016
- Title: Traffic Management — Intersection volume
- Description: real-time traffic volume and occupancy of lanes at council signalised intersections and approaches

`recorded` is the SCATS timestamp, preserved with its source offset.
`latest_data` is that timestamp for the newest returned row. The request
uses `order_by=recorded desc`, and the parser rejects a page that is not in
descending `recorded` order. It is the newest matching observation in the
filtered set when the source honours that sort, not the clock time of the
request.

`ct` is the source's cycle time. The field note does not name a unit, so
the CLI does not label it as seconds. `link_plan` is the linking plan.
`married` stays the source text, usually `Y` or `N`, and is not turned into
a boolean. `ss` is the sub-system number. `tsc` is the traffic signal
controller site id. `lane` is the strategic approach.

`ds1` to `ds4` are degree of saturation: average occupancy time of a lane
detector, expressed by the source as a percentage. `mf1` to `mf4` are
measured flow: vehicles for that cycle and lane. `rf1` to `rf4` are
reconstituted flow: the SCATS expected vehicle count for that cycle and
lane. The API sends these as strings or null. Null means that detector slot
was not reported. A reported zero stays `"0"`. The CLI does not coerce
either value.

The volume dataset has no coordinates. The publisher points at a separate
intersection-location reference dataset. That dataset is outside this skill.
Join volumes to `signals` on `tsc` when a point is required.

## Signals

- Dataset: `traffic-management-signal-locations`
- Records: `https://data.brisbane.qld.gov.au/api/explore/v2.1/catalog/datasets/traffic-management-signal-locations/records`
- Metadata read 2026-10-11, separately from the volume dataset: `metas.default.license` was `CC BY 4.0` and `license_url` was `https://creativecommons.org/licenses/by/4.0/`
- Publisher: Brisbane City Council
- Attribution stated by the dataset: © Brisbane City Council 2026
- Title: Traffic Management — Signal locations
- Description: location of traffic signals operated by Brisbane City Council
- Territory metadata names Brisbane and Logan

`objectid`, `tsc`, `areanum` and `globalid` are source strings.
`subsystem` is a source integer. `geo_point_2d.lon` and `geo_point_2d.lat`
are the published longitude and latitude. `geo_shape` is a GeoJSON Feature
whose Point coordinates are the same pair in longitude, latitude order. The
parser rejects a record when those coordinates differ by more than 0.00001
degrees. There is no per-record time, so signal results omit `latest_data`.

`--bbox minLon,minLat,maxLon,maxLat` is sent upstream as ODS
`in_bbox(geo_point_2d, minLat, minLon, maxLat, maxLon)`. That function
takes latitude then longitude. A returned point must lie inside the box.
The same check is repeated locally. Boxes that cross the antimeridian are
rejected before the request.

GeoJSON geometry uses `geo_point_2d` longitude then latitude. Properties
are the non-geometry identity fields. `meta.total_count` remains the source
count.

## Bounds and robots

Each call is one HTTPS GET with a named User-Agent, a 15-second default
timeout, and a 256 KiB cap. `--limit` is 1 to 20. The CLI does not send
offset, does not follow a redirect to another host, and does not request
export or download paths.

The portal `robots.txt` for `User-agent: *` disallows `/api/`, while the
Googlebot group allows `/api/` except export paths. This client does not
spoof Googlebot and does not call export or download URLs. It uses the
published records API for these two CC BY 4.0 datasets only.

`meta.total_count` is a JSON integer from the source. A successful response
with `total_count` 0 and an empty `results` array is an empty result. A
non-JSON body, a truncated body, HTTP 400, or a record whose fields do not
match the documented set is a schema failure. HTTP 429 is rate limiting and
keeps `Retry-After` when present. HTTP 503 and timeouts are upstream
failures.
