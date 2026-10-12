# LINZ tide-gauge API notes

## Official links

- Gauge browser: https://sealevel-data.linz.govt.nz/index.html?tidegauge=AUCT
- Download description: https://www.linz.govt.nz/products-services/data/types-linz-data/sea-level-data/sea-level-data-downloads
- Licence named on that download page: http://creativecommons.org/licences/by/3.0/nz

The page says the work is licensed under Creative Commons Attribution 3.0 New Zealand, and that reuse must attribute Land Information New Zealand. Auckland civic-data catalogue row S1873 text says "CC BY 4.0 (attribute LINZ)". The download page is the licence used here.

## Calls

| Command | URL |
|---|---|
| `gauges` | `https://sealevel-data.linz.govt.nz/api/listGauges` |
| `datasets` | `https://sealevel-data.linz.govt.nz/api/getGaugeData/{GAUGE}` |
| `files` | `https://sealevel-data.linz.govt.nz/api/listDatasetFiles/{GAUGE}/{YEAR}/{SENSOR}` |
| `readings` | `https://sealevel-data.linz.govt.nz/tidegauge/{GAUGE}/{YEAR}/{SENSOR}/{GAUGE}_{SENSOR}_{YEAR}{DDD}.zip` |

`DDD` is the UTC day of year, three digits. The zip holds one CSV of the same basename. The client builds these paths from the gauge code, year, sensor, and UTC date. It does not accept a caller URL.

`listDatasetFiles` also names bundles that are not one UTC day. A whole year is `{GAUGE}_{SENSOR}_{YEAR}.zip`. A part year is `{GAUGE}_{SENSOR}_{YEAR}_{START}-{END}.zip`, with `START` and `END` as three-digit UTC day-of-year numbers. Auckland 2025 lists `AUCT_40_2025.zip` (2,515,571 bytes) ahead of the daily zips. Auckland 2009 lists `AUCT_40_2009_085-365.zip`. `files` labels those in `archive_bundles` and pages only the daily names. `readings` downloads the matching daily zip only. A name that is neither a daily file nor one of those two bundle shapes fails the listing. Bundle listing sizes may exceed 2,000,000 bytes. The daily zip download bound stays 2,000,000 bytes.

## Clock and height

The Auckland site text says the record interval is one minute and the time system is UTC. A daily CSV row is `GAUGE,YYYY-MM-DD HH:MM,height`. `2026-01-01 11:00` is `2026-01-01T11:00:00Z`. It is not shifted to a New Zealand local day.

`--date` selects the daily zip whose year and day-of-year equal that calendar date. `archive_date` is that filename date. `observed_at` is the CSV minute, copied as written. `latest_data` on `readings` is the last observation minute in that file, which may be on the adjacent calendar date. When the file contains more than one calendar date, `observation_window` records the first stamp, the last stamp, and `observation_dates`. This command does not assemble one civil day from neighbouring zips: Auckland 2020-01-08 and 2020-01-09 leave a gap between 23:54 and the next file, and Auckland 2020-08-06 overlaps 2020-08-07.

Auckland sensor 40 alignments checked for this skill:

- Through 2020-01-08, the file named for day D starts at D−1 23:54 and ends at D 23:53. `AUCT_40_2020001` is 2019-12-31 23:54 through 2020-01-01 23:53. Owenga (`CHIT_40_2020001`) has the same window.
- From 2020-01-09 through 2020-08-06, the file named for day D starts at D 23:54 and ends at D+1 23:53. `AUCT_40_2020153`, and the same ordinal for Wellington (`WLGT`), Lottin Point (`LOTT`), and Owenga, are 2020-06-01 23:54 through 2020-06-02 23:53.
- From 2020-08-07 through at least 2021-11-01, sampled Auckland days are one UTC date from 00:00 through 23:53. Later checked days, including 2025-06-01 and 2026-01-01, are 00:00 through 23:59.

A file may also be shorter than 1,440 minutes. Auckland sensor 41 on 2012-08-28 has 1,260 minutes and still ends at 23:59 UTC. A timestamp more than one calendar day away from `archive_date`, or a file that does not contain `archive_date` at all, is `schema_failure`.

