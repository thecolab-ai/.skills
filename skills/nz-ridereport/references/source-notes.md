# Auckland Ride Report source notes

Primary source URL: https://public.ridereport.com/auckland

Authentication: none

Last verified: 2026-10-11

Outbound hosts:

- `public.ridereport.com` — public dashboard page, including the published vehicle and period catalogue
- `api.ridereport.com` — `GET /public/settings?slug=auckland&environment=production`
- `public-data-exports-production.s3-us-west-2.amazonaws.com` — Auckland `trip_metrics.json` only

The official dashboard client reads aggregate exports from:

`https://public-data-exports-production.s3-us-west-2.amazonaws.com/auckland/data-export/{vehicle}/{period}/trip_metrics.json`

`{vehicle}` and `{period}` come from the dashboard catalogue. Auckland currently publishes `scooter`, `e-bike`, and `all`, with quarter keys such as `2026-Q3` and an `all` period where the page lists it. The CLI refetches that catalogue before each metrics read and refuses any other token.

## Licence

The export dialog on the public dashboard states: "Data may be used with a link to public.ridereport.com and attribution to Ride Report."

That sentence is the data reuse term recorded in `meta.licence`. It is not a Creative Commons or other named open-data licence. The site footer also states that Ride Report reserves copyright. This skill's MIT licence covers only its code. Every human result repeats the attribution and the dashboard link. Do not drop them when summarising a result.

The public page describes the dashboard as aggregated and anonymised e-scooter and bike-share data. Daily trip counts in the live quarterly file are coarse city totals, not individual journeys.

## What this skill reads

`dashboard` returns the agency name, population, active operators, measurement system, earliest metrics day when present, map bounds when they are a finite WGS84 box, and the catalogue of vehicle periods.

`metrics` returns one city aggregate: total trips, average trips per day, and average trip speed in metres per second. Duration, distance, active vehicles, and trips per vehicle are included only when the export provides finite values. `meta.latest_data` is the last `tripsPerDay` bucket date in that export. It is the source's last included day, not the retrieval time.

`--series trips` reads `tripsPerDay`. `duration` reads `tripDuration`. `distance` reads `tripDistancePerDay`. `vehicles` reads `meanActiveVehiclesPerDay`. `utilisation` reads `tripsPerVehiclePerDay`. Buckets stay in source order. Output is truncated to `--limit` and the warning says so. The default command does not emit buckets. The all-time scooter file is about half a megabyte uncompressed; the size cap is 1 MiB, and the default summary still returns one record.

## What this skill does not read

The same public client can request `route_aggregation.geojson` (about 2.8 MB uncompressed; binned segment counts such as `< 100`, keyed by opaque ids) and `base-data/street_segments.geojson` (about 12 MB compressed). Those files are not fetched. Joining them would reconstruct street-level aggregates and is outside this bounded city-metrics command. This skill also does not call the export dialog's email form, does not retry an HTTP 403 through a proxy, and does not read BikeMaps incident reports or council traffic-counter series.

An absent metrics object is HTTP 403 or 404 from the export host. The official client treats both as "no data for the current selection". The CLI returns an empty `results` array and `no_export`. The same statuses on the dashboard page or settings URL are blocked or unavailable, not an empty success.

## Errors

| Exit | Meaning |
|---:|---|
| 2 | Vehicle, period, or limit is not in the published contract |
| 4 | Rate limit or a block on the page or settings host. `retry_after` is set only for a numeric `Retry-After` of at most six digits |
| 5 | Timeout, HTTP 5xx, or other network failure. The message includes `timed out` or `network error` |
| 6 | Malformed JSON, non-finite numbers, or a metrics object without `totalTripCount` |
| 7 | Redirect or URL outside the three Auckland allowlist shapes |

Each request uses a 10-second timeout. Page bodies are capped at 256 KiB, settings at 64 KiB, and metrics at 1 MiB after decompression. At most two redirects are followed, and the final URL must still be the Auckland page, the Auckland settings read, or the exact `trip_metrics.json` path.
