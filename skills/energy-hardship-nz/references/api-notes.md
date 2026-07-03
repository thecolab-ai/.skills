# API notes — energy-hardship-nz

Three independent public sources, each with a different shape. No login, API
key, or rate-limit token for any of them.

## 1. MBIE Report on Energy Hardship Measures

Page: `https://www.mbie.govt.nz/building-and-energy/energy-and-natural-resources/energy-statistics-and-modelling/energy-publications-and-technical-papers/reporting-on-energy-hardship-measures`

Excel-only release (no CSV sibling seen as of the Dec 2025 release, data to
year ended June 2024). The CLI scrapes the page HTML for the first `.xlsx`
link (`find_links(html, page_url, ".xlsx")`) rather than hardcoding a
filename, since MBIE renames the file per release.

`.xlsx` is a zip of XML parts. `parse_xlsx()` reads `xl/sharedStrings.xml`,
`xl/workbook.xml`, and `xl/_rels/workbook.xml.rels` with stdlib
`zipfile` + `xml.etree.ElementTree` (no pip dependency), then picks the first
sheet whose name doesn't contain "guide"/"cover"/"notes"/"readme"/"contents"
and returns every populated row verbatim. `rows_to_records()` treats the
first row with 2+ non-empty cells as the header.

The workbook's "five energy-hardship measures" are laid out as data rows —
exact row/column labels are not hardcoded (they've shifted release to
release), so `measures --year-ended YYYY` does a substring match for the year
across all cell values and falls back to the full table with a `note` when
nothing matches.

## 2. Stats NZ HES household expenditure statistics

CKAN discovery, same pattern as the `household-hardship-nz` skill:

- Search: `GET https://catalogue.data.govt.nz/api/3/action/package_search?q=household+expenditure+statistics&rows=10`
- Show: `GET https://catalogue.data.govt.nz/api/3/action/package_show?id=<dataset-name>`

The CLI filters `package_search` results to those whose `title` contains
"expenditure" and takes the first match, rather than hardcoding a dataset
slug — HES releases get a new dataset id each year. Within that dataset's
`resources[]`, `pick_resource()` scores each resource by keyword overlap
(`detailed`, `expenditure`, the requested year) against its `name`/`url`/
`format` and picks the best-scoring one.

The resource may be a plain `.csv` or a `.zip` of one; `csv_records_from_bytes()`
detects a zip by its `PK` magic bytes and extracts the first `.csv` member
inside, mirroring `household-hardship-nz`'s ZIP handling.

Row filtering for `burden` looks for cells containing an electricity/energy
keyword (`electric`, `power`, `domestic fuel`, `energy`) alongside `decile` or
`quintile` and the requested year, since the exact HES column names for
category/breakdown vary by release. When nothing matches, the CLI returns the
first 20 raw rows with a `note` so the actual column names are visible.

## 3. Electricity Authority EMI — Disconnections for Non-Payment

Dataset listing: `https://www.emi.ea.govt.nz/Retail/Datasets/Disconnections`

This is a genuine EMI dataset directory (not the Power-BI-embedded public
dashboard at ea.govt.nz, which isn't scrapeable). `find_csv_files()` regex-
scrapes the directory listing HTML for `*.csv` filenames and resolves them
against the directory URL, the same approach `nz-electricity` uses for its
EMI final-energy-price and generation datasets.

Each matched CSV is downloaded and parsed with stdlib `csv.DictReader`. A
date/month/period column is located by header-name regex (`date|month|period`)
and used to filter by `--from`/`--to` (`YYYY-MM`). If the listing yields no
`.csv` links at all (e.g. the dataset moves to a different format), the CLI
returns `available: false` with a `note` rather than failing silently.

## User-Agent and timeouts

Requests send `User-Agent: energy-hardship-nz-skill/1.0`. Timeouts are 15s
for HTML/JSON metadata calls and 45s for workbook/CSV downloads.