`latest_data` on `files` is the newest `modified` date in the dataset listing, which is a file date, not an observation. `datasets` uses the newest published year. `gauges` has no source date, so `latest_data` is omitted. `retrieved_at` is always when this client ran.

The site text says the sensors are liable to drift and that the data has not been quality controlled. Heights are the published decimal metre strings, at most four digits before the decimal point and four after. `height_reference` is `gauge zero (TG0)`. The Auckland note gives a reference-port chart-datum relationship for benchmark DD1N and says the nearby reference gauge should be used for long-term analysis. These readings are not reduced to that datum by this skill. Sensor 40 and sensor 41 are separate series, not interchangeable defaults. At Auckland on 2026-01-01 00:00 UTC, sensor 40 is 5.002 m and sensor 41 is 4.777 m. The Auckland history says sensor 40 was reset in 2011, so a multi-year sensor 40 series is not continuous.

Scott Base and Cape Roberts publish sensor `00` only. The archive member name still has to match the requested sensor. Their gauge text also describes yearly serialisations this skill does not download. Daily zips checked for this skill use the datetime layout below. A yearly layout in a daily zip is `schema_failure`, not a guessed conversion.

Scott Base daily rows checked for 2016 and 2020 are `SCOT,yyyy-mm-dd hh:mm,height` in metres. The gauge text labels that field NZST, and the 2016-01-05 15:50 example in the text is the first row of `SCOT_00_2016005`. `observation_time` is `NZST` and `observed_at` keeps those clock numbers with offset `+12:00`. NZST is not shifted to daylight time. The filename day matches that NZST calendar date; `files` still keys the row as `utc_date` and says so in `filename_date_meaning`. Scott Base 2020-06-01 is 288 rows, 00:00 through 23:55, one date. Some later Scott Base years list only an annual zip plus a blank directory row (`name` empty, `size` 0, URI the dataset directory). That placeholder is ignored. `SCOT_00_2026_01-03.zip` is a month span in the filename (`month_start` `01`, `month_end` `03`), not days 1 through 3, and it is not downloaded.

Cape Roberts site text says the time system is UTC. Daily rows checked for 2008 are three fields. From at least 2011, daily rows add the three trailing fields named in the gauge text: sample count (0–30), sea-water temperature in °C, and atmospheric pressure in hPa. Those become `sample_count`, `sea_temperature_c`, and `pressure_hpa`. They are not copied onto other gauges. `ROBT_00_2015152` runs from 2015-06-01 00:05 through 2015-06-02 00:00. Some later Cape Roberts days stay inside the filename date, for example 2024-06-01 from 00:00 through 23:55. A year that lists only `ROBT_00_2020.zip` has no daily reading.

A raw CSV fixture has no sensor column. `sensor_origin` is `request` and `sensor_verified` is false. A zip fixture or a live daily file encodes the sensor in the member name, so `sensor_origin` is `archive_name`.

## Limits

Each HTTP call times out after 10 seconds unless `--timeout` sets 1–60. A readings request can make four calls: gauge list, datasets, file list, then one daily zip. Responses and daily zip members above 2,000,000 bytes are refused. Annual, day-of-year, and month bundles are not downloaded. File pages default to 20 and cap at 366. Reading pages default to 60 and cap at 1,440. Offsets cap at 100,000. Years are 1990–2100. Sensors are the published token `00` or an integer from 1 to 99 with no leading zero, and the token must appear in the gauge dataset list. `0`, `01`, and `100` are rejected. `modified` must be a real calendar date. A blank `--fixture` stays in fixture mode and is rejected. It does not fall through to the live host.

An empty file list from a published dataset is a successful empty result. A missing gauge, missing dataset, or filename date absent from the daily file list is `query_status: no_match`. HTTP failures, blocks, and invalid JSON or CSV are errors with empty `results`. Duplicate minutes, dates outside the filename date and its adjacent calendar day, unsafe zip paths, and cross-host redirects fail closed.

`nz-tides-surf` serves LINZ tide predictions from `static.charts.linz.govt.nz`. It does not read this observation archive.
