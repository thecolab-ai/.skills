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

`latest_data` on `readings` is the last observation minute in that file. `latest_data` on `files` is the newest `modified` date in the dataset listing, which is a file date, not an observation. `datasets` uses the newest published year. `gauges` has no source date, so `latest_data` is omitted. `retrieved_at` is always when this client ran.

The site text says the sensors are liable to drift and that the data has not been quality controlled. Heights are the published decimal metre strings, at most four digits before the decimal point and four after. `height_reference` is `gauge zero (TG0)`. The Auckland note gives a reference-port chart-datum relationship for benchmark DD1N and says the nearby reference gauge should be used for long-term analysis. These readings are not reduced to that datum by this skill. Sensor 40 and sensor 41 are separate series, not interchangeable defaults. At Auckland on 2026-01-01 00:00 UTC, sensor 40 is 5.002 m and sensor 41 is 4.777 m. The Auckland history says sensor 40 was reset in 2011, so a multi-year sensor 40 series is not continuous.

A daily CSV must stay on the UTC date in the file name. Auckland, Wellington (`WLGT`), and Lottin Point (`LOTT`) days checked for this skill do that. Owenga (`CHIT`) files checked for 2020 are a 1,440-minute window that starts at 23:54 on the previous UTC day, so `readings` returns `schema_failure` instead of mixing the two dates. A file may also be shorter than 1,440 minutes. Auckland sensor 41 on 2012-08-28 has 1,260 minutes and still ends at 23:59 UTC.

A raw CSV fixture has no sensor column. `sensor_origin` is `request` and `sensor_verified` is false. A zip fixture or a live daily file encodes the sensor in the member name, so `sensor_origin` is `archive_name`.

## Limits

Each HTTP call times out after 10 seconds unless `--timeout` sets 1–60. A readings request can make four calls: gauge list, datasets, file list, then one daily zip. Responses and daily zip members above 2,000,000 bytes are refused. Annual and part-year bundles are not downloaded. File pages default to 20 and cap at 366. Reading pages default to 60 and cap at 1,440. Offsets cap at 100,000. Years are 1990–2100. Sensors are integers 1–99 that must appear in the gauge dataset list. `modified` must be a real calendar date. A blank `--fixture` stays in fixture mode and is rejected. It does not fall through to the live host.

An empty file list from a published dataset is a successful empty result. A missing gauge, missing dataset, or UTC day absent from the file list is `query_status: no_match`. HTTP failures, blocks, and invalid JSON or CSV are errors with empty `results`. Duplicate minutes, timestamps on another UTC date, unsafe zip paths, and cross-host redirects fail closed.

`nz-tides-surf` serves LINZ tide predictions from `static.charts.linz.govt.nz`. It does not read this observation archive.
