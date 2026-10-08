# OSM NZ API notes

This skill is an unofficial lightweight wrapper around the public OpenStreetMap Overpass API.

## Source and auth

- Service: OpenStreetMap Overpass API
- Endpoint: `https://overpass-api.de/api/interpreter`
- Auth model: none — public, no API key, no login, no rate-limiting account required
- Fair use: avoid rapid repeated queries; Overpass is a shared community resource

## How it works

The Overpass API accepts POST requests with an `application/x-www-form-urlencoded` body containing a single `data` field with an Overpass QL query. The query language is a declarative syntax for filtering OSM elements by tags and geographic bounds.

Example query to find restaurants within 2 km of a point:

```text
[out:json][timeout:8][maxsize:8388608];
(
  node["amenity"="restaurant"] (around:2000,-36.8485,174.7633);
  way["amenity"="restaurant"] (around:2000,-36.8485,174.7633);
);
out center tags;
```

## Response shape

```json
{
  "version": 0.6,
  "generator": "Overpass API",
  "osm3s": { ... },
  "elements": [
    {
      "type": "node",
      "id": 123456789,
      "lat": -36.8481234,
      "lon": 174.7635678,
      "tags": {
        "amenity": "restaurant",
        "name": "The French Cafe",
        "cuisine": "french",
        "addr:street": "210 Symonds Street",
        "addr:city": "Auckland"
      }
    }
  ]
}
```

For `way` elements, coordinates come from the `center` object (Overpass computes the centroid).

## Category mapping

The CLI maps 9 user-friendly category names to specific OSM tag pairs:

| Category | OSM keys used | Examples |
|----------|--------------|----------|
| food | amenity | restaurant, cafe, bar, pub, fast_food |
| grocery | shop | supermarket, convenience, grocery, bakery |
| outdoors | leisure, natural | park, garden, beach, nature_reserve |
| culture | tourism, amenity | museum, gallery, theatre, cinema, library |
| attractions | tourism, historic | viewpoint, monument, zoo, castle |
| sports | leisure | sports_centre, swimming_pool, stadium |
| shopping | amenity, shop | marketplace, mall, department_store |
| transport | highway, railway, amenity | bus_stop, station, ferry_terminal |
| worship | amenity | place_of_worship |

## Discovery notes

- OSM data is community-maintained — coverage and tag quality vary significantly
- Urban NZ areas (Auckland, Wellington, Christchurch) have good coverage
- Rural areas may have sparse or missing POIs
- Some businesses may be mapped but lack name tags — these are filtered out
- The Overpass API `[timeout:8][maxsize:8388608]` bounds server processing; the HTTP timeout is 10 seconds
- Duplicate results (same name + category) are deduplicated
- The public `overpass-api.de` instance is shared; consider using a local instance for production

## Stability and safety

- The Overpass API schema and endpoint are stable but not formally versioned
- Do not use for safety-critical navigation or emergency services
- Respect fair-use limits — the CLI has no built-in rate limiting across invocations
- OSM tags can be inaccurate, incomplete, or outdated — verify critical information
- Do not redistribute bulk OSM datasets through this wrapper

## Raw tags in a bbox or area

`query` accepts repeatable `--tag key=value` filters, combined with AND.
`key=*` selects any object carrying the key. Keys are validated and values are
quoted as string literals; this is not a raw Overpass QL or regex interface.
`nwr` includes nodes, ways and relations. Unnamed features and full tags survive.
Bboxes use WGS84 minLon,minLat,maxLon,maxLat and at most 1 degree wide/high.
Overpass internally receives south,west,north,east.

`--area` is a numeric Overpass area ID, not a relation ID or name. An OSM relation
usually maps to relation ID + 3600000000 when Overpass has generated its area.
Area queries also restrict results to the mainland/Chatham NZ bounding rectangles.
The endpoint returns at most limit+1 elements (maximum 101); the CLI trims the
extra element and reports `truncated`. It does not report a full matching count.
Output order follows Overpass, not distance. Response bytes are capped at 8 MiB.
Any upstream `remark` is an incomplete-query error, not a successful partial list.

GeoJSON contains point geometry. Way/relation centres represent the bounding
box of the entire object and may be outside the query bbox; use an actual
geometry source for fence lines. `latest_data` is `osm3s.timestamp_osm_base`,
not a guarantee that every tag was surveyed at that time. Attribution: OSM
contributors, ODbL 1.0 (the licence is also stated by `osm3s.copyright`).

`tests/fixtures/spatial.json` is a trimmed public fence response. Fixture checks
in `scripts/spatial_contract.py` run through both `scripts/test_contract.py`
and `scripts/smoke_test.py`.
