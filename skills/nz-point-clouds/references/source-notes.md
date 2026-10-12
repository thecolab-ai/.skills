# NZ point-cloud source notes

Authentication: none

Last verified: 2026-10-11

Primary source URL: https://portal.opentopography.org/API/otCatalog

Outbound hosts: portal.opentopography.org and opentopography.s3.sdsc.edu.

OpenTopography publishes a keyless catalogue at
`/API/otCatalog`. This skill sends `productFormat=PointCloud`, `detail=false`,
`outputFormat=json`, and a WGS84 box. `detail=false` avoids collection
boundary polygons. The box must lie inside longitude 165 to 179.5 and latitude
-48 to -33, which covers mainland New Zealand, Stewart Island / Rakiura, and
the Chatham Islands. Boxes that cross the antimeridian are rejected. The
catalogue response is one document, capped at 200 datasets and 512 KiB. The
command then slices it with `--limit` (1 to 50, default 20) and `--offset`
(0 to 500).

Dataset metadata comes from the public dataset page
`/lidarDataset?opentopoID=OTLAS.######.#####.#`. The page embeds Schema.org
JSON-LD. The skill reads `@type`, identifier, name, alternate name, licence,
citation, capture interval, publisher, and the `geo.box` string. It does not
read embedded boundary polygons. `geo.box` is `south,west north,east`; results
emit `[west, south, east, north]`. `--format geojson` draws that box as one
polygon in longitude, latitude order. A missing box stays null.

The file list is an anonymous HTTPS ListObjectsV2 request to
`https://opentopography.s3.sdsc.edu/pc-bulk` for the dataset `alternateName`
prefix. `max-keys` is the requested limit. A truncated page returns
`next_page`, which the next call sends as `continuation-token`. The skill
accepts only a short opaque page cursor from that field. Keys must stay under
the prefix. Object URLs are shown for later use; the client never requests
them, and a list call whose path is not exactly `/pc-bulk` is refused.

## Licence

`files` runs only when JSON-LD `license` is exactly `CC-BY-4.0`. The catalogue
search does not include a licence, so it cannot authorise a file list.
`Not-Provided` is a stated absence of reuse terms, not an implied Creative
Commons licence. Auckland 2013 (`OTLAS.062016.2193.1`, prefix `Auckland_2013`)
was observed on 2026-10-11 with `license` `Not-Provided`; `files` stops before
listing that prefix. Auckland Part 1 2024 (`OTLAS.042025.2193.1`, prefix
`NZ24_Auckland`) states `CC-BY-4.0`.

CC BY 4.0 attribution still applies to reuse of a listed dataset. Keep the
`citation` from `info`. OpenTopography also asks users to acknowledge
OpenTopography and the dataset source. The skill's MIT code licence is not the
data licence.

`latest_data` is the end date of `temporalCoverage` when that value ends in
`YYYY-MM-DD`. It is the capture interval, not `dateCreated` and not the time
of retrieval.

## Errors

| Condition | Exit | Type |
|---|---:|---|
| Bbox outside the NZ window, bad id, bad limit, bad page cursor | 2 | invalid_input |
| HTTP 429 or access blocked | 4 | blocked |
| Timeout, HTTP 5xx, oversized response | 5 | upstream_unavailable |
| Malformed JSON, JSON-LD, or listing XML, including a doctype | 6 | schema_failure |
| Off-host redirect, non-CC-BY-4.0 file list, missing dataset file list | 7 | unsupported_operation |

A missing dataset page is an empty `info` result with warning
`dataset_not_found`. The same miss refuses `files` because the licence cannot
be verified. An empty file page for a CC-BY-4.0 dataset is a successful empty
list. Parser fixtures are synthetic. They are not live OpenTopography records.

There is no API key, signed URL, or bulk mirror. Raster DEM and DSM products
belong to `nz-stac`. LINZ Data Service layer search belongs to
`linz-data-service`.
