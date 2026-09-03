# Official source contract and verification notes

## Declared source metadata

- Primary source: https://catalogue.data.govt.nz/dataset/nzta-highway-information1
- Authentication: none
- Last verified: 2026-09-03
- Allowed outbound domains: `catalogue.data.govt.nz`, `trafficnz.info`,
  `services.arcgis.com`, `www.journeys.nzta.govt.nz`

## Ownership and discovery

The canonical discovery record is the data.govt.nz CKAN package
`nzta-highway-information1`, titled **NZTA Highway Information**. It identifies
**NZ Transport Agency** as the organisation and describes the data as traffic
congestion, travel times, incidents, cameras, and variable-message signs.

The CKAN package API is:

`https://catalogue.data.govt.nz/api/3/action/package_show?id=nzta-highway-information1`

On 2026-09-03 it returned HTTP 200 and two official resources:

1. `ArcGIS Hub Dataset`: `https://opendata-nzta.opendata.arcgis.com/maps/NZTA::nzta-highway-information`
2. `ArcGIS GeoService`: `https://services.arcgis.com/CXBb7LAjgIIdcsPt/arcgis/rest/services/NZTA_Highway_Information/FeatureServer`

The CKAN package resources do not directly list `trafficnz.info`; the first-party
traffic feed is documented separately through the live WADL below.

The catalogue web page may present an anti-bot interstitial. The CKAN API is the
machine-readable discovery surface and does not require a key.

## Source licence status

On 2026-09-03 the live CKAN package returned `isopen: false` and null values for
`license_id`, `license_title`, and `license_url`. No open-data licence may be
inferred from catalogue publication or public API access. The MIT licence in
`SKILL.md` applies only to this skill's code and documentation, not to NZTA's
source data. This client confines itself to bounded, read-only current queries;
reuse, redistribution, or republication of returned source data requires separate
due diligence and, where necessary, permission from NZTA.

## Traffic and Travel API v4

The authoritative first-party traffic feed is the live WADL contract at:

`https://trafficnz.info/service/traffic/rest/4?_wadl`

The resource root itself returns HTTP 404 when requested without a method path.
On 2026-09-03 that WADL returned HTTP 200 `application/xml`.

Relevant GET resources declared by the WADL are:

| Data | Nationwide resource | Other declared shapes |
|---|---|---|
| Cameras | `cameras/all` | by journey, region, or bounds |
| Road events | `events/all/{zoomlevel}` | by journey, region, or bounds |
| Journeys | `journeys/all/{zoomlevel}` | by region or bounds |
| Regions | `regions/all/{zoomlevel}` | within bounds |
| TIM signs | `signs/tim/all` | by journey, region, or bounds |
| VMS signs | `signs/vms/all` | by journey, region, or bounds |
| Highway ways | `ways/all/{zoomlevel}` | by region or bounds |

The API returns JSON as `{"response": {"<collection>": [...]}}`. The skill
uses only these HTTPS nationwide resources and applies local filters and a hard
result cap:

- events: `events/all/10` -> `response.roadevent`
- cameras: `cameras/all` -> `response.camera`
- displayed travel times: `signs/tim/all` -> `response.tim`
- VMS: `signs/vms/all` -> `response.vms`
- regions: `regions/all/10` -> `response.region`

No cookie, browser, username, password, or API key is required. The skill makes
GET requests only.

## Fields proved by the WADL

The WADL defines, among others:

- `roadEvent`: id, event type/description/comments, location, impact, planned,
  status, geometry, start/end, created/modified/update due, expected resolution,
  restrictions, alternative route, region/journey/way relationships
- `camera`: id/name/description, direction/highway, coordinates, image/thumb/view
  URL paths, offline and maintenance flags, region/journey/way relationships
- `vmsSign`: id/name/description, current message, message/update timestamps,
  direction, coordinates, region/journey/way relationships
- `timSign`: id/name, enabled/mode/virtual, timestamp, coordinates, pages/lines,
  and region/way/journey relationships
- `journeyLeg`: speed, time, effective speed limit, coverage, flow, and free-flow
  time fields

A field's presence in the schema does not prove that it is populated or fresh.
The parser therefore preserves nulls, fails closed when required collections are
missing, and exposes retrieval time separately from item-update time.

## Why congestion is not inferred

The catalogue description and journey schema mention congestion/travel-time
telemetry. During 2026-09-03 verification:

- `journeys/all/10` and region-specific journey endpoints repeatedly exceeded the
  required 10-second request budget; and
- the official Journey Planner `journeys.json` web cache was reachable but its
  leg `speed`, `time`, `effectiveSpeedLimit`, `coverage`, `flow`, and
  `freeFlowTime` values were all zero/unpopulated in the observed snapshot.

The TIM endpoint was responsive and returned displayed destination minutes. The
skill therefore exposes those values but sets `congestion_status: null` and
`source_provides_baseline: false`. This is an intentional safety boundary, not a
missing calculation.

## ArcGIS cross-check

The CKAN package's second resource resolved on 2026-09-03 to:

`https://services.arcgis.com/CXBb7LAjgIIdcsPt/arcgis/rest/services/NZTA_Highway_Information/FeatureServer`

The service reported:

- layer 0: `Road Events`, point geometry, max record count 2,000
- layer 1: `Road Area Events`, polyline geometry, max record count 2,000
- capabilities include Query; sync is disabled

A bounded layer-0 `returnCountOnly=true` query returned 158 records during the
verification. This independently proves that the official event dataset remains
live. The CLI does not silently combine ArcGIS and Traffic and Travel records,
because their freshness and field semantics differ.

## Observed live health on 2026-09-03

Successful bounded reads observed:

- events: 191 source records, about 2.1 seconds
- cameras: 319 source records, about 5.4 seconds
- VMS: 392 source records, about 5.1 seconds
- TIM: 270 source records, about 6.9 seconds on retry
- regions: 14 source records, close to the 10-second timeout on one probe

One concurrent TIM probe was refused before a sequential retry succeeded. The
skill declares source health `degraded` rather than overstating reliability.
Counts and timing are observations, not guarantees; rerun the smoke test for the
current state.

## Safety and completeness boundary

Operational conditions can change at any time. A missing result does not prove a
clear or safe road. The API does not promise complete local-road coverage,
per-camera image timestamps, or a congestion baseline for TIM displays. Confirm
important journeys with NZTA Journey Planner, encountered road signs, emergency
directions, and relevant local authorities.
