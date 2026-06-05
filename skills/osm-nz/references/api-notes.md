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
[out:json][timeout:25];
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
- The Overpass API `[timeout:25]` ensures queries don't hang forever
- Duplicate results (same name + category) are deduplicated
- The public `overpass-api.de` instance is shared; consider using a local instance for production

## Stability and safety

- The Overpass API schema and endpoint are stable but not formally versioned
- Do not use for safety-critical navigation or emergency services
- Respect fair-use limits — the CLI has no built-in rate limiting across invocations
- OSM tags can be inaccurate, incomplete, or outdated — verify critical information
- Do not redistribute bulk OSM datasets through this wrapper
