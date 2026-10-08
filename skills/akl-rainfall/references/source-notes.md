# Environment Auckland source notes

- Authentication: none
- Last verified: 2026-10-08

Verified 8 October 2026 against the real public endpoints, without authentication
or cookie headers. Publisher: Auckland Council, Environment Auckland portal.
Primary source: <https://environmentauckland.org.nz/>.

## Verified requests

All paths below are relative to `https://environmentauckland.org.nz`.

| Surface | Request and observed behaviour |
|---|---|
| Site catalogue | POST `/Data/Data_List` with form `page=1&pageSize=1000` and numeric `parameters[i]`; returns `Data`, `Total` |
| Rainfall | Parameter 78, source name `Rainfall`: 254 datasets at 254 sites |
| River/stream level | Parameter 40, `River Water Level`: 92 datasets at 92 sites |
| River/stream flow | Parameter 82, `River Discharge`: 79 datasets at 79 sites |
| Combined | All three numeric IDs return 425 datasets at 346 sites |
| All portal locations | Catalogue without parameter IDs returns 762 locations, including other monitoring types |
| Per-location datasets | GET `/Data/DataSets?locationid=328` returns Manukau rainfall metadata; `locationid` is the **internal** `LocationId`, not site identifier 649940 |
| Conversion options | GET `/Export/DatasetCalculations?datasetId=16418` exposes units and point/interval calculations |
| JSON download | GET or read-only form POST `/Export/BulkExportJsonFile` returns `Datasets`, `TimeRange`, `NumRows`, `Rows`, `Disclaimers` |

The portal's public `/bundles/admin.js` identifies the export paths and request
fields. Numeric parameter IDs were confirmed by catalogue responses identifying
the actual returned parameter. The CLI checks every returned parameter name.
No site or dataset labels are constructed from assumed names. One rainfall series
is labelled `Continous`; preserve the actual `DatasetIdentifier`.

The visible `/Data/Map` page redirects to a public disclaimer screen. Direct data
catalogues and `/Export/BulkExportJsonFile` work anonymously without accepting that
screen. `/Export/BulkExport` and `/Export/BulkExportJson` returned HTTP 200 with
empty bodies during anonymous probes, including requests with full conversion
options. Those empty responses are not evidence of a usable CSV API.
The verified JSON-file endpoint is sufficient, so no fallback source is used.
Recorded rainfall gauges have different cadences. Mixed-cadence time-aligned bulk
exports returned empty bodies, whereas each individual gauge returned data. Latest
therefore fetches each active gauge independently, with at most four simultaneous
requests. Two gauges exported together at a common hourly interval worked. Region-
wide latest takes more requests than discovery or one-site series.

## Export form fields

Use `DateRange=Custom`, `StartTime`, `EndTime` (YYYY-MM-DD HH:mm), `TimeZone=12`,
`Calendar=CALENDARYEAR`, `Step=1`, `ExportFormat=json`, `TimeAligned=True`,
`RoundData=False`; include grades, approvals, qualifiers and interpolation types.
For each index, send `Datasets[i].DatasetName`, `.Calculation`, `.UnitId`.

| Parameter | Unit ID | Exported unit | Recorded calculation | Hour/day calculation |
|---|---:|---|---|---|
| Rainfall | 332 | mm | Instantaneous | Aggregate (total) |
| River Water Level | 282 | m | Instantaneous | Aggregate (average) |
| River Discharge | 306 | m^3/s | Instantaneous | Aggregate (average) |

Intervals are `PointsAsRecorded`, `Hourly`, `Daily`. These calculations/units were
confirmed in conversion metadata and actual rainfall, level and flow downloads.
Level and flow also expose minimum, maximum and interval-end values; this CLI
requests the verified `Aggregate` average option.

`Datasets` identifies the parameter, label, location and exported unit. Each row
has `Timestamp` and `Points`; each point identifies its dataset and value plus
quality fields. A time-aligned row can contain multiple gauges. Source `"NaN"`
means missing; it appears at the first aggregate boundary because the preceding
interval is unavailable in the requested window. The CLI preserves it as null.
Aggregate timestamps mark the interval end; each aggregate includes explicit
`period_start`/`period_end`. Daily periods are midnight–midnight fixed NZST,
which is 01:00–01:00 NZDT in summer. Use these bounds for day attribution.
It clips observations to the requested inclusive bounds and fails on mismatched
units, unexpected datasets, duplicate timestamps, malformed values or row counts.

Parser fixtures in `../tests/fixtures/` are hand-written synthetic JSON, with
fictional station identifiers, names, coordinates, dates and values. Their
manifest is `../tests/fixtures/fixtures.json`. They mirror the Data_List and
BulkExportJsonFile shapes and contain no captured source responses.

## Time, data quality and terms

The portal notice explicitly says data is recorded in NZ Standard Time (UTC+12).
Catalogue record times are naive; exports include `+12:00`. Do not use
`Pacific/Auckland` daylight-saving conversion for naive source timestamps.
Historical gauges remain in discovery. Latest queries use actual current NZST
and a 72-hour window, excluding advertised end-of-record dates outside that
window; they do not anchor a query to an obsolete gauge's last observation.

The [public disclaimer](https://environmentauckland.org.nz/Disclaimer) was checked
on 8 October 2026. Its General Terms and Conditions, clauses 1–4, state:

> 1. Auckland Council owns the copyright on the data.
>
> 2. Auckland Council shall be acknowledged as the source of the data used in any publication, media statement or other documents, or oral statements which include the data and are made available to third parties, including the general public.
>
> 3. The data is accessed with the understanding that it is for the sole use of the recipient, or its agents, and it is not intended that this data will be sold, lent or given to any third party other than for the purposes it is provided for. Data may not be sold to any third party in an unmodified form without agreement of Auckland Council.
>
> 4. The user of the data agrees to indemnify Auckland Council for any losses sustained as a consequence of a breach of any of these conditions.

Do not redistribute or republish raw extracts without agreement. Attribute
Auckland Council in outputs. No Creative Commons licence was identified; public
access does not establish open reuse rights. Some stations are operated by
ESNZ/NIWA and distributed through the Council portal;
check the station owner and its terms before reuse. Publisher metadata identifies
the portal host, not necessarily the operator of each gauge.

Data may be measured or synthesised and of varying quality; current examples
may carry grade 200 (`Non Verified`). Grade 0 (`UNDEF`) accompanies missing
aggregates. Do not use these data for
safety decisions; the disclaimer cautions against personal/public safety and
monetary/operational decisions without careful consideration.

Historical data/additional parameters: Council's contact dashboard is
<https://environmentauckland.org.nz/Data/Dashboard/457>. Access beyond available
anonymous series may require a Council data request; the CLI does not promise it.
The hosted official vendor [user guide](https://environmentauckland.org.nz/Content/Manuals/en/UserGuide.pdf)
describes downloadable export URLs and date/interval selection.
