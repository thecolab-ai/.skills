# Source notes

- Primary owner: Flamingo
- Primary source: https://data.rideflamingo.com/gbfs/3/auckland/gbfs.json
- Data licence: CC BY 4.0 when `system_information.data.license_id` is `CC-BY-4.0`
- Declared outbound hosts: data.rideflamingo.com
- Access mode: public-api
- Authentication: none
- Last verified: 2026-10-11

Verified on 2026-10-11 with three GETs, a 10 second timeout, and User-Agent
`TheColabSkills/1.0 (+https://github.com/thecolab-ai/.skills)`. No redirect left
`data.rideflamingo.com`. `https://data.rideflamingo.com/robots.txt` returned
HTTP 404 `not_found`. There was no published disallow rule to bypass.

| File | Status | Bytes | ttl seconds | last_updated |
|---|---:|---:|---:|---|
| `/gbfs/3/auckland/gbfs.json` | 200 | 1018 | 3600 | 2025-02-15T10:17:01+00:00 |
| `/gbfs/3/auckland/system_information.json` | 200 | 723 | 3600 | 2026-10-11T18:12:33+00:00 |
| `/gbfs/3/auckland/vehicle_status.json` | 200 | 695851 | 60 | 2026-10-11T18:12:34+00:00 |

The discovery document listed nine feeds, all on this host and the Auckland
path: `system_information`, `system_alerts`, `system_pricing_plans`,
`station_information`, `station_status`, `geofencing_zones`, `vehicle_status`,
`vehicle_types`, `gbfs_versions`. This skill reads only the discovery file,
`system_information`, and `vehicle_status`. It does not download the others.

`system_information.data.license_id` was `CC-BY-4.0`. The file had no
`license_url`. `vehicle_status` does not repeat `license_id`, so the vehicles
command omits `meta.licence` rather than copying a licence from another file.
Run `system` for the stated token. A missing `license_id` is a schema failure.
A different token is returned as stated and is not relabelled as CC BY 4.0.

`name` is a GBFS 3.0 localised list. The English text was `Flamingo`.
`system_id` was `flamingo_auckland`. `timezone` was `Etc/UTC`. That string is
kept as published. It is not rewritten to Pacific/Auckland.

`vehicle_status` held 1287 vehicles. Observed fields were `vehicle_id`, `lat`,
`lon`, `current_range_meters`, `last_reported`, `vehicle_type_id`,
`rental_uris`, `pricing_plan_id`, `is_reserved`, and `is_disabled`. No path,
route, trip, or history field was present. `rental_uris` points at
`ride.flamingoscooters.com` and is dropped so this command stays a position
snapshot. `current_range_meters` is metres. Coordinates are WGS84. Output order
is `vehicle_id`. `--bbox` is local point containment after the one download.

`last_updated` and `last_reported` are kept with their source offset.
`meta.latest_data` is that file's `last_updated`, not the retrieval time and
not a track. The discovery file's 2025 timestamp is not the vehicle snapshot.

A feed `ttl` of 0 means the provider marks the snapshot as already due for
refresh. This command still performs one GET and does not poll. A positive ttl
is honoured with a temp-directory cache: a later call for the same URL inside
that ttl reuses the body and the original `retrieved_at`. The cache is not a
trajectory store.

Bounds: timeout 10 seconds, response cap 2000000 bytes, at most 30 feeds, at
most 5000 vehicles parsed, and `--limit` from 1 to 100. Requests must be HTTPS
on `data.rideflamingo.com` under `/gbfs/3/auckland/` and end in `.json`.
Off-host redirects and feed URLs are refused. Empty vehicle lists are an empty
success. A non-empty list with no usable positions, malformed JSON, NaN, a
non-3.0 version, or an unreadable ttl is a schema failure. HTTP 429 is
rate limiting. HTTP 503 and timeouts are upstream outages. None of those are
empty successes.

A cold-cache smoke performs one GET for each of the three files. A later call
inside that file's ttl reuses the response and the original retrieval time.

`nz-ridereport` reads `public.ridereport.com` aggregate metrics. `gtfs-nz`
reads static GTFS. Neither reads this GBFS host.
