---
name: property-rates-nz
description: Query Auckland Council public property rates, capital value (CV), land value, improvement value, and annual rates through the council's no-login rate-assessment API. Use when the task involves Auckland property CV, council valuation, land value, improvement value, annual rates total, floor area, land area, or legal description. Read-only; requires an Auckland Council property ID (ACRateAccountKey).
---

# Property Rates NZ — Auckland Council Valuations

## Goal

Query live Auckland Council property rate-assessment data — capital value, land value, annual rates, floor area, and property details — through a deterministic CLI with JSON output.

## Use this when

- A user asks for the capital value (CV) of an Auckland property
- A user wants to know annual council rates for an address
- A user needs land value vs improvement value breakdown
- A user asks for floor area, land area, or legal description from council records
- A user has an Auckland Council property/rating ID and wants official valuation data
- A workflow needs machine-readable council valuation data

## Do not use this for

- Market value estimates or sale price predictions; use `homes-nz` for HomesEstimate
- Active property listings; use `trademe-nz` for listings, `homes-nz` for estimates
- Properties outside Auckland Council jurisdiction
- Finding a property ID from an address — this skill requires a known property ID
- CV history or multiple valuation dates — the API returns the current assessment only

## Finding a Property ID

This skill requires an Auckland Council property ID (ACRateAccountKey). To find one:

1. Use the Auckland Council rates search page: `https://www.aucklandcouncil.govt.nz/en/property-rates-valuations/find-property-rates-valuation.html`
2. Search by address to get your property ID
3. The property ID is a numeric string (e.g., `12343300679`)

Alternatively, use the `auckland-bin-schedule` skill to look up a property ID from an address, then use the returned property ID here.

## CLI

Run with:

```bash
python3 skills/property-rates-nz/scripts/cli.py <command> [flags]
```

### Commands

- `rates <property-id> [--json]` — fetch full council valuation and rates data

Examples:

```bash
python3 skills/property-rates-nz/scripts/cli.py rates 12343300679
python3 skills/property-rates-nz/scripts/cli.py rates 12343300679 --json
```

## Resources

- CLI entrypoint: `scripts/cli.py`
- Smoke test: `scripts/smoke_test.py`
- API notes: `references/api-notes.md`

## Notes

- No API key, login, or account required — the CLI extracts a public bearer token from the council search page at runtime (same approach as `auckland-bin-schedule`)
- The API is at `experience.aucklandcouncil.govt.nz/nextapi/property/{id}/rate-assessment`
- The property ID (ACRateAccountKey) is the same one used by the bin schedule and rates search
- Valuation date is typically set by Auckland Council's triennial revaluation cycle
- Treat values as official council snapshots, not real-time market data
- Annual rates figure is the total rates assessment, not what's currently paid
- Auckland Council only — other councils (Wellington, Christchurch) have different systems
