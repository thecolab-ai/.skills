# NZ road closures API notes

This skill is a lightweight read-only wrapper around public NZTA / Waka Kotahi Journey Planner data. It targets national state-highway road events and traffic cameras, not local council roads.

## Source and auth

- Journey Planner highway conditions: `https://www.journeys.nzta.govt.nz/highway-conditions/traffic-and-travel-list-view`
- Journey Planner traffic cameras: `https://www.journeys.nzta.govt.nz/traffic-cameras`
- NZTA Traffic and Travel API overview: `https://www.nzta.govt.nz/traffic-and-travel-information/use-our-data/about-the-apis`
- NZTA Traffic and Travel terms: `https://www.nzta.govt.nz/traffic-and-travel-information/use-our-data/terms-of-use`
- REST WADL: `https://trafficnz.info/service/traffic/rest/4?_wadl`

No username, password, account cookie, private token, or API key is required for the implemented read-only operations.

## Endpoint families used by the CLI

The Journey Planner SPA loads public GeoJSON cache files from:

- `GET https://www.journeys.nzta.govt.nz/assets/map-data-cache/delays.json`
- `GET https://www.journeys.nzta.govt.nz/assets/map-data-cache/cameras.json`
- `GET https://www.journeys.nzta.govt.nz/assets/map-data-cache/regions.json`
- `GET https://www.journeys.nzta.govt.nz/assets/map-data-cache/journeys.json`

Observed response headers on 23 May 2026 included `Cache-Control: max-age=60, public` for `delays.json` and `cameras.json`, so the public Journey Planner cache should be treated as approximately minute-refresh data. The files also include a top-level `lastUpdated` epoch value.

## Related Traffic and Travel REST services

NZTA documents `https://trafficnz.info/service/traffic/rest/4` as the REST endpoint for Traffic and Travel data. The WADL advertises, among others:

- `GET /events/all/{zoomlevel}`
- `GET /events/byregion/{region}/{zoomlevel}`
- `GET /cameras/all`
- `GET /cameras/byregion/{region}`
- `GET /journeys/all/{zoomlevel}`
- `GET /regions/all/{zoomlevel}`

The CLI uses the Journey Planner cache rather than `events/all/-1` because the cache matches the current Journey Planner map/list feed. A live check of `events/all/-1` returned records with `status: Resolved` as well as active records, so it needs additional lifecycle filtering before it can be a drop-in source for "current" closures.

## Schema notes

`delays.json` is a GeoJSON `FeatureCollection`:

- Top-level: `type`, `lastUpdated`, `features[]`
- Feature properties include `id`, `ExternalId`, `InternalId`, `type`, `EventType`, `EventDescription`, `EventComments`, `LocationArea`, `Impact`, `Status`, `IsPlanned`, `InformationSource`, `StartDate`, `EndDate`, `ExpectedResolution`, `LastUpdatedNice`, `LastUpdatedAgo`, and `regions[]`
- Observed `properties.type` values: `closures`, `roadworks`, `hazards`, `warnings`
- Observed `EventType` values include `Road Closure`, `Road Work`, `Scheduled Road Work`, `Road Hazard`, `Area Warning`, and `News`
- Geometry may be `Point`, `LineString`, or `MultiLineString`

`cameras.json` is a GeoJSON `FeatureCollection`:

- Feature properties include `id`, `ExternalId`, `Name`, `Description`, `Direction`, `ImageUrl`, `ThumbUrl`, `Offline`, `UnderMaintenance`, `RegionID`, `TasRegionId`, and `TasJourneyId`
- Camera image URLs currently point at `https://www.trafficnz.info/camera/{id}.jpg`

`regions.json` maps Journey Planner region ids and slugs to Traffic and Travel `tasId` values. `journeys.json` uses Traffic and Travel region ids in route `regions[]`, so the CLI compares both Journey Planner ids and `tasId` values when filtering.

## Severity scale

NZTA does not expose a single numeric severity field in the Journey Planner cache. The CLI derives a coarse `severity` field from `Impact` and `properties.type`:

- `severe` - road closed or `type=closures`
- `moderate` - delays or vehicle restrictions
- `caution` - caution, hazards, or warnings
- `roadworks` - road-work event without a stronger impact
- `info` - no stronger signal present

The original `Impact`, `EventType`, and `type` fields are preserved in JSON output.

## Scope notes

- InfoConnect APIs were officially decommissioned on 1 October 2024; use the documented Traffic and Travel APIs instead.
- Auckland Transport public transport data is already covered by `skills/at-transport`, and that skill explicitly excludes traffic or road conditions.
- A quick regional-council check found Christchurch City Council's public "Work in your area" page is available as HTML, but no clean local-road JSON feed was added here. Local-road feeds remain a stretch goal outside this state-highway-focused skill.
- Avoid high-volume polling. Use narrow filters and respect the public cache TTL.
- Do not commit browser HARs, HTML dumps, JS bundles, cookies, or screenshots into this skill.
