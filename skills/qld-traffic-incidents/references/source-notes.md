# Queensland traffic incidents

## Source

- Dataset: `queensland-traffic-incidents`
- Primary source: https://queensland.opendatasoft.com/api/explore/v2.1/catalog/datasets/queensland-traffic-incidents
- Metadata: `https://queensland.opendatasoft.com/api/explore/v2.1/catalog/datasets/queensland-traffic-incidents`
- Authentication: none
- Last verified: 2026-10-12
- Records: the same path plus `/records`
- Portal host: `queensland.opendatasoft.com`
- Publisher field read from `metas.default.publisher`: Queensland
- Catalogue title: Queensland Traffic Incidents

Verified on 2026-10-12 with one metadata GET and one records GET (`limit=1`,
selected fields only). Both returned HTTP 200. `metas.default.license` was
`CC BY 4.0` and `license_url` was
`https://creativecommons.org/licenses/by/4.0/`. `data_processed` was
`2026-10-11T18:03:09+00:00`. The records response `total_count` was 457.
Those counts and timestamps change; the CLI reads them from the response and
does not hard-code them.

A sampled record named Department of Transport and Main Roads in its nested
`source.provided_by` text and linked `https://qldtraffic.qld.gov.au`. This
skill does not call `api.qldtraffic.qld.gov.au` or any host other than
`queensland.opendatasoft.com`. It copies `url` into `event_url` when that
field is a string.

Attribution for reuse: Queensland, CC BY 4.0.

The skill refuses to emit records when `license` is missing or is not exactly
`CC BY 4.0` with a `license_url` containing
`creativecommons.org/licenses/by/4.0`. Licence uncertainty is an error.

## What the command returns

`incidents --limit N` sends Explore API v2.1 parameters:

- `limit` from 1 to 20
- `select` of the operational fields below, not `geo_shape`
- `order_by=last_updated desc`
- optional `where`

Returned record fields:

| Output | Source field | Meaning |
|---|---|---|
| `id` | `id` | Incident id |
| `status` | `status` | Publication status |
| `category` | `incident_category` | Incident category |
| `event_subtype` | `advicea` | Event subtype |
| `advice` | `adviceb` | Advice text |
| `description` | `otheradvice` | Description |
| `road_name` | `roads_main_street` | Road name |
| `suburb` | `roads_suburb` | Locality |
| `lga` | `lga` | Local government area |
| `impact_type` | `impact_impact_type` | Impact type |
| `impact_subtype` | `impact_impact_subtype` | Impact subtype |
| `priority` | `event_priority` | Priority |
| `duration_start` | `duration_start` | Source timestamp, unmodified |
| `duration_end` | `duration_end` | Source timestamp, unmodified |
| `last_updated` | `last_updated` | Source timestamp, unmodified |
| `event_url` | `url` | Source-stated event URL, not fetched |
| `longitude`, `latitude` | `geo_point_2d.lon`, `geo_point_2d.lat` | Published point, no reprojection |

Null source fields stay null. The skill does not invent incidents.

`meta.latest_data` is `metas.default.data_processed` when that string is
present. It is the dataset processing time, not the newest incident
`last_updated`, and it is not inferred from the retrieval clock.
`meta.total_count` is the upstream match count for the filter. `results`
contains only the bounded window.

`geo_shape` is omitted. On a sampled record that geometry was a line tagged
EPSG:7844 and made a one-row payload about 25 KB. Point output copies
`geo_point_2d` longitude then latitude. GeoJSON features use that order.
The dataset title is Queensland Traffic Incidents, but a published point can
fall outside Queensland. On 2026-10-12 the newest `last_updated` row was a
hazard on Snowy Mountains Highway at Bemboka with local government area `Nsw`
and point 149.486309815, -36.611448086. The CLI keeps that point as published.
A record with a null point has `"geometry": null` so the incident is not
dropped. `--bbox` is applied upstream with
`in_bbox(geo_point_2d, minLat, minLon, maxLat, maxLon)`, which keeps points
inside the box. It does not test whether a road line intersects the box.

Optional `--status`, `--category` and `--lga` are exact ODSQL string matches.
Values must be 1 to 80 characters from letters, numbers, spaces and
`.`, `'`, `’`, `/`, `&`, `-`. Quotes and backslashes are rejected before any
request.

## Bounds and transport

- Timeout: 15 seconds per GET
- Response cap: 256 KiB. A larger body is a schema failure, not a partial success
- Redirects: at most two, HTTPS, host `queensland.opendatasoft.com`, port 443 only
- Direct connection. Environment proxies are not used
- User-Agent: `thecolab-qld-traffic-incidents/1.0 (public data skill; keyless)`
- No caller-supplied URL
- There is no offset parameter, so one invocation cannot walk the full set

Each live invocation reads dataset metadata, checks the licence, then reads
records. Metadata failure skips the records request.

## Errors

| Condition | Code | Type |
|---|---:|---|
| Malformed limit, bbox or filter | 2 | `invalid_input` |
| HTTP 401, 403, or 429 | 4 | `blocked` |
| Licence missing or not CC BY 4.0 | 4 | `blocked` |
| Timeout, DNS failure, HTTP 503 and other HTTP 5xx | 5 | `upstream_unavailable` |
| Non-JSON, truncated JSON, or an unexpected record shape | 6 | `schema_failure` |
| Off-host, downgraded, or extra redirect | 7 | `unsupported_operation` |

HTTP 429 keeps the upstream `Retry-After` header in `error.retry_after` when
the header is present. Empty `results` with `total_count` 0 is success.
Outage and licence refusal are not empty success.

`--json`, and `--format geojson` even without `--json`, print one JSON object
on stdout and no stderr. Other failures print one line on stderr.

## Offline fixture seam

`QLD_TRAFFIC_INCIDENTS_FIXTURE=positive` reads only
`tests/fixtures/dataset-positive.json` and
`tests/fixtures/records-positive.json`. Any other value is `invalid_input`.
Unset, the command uses the network. Contract tests set the variable. The live
smoke test removes it. The fixtures are synthetic schema examples, not a live
extract.

## Coverage

`nz-data-catalogue` lists `queensland.opendatasoft.com` inside a large source
inventory. It does not query this dataset. `nzta-highway-info` and
`nz-road-closures` are New Zealand highway sources. Brisbane intersection
volumes are a different host and a different contract.
