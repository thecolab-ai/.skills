# Source notes — NZ SeaRise projections

- Primary owner: NZ SeaRise programme (Antarctic Research Centre at Victoria
  University of Wellington, GNS Science, NIWA; Takiwā hosts the public map)
- Primary source: https://zenodo.org/records/14722058 (projections, v4)
- Record API: https://zenodo.org/api/records/14722058
- Concept record (all versions): https://zenodo.org/records/10976241
- Declared outbound hosts: zenodo.org
- Access mode: public-download
- Authentication: none
- Last verified: 2026-07-26

## Version history and why two records are read

Concept record `10976241` has four published versions (enumerated via
`https://zenodo.org/api/records?q=conceptrecid:10976241&all_versions=true`):

| Version | Record | Published | Files |
| --- | --- | --- | --- |
| v1 | 10976242 | 2024-04-16 | `NZ_VLM_final_Apr2024.csv`, both `NZSeaRise_proj_*.csv` |
| v2 | 11201071 | 2024-05-16 | `NZ_VLM_final_May24.csv` only |
| v3 | 11398538 | 2024-05-31 | `NZ_VLM_final_May24.csv`, both `NZSeaRise_proj_*.csv` |
| v4 | 14722058 | 2025-01-23 | `NZ_Searise_noVLM-2005.csv`, `NZ_Searise_VLM-2005.csv` |

**v4 did not republish the site-details/VLM file.** Pinning v4 alone would lose
site coordinates and VLM rates; pinning v3 alone would serve superseded
projections. The skill therefore reads each file from the newest version that
publishes it, and `record` reports both record URLs so provenance stays
explicit.

v4's own release note states it "corrects a missing scenario (SSP3-7.0) with no
VLM" and adds 2005 entries. A full scan of both noVLM tables (2026-07-26)
found the same confidence × scenario coverage in v3 and v4, so the correction
did not change which scenarios are present in the published v3 file; what v4
measurably adds is a zeroed 2005 baseline row per site/scenario (v3 noVLM
1,046,912 rows → v4 1,104,165) and a third decimal place on every value.
Spot-checking site 2503 across all 128 shared keys found every value equal to
v3's after rounding to 2 dp.

## Files used

| File | Record | Size | Used by |
| --- | --- | --- | --- |
| `NZ_VLM_final_May24.csv` | v3 `11398538` | 674 KB | `sites`, `vlm` |
| `NZ_Searise_VLM-2005.csv` | v4 `14722058` | 58.0 MB | `projections` (default) |
| `NZ_Searise_noVLM-2005.csv` | v4 `14722058` | 57.9 MB | `projections --no-vlm` |

Download URLs are `<record>/files/<name>` (a `?download=1` suffix is
accepted but unnecessary). Zenodo serves anonymous requests and supports HTTP
Range; a full `projections` call measured ~33 s in verification. Note plain
`urllib` without browser-shaped headers gets HTTP 403 from Zenodo's file
endpoint — the shared `nzfetch` layer is required, not optional.

The `record` command reads the small Zenodo JSON API response and normalizes
the record ID, DOI, version, publication date, title, creators, licence, and
file inventory. File entries retain the upstream key, byte size, checksum, and
download URL. Neither record declares a free-form `metadata.version`; Zenodo's
zero-based `metadata.relations.version[].index` is surfaced as the one-based
version (v4's `index: 3` → `"4"`). This metadata call does not download any
dataset file.

## Column layout (verified 2026-07-26)

`NZ_VLM_final_May24.csv`: `Site ID, Lon, Lat, Vertical Rate (mm/yr),
Vertical Rate - BOP corrected (mm/yr), 1-sigma uncertainty (mm/yr),
Number of obs, Quality Factor, Average distance between coastal point and
observations` plus trailing empty columns the parser ignores. **8,173 data
rows**, ids spanning 0..8178 — six ids in that range have no site-details row
even though the projection tables carry them, so `vlm` can legitimately fail
for an id `projections` accepts. 2 km coastal spacing. Negative rate =
subsidence.

Projection tables: `Confidence, site, year, <p17>, <p50>, <p83>, SSP,
scenario`, covering **8,179 distinct site ids**. The percentile columns are
labelled `0.17`/`0.5`/`0.83` in v3 and `17`/`50`/`83` in v4; `SSP` is
upper-case in v3 (`SSP3`) and lower-case in v4 (`ssp3`); and the forcing level
loses its trailing zero in v4 (`7.0` → `7`). The parser resolves whichever
percentile spelling is present and normalises every scenario to a canonical
`SSP3-7.0` label, so both releases yield identical output and `--scenario`
accepts either form. A header set carrying neither spelling fails closed with
`source_schema_failure` rather than silently reading nothing.

Rows are block-ordered by (confidence, SSP/scenario, year) with all sites
inside each block, so per-site extraction requires a full scan — there is no
early exit. Multi-site extraction builds one requested-ID lookup and selects
every requested site during the same iterator pass; it does not materialize a
list containing every CSV row. Values are metres of sea-level rise relative to
the 1995–2014 baseline, at a 2005 baseline plus decadal steps 2020–2300 (30
year values in v4, 29 in v3). Confidence values are
`low_confidence`/`medium_confidence`, surfaced as `low`/`medium`.

Low confidence is published only for SSP1-2.6 and SSP5-8.5; SSP1-1.9, SSP2-4.5
and SSP3-7.0 are medium-confidence only. That asymmetry is upstream, not a
parser artefact, and surfaces as an explicit empty result.

## Relationship to searise.takiwa.co

The public map at https://searise.takiwa.co is a Takiwā SPA behind a guest
session; its per-site projection JSONs live in a Takiwā S3 bucket with
undocumented semantics (weighted VLM-blend combinations). This skill
deliberately reads the peer-reviewed Zenodo publication instead — documented
columns, stable DOI, CC BY 4.0 — and treats the map as a viewer, not a source.

## Reuse and citation

CC BY 4.0 (declared as `cc-by-4.0` on the record).

The **dataset** authors, in Zenodo's own order, are Hamling, Ian; Naish, Tim;
Levy, Richard; Hreinsdóttir, Sigrún; Bengtson, Shannon; Praveen, Kumar — cite
it as Hamling, I. et al., *New Zealand Vertical land movement and sea rise
projections*, Zenodo, https://doi.org/10.5281/zenodo.14722058.

The **associated paper** is Naish, T. et al. (2024), "The significance of
vertical land movements at convergent plate boundaries in probabilistic
sea-level projections for AR6 scenarios: the New Zealand case", *Earth's
Future* — title taken verbatim from the v4 record description. Earlier notes in
this repository cited a paraphrased title and named the paper's first author as
the dataset's; both were wrong and are corrected here.

The programme states projections will be periodically updated after peer
review. Re-check the concept record for a v5 when `last_verified` ages —
particularly whether a later version restores the site-details file, which
would let the skill read a single record again.

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
