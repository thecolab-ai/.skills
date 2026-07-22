# Source notes

- Primary owner: GeoNet
- Primary source: https://api.geonet.org.nz/
- Declared outbound hosts: api.geonet.org.nz, tilde.geonet.org.nz
- Access mode: public-api
- Authentication: none
- Last verified: 2026-07-22

Tilde (`https://tilde.geonet.org.nz/v4/`) is GeoNet's open time-series API for
low-rate sensor data. Verified endpoints: `dataSummary/` (domain overview),
`dataSummary/<domain>` (stations, coordinates, series with latest-record times),
and `data/<domain>/<station>/<name>/<sensorCode>/<method>/<aspect>/latest/<window>`
with windows 30m/6h/1d/2d/7d/30d. Timestamps are UTC. Coastal tsunami gauges
stream 15-second water heights near-real-time; DART buoys routinely report
15-minute summaries and only stream `water-height` during tsunami events, and an
offline buoy's staleness is reported explicitly rather than as an empty success.

The skill is read-only unless its SKILL.md metadata explicitly declares mutations. Live results must retain source and retrieval-time context. A blocked, unavailable, or changed source is an explicit failure state, never an empty successful dataset.
