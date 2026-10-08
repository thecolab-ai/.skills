# Source notes and interpretation

Authentication: none

Last verified: 2026-10-08

Outbound hosts: knowledgeauckland.org.nz, www.knowledgeauckland.org.nz,
www.hud.govt.nz, www.kaingaora.govt.nz.

Verified 8 October 2026 using the catalogue searches `housing update`,
`capacity for growth`, `HBA`, `demolished`, `MCERT` and `housing delivery`,
then real public downloads. The executable registry is `scripts/sources.py`.
Do not use retrieval time as an observation date.

## Council monthly housing update

Landing page: https://knowledgeauckland.org.nz/publications/auckland-monthly-housing-update-datasheet/

Verified current workbook: https://knowledgeauckland.org.nz/media/rayokdv3/auckland-monthly-housing-update-datasheet-09september-2026.xlsx

The CLI resolves this link again on each invocation; it does not construct URLs
from month names. The September 2026 workbook has seven sheets. This skill reads
four supply-related sheets; migration and residential median price series are
outside its supply focus.

- `Dwellings Consented`: regional dwelling types, total, annual rolling total,
  Kāinga Ora/TRC counts, dwellings inside the rural urban boundary (RUB), and
  the published total in hazard zones. Hazard categories can overlap; no sums
  of the individual hazard categories are calculated.
- `Dwellings Consented By LB`: local-board monthly dwelling counts. The regional
  monthly total is already in `Dwellings Consented`, so it is not duplicated.
- `Dwellings with CCCs`: dwelling completions evidenced by code compliance
  certificates and consent-to-CCC timing groups; not demolition counts.
- `Residential Parcels Created`: counts under 5,000 m², counts of all sizes,
  annual totals and locations inside/outside RUB. Parcels are not dwellings.

Records contain `sheet`, `area`, `area_type`, `period` (YYYY-MM), `unit` and a
`measures` object with explicit measure names. Missing or dash cells become
JSON null, never zero. The current workbook reports consent/CCC data to July
2026 and parcels to August 2026. `meta.latest_data` is the latest observation
month across the supported sheets, independent of an area/month filter;
read each record's `period` for its actual observation month. Historical values
come from the current workbook and may have been revised.

No file-specific open data licence was verified. Knowledge Auckland links to
Auckland Council terms; the CLI omits `licence` for Council data rather than
substituting this repository's MIT code licence. The landing page disclaims
accuracy and responsibility for decisions made from this dataset.

## Residential capacity and feasibility

Publication: https://knowledgeauckland.org.nz/publications/auckland-council-capacity-for-growth-study-20222023-data-housing/

Totals workbook: https://knowledgeauckland.org.nz/media/gzyj4pvk/auckland-council-hba-2023-pc78-outputs-from-housing-and-housing-hba-models-october-2023-v2-unlinked.xlsx

Typology workbook: https://knowledgeauckland.org.nz/media/2xdluxge/auckland-council-hba-2023-feasibilitysummary_by_lb.xlsx

The paired totals come from the `Total` row of `Plan-enabled Feasible x LBA`:
`plan_enabled_capacity` and `feasible_capacity`, in dwellings. The model labels
its version October 2023 and the downloadable workbook identifies PC78.
It publishes 19 mainland local-board areas and an Auckland aggregate; island
boards are not present in this table. The skill reads source totals without
rounding, extrapolation, or treating capacity as actual construction forecasts.
The headings report plan-enabled and plan-enabled-and-feasible capacity.

`--detail typology` reads `Max_Profit` and `MinDUPrice`. It returns the original
selection name, built form, feasible dwelling count, and minimum/maximum/average/
median dwelling price (NZD). These are model price outputs, not current sale
prices. Selections are alternatives and overlap with the totals; they are not
additive. No source reuse licence was verified for these files.

