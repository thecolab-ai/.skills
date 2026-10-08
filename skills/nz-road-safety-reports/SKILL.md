---
name: nz-road-safety-reports
description: "Query keyless NZ cycling near-miss and collision reports, fixed safety camera locations and camera infringements. Use for Auckland corridor screening and road safety evidence; use nzta-crash-data-nz for CAS crashes."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "transport"
  thecolab.source_owner: "BikeMaps.org; NZ Transport Agency Waka Kotahi; New Zealand Police; Auckland Transport"
  thecolab.source_type: "mixed"
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
  thecolab.source_url: "https://bikemaps.org/"
  thecolab.allowed_domains: "bikemaps.org,nzta.govt.nz,www.nzta.govt.nz,www.police.govt.nz,raw.githubusercontent.com"
  thecolab.last_verified: "2026-10-08"
  thecolab.health: "degraded"
  thecolab.maintainer: "@adam91holt"
---

# NZ Road Safety Reports

Read keyless cycling near-miss and collision reports, fixed safety camera
locations, historical Auckland camera zones and recent Police traffic alerts.
Use this for corridor screening, then use **`nzta-crash-data-nz`** for official
CAS crash records. Self-reported incidents and infringements do not establish
crash risk, exposure, causation or a safe route.

Run the stdlib Python CLI in `scripts/cli.py`; every command supports `--json`.
Read [references/source-notes.md](references/source-notes.md) for source shapes,
reuse limits, spatial semantics and the NZTA access limitations.

| Command | Behaviour |
|---|---|
| `sources` | Six source URLs, publishers, formats and caveats; no live health probe |
| `incidents --source bikemaps --kind nearmiss|collision` | Bounded BikeMaps GeoJSON; Auckland bbox by default |
| `cameras [--bbox ...]` | NZTA fixed camera points, national by default; currently blocked from the verification network |
| `infringements [--camera ...] [--from YYYY-MM-DD --to YYYY-MM-DD]` | Attempts the May 2026 release page; filters are **gated** until the real workbook schema can be verified |
| `alerts` | Recent national Police traffic RSS items; no spatial filter |
| `camera-zones [--bbox ...]` | Historical Auckland CSV zones as straight endpoint segments |
| `corridor --near lon,lat --radius m` | BikeMaps reports, NZTA cameras and historical zones within a radius; reports unavailable sources and the infringement gate |

```bash
python3 scripts/cli.py sources --json
python3 scripts/cli.py incidents --source bikemaps --kind nearmiss --json
python3 scripts/cli.py incidents --source bikemaps --kind collision --bbox 174.735,-36.905,174.745,-36.875 --format geojson
python3 scripts/cli.py cameras --bbox 174.4,-37.2,175.2,-36.4 --json
python3 scripts/cli.py infringements --camera "Great North Road" --from 2026-01-01 --to 2026-05-31 --json
python3 scripts/cli.py alerts --json
python3 scripts/cli.py camera-zones --format geojson
python3 scripts/cli.py corridor --near 174.740,-36.890 --radius 500 --format geojson
```

Spatial commands offer `--format geojson`, which implies machine-readable
output. `--bbox` is WGS84 **minLon,minLat,maxLon,maxLat**; for negative longitude
use `--bbox=-180,-90,180,90`. BikeMaps defaults to
`174.4,-37.2,175.2,-36.4`. Camera and zone filtering is local; point containment
and zone segment intersection include the boundary. BikeMaps also receives the
bbox upstream and the CLI checks returned points locally.

Corridor radius defaults to 500 m, maximum 20 km. Distance uses a local tangent
plane, so it is approximate, especially over long distances. It is distance to
a point, not a road-following corridor. GeoJSON contains spatial features only.
Police RSS has no coordinates and appears as `not_spatial` in `source_status`;
use `alerts` for national context, without claiming those alerts are nearby.

Corridor output always sets `complete: false` and lists source status and
warnings. Access failures can coexist with useful records; parser/schema errors
fail the command. Empty nearby results do not mean the corridor is safe.

Direct JSON uses `meta` and a `results` array. Mixed sources carry provenance
in each feature's properties. Unknown data licences are omitted; public access
alone does not grant bulk reuse rights. BikeMaps exports omit narratives,
identifiers and demographic fields. Every network call uses a 10-second timeout
and the shared `nzfetch` blocked/rate-limit handling. No credentials are needed.

`infringements` is an explicit access/schema gate, **not a working infringement
row extractor**: current network blocks return code 4; if the listing becomes
accessible, code 7 gives the discovered official download URL. Camera/date
options are validated but never silently ignored in a successful result.
Do not invent workbook headers, counts, camera joins or date filtering.

Validation: `scripts/test_contract.py` runs deterministic contracts and synthetic
parser fixtures from `tests/fixtures/`; `scripts/smoke_test.py` probes real public
sources and distinguishes successful assertions from upstream skips.
