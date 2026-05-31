# API notes — household-hardship-nz

Source: **Stats NZ Household Economic Survey (HES), "Household Wellbeing"**
releases, published on **data.govt.nz** behind the public CKAN API. No login,
API key, or rate-limit token. Read-only.

## CKAN discovery endpoints

- Search datasets:
  `GET https://catalogue.data.govt.nz/api/3/action/package_search?q=<terms>&rows=<n>`
  Returns `result.count`, `result.results[].name`, `result.results[].title`.
  ~39 datasets match "household economic survey wellbeing" (incl. 2018-19,
  2020-2021, and "Warm and Dry" releases).

- Show one dataset's resources:
  `GET https://catalogue.data.govt.nz/api/3/action/package_show?id=<dataset-name>`
  Returns `result.resources[]` with `name`, `format` (`zip/csv`), and a direct
  `url` to a downloadable ZIP archive.

Default dataset id:
`household-economic-survey-2020-2021-household-wellbeing-including-maori-households`

## Resources (ZIP-of-CSV)

Each resource `url` is an `application/zip` archive (~3-9 KB) of CSV tables,
unpacked with stdlib `zipfile` + `csv`. The CLI picks a resource by substring of
its `name`:

- `household - income series` → `households.zip` (12 CSVs, the main tables)
- `households - low income series` → `households-lowincome.zip` (4 affordability
  CSVs restricted to low-income households)

(Other resources cover Maori households and "people in households" series.)

## CSV tables and columns

All count tables share the columns: `Households`, `LCI`, `UCI` (95% confidence
bounds), `RSE` (relative standard error %), and `Flag` (`*` = high sampling
error). The CLI maps these to `households`, `lci`, `uci`, `rse_percent`, `flag`.

| CLI command | region table | ethnicity table | category column |
|-------------|--------------|-----------------|-----------------|
| `hardship` | `t2a_hardship_rc.csv` | `t2a_hardship_eth.csv` | `Hardship` (In hardship / Not in hardship) |
| `income-adequacy` | `t3a_adeqinc_reg.csv` | `t3b_adeqinc_eth.csv` | `AdeqInc` (Income is adequate / not adequate) |
| `affordability` | `t1a_affordability_reg.csv` | `t1c_affordability_eth.csv` | `Affordability` (More than 30%/40%/50%) |
| `affordability --tenure` | `t1b_affordability_ten.csv` | — | `Tenure` (Owned / Renting) |
| `low-income` | `t4a_lowinc_reg.csv` | `t4b_lowinc_eth.csv` | `LowHhldIncAHC` (Low income / Not low income) |
| `gini` | `t5a_gini_reg.csv` | `t5b_gini_eth.csv` | `Gini` (coefficient 0-100) |

With `affordability --lowincome` the table names gain a `_lowincome` suffix and
come from the low-income ZIP, e.g. `t1c_affordability_eth_lowincome.csv`.

The Gini tables differ: `Gini`, `LCI`, `UCI`, `RSE`, `Flag` (no household count).
The CLI returns `gini`, `lci`, `uci`, `rse_percent`, `flag` as floats.

## User-Agent

Requests send `User-Agent: household-hardship-nz-skill/1.0`. Timeouts are 60s for
JSON and 90s for ZIP downloads.
