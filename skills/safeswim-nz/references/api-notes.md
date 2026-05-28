# SafeSwim NZ API notes

This skill is an unofficial lightweight wrapper around public read-only SafeSwim REST endpoints used by the safeswim.org.nz web app.

## Source and auth

- Website: `https://safeswim.org.nz`
- Public API: `https://safeswim.org.nz/api`
- Auth model: none — public, no API key, no cookie, no login required

## Endpoints

- `GET /api/locations` — list of SafeSwim-supported NZ swimming locations with summary data (name, slug, position, water quality, patrol status)
- `GET /api/locations/{slug}` — full detail for a single location: description, forecasts (hourly water quality, temperature, wind, UV, tide), tags (facilities + hazards), alerts, patrol info, camera ID, images

## Data shape

### Location summary (`/api/locations`)

```json
{
  "locations": [
    {
      "name": "Takapuna",
      "alternative_name": null,
      "slug": "takapuna",
      "position": [-36.7916, 174.7791],
      "patrolled": true,
      "state": {
        "quality": "GREEN",
        "patrol": "Weekends 12pm-6pm",
        "safety": "Swim between the flags"
      }
    }
  ]
}
```

### Location detail (`/api/locations/{slug}`)

Additional fields include:
- `description`: paragraph about the swimming location
- `tags[]`: `LOCATION_FACILITY` (toilets, BBQ, playground, etc.) and `LOCATION_HAZARD` (rocks, rips, etc.)
- `forecasts`: arrays of hourly values (typically 48-72 hours)
  - `WATER_QUALITY`: GREEN/AMBER/RED/RED+/BLACK status each hour
  - `ATMOSPHERIC_TEMPERATURE`: °C
  - `WATER_TEMPERATURE`: °C
  - `WIND_SPEED`: km/h string
  - `WIND_DIRECTION`: cardinal
  - `UV_INDEX`: number
  - `WEATHER_CONDITIONS`: descriptive
  - `TIDE`: height in metres (may be null)
- `alerts[]`: wastewater overflow or contamination warnings
- `camId`: live webcam ID (if available)
- `images[]`: location photo identifiers/URLs

## Water quality codes

| Code | Meaning |
|------|---------|
| GREEN | Safe to swim |
| AMBER | Caution — check conditions |
| RED | Unsafe — do not swim |
| RED+ | Very unsafe — high risk |
| BLACK | Wastewater overflow — stay out of water |

## Discovery notes

- The full location list is fetched once and filtered in-process by the CLI; brief in-process caching avoids duplicate fetches within the same CLI invocation
- Water quality changes rapidly after rainfall (>5mm in 24h can trigger AMBER/RED)
- Not all locations return all forecast fields — some arrays may be sparse or absent
- SafeSwim covers only locations returned by the live API; it is not an all-NZ waterway catalogue
- The alternative_name field may contain Māori names for some locations
- Slugs are URL-safe, lowercase, usually hyphenated or compact lowercase (e.g. "takapuna", "murrays-bay", "piha")

## Stability and safety

- Treat quality data as live snapshots — conditions can change between API refreshes
- Forecast data is model-generated from MetService and NIWA sources
- Endpoint shapes can change without notice as this is not a formally documented public API
- Avoid high-frequency polling; the CLI caches for 2 seconds but manual rapid-fire calls should be avoided
- Do not use for safety-critical decisions — always check physical signage at the location
