# Source notes — GNS Science and GeoNet hazard services

- Primary owner: GNS Science / Earth Sciences New Zealand
- Primary archive source: https://shakinglayers.geonet.org.nz/api/v1/events
- Archive API base: https://shakinglayers.geonet.org.nz/api/v1
- ArcGIS source: https://gis.gns.cri.nz/server/rest/services
- Declared outbound hosts: gis.gns.cri.nz, shakinglayers.geonet.org.nz
- Access mode: public-api
- Authentication: none
- Last verified: 2026-07-26

## GeoNet ShakingLayers archive

The API documentation is at `https://shakinglayers.geonet.org.nz/api`. The CLI
uses only these read-only API v1 paths:

- `GET /api/v1/events[?year=YYYY]` — event ID array; without `year`, the API
  documents a recent-events window
- `GET /api/v1/events/{eventId}` — event `publicID` and versions in descending
  issue-time order
- `GET /api/v1/events/{eventId}/{version}` — resolved version metadata and file
  names; `version` may be `latest`
- `GET /api/v1/events/{eventId}/{version}/{fileName}` — one published file

Event IDs, version paths, and file names are validated as single safe path
segments before URL construction. Archive requests use `lib.nzfetch.fetch_bytes`
so the CLI can validate the returned final URL itself after redirect handling:
scheme, host, port, and API path must remain exact. HTTP 404 responses use a
structured `not_found` category that distinguishes event, version, and file
absence from generic upstream unavailability.

The CLI derives available measures from these published contour-line files:

| CLI measure | Published file | Units |
| --- | --- | --- |
| `mmi` | `intensity_mmi_contour_lines.json` | MMI |
| `pga` | `pga_g_contour_lines.json` | g |
| `pgv` | `pgv_cms_contour_lines.json` | cm/s |
| `psa0.3` | `psa_0p3_g_contour_lines.json` | g |
| `psa1.0` | `psa_1p0_g_contour_lines.json` | g |
| `psa3.0` | `psa_3p0_g_contour_lines.json` | g |

`event-data` returns the upstream GeoJSON without discarding its metadata,
features, CRS, or bounding box. It adds a top-level `provenance` object with
the requested and resolved version, issue status/time/type, measure, units,
file name, licence, and exact source URL. If a measure is not published for a
version, the CLI fails explicitly and lists the available measures and files.
When `latest` is requested, listed file URLs and the subsequent contour fetch
use the resolved immutable `versionpath`, preventing a moving-version race.

## Services used

Both services answer standard ArcGIS REST `query` requests anonymously, no key.
Feature queries use `f=geojson`; count and object-ID queries use `f=json`.
Verified live 2026-07-26.

### NZ Active Faults Database

`/Active_Faults/NZActiveFaultDatasets/MapServer` (ArcGIS Server 11.5):

- [0] 1:250 000 Active Faults — the NZAFD-AF250 national fault traces
- [1] 1:250 000 Fault Sense
- [2] 1:250 000 Recurrence Interval
- [3] 1:250 000 Last Event
- [4] 1:250 000 Slip Rate
- [5] 1:250 000 Single Event Displacement
- [6] High Resolution Active Fault Traces
- [7] Fault Avoidance Zones
- [8] Fault Awareness Areas

The same data also fronts `https://data.gns.cri.nz/af/` (NZAFD web app). The
1:250,000 layers derive from the QMAP-scale database; high-resolution traces,
avoidance zones, and awareness areas are progressively populated by region —
absence of an avoidance zone is not evidence a fault is absent.

### ShakingLayers

`/ShakingLayers/ShakingLayers/FeatureServer` — mean ground-motion contour
layers regenerated after significant NZ earthquakes:

- [1] mmi_mean_cont (Modified Mercalli Intensity)
- [4] pga_mean_cont (peak ground acceleration)
- [7] pgv_mean_cont (peak ground velocity)
- [10/13/16] psa0p3/psa1p0/psa3p0_mean_cont (pseudo-spectral acceleration)

The ArcGIS view is the convenient latest modelled output. It is not
measured-only data: ShakingLayers combines earthquake source information,
ground-motion models, and recorded strong-motion data, and reviewed runs may
incorporate further scientific inputs. Features carry only `Contour` values,
not event ID/version provenance. Use the archive commands for a specific event.

### ArcGIS query and metadata controls

`describe` requests a layer's ArcGIS JSON metadata and normalizes its fields,
aliases, descriptions/units when present, extent, spatial reference,
capabilities, geometry type, object ID field, and maximum record count.

Feature-query options map directly to ArcGIS REST:

| CLI option | ArcGIS parameter |
| --- | --- |
| `--count` | `returnCountOnly=true` |
| `--ids-only` | `returnIdsOnly=true` |
| `--no-geometry` | `returnGeometry=false` |
| `--offset` | `resultOffset` |
| `--order-by` | `orderByFields` |
| `--geometry-precision` | `geometryPrecision` |
| `--max-allowable-offset` | `maxAllowableOffset` |

`--count` and `--ids-only` are mutually exclusive. Bounding boxes accept both
`--bbox -180,-90,180,90` and `--bbox=-180,-90,180,90`, reject non-finite
values, and enforce longitude/latitude ranges before network access.
User-supplied `--fields` values accept only comma-separated ArcGIS identifiers;
`--order-by` accepts only comma-separated `FIELD [ASC|DESC]` clauses. Dotted
identifiers require complete, non-empty segments, and injection syntax such as
semicolons and functions is rejected before a request is made.

## Reuse and licence

The ArcGIS outputs report CC BY 4.0 attribution to GNS Science. GeoNet archive
outputs report the API site's CC BY 3.0 New Zealand attribution to GeoNet. The
NZAFD carries a database citation: Langridge et al. (2016), NZ Active Faults
Database, New Zealand Journal of Geology and Geophysics 59:86-96.

## Discovery context

Endpoints came from the WCC Emergency Management "Public Data for GIS
Overview" spreadsheet (2026-07-24), National sheet rows "Fault" and "Shaking
layers". The server root also exposes geology map services, landslide
response, and groundwater folders that this skill deliberately does not wrap —
one clear job: fault hazard and modelled shaking.

## Failure modes

- A requested event/version/file may not exist; the API's HTTP error is
  preserved as an upstream-unavailable failure rather than replaced with data.
- An archive response with missing versions/files, an unsafe file path, or
  non-GeoJSON contour data is a source-schema failure.
- Server occasionally answers HTTP 200 with an ArcGIS JSON `error` body — the
  CLI converts that to exit 5 with the upstream message.
- `resultRecordCount` caps at the server transfer limit; `exceededTransferLimit`
  surfaces as `truncated` in payloads.
