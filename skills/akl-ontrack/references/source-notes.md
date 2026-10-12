# AKLOnTrack source notes

- Primary owner: AKLOnTrack
- Primary source: https://aklontrack.com/data
- Data licence: CC BY 4.0. The observation index states `licence.name` CC BY 4.0, `licence.url` https://creativecommons.org/licenses/by/4.0/, and attribution "AKLOnTrack (aklontrack.com), from Auckland Transport's GTFS and GTFS-Realtime feeds". The docs page separately asks for the credit "AklOnTrack, from Auckland Transport data" and says commercial use is included. The data originates with Auckland Transport and is republished by AKLOnTrack, which says it is not affiliated with Auckland Transport. The skill's MIT code licence is not the data licence.
- Declared outbound hosts: data.aklontrack.com, aklontrack.com
- Access mode: public-api
- Authentication: none
- Last verified: 2026-10-11

Checked on 2026-10-11 from the public index and the docs page. The index was JSON, version 1, with `base_url` `https://data.aklontrack.com/open/v1/`. Day files were about 180–280KB when they contained observations. One indexed day, 2026-07-09, was a real empty file (zero trips and zero stops). No key is required.

## What the commands read

`index` reads only `https://data.aklontrack.com/open/v1/index.json`. It lists `days[]` observation entries. It does not download month bundles, trip-outcome files, or reference files, even though the same index names them.

`day` reads that index, chooses the path stored for the date, and GETs `https://data.aklontrack.com/open/v1/observations/YYYY/MM/DD.json`. The path must be exactly that pattern for the same date. `--latest` still fetches only one of those files: the newest catalogue day with `rows > 0` inside the byte cap.

Requests use a named User-Agent, a 15-second timeout, no proxy environment, and HTTPS only. Redirects must stay on `data.aklontrack.com` or `aklontrack.com`. User-supplied URLs are not accepted.

## Day file layout

The publisher documents this layout on https://aklontrack.com/data. Column names are in `fields` once. Rows are positional arrays in that order.

Trip columns: `trip_id`, `route_id`, `direction_id`, `trip_rel`, `feed_version`, `stops`.

Stop columns: `stop_sequence`, `stop`, `state`, `stop_rel`, `arrival_delay`, `departure_delay`, `arrival`, `departure`.

`stop` is an index into the day file's `stops` array. That array holds station ids such as `9322-6bc7f9b8`. This skill does not call `ref/stations.json`, so it does not add station names.

`t0` is midnight in Auckland at the start of `service_date`. `arrival` and `departure` are seconds from `t0`. Delay fields are seconds late; a negative number means early. `state`: 0 the train was seen to stop, 1 cancelled, 2 skipped, 3 Auckland Transport sent nothing. `trip_rel` and `stop_rel` are Auckland Transport status codes kept as integers. `direction_id` is 0 or 1 and means different things on different lines. `feed_version` is an index into `feed_versions`. `trip_id` can be an empty string when the publisher could not match the trip.

A stop array is a prefix of those columns. The first four values are always present. Later time fields may be omitted, and a present value may be JSON null. Both mean the feed did not include that time. The skill leaves them null and does not substitute zero. A row shorter than four values, or longer than the published columns, is a schema error.

`latest_data` on an index result is the newest `days[].date`. On a day result it is that file's `service_date`. It is not the time the command ran. `generated_at` is when AKLOnTrack built the index and is not reported as the observation date.

## Bounds and failures

The index may contain at most 800 day entries. A day file may contain at most 20,000 stop rows and 1,500,000 bytes. JSON output from `day` returns at most `--limit` rows (default 20, maximum 500) after `--offset`. The command checks the file's byte length and sha256 against the index, parses it, and checks that the stop-row count equals the index `rows` value before it slices. The index `trips` integer is copied as published. On 2026-07-23 it was not equal to the number of trip arrays in the day file, so it is not recomputed.

A catalogue day with zero rows is an empty result. A date that is not in the catalogue is invalid input. Non-JSON, a changed column list, a `t0` that is not Auckland midnight, a stop count that disagrees with the index, HTTP 429, HTTP 503, a timeout, and a redirect off the allowlist are errors. A licence object whose name is not `CC BY 4.0`, or which omits a Creative Commons BY 4.0 URL or attribution, is refused. An upstream outage is not reported as an empty set of trains.

## Coverage gap

`nz-data-catalogue` can name `data.aklontrack.com` because the host appears in its source catalogue allowlist. It does not parse this observation archive. `at-transport` is the live Auckland Transport API. `gtfs-nz` reads static timetables. `nz-trains` is Wellington Metlink realtime. None of those commands reads `/open/v1/index.json` or `observations/YYYY/MM/DD.json`.
