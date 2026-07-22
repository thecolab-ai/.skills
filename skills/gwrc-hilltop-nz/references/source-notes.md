# Source notes — GWRC Hilltop server

- Primary owner: Greater Wellington Regional Council
- Primary source: https://hilltop.gw.govt.nz/data.hts
- Declared outbound hosts: hilltop.gw.govt.nz
- Access mode: public-api
- Authentication: none
- Last verified: 2026-07-22

## Endpoint

`https://hilltop.gw.govt.nz/data.hts` is Greater Wellington Regional Council's public
Hilltop time-series server (the backend behind https://graphs.gw.govt.nz/). It answers
standard Hilltop REST queries with XML and needs no key, cookie, or login:

- `?Service=Hilltop&Request=SiteList&Location=LatLong[&Measurement=Flow]` — sites with WGS84 coordinates
- `?Service=Hilltop&Request=MeasurementList&Site=<name>` — data sources and measurements at one site
- `?Service=Hilltop&Request=GetData&Site=<name>&Measurement=<name>&TimeInterval=PT72H` — raw time series
- `?Service=Hilltop&Request=GetData&Collection=<name>[&Method=Total|Average&Interval=1 hour]` — collection-wide series with server-side aggregation
- `?Service=Hilltop&Request=CollectionList` — named collections (includes `Rainfall` and `River and Stream Levels`)

Verified live 22 July 2026 (server version 2606.0.2.92, `<Agency>GWRC</Agency>`).

## Characteristics observed

- ~700 sites total; ~120 in the `River and Stream Levels` collection and ~85 rain gauges
  in the `Rainfall` collection.
- Gauges log at ~5–15 minute intervals. GWRC documents that loggers upload every 2–3
  hours, so "latest" values can lag real conditions by that much — surfaced in SKILL.md
  and the `latest` command's guidance text.
- Timestamps are naive NZ local time strings; the CLI passes them through unchanged and
  labels them.
- Decommissioned gauges still answer collection queries with their last-ever data (one
  Miramar gauge returns 2016 data). The `rainfall`/`rivers` commands drop rows older
  than the freshest observation minus the window plus six hours of slack, and report the
  excluded count.
- The `River and Stream Levels` collection carries more than levels: temperature,
  dissolved oxygen, turbidity, compliance flows, and secondary/backup sensors
  (`Stage 2`, `Water Level 2`, `... (Backup Logger)` sites). The `rivers` command keeps
  only primary `Stage`/`Flow` items and dedupes per site.
- Spaces must be percent-encoded (`%20`); the server does not treat `+` as a space in
  every request type.
- Errors come back as `<HilltopServer><Error>...</Error>` with HTTP 200; the CLI maps
  unknown-site errors to invalid-input exit 2 and other server errors to exit 5.

## Generalisation

Most NZ regional councils run Hilltop servers with this exact query surface. Every
command takes `--base-url` so the skill works against other councils' endpoints
unchanged; only the GWRC default is baked in and allowlisted.

## Stability and licence

- No published rate limits; the CLI bounds windows (max 168 h for collection queries)
  and encourages narrow filters.
- GWRC publishes environmental data under CC BY 4.0 (attribute "Greater Wellington
  Regional Council"). The Hilltop endpoint itself carries no separate ToS page; treat
  it as a stable public service that GWRC's own graphing site depends on.
- River level/flow data is provisional until quality-coded; flood decisions belong to
  official warnings, not raw gauge reads.
