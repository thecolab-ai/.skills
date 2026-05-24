# GeoNet API notes

Public base:

```text
https://api.geonet.org.nz/
```

Verified endpoints:

- `quake?MMI=<n>` returns GeoJSON FeatureCollection of recent earthquakes filtered by reported/intensity MMI.
- `quake/<publicID>` returns detail GeoJSON FeatureCollection for one event; unknown IDs return an empty feature list with HTTP 200.
- `volcano/val` returns GeoJSON FeatureCollection of volcanic alert levels.
- `news/geonet` returns recent GeoNet news and volcanic activity bulletins.

Boundary: public read-only geohazard data. The CLI is not an emergency alerting system; always refer users to official Civil Defence/GeoNet guidance for safety-critical decisions.
