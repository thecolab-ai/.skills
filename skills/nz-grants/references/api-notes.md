# NZ grants source notes

## DIA / Granted.govt.nz Class 4 grant distribution history

Primary public sources:

- Granted portal: <https://www.granted.govt.nz/>
- data.govt.nz package: `class-4-grants-data` / "Grants from Gaming Machine Profits"
- CKAN API: <https://catalogue.data.govt.nz/api/3/action/package_show?id=class-4-grants-data>

The CLI discovers the current CSV resource from the CKAN package at runtime and falls back to the observed CSV resource URL if CKAN discovery is unavailable:

- `https://catalogue.data.govt.nz/dataset/b6b7f1cc-bfa4-4c7a-81e8-8a03f2983cae/resource/06d99ad0-47d6-4591-84c7-8872a4f77da9/download/class-4-grants-dataset-csv.csv`

Observed row fields include:

- `Society_Name` - Class 4 society/funder.
- `Organisation_Name` and `Final_Organisation_Name` - recipient names.
- `NZBN`.
- `Status` - accepted or declined.
- `Amount_Requested_Final`, `Amount_Granted_Final`, `Amount_Refunded_Clean`.
- `Date_of_Accept/Decline` and `Year_of_Accept/Decline`.
- `Category_1`, `Category_2`.
- `Territorial_Local_Authority` and `Region`.

The `class4 --period YYYY-H1|YYYY-H2` command derives half-year periods from `Date_of_Accept/Decline` when present. If older rows expose only a year field, they can match the year but cannot be split more precisely by month.

## CommunityMatters fund/opportunity pages

Primary source:

- Funds index: <https://www.communitymatters.govt.nz/funds/>

The skill uses standard-library HTML parsing to extract fund/opportunity links from the funds index and readable text from individual fund pages. `fund get` accepts either a slug (mapped to `/funds/<slug>/`) or a full CommunityMatters URL.

Returned opportunity records are deliberately source-backed and conservative: title/link on index extraction, then title, description metadata, page text, and application/guidance links on detail fetch. The skill does not submit forms or follow login-only SmartyGrants/application flows.

## Caveats and outage behaviour

- CommunityMatters can return HTTP 403 from headless/cloud environments due to Incapsula/Cloudflare-style protection. This skill reports `upstream_unavailable` and exits 2; smoke tests skip cleanly in that case.
- DIA/data.govt.nz CSV downloads can be large, so Class 4 commands stream rows and cap returned records with `--limit` while still computing totals for all matches.
- XLSX resources are not parsed because repository convention is Python standard library only. The implementation prefers CSV resources and documents the limitation.
- Frozen Lottery recipient CSVs on CKAN are out of scope for this skill.
