# Child Poverty NZ — endpoint and schema notes

## Source

Stats NZ publishes one Child Poverty Reduction Act (CPRA) statistics release per
year. The machine-readable artefact is a public ZIP of CSVs — plain `GET`, no
API key, no login, no User-Agent gate, no bot challenge.

- CSV-files index (discovery): `https://www.stats.govt.nz/large-datasets/csv-files-for-download/`
  - Embeds a JSON `pageViewData` blob (`<div id="pageViewData" data-value="…">`)
    listing `PageBlocks[].BlockDocuments[]` with `Title`, `DocumentLink`,
    `DocumentExtension`. The `releases` command parses this and keeps entries
    whose title contains "child poverty statistics", extracting the year from
    "year ended June YYYY". The newest entry is the default data source for every
    other command, so the skill never hardcodes a year.
- Per-release ZIP URL pattern (stable across years):
  `…/assets/Uploads/Child-poverty-statistics/Child-poverty-statistics-Year-ended-June-<YYYY>/Download-data/child-poverty-statistics-year-ended-june-<yyyy>.zip`
  (older years may have a `-corrected` suffix, e.g. 2024).

## ZIP contents

Each release ZIP contains three files:

1. `cp-national-datafile-csv.csv` — ~856 rows. National series, 9 measures ×
   5 estimate types × 2007-2025.
   Header: `MsCode,Year,EstCode,Estimate,SE,LowerCIB,UpperCIB,Flag`
2. `cp-reg-eth-dis-datafile.csv` — ~7276 rows. Disaggregated by region /
   ethnicity / disability, 2019-2025.
   Header: `MsCode,DemCode,EstCode,Year,Estimate,SE,LowerCIB,UpperCIB,Flag`
3. `cp-csv-codes.xlsx` — the code legend (an xlsx, i.e. a ZIP of XML; readable
   with stdlib `zipfile` via `xl/sharedStrings.xml`). The mappings below are
   lifted from it verbatim, so the CLI does not need to open the xlsx at runtime.

`LowerCIB` / `UpperCIB` are the lower/upper confidence-interval boundaries on the
estimate; `SE` is the absolute sampling error.

## Measures (MsCode)

| Code | Plain English |
|------|---------------|
| MEASA | BHC < 50% of median income, moving line (**primary** legislated measure) |
| MEASB | AHC < 50%, base/anchored financial-year line (**primary**) |
| MEASC | Material hardship (DEP-17, lacking 6+ of 17 items) (**primary**) |
| MEASE | BHC < 60%, moving line |
| MEASF | AHC < 60%, moving line |
| MEASG | AHC < 50%, moving line |
| MEASH | AHC < 40%, moving line |
| MEASI | Severe material hardship (DEP-17, lacking 9+ of 17 items) |
| MEASJ | Low income **and** hardship: AHC < 60% and in material hardship (combined) |

Verbatim from the release's `cp-csv-codes.xlsx` legend (Stats NZ skips MEASD).
The three primary CPRA measures are MEASA, MEASB and MEASC. Severe material
hardship (MEASI) is a subset of material hardship (MEASC), so MEASI ≤ MEASC.

BHC = before housing costs; AHC = after deducting housing costs.

## Estimate types (EstCode)

National file (`cp-national-datafile-csv.csv`):
- `A_Proportion` — proportion of children in the measure (%)
- `B_ChangeInProportion` — annual change in proportion (percentage points)
- `C_Number` — number of children in the measure (000s)
- `D_ChangeInNumber` — annual change in number (000s)
- `E_Population` — total number of children (000s)

Disaggregated file (`cp-reg-eth-dis-datafile.csv`):
- `A_Proportion` — proportion (%)
- `B_Number` — number of children in the measure (000s)
- `C_Population` — total number of children (000s)
- `D_Proportion_diff` — annual change in proportion (percentage points)
- `E_Number_diff` — annual change in number (000s)

## Demographic codes (DemCode)

Region (`REGC`): 01 Northland · 02 Auckland · 03 Waikato · 04 Bay of Plenty ·
05 Gisborne/Hawke's Bay · 06 Taranaki · 07 Manawatū-Whanganui · 08 Wellington ·
09 Tasman/Nelson/Marlborough/West Coast · 10 Canterbury · 11 Otago ·
12 Southland · 99 Total all regions.

Ethnicity (`ETHG`): 01 European · 02 Māori · 03 Pacific peoples · 04 Asian ·
05 Middle Eastern/Latin American/African · 06 Other ethnicity · 99 All ethnicities.

Disability (`DISD`/`DISH`): DISD01 Disabled children · DISD02 Non-disabled
children · DISH01 Children in disabled household · DISH02 Children in
non-disabled household · DISH99 Total (household).

## Caveats

- Regional figures absent for 2022; regional annual change absent for 2023
  (2022 data-quality issues).
- 2025 material-hardship and disability questions changed with the move to the
  Household Income and Living Survey; disabled-children hardship is not
  comparable to earlier years.
- `Flag = NA`: no prior-year data, so change is not applicable. Cells suppressed
  with `S` for confidentiality when fewer than six units contribute.
