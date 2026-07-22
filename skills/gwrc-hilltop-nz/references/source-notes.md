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
- Hilltop resolves `TimeInterval` relative to a gauge's LAST record, not now, so
  decommissioned gauges still answer queries with their last-ever data (one Miramar
  gauge returns 2016 data). The `rainfall`/`rivers` commands drop rows older than the
  freshest observation minus the window plus six hours of slack and report the excluded
  count; `latest` ages the reading against actual NZ time and sets `stale: true` (with
  a human-readable warning) when it falls outside the requested window.
- A primary rainfall sensor can flatline at 0 with a current timestamp while its
  backup records real rain (seen live at Waitatapia Stream at Taungata: primary 0.0 mm,
  backup 3.5 mm, same timestamp). The CLI reports the primary; cross-check
  neighbouring gauges before treating an isolated zero as ground truth.
- The `River and Stream Levels` collection carries more than levels: temperature,
  dissolved oxygen, turbidity, compliance flows, and secondary/backup sensors
  (`Stage 2`, `Water Level 2`, `... (Backup Logger)` sites). The `rivers` command keeps
  only primary `Stage`/`Flow` items and dedupes per site.
- Spaces must be percent-encoded (`%20`); the server does not treat `+` as a space in
  every request type.
- Errors come back as `<HilltopServer><Error>...</Error>` with HTTP 200; the CLI maps
  unknown-site errors to invalid-input exit 2 and other server errors to exit 5.
- Measurement labels are not unique per site. `MeasurementList` can expose several
  `Stage` rows under different data sources, each with a distinct `RequestAs` value.
  The `measurements` command prints that copy-pastable value. For a plain label,
  `latest` selects the matching row with the newest advertised `To` timestamp; an
  explicit `RequestAs` value selects that exact series.

## Generalisation

Most NZ regional councils run Hilltop servers with this exact query surface. The
registry (`councils` command / `--council`) ships the servers that answered the
standard queries when verified on 2026-07-22:

- gwrc — https://hilltop.gw.govt.nz/data.hts (default)
- hbrc — https://data.hbrc.govt.nz/Envirodata/data.hts
- marlborough — https://hydro.marlborough.govt.nz/data.hts
- northland — https://hilltop.nrc.govt.nz/data.hts
- tasman — https://envdata.tasman.govt.nz/data.hts

Collection names are council-specific (e.g. HBRC uses `HBRC_Rainfall`), so the
`rainfall`/`rivers` GWRC defaults need `--collection` when pointed elsewhere.
Probed but not shipped: Horizons, Gisborne, Environment Southland (hosts did not
resolve on the guessed patterns), Bay of Plenty (responded without an Agency
element). Arbitrary endpoints are not accepted: new official council servers must
be verified, added to the registry, and declared in `thecolab.allowed_domains`.

## Stability and licence

- No published rate limits; the CLI bounds windows (max 168 h for collection queries)
  and encourages narrow filters.
- GWRC publishes environmental data under CC BY 4.0 (attribute "Greater Wellington
  Regional Council"). The Hilltop endpoint itself carries no separate ToS page; treat
  it as a stable public service that GWRC's own graphing site depends on.
- River level/flow data is provisional until quality-coded; flood decisions belong to
  official warnings, not raw gauge reads.
