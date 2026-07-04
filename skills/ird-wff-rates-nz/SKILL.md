---
name: ird-wff-rates-nz
description: Query Inland Revenue Working for Families, Best Start, Minimum Family Tax Credit, In-Work Tax Credit, and FamilyBoost public rate/threshold parameters. Use when the task involves NZ family entitlement pre-check inputs, WFF tax-credit rates, abatement thresholds/rates, Best Start rules, FamilyBoost income caps, or official IRD eligibility source links. Read-only, no login or API key; optional source probes handle IRD availability gracefully.
---

# IRD WFF Rates NZ

## Goal

Expose source-backed Inland Revenue (IRD) public parameters for Working for Families tax credits, Best Start, Minimum Family Tax Credit, and FamilyBoost in a small Python CLI.

## Use this when

- You need the Family Tax Credit, In-Work Tax Credit, Best Start, or Minimum Family Tax Credit amount table for a tax year.
- You need Working for Families abatement thresholds/rates for entitlement pre-check variables.
- You need FamilyBoost reimbursement rates, quarterly income caps, maximum payments, abatement, or eligibility bullets.
- You need official IRD source URLs for rates and eligibility pages.

## Do not use this for

- Calculating a final entitlement or giving tax advice. Direct users to IRD/myIR or the official calculators for decisions.
- Applying for Working for Families or FamilyBoost, logging into myIR, or changing taxpayer details.
- Aggregate WFF statistics, recipient counts, or expenditure datasets; use `data-govt-nz` for CKAN/data.govt.nz statistics.
- Circumventing bot protection. If IRD source probing is unavailable, treat it as `upstream_unavailable` and use the cited URL for manual verification.

## CLI

```bash
python3 skills/ird-wff-rates-nz/scripts/cli.py rates --year 2027 --json
python3 skills/ird-wff-rates-nz/scripts/cli.py thresholds --year 2027 --json
python3 skills/ird-wff-rates-nz/scripts/cli.py credit get family-tax-credit --year 2027 --json
python3 skills/ird-wff-rates-nz/scripts/cli.py credit get best-start --year 2027 --probe --json
python3 skills/ird-wff-rates-nz/scripts/cli.py familyboost --json
```

Commands:

- `rates --year YYYY [--probe] [--json]` - all built-in WFF credit amount tables and abatement parameters for a tax year ending 31 March.
- `thresholds --year YYYY [--probe] [--json]` - WFF and Best Start income thresholds and abatement rates.
- `credit get <family-tax-credit|in-work|best-start|mftc> --year YYYY [--probe] [--json]` - one credit's amounts, eligibility summary, thresholds, and source URL.
- `familyboost [--probe] [--json]` - FamilyBoost quarterly reimbursement rates, income caps, maximums, abatement rates, claim quarters, and eligibility bullets.

`--probe` performs a timed read-only HTTP check against the cited public IRD page and returns availability plus a last-updated snippet when visible. Core JSON remains available without network access.

## Operational notes

- Tax year means the year ending 31 March; for example `2027` covers 1 April 2026 to 31 March 2027.
- The helper is standard-library Python only and has no API key, login, cache, browser, or third-party dependency.
- Built-in numeric schedules are intentionally narrow and source-cited; re-check after each Budget/1 April update.

## Resources

- CLI: `scripts/cli.py`
- Smoke test: `scripts/smoke_test.py`
- Source notes: `references/api-notes.md`
