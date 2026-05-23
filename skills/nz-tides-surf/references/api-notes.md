# NZ Tides + Surf API notes

This skill is a lightweight read-only wrapper around official LINZ tide prediction data and no-login SwellMap surf forecast pages. It does not use account credentials, cookies, API keys, browser automation, or write actions.

## Source and auth

Implemented sources:

- LINZ tide prediction page: `https://www.linz.govt.nz/products-services/tides-and-tidal-streams/tide-predictions`
- LINZ tide port index: `https://www.linz.govt.nz/api/v1/tp`
- LINZ annual tide CSV tables: `https://static.charts.linz.govt.nz/tide-tables/maj-ports/csv/{Prediction File} {Year}.csv`
- SwellMap surf forecast pages: `https://www.swellmap.com/surf-forecasts/new-zealand/{location}`

Investigated but not wired as primary data sources:

- Surfline: `https://www.surfline.com/surf-report`; direct requests to `services.surfline.com` returned Cloudflare challenge HTML / 502 responses from this environment.
- NIWA marine forecast: `https://niwa.co.nz`; a no-key public marine wave forecast endpoint was not confirmed. The existing `metservice-nz` skill covers key-backed MetOcean marine variables.
- Magicseaweed: discontinued.

No personal username, password, API key, private token, cookie, or browser session is required for the implemented commands.

## LINZ tide endpoints

### Port index

Endpoint:

```text
GET https://www.linz.govt.nz/api/v1/tp
```

Observed response shape:

```json
[
  {
    "name": "Auckland",
    "field_location": "-36.84307,174.76946",
    "field_tide_type": "Daily Predictions",
    "field_tide_offset_file": "",
    "field_tide_reference_port": "",
    "field_tide_prediction_file": "Auckland"
  }
]
```

Important fields:

- `name` - display port name
- `field_location` - `lat,lon`
- `field_tide_type` - usually `Daily Predictions` or `Offset`
- `field_tide_reference_port` - reference port for offset ports
- `field_tide_prediction_file` - file stem for direct annual CSV predictions when present

### Annual CSV tide table

Endpoint pattern:

```text
GET https://static.charts.linz.govt.nz/tide-tables/maj-ports/csv/Auckland%202026.csv
```

CSV shape:

```text
070,Auckland,36 deg 51'S,174 deg 46'E
Based on constituent set with reference date:,01-Jul-2015
Local Std or Daylight Time,Tidal heights in metres.
1,Th,1,2026,05:47,3.1,11:51,0.8,18:06,3.1,,
```

The CLI parses rows as:

- day number
- weekday abbreviation
- month number
- year
- up to four `(time, height_m)` pairs

The CSV does not label each pair as high or low, so the CLI classifies high/low by comparing each event height to adjacent events after sorting the annual series.

## LINZ tide aliases

The CLI maps common surf-beach wording to practical LINZ tide companions:

- `Piha`, `Muriwai`, `Bethells`, `Karekare` -> `Anawhata`
- `Mt Maunganui`, `Mount Maunganui`, `Tay Street` -> `Moturiki Island`
- `Lyall Bay`, `Breaker Bay` -> `Wellington`
- `Raglan`, `Manu Bay` -> `Raglan`

These aliases are convenience routing only. JSON output includes both the user query and resolved LINZ port.

## SwellMap surf endpoint

Page endpoint:

```text
GET https://www.swellmap.com/surf-forecasts/new-zealand/piha
```

The page is server-rendered by Next.js and embeds a JSON payload in:

```html
<script id="__NEXT_DATA__" type="application/json">...</script>
```

Useful payload path:

```text
props.pageProps.initialState.forecast.forecastData
```

Direct `_next/data` JSON responses use the same object without the outer `props`
wrapper: `pageProps.initialState.forecast.forecastData`.

Observed forecast arrays:

- `time[]` - local forecast timestamps in `YYYYMMDDHHMM`
- `rating[]` - SwellMap surf rating
- `wave[]` - wave height in metres
- `swell[]` - swell height in metres
- `set_face[]` - surf face height in metres
- `period[]` - swell period in seconds
- `swell_dir[]` - swell direction degrees
- `wind_sp[]`, `wind_gust[]`, `wind_dir[]` - source wind values and wind direction degrees
- `summary_description[]` - weather summary text
- `sea_temp[]` - sea temperature objects with Celsius values
- `tide[]` - forecast-local tide rows with `time`, `level`, and `depth`

The JSON payload includes `lastUpdated`, `timezone`, location metadata, and the current region's nearby locations. The CLI normalizes 3-hourly rows and keeps all times in `Pacific/Auckland`.

## Best-break scoring

`best-break` fetches each curated break for the requested region, filters to the requested date, and scores the morning rows between 05:00 and 11:59 NZ time. If a source has no morning rows for that date, the command falls back to all rows on the date.

Sort order:

1. highest average SwellMap rating
2. highest average swell period
3. highest average wave height

The output is a forecast comparison, not a guarantee. Local banks, wind shelter, crowding, road conditions, and ability level still matter.

## Stability and safety

- Treat LINZ tide predictions as official predictions, not observed tide-gauge measurements.
- Treat SwellMap surf results as live forecast snapshots.
- LINZ CSV filenames depend on the `field_tide_prediction_file` stem and year; offset-only ports may not have direct CSV support.
- SwellMap's Next.js build id changes, so the CLI parses the embedded page payload instead of hard-coding `_next/data/{buildId}` URLs.
- SwellMap forecast arrays did not expose unit labels for wind speed in the JSON payload; the CLI names these `wind_speed_source` and `wind_gust_source`.
- Prefer small targeted requests and avoid high-volume crawling.
- Do not use this skill for emergency, rescue, commercial navigation, or safety-critical marine decisions.
