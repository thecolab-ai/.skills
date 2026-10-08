---
name: nz-recycling-locator
description: "Find New Zealand reuse and recycling drop-offs by material and location, including salvaged building stock locations, op shops and Christchurch collection depots, plus text search of repair cafés and Tyrewise collection sites. Use when locating material collection services or searching local repair events."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "environment"
  thecolab.source_owner: "RecycleMap NZ, WasteMINZ and collection networks"
  thecolab.source_type: "mixed"
  thecolab.auth: "none"
  thecolab.access_mode: "public-api"
  thecolab.data_class: "public"
  thecolab.writes: "false"
  thecolab.browser: "false"
  thecolab.risk: "low"
  thecolab.cache_ttl: "24h"
  thecolab.schema_version: "1"
  thecolab.skill_type: "public-api"
  thecolab.pack: "nz-public-data"
  thecolab.source_url: "https://www.recyclemap.co.nz/"
  thecolab.allowed_domains: "www.recyclemap.co.nz,www.google.com,www.opengis.net,www.sitemaps.org,www.aucklandcouncil.govt.nz,www.repairnetworkaotearoa.org.nz,www.tyrewise.co.nz,www.e-cycle.co.nz,services7.arcgis.com,agrecovery.co.nz,api.mapme.com,techcollect.nz,base44.app,trowrestore.com,gis.ccc.govt.nz,zerowaste.co.nz,www.habitat.org.nz,www.makingzerowastework.org.nz"
  thecolab.last_verified: "2026-10-08"
  thecolab.health: "degraded"
  thecolab.maintainer: "@adam91holt"
---

# NZ recycling locator

Find reuse and recycling drop-offs by material and WGS84 location; text-search
repair cafés and Tyrewise sites. Use
`scripts/cli.py` (Python 3.10+, stdlib). All commands support `--json`.
Read [source notes](references/source-notes.md) for coverage, acceptance limits,
upstream schemas and the unimplemented Council command.

```bash
python3 scripts/cli.py sources --json
python3 scripts/cli.py materials --source recyclemap --json
python3 scripts/cli.py find --material battery --near=174.7633,-36.8485 --radius 10 --json
python3 scripts/cli.py find --material concrete --near=174.7633,-36.8485 --source branz --radius 30 --format geojson
python3 scripts/cli.py search "Manurewa" --bbox=174.5,-37.2,175.2,-36.5 --json
python3 scripts/cli.py search "repair" --source repair --json
python3 scripts/cli.py search "Ranui" --source trow --json
python3 scripts/cli.py search "EcoDrop" --source christchurch --bbox=172.4,-43.7,172.8,-43.3 --format geojson
python3 scripts/cli.py search "Panmure" --source habitat --json
python3 scripts/cli.py search "recovery" --source zerowaste --json
python3 scripts/cli.py search "Onehunga" --source crc --json
python3 scripts/cli.py item "battery" --json
```

1. Check `sources` for **live** status. TROW is skipped unless `--source trow`
   is supplied. It reports blocked/skipped sources without
   pretending they are empty directories. Repair status counts sitemap URLs;
   search fetches the linked café detail pages.
2. Use `materials` to inspect publisher labels. `find` accepts common aliases
   such as `battery`, `car battery`, `ewaste`, `paper` and `metal`; other
   terms match material labels case-insensitively by substring. Aliases match
   whole labels: `battery` excludes `Car Batteries`; `clothing` includes both
   resalable and non-resalable clothing labels as well as op shops and textiles.
   `search` matches all words in names, addresses, labels and source descriptions,
   including restrictions.
3. `find` requires `--near=longitude,latitude`; radius defaults to 20 km.
   `find` and `search` support `--bbox=minLon,minLat,maxLon,maxLat` and
   `--format geojson`. Null coordinates remain null and are excluded from
   spatial filters using local point containment. Default spatial queries skip
   Tyrewise, TROW, CRC and repair sources; explicit `--source` still selects them. Use
   text search for these listings. Tyres with coordinates may appear in other feeds.
4. Present source links, material restrictions, charges and opening hours.
   A site listed for one battery type may exclude another. Confirm acceptance
   with the operator, particularly damaged batteries and commercial loads.

Repeat `--source` to combine selected feeds: `recyclemap`, `wasteminz`, `repair`,
`tyrewise`, `ecycle`, `branz`, `agrecovery`, `beautification`, `council`,
`techcollect`, `trow`, `christchurch`, `zerowaste`, `habitat`, `crc`. Defaults include
the twelve other working directories. TROW requires explicit `--source trow`
for all commands: its undocumented internal Base44 endpoint returns
`seller_email`, `seller_name` and `created_by` for every stock record.
These personal fields are discarded; they never appear in output or cache.
Council and TechCollect are also explicit selections. Council guidance is not implemented;
TechCollect has no verified script-accessible feed. They return exit 7 when they
are the only selected sources; with a working source they appear in
`source_status` and warnings with `result_status: partial`
(exit 0 when records remain). Neither website is fetched.

`item` returns `unsupported_operation` (exit 7) with the Council URL to consult.
It does not fetch or interpret Council disposal guidance.

Every record includes `name`, `address`, `lon`, `lat`, `materials`, `hours`,
`source`, and `provenance`. Record provenance has `source_url`, `publisher`,
`retrieved_at`, plus `licence` and `latest_data` only when known. JSON output
has `meta` and `results`; GeoJSON has `meta` and `features` with records in
feature properties. Errors have `meta`, empty `results`, and a typed `error`.
`materials` groups retain a provenance list; flat fields appear only for groups
from one source. `source_status` and `warnings` expose source failures;
`result_status: partial` indicates incomplete results. If no matching records
remain and any selected source failed, the query returns that failure.

TROW groups available and pre-sale stock by publisher location label, merging
“Trow Group Yard, Ranui” and “TROW Yard - Ranui. Auckland 0612” into one Ranui
yard; sold stock is excluded. It has no verified coordinates, street addresses or opening hours.
Use text search and arrange collection; these are not confirmed donation sites.
The `crc` source provides Auckland CRC addresses without verified coordinates;
use text search. The `reuse` alias also matches Beautification’s “Rehome” label.
Christchurch depots expose broad refuse/recycling/green-waste flags. Habitat
provides op-shop addresses and coordinates. Zero Waste Aotearoa lists network
members with unverified service types; its category endpoint blocks scripts, so
category IDs are not interpreted as materials. Some member map coordinates
conflict with addresses; confirm the location before travelling.

BRANZ planned facilities are excluded. Human output shows facility type and
status; warnings identify service contractors or entries not marked Existing.
Confirm that these operators accept public drop-offs before recommending them.

Data commands cache normalised public records in `$XDG_CACHE_HOME/nz-recycling-locator`
(or `~/.cache/nz-recycling-locator`) for 24 hours; `--refresh` bypasses it.
Cached records retain their actual retrieval time. `sources` always checks live. No cache is used after a failed
refresh. `--limit 20` bounds search/find output; `--limit 0` returns all matches.
Data queries and live status probes load up to four sources concurrently,
retaining each source's request
pacing and selection order. Counts refer to source entries; overlapping sites
are deliberately kept with separate provenance. Network calls have 10-second timeouts.

Run `scripts/test_contract.py` for deterministic synthetic-fixture, provenance,
spatial and error checks. Run `scripts/smoke_test.py` for bounded live probes;
source outages are reported as skips and parser regressions as failures.