The source also publishes site-level File Geodatabase archives, including
https://knowledgeauckland.org.nz/media/42kl1kwk/pec-residential-part1.zip
and a linked part 2 publication. They exclude property ownership information.
Part 2 download: https://knowledgeauckland.org.nz/media/ynch3j4d/pec-residential-part2.zip
Both publication links and part 1's HTTP 200 download headers were verified.
These large residential archives are discoverable through `sources` but are
not downloaded or parsed by this stdlib summary CLI. Zoning queries should use
`nz-arcgis`; GIS software is required for the downloadable geodatabases.

## HBA 2023 business capacity

Publication: https://knowledgeauckland.org.nz/publications/auckland-council-capacity-for-growth-study-20222023-data-business-capacity/

Download: https://knowledgeauckland.org.nz/media/hv2j4xcw/pec-business.zip

Verified keyless 14,810,876-byte ZIP with five geodatabases: AUPOIP floorspace,
PC78 floorspace, basezone floorspace, vacant land and vacant potential.
`capacity --dataset business` returns `archive_inventory` records with the
geodatabase path, file count and declared uncompressed bytes. It does not extract
files, read spatial records, or accept area/zone/typology filters. The publication
states GIS software is needed; no reuse licence was verified.

## HUD / MCERT social housing delivery

Landing page: https://www.hud.govt.nz/stats-and-insights/the-government-housing-dashboard/further-information

Verified download: https://www.hud.govt.nz/assets/Housing-dashboard-data-download-August-2026.xlsx?m=501cb74296a5aef93adff4b078d2e0014ceb7bcb

The CLI resolves the current workbook link again, preserving its public cache
version query. It streams only `Social housing` and selects the `Delivery` series.
Output retains `dimensions` as ordered name/value pairs: total/provider,
delivery supertype and delivery type. Totals and breakdowns overlap; do not sum
all returned rows. Values can be negative stock adjustments. `Delivery` includes
new builds, leases, buy-ins, redirects, transfers and removed/adjusted stock;
that last category also includes sales and expired leases, so **it cannot be
used as a demolition count**. Default area is Auckland; explicit area substrings
can select other published regions. `meta.latest_data` is the latest source
observation month in the social housing worksheet, before filtering.

The default reuse licence is CC BY 4.0, except identified third-party material:
https://www.hud.govt.nz/about-us/copyright-and-disclaimer
The workbook instructions request use of the published dashboard for publication
purposes. Definitions and caveats are on the landing page; rounding/suppression
and revisions mean these figures may differ from other sources. The separate
Budget 2024/2025 delivery dashboard found in the catalogue is PDF-only; this
structured workbook is not a replacement for that specific funding pipeline.

## Kāinga Ora demolition OIA

Catalogue source S0823: https://www.kaingaora.govt.nz/assets/Publications/OIAs-Official-Information-Requests/August-2025/26-August-2025-Demolished-Social-Housing-Statistcs.pdf?v=e3bf5397c490918b2b6b4d7d0743bd9abb1a3152

It is a public August 2025 PDF release, not an XLSX/CSV endpoint. Both its PDF
and robots.txt returned a bot challenge from this network. No PDF contents,
site counts, areas or licence were independently verified. `demolitions` is an
explicit unsupported operation (exit 7) and provides this URL for source review;
it makes no network request and produces no supposed site records.

## Access, runtime and tests

Knowledge Auckland and HUD robots.txt returned HTTP 404 at verification. No
access restrictions were bypassed and no authenticated endpoints are used.
The Council terms page linked from Knowledge Auckland was blocked to this
network; no open data reuse licence is assumed for its files.
HTTP requests use shared `nzfetch` with a 10-second timeout and a host allowlist.
All JSON failures include provenance and codes 2 (input), 4 (blocked/rate-limited),
5 (network), 6 (schema) or 7 (unsupported). Retry-After is preserved when supplied.

The XLSX reader limits expanded archives to 256 MiB and streams worksheet rows.
HUD's current social housing sheet is about 111 MB expanded. Formula results
must be cached by the publisher; missing caches and Excel error cells fail.
Fixtures are small synthetic OOXML workbooks/ZIPs in the observed response
shapes, with invented values. Live datasets are never committed.
