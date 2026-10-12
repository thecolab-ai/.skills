---
name: gns-auckland-geology
description: "Query GNS Science Auckland urban geological units from the public WFS. Use for a bounded WGS84 bounding-box lookup of unit code, stratigraphic name, age code, map scale, and polygon geometry. Do not use for active faults, shaking layers, or geological maps of other cities."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "geospatial"
  thecolab.source_owner: "GNS Science"
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
  thecolab.source_url: "https://data.gns.cri.nz/webmaps/gns/wfs"
  thecolab.allowed_domains: "data.gns.cri.nz"
  thecolab.last_verified: "2026-10-12"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# GNS Auckland geology

Read Auckland urban geological map units from the GNS Science WFS. The command
requests one feature type, `gns:NZL-Urban_Auckland_geological_units`, inside a
WGS84 bounding box, and stops after the requested count. Python 3.10+, standard
library only. No API key.

`gns-hazards-nz` reads active-fault and shaking-layer services. `nz-arcgis`
can call `gis.gns.cri.nz`. Neither reads this WFS type.

Use `scripts/cli.py`. `units` accepts `--json`. Human text is the default.
`--format geojson` prints a FeatureCollection. Read `references/source-notes.md`
for the licence, axis order, and error codes.

## Commands

```bash
python3 skills/gns-auckland-geology/scripts/cli.py units --bbox 174.76,-36.86,174.78,-36.84 --limit 1 --json
python3 skills/gns-auckland-geology/scripts/cli.py units --bbox 174.76,-36.86,174.78,-36.84 --limit 1 --format geojson
```

`--bbox` is `minLon,minLat,maxLon,maxLat` in WGS84 decimal degrees. A box that
starts with a negative longitude needs the equals form, for example
`--bbox=-180,-90,180,90`. `--limit` is an integer from 1 to 5. There is no
paging flag. Published unit codes may contain `~` and `+`, as in `tl~` and
`Qval+tl~`. A leading `?` is the GNS uncertainty marker, as in `?Pks~`. The
raw code is kept and `uncertain` is true. An empty code, a leading `~` or
`+`, whitespace, or markup is rejected. A null stratigraphic name is omitted.

The WFS `BBOX` is the intersection filter. A feature a short distance outside
the box is kept. A feature far outside is omitted and counted in
`dropped_outside_bbox`. One such feature does not discard the other units.
If every feature is far outside the box, the command fails with a schema
error. An empty `results` array means the server reported no intersection.

## Boundaries

- One `units` command sends one GetFeature request. Timeout 15 seconds.
- The response cap is 512 KiB. A larger body is an error, not a partial map.
- Requests stay on `https://data.gns.cri.nz/webmaps/gns/wfs`.
- Attribute GNS Science under Creative Commons Attribution 3.0 New Zealand.

## Resources

- `scripts/cli.py` — canonical command entrypoint
- `scripts/test_contract.py` — deterministic contract and parser fixtures
- `scripts/smoke_test.py` — fixture checks and bounded live probes
- `references/source-notes.md` — licence, CRS, fields, and errors
