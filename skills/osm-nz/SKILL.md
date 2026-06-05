---
name: osm-nz
description: Query OpenStreetMap Overpass API for nearby points of interest, attractions, amenities, shops, and services around any NZ location. Use when the task involves finding what's nearby — restaurants, cafes, parks, shops, transport stops, museums, beaches — given coordinates or an address. No login or API key required. Read-only.
---

# OSM NZ — OpenStreetMap Nearby Search

## Goal

Query OpenStreetMap data for points of interest around a location using the public Overpass API, with a lightweight deterministic CLI.

## Use this when

- A user asks "what's near me" or "what's around this area"
- A user wants to find nearby restaurants, cafes, parks, or shops
- A user needs a list of supermarkets, convenience stores, or food options in an area
- A user asks about attractions, museums, viewpoints, or historic sites nearby
- A user wants to know what transport options (bus stops, train stations, ferry terminals) are close
- A workflow needs structured, geocoded POI data

## Do not use this for

- Real-time business hours, ratings, or reviews — OSM data is static and crowdsourced
- Driving directions or route planning — this only returns locations
- Guaranteed completeness — OSM coverage varies by area
- High-precision address geocoding — OSM tags are community-maintained
- Live public transport schedules — this only returns stop locations

## Preferred workflow

1. Use `nearby <lat> <lon>` to find all POIs around a location with walking/driving times
2. Filter by category with `--category` for targeted results
3. Use `--json` for agent chaining, comparisons, or structured reports
4. Sort by distance (default) and scan the closest options first

## CLI

Run with:

```bash
python3 skills/osm-nz/scripts/cli.py <command> [flags]
```

### Commands

- `nearby <lat> <lon> [--radius N] [--category CAT] [--limit N] [--json]` — POIs around a coordinate
- `categories` — list available category filters

### Category filters

| Filter | What it covers |
|--------|---------------|
| `food` | Restaurants, cafes, bars, pubs, fast food |
| `grocery` | Supermarkets, convenience stores, bakeries, butchers |
| `outdoors` | Parks, gardens, beaches, nature reserves |
| `culture` | Museums, galleries, theatres, libraries |
| `attractions` | Viewpoints, monuments, historic sites, zoos |
| `sports` | Sports centres, swimming pools, stadiums |
| `shopping` | Markets, malls, general retail |
| `transport` | Bus stops, train stations, ferry terminals |
| `worship` | Churches, mosques, temples, all places of worship |

If no `--category` is given, all categories are returned.

Examples:

```bash
python3 skills/osm-nz/scripts/cli.py nearby -36.8485 174.7633 --radius 2000
python3 skills/osm-nz/scripts/cli.py nearby -36.8485 174.7633 --category food --limit 10 --json
python3 skills/osm-nz/scripts/cli.py nearby -41.2865 174.7762 --category culture --radius 5000
python3 skills/osm-nz/scripts/cli.py categories
```

## Resources

- CLI entrypoint: `scripts/cli.py`
- Smoke test: `scripts/smoke_test.py`
- API notes: `references/api-notes.md`

## Notes

- No API key, login, or account required — Overpass API is public and free
- Results are sorted by distance from the query point (closest first)
- Walking time estimated at 5 km/h; driving at 30 km/h (urban average)
- Travel mode is "walk" for places under 1.5 km, "drive" otherwise
- The Overpass API has a fair-use policy — avoid rapid repeated queries
- Coordinates are limited to New Zealand bounds and radius is capped at 10 km to protect the shared public API
- OSM data coverage varies: urban areas are well-mapped, rural areas less so
- Some results may lack names or have incomplete tags — these are filtered out
