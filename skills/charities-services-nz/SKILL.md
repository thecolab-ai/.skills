---
name: charities-services-nz
description: Query Charities Services New Zealand public OData for registered charities, organisation metadata, officers-linked records, sectors, annual-return financials, and grant-making signals. Use when the task involves NZ charity lookup, charity registration numbers, grant-making charities, GrantsPaidWithinNZ, annual returns, Charities Register summaries, or schema discovery from odata.charities.govt.nz. Read-only and no API key required.
---

# Charities Services NZ

## Goal

Query the public Charities Services OData service through a deterministic no-login Python CLI. The skill focuses on registered charity discovery, charity record lookup, OData schema inspection, and grant-making spot queries.

## Use this when

- A user asks to find or inspect a New Zealand charity by name, OrganisationId, or CC registration number
- A workflow needs registered/deregistered status, contact fields, addresses, NZBN, Companies Office number, sector/activity/beneficiary IDs, or Charities Register summary URLs
- A task asks for grant-making charities or organisations whose purpose is to give grants and donations
- A task needs latest annual-return financial fields such as `GrantsPaidWithinNZ`, `GrantsPaidOutsideNZ`, `TotalGrossIncome`, `TotalExpenditure`, or `TotalAssets`
- You need to discover OData collections or entity fields before writing a narrow query

## Do not use this for

- Private, suppressed, authenticated, or non-public charity data
- Filing annual returns or making changes to a charity record
- Bulk mirroring the full Charities Register or annual-return database
- Treating historical latest-return rows as current funding availability without checking registration status and year-ended date
- Companies Register governance/shareholder detail; use `companies-office-nz` for company-specific governance data

## CLI

```bash
python3 skills/charities-services-nz/scripts/cli.py collections
python3 skills/charities-services-nz/scripts/cli.py fields Organisations
python3 skills/charities-services-nz/scripts/cli.py search "Auckland Foundation" --json
python3 skills/charities-services-nz/scripts/cli.py entity CC48800 --id-type cc --json
python3 skills/charities-services-nz/scripts/cli.py grant-intent --registered-only --limit 10 --json
python3 skills/charities-services-nz/scripts/cli.py grants-paid --registered-only --min-amount 100000 --limit 10 --json
python3 skills/charities-services-nz/scripts/cli.py query GrpOrgLatestReturns --filter "GrantsPaidWithinNZ gt 0" --select "Name,CharityRegistrationNumber,RegistrationStatus,YearEnded,GrantsPaidWithinNZ" --orderby "GrantsPaidWithinNZ desc" --limit 5 --json
```

Commands:

- `collections [--json]` - list available OData collections from the service document
- `fields ENTITY [--json]` - list fields and OData types from `$metadata`
- `search QUERY [--registered-only] [--limit N] [--json]` - search `Organisations` by `Name`
- `entity IDENTIFIER [--id-type org|cc] [--json]` - lookup one `Organisations` row by numeric `OrganisationId` or CC registration number
- `grant-intent [--registered-only] [--limit N] [--count] [--json]` - run the spot query `Organisations?$filter=PurposeToGiveGrantsAndDonations eq true`
- `grants-paid [--min-amount N] [--registered-only] [--limit N] [--count] [--json]` - run the spot query `GrpOrgLatestReturns?$filter=GrantsPaidWithinNZ gt 0`, default ordered by `GrantsPaidWithinNZ desc`
- `query ENTITY [--filter ODATA] [--select FIELDS] [--orderby EXPR] [--limit N] [--skip N] [--count] [--json]` - generic read-only OData query wrapper

## Grant-making workflow

1. Start with `grant-intent --registered-only --json` when the question is about charities whose stated purpose includes giving grants/donations. Confirm rows include `PurposeToGiveGrantsAndDonations: true` and current `RegistrationStatus`.
2. Use `grants-paid --registered-only --min-amount <amount> --json` when the question needs actual latest-return grant payments. Check `YearEnded` because many rows are historical and “latest return” can be old.
3. For a short list, include `Name`, `CharityRegistrationNumber`, `RegistrationStatus`, `YearEnded`, `GrantsPaidWithinNZ`, `TotalGrossIncome`, and `CharitySummaryURL`.
4. For due diligence, follow up with `entity <CC> --id-type cc --json` and the public `CharitySummaryURL`; do not infer eligibility, application windows, or current grant programmes from OData financial fields alone.

## Resources

- CLI entrypoint: `scripts/cli.py`
- Smoke test: `scripts/smoke_test.py`
- API notes and known spot queries: `references/api-notes.md`

## Notes

- Source: `https://www.odata.charities.govt.nz/`
- The service is OData v2-style JSON (`application/json;odata=verbose`) and XML metadata.
- Spot queries investigated on 2 July 2026: `Organisations?$filter=PurposeToGiveGrantsAndDonations eq true` and `GrpOrgLatestReturns?$filter=GrantsPaidWithinNZ gt 0`.
- Use `--count` sparingly: it asks for `$inlinecount=allpages` and can be slower on broad filters.
- Keep `$top` small and paginate with `--skip`; this skill is for targeted lookup, not bulk extraction.
