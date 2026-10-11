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

## Clock and height

The Auckland site text says the record interval is one minute and the time system is UTC. A daily CSV row is `GAUGE,YYYY-MM-DD HH:MM,height`. `2026-01-01 11:00` is `2026-01-01T11:00:00Z`. It is not shifted to a New Zealand local day.

`latest_data` on `readings` is the last observation minute in that file. `latest_data` on `files` is the newest `modified` date in the dataset listing, which is a file date, not an observation. `datasets` uses the newest published year. `gauges` has no source date, so `latest_data` is omitted. `retrieved_at` is always when this client ran.

The site text says the sensors are liable to drift and that the data has not been quality controlled. Heights are the published decimal metre strings. The Auckland note gives a reference-port chart-datum relationship for benchmark DD1N and says the nearby reference gauge should be used for long-term analysis. These readings are not reduced to that datum by this skill. Sensor 40 and sensor 41 are separate series. The Auckland history says sensor 40 was reset in 2011, so a multi-year sensor 40 series is not continuous.

## Limits

Each HTTP call times out after 10 seconds unless `--timeout` sets 1–60. A readings request can make four calls: gauge list, datasets, file list, then one zip. Responses above 2,000,000 bytes are refused. File pages default to 20 and cap at 366. Reading pages default to 60 and cap at 1,440. Offsets cap at 100,000. Years are 1990–2100. Sensors are integers 1–99 that must appear in the gauge dataset list.

An empty file list from a published dataset is a successful empty result. A missing gauge, missing dataset, or UTC day absent from the file list is `query_status: no_match`. HTTP failures, blocks, and invalid JSON or CSV are errors with empty `results`. Duplicate minutes, timestamps on another UTC date, unsafe zip paths, and cross-host redirects fail closed.

`nz-tides-surf` serves LINZ tide predictions from `static.charts.linz.govt.nz`. It does not read this observation archive.
