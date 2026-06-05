# LAWA API notes

Browser/CDP sweep of LAWA pages found public Umbraco endpoints:

```text
GET https://www.lawa.org.nz/umbraco/api/mapservice/RiverQualitySites
GET https://www.lawa.org.nz/umbraco/api/swimservice/getswimsites?regionid=&sitetype=&sortby=status&siteName=
GET https://www.lawa.org.nz/umbraco/api/commonapi/GetNonMciIndicatorDataForAllLocations
GET https://www.lawa.org.nz/umbraco/api/commonapi/GetMciIndicatorDataForAllLocations
```

`RiverQualitySites` returns region polygons/backgrounds plus monitoring sites with fields such as `Id`, `Latitude`, `Longitude`, `Name`, `Url`, `Code`, `Attributes`, `SiteType`, `DataType`, `HasScientificData`, and `HasEcologyData`.

Indicator endpoints return records keyed by `LawaId` and `Parameter` with `Median`, `NofBand`, `StateScore`, and trend score fields.

`getswimsites` returns a JSON wrapper containing HTML card snippets, `TotalResultCount`, and `NextIndex`; the CLI parses useful names, subtitles, grades, and URLs from the snippets.

Boundary: public read-only environmental summaries. Do not submit forms or imply medical/safety advice beyond LAWA's displayed status/grade.
