# NZTA Crash Data NZ API Notes

## Sources

- ArcGIS Hub dataset page: `https://opendata-nzta.opendata.arcgis.com/datasets/NZTA::crash-analysis-system-cas-data-1/about`
- ArcGIS FeatureServer layer: `https://services.arcgis.com/CXBb7LAjgIIdcsPt/arcgis/rest/services/CAS_Data_Public/FeatureServer/0`
- ArcGIS query endpoint: `https://services.arcgis.com/CXBb7LAjgIIdcsPt/arcgis/rest/services/CAS_Data_Public/FeatureServer/0/query`
- data.govt.nz CKAN package: `https://catalogue.data.govt.nz/dataset/crash-analysis-system-cas-data5`
- CKAN package API: `https://catalogue.data.govt.nz/api/3/action/package_show?id=crash-analysis-system-cas-data5`
- CSV mirror resource: `https://opendata-nzta.opendata.arcgis.com/api/download/v1/items/8d684f1841fa4dbea6afaefc8a1ba0fc/csv?layers=0`

The service is keyless and read-only. Use `urllib.request` with a user-agent;
no ArcGIS SDK, `requests`, browser session, or API key is required.

## Endpoint Shape

The FeatureServer layer currently reports:

- layer name: `CAS_Data_public`
- object id field: `OBJECTID`
- max record count: `2000`
- geometry: point layer, NZTM (`wkid` 2193)
- fields: 70 public crash-level fields

Use POST form encoding for larger ArcGIS query requests, especially
`outStatistics`, to avoid long URLs. Always pass `f=json` and
`returnGeometry=false` unless geometry is explicitly needed.

Common query parameters:

```text
where=crashYear >= 2025 AND crashYear <= 2026
outFields=OBJECTID,crashYear,crashSeverity,region,tlaName,fatalCount
orderByFields=crashYear DESC, OBJECTID DESC
resultOffset=0
resultRecordCount=2000
f=json
```

For totals, prefer server-side `returnCountOnly=true` or `outStatistics` rather
than paging through all records.

## Field Caveats

Useful public fields include:

- `crashYear`, `crashFinancialYear`
- `crashSeverity`: `Fatal Crash`, `Serious Crash`, `Minor Crash`,
  `Non-Injury Crash`
- `region`, `tlaName`
- `fatalCount`, `seriousInjuryCount`, `minorInjuryCount`
- `weatherA`, `weatherB`, `light`, `streetLight`, `roadSurface`, `urban`
- `speedLimit`, `advisorySpeed`, `temporarySpeedLimit`
- road user / vehicle indicators such as `bicycle`, `pedestrian`,
  `motorcycle`, `moped`, `truck`, `bus`, `schoolBus`, `train`
- road/object indicators such as `roadworks`, `slipOrFlood`, `bridge`,
  `ditch`, `guardRail`, `parkedVehicle`, `postOrPole`, `trafficSign`, `tree`

The public FeatureServer does not expose an exact `crashDate` field. The CLI
accepts `--from`/`--to` dates for a stable user interface, but filters by the
calendar years implied by those dates. Make this caveat visible whenever
reporting date-bounded results.

The public layer also does not expose detailed driver contributing-factor codes
such as alcohol/drugs, speed as a cause, or fatigue. The `factors` command
therefore aggregates public indicator fields and distributions. Do not describe
those as causal contributing factors.

## Pagination And Caps

CAS contains hundreds of thousands of rows. Never issue an unbounded
full-history query by default.

- Default `crashes` and `factors` windows are bounded to the last two calendar
  years.
- `crashes` enforces a local `--limit` with an upper bound of 5000 returned
  records.
- FeatureServer paging uses `resultOffset` and `resultRecordCount`, with page
  size at or below the service max of 2000.
- CSV mirror fallback is capped by `--scan-cap`; broad/current-year CSV scans
  may be partial and should say so.

## Reporting Lag

CAS is updated monthly. Fatal crashes generally appear within about 1 working
day. Serious and minor injury crashes can lag by about 4 weeks while Police and
CAS coding follow-up is completed. Recent-week DSI/minor totals can therefore
undercount final figures; include a lag note for current or very recent windows.
