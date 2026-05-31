# MSD Benefits NZ - API and dataset notes

## Source

Ministry of Social Development (MSD), "benefit fact sheets" statistics, December 2019 release. These are static CSV files served over plain HTTPS GET with no login, API key, cookie, or bot challenge. Content-type is `text/csv`.

## Wired endpoints

All three files live under:

```
https://www.msd.govt.nz/documents/about-msd-and-our-work/publications-resources/statistics/benefit/2019/
```

| CSV key  | File                                                          | Size    | Data rows |
|----------|--------------------------------------------------------------|---------|-----------|
| national | `national-level-benefit-data-dec-19.csv`                     | ~3.6 MB | 25,874    |
| nzs      | `new-zealand-superannuation-and-veteran-s-pension-dec-19.csv`| ~87 KB  | 748       |
| region   | `work-and-income-region-level-benefit-data-dec-19.csv`       | ~12.6 MB| 94,916    |

All parse cleanly with Python stdlib `csv.DictReader` (UTF-8 with BOM, handled via `utf-8-sig`).

## Schemas

**national** header:
`Quarter, Benefit_Group, Benefit_Subgroup, Incapacity_or_Child_age, Continuous_duration, Gender, Age_Group, Ethnicity, Count`

- `Benefit_Group`: `Jobseeker Support`, `Sole Parent Support`, `Supported Living Payment`, `Youth Payment and Young Parent Payment`, `Other Main Benefits`
- `Age_Group`: `18-24`, `25-39`, `40-54`, `55-64`, `Age suppressed`
- `Gender`: `Female`, `Male`, `Gender suppressed`
- `Ethnicity`: `Maori`, `NZ European`, `Pacific peoples`, `All other ethnicities`, `Ethnicity suppressed`, `Unspecified`

**nzs** header (same as national except age column):
`Quarter, Benefit_Group, Benefit_Subgroup, Incapacity_or_Child_age, Continuous_duration, Gender, Age_group2, Ethnicity, Count`

- `Benefit_Group`: `New Zealand Superannuation`, `Veteran's Pension`
- `Age_group2`: `Under 65`, `65 and over`, `Age suppressed`

**region** header (adds `Region`, drops `Continuous_duration`):
`Quarter, Region, Benefit_Group, Benefit_Subgroup, Incapacity_or_Child_age, Gender, Age_Group, Ethnicity, Count`

- `Region` (MSD Work and Income service regions, not regional councils): `Auckland Metro`, `Bay of Plenty`, `Canterbury`, `Central`, `East Coast`, `Nelson`, `Northland`, `Other region`, `Southern`, `Taranaki`, `Waikato`, `Wellington`
- `Benefit_Group`: `Jobseeker Support`, `Sole Parent Support`, `Supported Living Payment`, `Other Main Benefits` (no Youth Payment in this file)

## Quarters

All three files span `Dec_14` through `Dec_19`, quarterly:
`Dec_14, Mar_15, Jun_15, Sep_15, Dec_15, ... Mar_19, Jun_19, Sep_19, Dec_19`.

The latest quarter is `Dec_19`, which the CLI uses as the default `--quarter`.

## Caveats

- **Frozen historical series.** This is the December 2019 release in this exact flat-CSV schema; it is not updated. For current benefit numbers, point users to the live MSD benefit fact sheets at msd.govt.nz.
- **Confidentiality suppression.** MSD randomly rounds counts and replaces small cells with `... suppressed` / `Unspecified` category labels. The CLI sums these into totals and surfaces them as their own breakdown rows; do not treat a single cell as an exact case count.
- `Count` is an integer recipient count. Totals are exact sums of the rows matched by the chosen filters and quarter.
- The CLI is read-only and writes no cache files; it fetches the live CSV for each command.

## Command behaviour

- `list-quarters` returns distinct `Quarter` values for one CSV.
- `main-benefits` / `region` default to grouping by `Benefit_Group` when no breakdown flag is supplied; with `--group` set and no breakdown flags they return a single total. Breakdown flags (`--gender`, `--ethnicity`, `--age`) aggregate `Count` by those dimensions.
- `nz-super` mirrors `main-benefits` with `--age-group` mapping to `Age_group2` (Under 65 / 65 and over).
- `trend` sums `Count` per quarter for one `Benefit_Group` from the national CSV, with an optional gender filter (`F`/`Female`/`M`/`Male`).
