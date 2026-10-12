# UHSLC GESLA New Zealand sea level

- Primary owner: University of Hawaii Sea Level Center
- Primary source URL: https://uhslc.soest.hawaii.edu/erddap/info/global_hourly_gesla/index.html
- Dataset: ERDDAP tabledap `global_hourly_gesla` on host uhslc.soest.hawaii.edu
- Authentication: none
- Last verified: 2026-10-11
- Data licence: The data may be used and redistributed for free but is not intended for legal use, since it may contain inaccuracies. Neither the data Contributor, ERD, NOAA, nor the United States Government, nor any of their employees or contractors, makes any warranty, express or implied, including warranties of merchantability and fitness for a particular purpose, or assumes any legal liability for the accuracy, completeness, or usefulness, of this information.

The licence text is the NC_GLOBAL `license` attribute on the dataset info page. The code licence of this skill does not set the data licence.

## What this skill requests

Every live call is one HTTPS GET built by the CLI:

`https://uhslc.soest.hawaii.edu/erddap/tabledap/global_hourly_gesla.csv?time,sea_level,flag1,flag2,record_id&record_id="<station>"&time>="<from>"&time<"<to>"`

The dataset id contains the word global. The request still names one station and a half-open UTC window of at most 48 hours. There is no command for the unconstrained table, a station list, or a caller-supplied URL. Redirects must stay on `https://uhslc.soest.hawaii.edu`. The client sends `User-Agent: thecolab-uhslc-gesla-nz/1.0 (public research; +https://github.com/thecolab-ai/.skills)` and a 15 second timeout. A response above 65536 bytes or 400 data rows is refused whole; a partial series is not returned.

`--fixture` reads one CSV file name from `tests/fixtures`. It does not take a path or a URL and it does not open a network connection.

## Units, flags and missing values

Verified from the dataset info page on 2026-10-11:

| Field | Published unit or vocabulary |
|---|---|
| time | UTC. CSV units row is `UTC`. NC_GLOBAL `TIME_ZONE_HOURS` is `0`. |
| sea_level | `m`. Long name `Sea Level`. |
| missing sea level | `-99.9999` (`NULL_VALUE`, `_FillValue` and `missing_value`) |
| flag1 | 0 no_quality_control, 1 correct_value, 2 interpolated_value, 3 doubtful_value, 4 isolated_spike_or_wrong_value, 5 missing_value |
| flag2 | 0 do_not_use, 1 use. `flag_values` are `0, 1` and `flag_meanings` are `do_not_use use`. |
| record_id | Unique GESLA time-series id. Comment: canonical name-code-country-provider filename stem. |

`DATUM_INFORMATION` is `Unspecified`. Do not relabel a value as chart datum, mean sea level, or a LINZ prediction. A `flag2` of `do_not_use` remains in the result with that meaning. A missing sea-level token becomes JSON null and `sea_level_missing: true`. Any other decimal token is kept as published text, including repeated timestamps and distinct decimal spellings of nearly equal values.

The CSV response does not state the dataset end, so series results omit `latest_data`. Do not read `retrieved_at` as data freshness. On 2026-10-11 the info page stated `time_coverage_start` `1800-01-01T07:40:00Z` and `time_coverage_end` `2026-07-15T16:30:00Z`. `START_DATE_TIME` `1950/01/01 00:00:00` and `END_DATE_TIME` `2026/07/01 00:00:00` are different attributes and are not copied into `latest_data`.

## Empty results and errors

ERDDAP returns HTTP 404 with `no matching results` both for an in-range window with `nRows = 0` and for a time outside the variable range. Both are an empty `results` array. They are not filled with invented rows. Any other 404 is a schema failure. HTTP 429 is exit 4 and keeps the raw `Retry-After` header when the source sends one. HTTP 503 and timeouts are exit 5. Malformed, truncated, non-CSV, unexpected units, an unknown flag code, or a row outside the requested window is exit 6. A window longer than 48 hours, an over-size response, or an off-host redirect is exit 7 and is rejected without returning a partial series.

## Coverage that this skill does not replace

This is the UHSLC GESLA hourly and sub-hourly series. It is not the LINZ sealevel-data minute archive (`linz-tide-gauges-nz`), not LINZ tide predictions or surf forecasts (`nz-tides-surf`), not recent GeoNet coastal tsunami-gauge readings, not SeaRise coastline projections, and not NIWA coastal ArcGIS layers. On 2026-10-11, main `1dd7e68faf707bdce2fb95542ebcce2d1f74f594` had no `uhslc-gesla-nz` skill, and open pull requests did not add this dataset.

## Smoke window

The live probe requests `auckland-auct-nzl-ttw` from `2024-01-01T00:00:00Z` inclusive to `2024-01-01T02:00:00Z` exclusive. A check on 2026-10-11 returned repeated hourly rows, including `2024-01-01T00:00:00Z` at `5.871` m with flag1 `3` (doubtful_value) and flag2 `0` (do_not_use). That sample is a public observation, not a fixture. Fixtures under `tests/fixtures` are synthetic.
