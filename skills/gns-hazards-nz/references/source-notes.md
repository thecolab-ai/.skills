# Source notes — GNS Science ArcGIS hazard services

- Primary owner: GNS Science (Te Pū Ao)
- Primary source: https://gis.gns.cri.nz/server/rest/services
- Declared outbound hosts: gis.gns.cri.nz
- Access mode: public-api
- Authentication: none
- Last verified: 2026-07-24

## Services used

Both services answer standard ArcGIS REST `query` requests with `f=geojson`,
anonymously, no key. Verified live 2026-07-24.

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

Features carry only `Contour` values — no event id or timestamp — and the
service holds the most recently published event model. The service description
is empty, so the CLI surfaces an explicit note that contours are per-event, not
a permanent hazard surface. The companion GeoNet product lives at
https://shakinglayers.geonet.org.nz; if per-event history is ever needed this
skill should grow a GeoNet ShakingLayers endpoint rather than overloading the
ArcGIS view.

## Reuse and licence

GNS publishes these services under CC BY 4.0 (attribute GNS Science). The
NZAFD carries a database citation: Langridge et al. (2016), NZ Active Faults
Database, New Zealand Journal of Geology and Geophysics 59:86-96.

## Discovery context

Endpoints came from the WCC Emergency Management "Public Data for GIS
Overview" spreadsheet (2026-07-24), National sheet rows "Fault" and "Shaking
layers". The server root also exposes geology map services, landslide
response, and groundwater folders that this skill deliberately does not wrap —
one clear job: fault hazard and measured shaking.

## Failure modes

- Server occasionally answers HTTP 200 with an ArcGIS JSON `error` body — the
  CLI converts that to exit 5 with the upstream message.
- `resultRecordCount` caps at the server transfer limit; `exceededTransferLimit`
  surfaces as `truncated` in payloads.
