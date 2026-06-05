# Public Housing NZ — endpoint and dataset notes

All data is published by the **Ministry of Housing and Urban Development (HUD)**
on data.govt.nz, served from the CKAN instance at `https://catalogue.data.govt.nz`.
Everything below is public, read-only, no login, no API key, no bot challenge.

## Wired CSV resources (CKAN DataStore-backed downloads)

| `--resource` key | Dataset | Resource ID | Rows |
|---|---|---|---|
| `sochouse` | Social Housing Tenancies (IRRS + Market Rent) | `37acd9dc-c7aa-467c-a899-f2d3923b1a2e` | ~2,031 |
| `publichomes` | Public Homes Stock by TLA/provider | `169a57e5-8bf2-4799-9fd6-fd3eaceee060` | ~9,437 |
| `as` | Accommodation Supplement recipients & weekly spend | `66a8ec7f-8027-4f05-a46b-f2160c2784fb` | ~2,277 |
| `local` | Local Housing Statistics dashboard | `30ed710c-79d9-4343-b36b-a18c2012ea0e` | ~50,450 |

`sochouse`, `publichomes`, and `as` belong to the parent dataset
`877577c5-b059-4750-84eb-730662ae92b8` (Housing Support quarterly data,
metadata_modified ~2025-05, data through Dec 2024). `local` belongs to dataset
`7445503d-5e59-43f3-a3bd-862d2b8a1e3e` (Local Housing Statistics dashboard).

Download URL shape:
`https://catalogue.data.govt.nz/dataset/<dataset_id>/resource/<resource_id>/download/<file>.csv`

## CSV columns

- **sochouse_output.csv**: `Series, TLA_Name, As_At_Date, Total IRRS and Market Rent Tenancies`
- **publichomes_output.csv**: `TLA, Area_Name, As_At_Date, Provider, Total Public Homes`
  - `Provider` is `KO` (Kainga Ora) or `CHP` (community housing provider)
  - Suppressed counts appear as the literal `s`
  - `Area_Name` is mostly numeric TLA codes plus a `Not geolocated` rollup, so
    filter by `--provider`/`--date`, not TLA name
- **as_output.csv**: `Series, Area, AS Recipients, Total Weekly AS, Date, Area_Type`
- **local_housing_stats.csv**: `Group_ID, Group_Type, Group_Name, date, year, series, value, prefix, ethnicity, theme`
  - `Group_Type` is `NZ` or `TA`; `theme` includes Affordability, Bonds,
    Building Consents, Census Crowding, MSD, Rent Proportion, Sales, population
  - 63 distinct series, including `1-year change in Housing Register per 10k population`

## CKAN action API (used by `datasets` and `query`)

- `GET /api/3/action/package_search?q=<terms>&rows=<n>` — discover datasets and
  detect new quarterly releases. Returns `result.count` and `result.results[]`
  (each with `metadata_modified` and `resources[]`).
- `GET /api/3/action/datastore_search?resource_id=<id>&limit=<n>&filters=<json>&q=<text>`
  — server-side filtering of any wired resource. Returns
  `result.total` and `result.records[]` (mirroring the CSV columns).
  Dates come back as ISO datetimes, e.g. `2022-12-31T00:00:00`.
  CKAN also adds a `_full_text` field, which the CLI strips from output.

## Known gaps / caveats

- The exact current **Public/Social Housing Register** wait-list headcount is
  published by HUD as **XLSX + HTML**, not clean CSV, and is intentionally not
  wired. Use `local-stats --series "Change in Housing Register"` for the register
  trend, or `datasets --query "public housing register"` to find the latest
  register release resource.
- CSV download URLs are stable per resource ID; new quarterly data refreshes the
  same resource. Use `datasets` to check `metadata_modified` for recency.

## Conventions

- User-Agent: `public-housing-nz-skill/1.0`
- Read-only; no mutation, auth, cookies, or browser automation
- Standard library only (`urllib`, `csv`, `json`, `argparse`, `re`)
