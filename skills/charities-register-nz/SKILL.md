---
name: charities-register-nz
description: Query the New Zealand Charities Services Register public OData API for charity search, organisation details, officers, activities, annual-return financials, and grantmaker census queries. Use when the task involves NZ charity registration numbers, OrganisationId-linked officers, latest/all annual returns, GrantsPaidWithinNZ, grant-making charities, or Charities Register OData fields. Read-only, keyless, and no login required.
---

# Charities Register NZ

## Goal

Use the public Charities Services Register OData endpoint to perform targeted, read-only lookups against New Zealand registered and formerly registered charities.

## Use this when

- A user asks to search New Zealand charities by name or inspect a charity by CC registration number.
- A workflow needs an `OrganisationId` for follow-up officer or annual-return lookups.
- A task needs registered charity status, NZBN, Companies Office number, sectors, activities, beneficiaries, public contact/address fields, or Charities Register summary URLs.
- A task asks for grantmakers or a grantmaker census using latest-return fields such as `GrantsPaidWithinNZ`, `GrantsPaidOutsideNZ`, `GrantsAndDonationsMade`, `TotalGrossIncome`, `TotalExpenditure`, and `TotalAssets`.
- A task needs the public activity taxonomy from `Activities`.

## Do not use this for

- Filing returns, updating charity records, logging in, or accessing non-public/suppressed data.
- Bulk mirroring the full register beyond targeted queries.
- Treating annual-return grant payments as current grant availability without checking year-ended dates and the charity's own public website.
- Surfacing officer emails. The CLI strips email-like fields from officer results if the upstream schema ever exposes them.

## CLI

```bash
python3 skills/charities-register-nz/scripts/cli.py search "Auckland Foundation" --json
python3 skills/charities-register-nz/scripts/cli.py org CC48800 --json
python3 skills/charities-register-nz/scripts/cli.py officers 260723 --json
python3 skills/charities-register-nz/scripts/cli.py returns 260723 --json
python3 skills/charities-register-nz/scripts/cli.py grantmakers --min-grants 10000 --json
python3 skills/charities-register-nz/scripts/cli.py activities --json
```

Commands:

- `search <name> [--limit N] [--json]` - search `Organisations` by charity name.
- `org <registration-number> [--json]` - fetch one organisation by CC registration number, returning its `OrganisationId` for linked lookups.
- `officers <id> [--json]` - list public officers for an `OrganisationId`; email-like fields are removed.
- `returns <id> [--all] [--json]` - fetch latest or all annual-return/financial rows for an organisation/group id from `GrpOrgLatestReturns` or `GrpOrgAllReturns`.
- `grantmakers [--min-grants N] [--limit N] [--json]` - latest-return rows where `GrantsPaidWithinNZ` is at or above the threshold, ordered descending.
- `activities [--json]` - list public activity taxonomy rows.

## Caveats

- Source: `https://www.odata.charities.govt.nz/` (keyless public OData; metadata currently advertises OData v1/v2-style JSON even though the public catalogue describes the endpoint as OData).
- Requests cap `$top` at 1000 rows. Paginate with `--skip`; do not use this skill for unrestricted bulk extraction.
- The catalogue CSV mirror uses `$returnall=true` (for example `Organisations?$format=csv&$returnall=true`) and can be used as a fallback for `search`/`org` when the JSON endpoint is blocked.
- Incapsula/bot protection may return HTTP 403. The CLI reports `blocked_by_upstream` and, for organisation searches/lookups, tries the public CSV mirror before failing.
- Officer data is public register data, but do not surface officer emails; this skill removes email-like fields from officer output.

## Resources

- CLI entrypoint: `scripts/cli.py`
- Smoke test: `scripts/smoke_test.py`
- API notes: `references/api-notes.md`
