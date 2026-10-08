---
name: akl-housing-capacity
description: "Query Auckland housing supply trends and 2022/23 plan-enabled and feasible housing capacity. Use for monthly housing updates, local-board growth capacity and housing demolition source discovery."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "housing"
  thecolab.source_owner: "Auckland Council"
  thecolab.source_type: "official"
  thecolab.auth: "none"
  thecolab.access_mode: "public-download"
  thecolab.data_class: "public"
  thecolab.writes: "false"
  thecolab.browser: "false"
  thecolab.risk: "low"
  thecolab.cache_ttl: "none"
  thecolab.schema_version: "1"
  thecolab.skill_type: "public-download"
  thecolab.pack: "nz-public-data"
  thecolab.source_url: "https://knowledgeauckland.org.nz/"
  thecolab.allowed_domains: "knowledgeauckland.org.nz,www.knowledgeauckland.org.nz,www.hud.govt.nz,www.kaingaora.govt.nz"
  thecolab.last_verified: "2026-10-08"
  thecolab.health: "degraded"
  thecolab.maintainer: "@adam91holt"
---

# Auckland housing capacity

Use `scripts/cli.py` to read the current Auckland Council housing datasheet,
2022/23 PC78 residential capacity summaries and HUD/MCERT social housing delivery.
Python 3.10+ standard library only; no keys or setup required.

```bash
python3 skills/akl-housing-capacity/scripts/cli.py sources --json
python3 skills/akl-housing-capacity/scripts/cli.py housing-update --json
python3 skills/akl-housing-capacity/scripts/cli.py housing-update --month 2026-07 --area "Henderson-Massey" --json
python3 skills/akl-housing-capacity/scripts/cli.py housing-update --source hud --month 2026-08 --area Auckland --json
python3 skills/akl-housing-capacity/scripts/cli.py capacity --area Whau --json
python3 skills/akl-housing-capacity/scripts/cli.py capacity --detail typology --area Whau --json
python3 skills/akl-housing-capacity/scripts/cli.py capacity --dataset business --json
python3 skills/akl-housing-capacity/scripts/cli.py demolitions --area Auckland --json
```

1. Use `sources` for the offline verified URL registry and access limitations.
   It labels records `retrieval_kind: source_registry`; it does not fetch data.
2. `housing-update` discovers the current XLSX link on the official landing page.
   `--month` selects an **observation month** from the latest workbook, not an
   archived publication. Without it, Council results use the latest month per
   sheet and area; HUD results use the latest delivery month for the chosen area.
   The default HUD area is Auckland. Council results include regional consents,
   CCCs, parcel creation and local-board consents. Area matching ignores accents,
   spaces and hyphens; a name substring can match more than one board.
3. `capacity` returns paired plan-enabled/feasible dwelling totals from the PC78
   model. `--detail typology` returns built-form capacity and dwelling prices
   under the alternative `Max_Profit` and `MinDUPrice` selections. Keep scenarios
   separate; do not sum overlapping selections or regional and local-board totals.
4. `capacity --dataset business` verifies and inventories the public HBA 2023
   ZIP. These are file counts and sizes for File Geodatabases, not business
   feature counts or floorspace estimates. Feature queries need GIS software.
5. `demolitions` returns exit 7 (`unsupported_operation`) with the public Kāinga
   Ora OIA URL. The release is PDF-only, and live retrieval was blocked on the
   verification network; no structured site extract was verified. Do not
   interpret this error as zero demolitions.

`--zone` is accepted on `capacity` but returns exit 7: the supported XLSX tables
have no zone field. For **PC120 zoning maps**, use the existing `nz-arcgis` skill
with the relevant Auckland Council service. PC120 zoning and the historic PC78
capacity model are different sources and dates. These summary commands contain
no coordinates, so they do not offer `--bbox` or GeoJSON.

JSON uses `{meta, results}` with source URL, publisher and UTC retrieval time;
known data licence and latest reporting period appear in `meta`. Errors use the
same envelope, empty results and a typed `error`, and exit non-zero. Valid filters
with no matching observations return an empty results array. Missing sheets,
changed headers and failed downloads are errors, not empty successes.

Read [references/source-notes.md](references/source-notes.md) for exact downloads,
field meanings, licensing, overlap and coverage limits. The XLSX reader in
`scripts/workbook.py` uses `zipfile` and `xml.etree.ElementTree`, streams the large
HUD worksheet, and reads cached formula results without calculating formulas.
Synthetic format fixtures live in `tests/fixtures/`.

```bash
python3 skills/akl-housing-capacity/scripts/test_contract.py
python3 skills/akl-housing-capacity/scripts/smoke_test.py
```
