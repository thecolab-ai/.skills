# Source notes — NZ SeaRise projections

- Primary owner: NZ SeaRise programme (Antarctic Research Centre at Victoria
  University of Wellington, GNS Science, NIWA; Takiwā hosts the public map)
- Primary source: https://zenodo.org/records/11398538
- Record API: https://zenodo.org/api/records/11398538
- Declared outbound hosts: zenodo.org
- Access mode: public-download
- Authentication: none
- Last verified: 2026-07-24

## Files used (Zenodo record 11398538, v3, published 2024-05-31)

| File | Size | Used by |
| --- | --- | --- |
| `NZ_VLM_final_May24.csv` | 674 KB | `sites`, `vlm` |
| `NZSeaRise_proj_vlm.csv` | 53.8 MB | `projections` (default) |
| `NZSeaRise_proj_novlm.csv` | 53.6 MB | `projections --no-vlm` |

Download URLs are `<record>/files/<name>` (a `?download=1` suffix is
accepted but unnecessary). Zenodo serves anonymous requests and supports HTTP
Range; a full `projections` call measured ~22 s in verification.

The `record` command reads the small Zenodo JSON API response and normalizes
the record ID, DOI, version, publication date, title, creators, licence, and
file inventory. File entries retain the upstream key, byte size, checksum, and
download URL. Record 11398538 does not declare a free-form
`metadata.version`; Zenodo's zero-based `metadata.relations.version[].index`
is surfaced as the one-based version (`2` → `"3"`). This metadata call does
not download any dataset file.

## Column layout (verified 2026-07-24)

`NZ_VLM_final_May24.csv`: `Site ID, Lon, Lat, Vertical Rate (mm/yr),
Vertical Rate - BOP corrected (mm/yr), 1-sigma uncertainty (mm/yr),
Number of obs, Quality Factor, Average distance between coastal point and
observations` plus trailing empty columns the parser ignores. ~7,500 sites,
ids 0..N, 2 km coastal spacing. Negative rate = subsidence.

`NZSeaRise_proj_*.csv`: `Confidence, site, year, 0.17, 0.5, 0.83, SSP,
scenario`. Rows are block-ordered by (confidence, SSP/scenario, year) with
all sites inside each block, so per-site extraction requires a full scan —
there is no early exit. Multi-site extraction builds one requested-ID lookup
and selects every requested site during the same iterator pass; it does not
materialize a list containing every CSV row. Values are metres of sea-level rise relative to the
1995–2014 baseline at decadal steps 2020–2300. Scenario label = `SSP` +
`scenario` columns joined (`SSP2` + `4.5` → `SSP2-4.5`); confidence values
are `low_confidence`/`medium_confidence`, surfaced as `low`/`medium`.

## Relationship to searise.takiwa.co

The public map at https://searise.takiwa.co is a Takiwā SPA behind a guest
session; its per-site projection JSONs live in a Takiwā S3 bucket with
undocumented semantics (weighted VLM-blend combinations). This skill
deliberately reads the peer-reviewed Zenodo publication instead — documented
columns, stable DOI, CC BY 4.0 — and treats the map as a viewer, not a source.

## Reuse and citation

CC BY 4.0. Cite: Naish, T. et al. (2024), "The significance of interseismic
vertical land movement for projections of relative sea-level rise in Aotearoa
New Zealand", Earth's Future / Zenodo record 11398538 (dataset v3,
NZSeaRise_V2_2024). The programme states projections will be periodically
updated after peer review — check the Zenodo record for newer versions when
`last_verified` ages.

## Failure modes

- Missing required record fields or projection columns produce a structured
  `source_schema_failure` rather than an invented or fixture-backed result.
- A valid single-site request with no source rows exits non-zero with
  `site_not_found`. In multi-site mode the same condition is retained in input
  order as a `not_found` result; a known site removed by filters is `empty`.
- Zenodo rate-limits aggressively parallel downloads; the CLI makes exactly
  one request per command. A multi-site projection call still performs one
  fetch and one CSV scan, including when IDs are duplicated.
- Projection CSV bodies are held only for the lifetime of the process by the
  shared fetch layer and CSV reader. No persistent file or cache is created.
