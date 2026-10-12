---
name: bkg-starkregen-wms
description: "Query the BKG Hinweiskarte Starkregengefahren WMS for Germany heavy-rain hint layers and one extraordinary-event flow-velocity point. Use for GetCapabilities layer names and a single GetFeatureInfo Geschwindigkeit value at a WGS84 latitude and longitude. Distinguish a measured zero from no data, and send EPSG:4326 as latitude then longitude. Not the Berlin or Frankfurt flood services."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "public-data"
  thecolab.source_owner: "Bundesamt für Kartographie und Geodäsie (BKG)"
  thecolab.source_type: "official"
  thecolab.auth: "none"
  thecolab.access_mode: "public-api"
  thecolab.data_class: "public"
  thecolab.writes: "false"
  thecolab.browser: "false"
  thecolab.risk: "low"
  thecolab.cache_ttl: "none"
  thecolab.schema_version: "1"
  thecolab.skill_type: "public-api"
  thecolab.pack: "nz-public-data"
  thecolab.source_url: "https://sgx.geodatenzentrum.de/wms_starkregen"
  thecolab.allowed_domains: "sgx.geodatenzentrum.de"
  thecolab.last_verified: "2026-10-11"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# BKG Starkregen WMS

Read one official WMS for the BKG heavy-rain hint map. Use the Python CLI in
`scripts/cli.py`. The skill lists named layers and samples one flow-velocity
point. It does not download a Germany-wide map.

## Commands

```bash
python3 skills/bkg-starkregen-wms/scripts/cli.py layers --json
python3 skills/bkg-starkregen-wms/scripts/cli.py velocity --lat 52.0 --lon 10.0 --json
```

- `layers` reads GetCapabilities once and returns every named layer, up to 160.
  It does not call GetMap.
- `velocity --lat LAT --lon LON` sends one GetFeatureInfo for
  `geschwindigkeit_agw` (extraordinary-event flow velocity). Width and height
  stay at 101. The centre pixel is I=50, J=50.

## Coordinates and values

`--lat` and `--lon` are WGS84 decimal degrees, latitude then longitude. The
request uses WMS 1.3.0 and EPSG:4326. In that CRS the bounding-box axis order
is latitude, then longitude. The capabilities bounding box for
`geschwindigkeit_agw` advertises the same order (`minx` is latitude). A
longitude-first box is refused. CRS:84 on the same service is the opposite
order and is not used.

`Geschwindigkeit` is the source field. The service documents a 1 metre raster
resolution; it does not state a velocity unit, so the CLI does not label one.
`state` is `value` or `no_data`:

- `0` or `0.0` is a measured zero (`state` `value`).
- `no features were found` is no data (`no_data_reason` `no_feature`). The
  velocity is null, not zero.
- The exact token `-9999` or `-9999.0` is no data (`no_data_reason`
  `sentinel`). It is kept as `source_token` and is not returned as
  `geschwindigkeit`.

JSON success output is `{"meta": {...}, "results": [...]}`. `meta` carries
`source_url`, `publisher`, `retrieved_at`, and `licence` when the capabilities
Fees text states Datenlizenz Deutschland Namensnennung 2.0. Failures use
`results: []` and `error` with `code`, `type`, and `message`. An empty body, a
service exception, or a missing Geschwindigkeit field is a schema failure, not
an empty success.

Read [references/source-notes.md](references/source-notes.md) for the licence,
attribution, fixtures, and request bounds. Run `scripts/test_contract.py` and
`scripts/smoke_test.py`.
