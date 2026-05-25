---
name: stats-nz
description: Query official Stats NZ data: CPI, GDP, population estimates/projections, migration, and CSV catalogue. No API key or browser session required.
---

# Stats NZ

## Goal

Query official New Zealand statistics through a small deterministic CLI with human-readable and JSON output, without browser automation, login, API keys, or local cache state.

This skill ships support for:

- Consumers price index quarterly index numbers
- National estimated population and national population projections
- Regional council estimated resident population from Stats NZ place summaries
- International long-term migrant arrivals, departures, and net migration
- Quarterly GDP production and expenditure headline series
- Exact series lookup for the wired CPI and GDP CSV releases
- Search over the Stats NZ large-datasets CSV catalogue

## Use this when

- A user asks for official New Zealand CPI, GDP, population, or migration figures
- A user needs recent Stats NZ release values in a repeatable command-line workflow
- A user wants a Stats NZ CSV dataset URL or to search the public CSV catalogue
- A workflow needs public, no-login, machine-readable Stats NZ data
- Another tool or agent needs JSON output from official New Zealand statistics

## Do not use this for

- Private, unpublished, embargoed, or authenticated Stats NZ data
- Administrative Data Explorer or OData API calls that require subscription keys
- Geospatial boundaries, maps, or GIS workflows from datafinder.stats.govt.nz
- Census microdata, confidentialised unit records, or custom table-builder extraction
- Redistributing public-data extracts as a standalone dataset

## Preferred workflow

1. Run `scripts/cli.py` with the narrowest subcommand that answers the task
2. Use `cpi` for the headline quarterly all-groups CPI index
3. Use `population` for national estimates, `population --projection YEAR` for national projections, or `population --region REGION` for regional council population
4. Use `migration` for latest long-term migrant arrivals, departures, and net migration
5. Use `gdp` for quarterly headline GDP production and expenditure series
6. Use `series <id>` when the user gives a Stats NZ `Series_reference`
7. Use `search <query>` before adding a new Stats NZ CSV-backed command
8. Use `--json` when another tool or agent needs machine-readable output
9. Mention Stats NZ as the upstream source and include the release URL when reporting figures

## CLI

Run with:

```bash
python3 skills/stats-nz/scripts/cli.py <command> [flags]
```

## Commands

- `cpi [--from DATE] [--to DATE] [--json]` - Consumers price index quarterly all-groups index for New Zealand
- `population [--region REGION] [--projection YEAR] [--scenario SCENARIO] [--json]` - national population, regional council population, or national projection
- `migration [--json]` - latest estimated long-term migrant arrivals, departures, and net migration
- `gdp [--from DATE] [--to DATE] [--json]` - quarterly headline GDP production and expenditure measures
- `series ID [--from DATE] [--to DATE] [--limit N] [--json]` - observations for a wired Stats NZ `Series_reference`
- `search QUERY [--limit N] [--json]` - search the Stats NZ large-datasets CSV catalogue

Examples:

```bash
python3 skills/stats-nz/scripts/cli.py cpi
python3 skills/stats-nz/scripts/cli.py cpi --from 2025-03 --json
python3 skills/stats-nz/scripts/cli.py population --json
python3 skills/stats-nz/scripts/cli.py population --region auckland --json
python3 skills/stats-nz/scripts/cli.py population --projection 2050 --json
python3 skills/stats-nz/scripts/cli.py migration --json
python3 skills/stats-nz/scripts/cli.py gdp --json
python3 skills/stats-nz/scripts/cli.py series CPIQ.SE9A --limit 4 --json
python3 skills/stats-nz/scripts/cli.py search "gross domestic product" --limit 5 --json
```

## Resources

- CLI entrypoint: `scripts/cli.py`
- API and dataset notes: `references/api-notes.md`

## Notes

- Stats NZ is the upstream source for all implemented commands
- No API key, username, password, cookie, or browser session is required for implemented commands
- `cpi`, `gdp`, `migration`, `series`, and `search` use the public Stats NZ large-datasets CSV catalogue at `https://www.stats.govt.nz/large-datasets/csv-files-for-download/`
- `population` uses public Stats NZ indicator, projection release, and place-summary pages
- The modern Stats NZ OData/API surface was not wired because live discovery indicated subscription-key requirements; this skill stays no-login and read-only
- CSV release URLs change as new releases are published; the CLI discovers the current release from the Stats NZ catalogue where possible
- Default output is human-readable; every data command supports `--json` for chaining into other tools
- Avoid high-volume polling; use narrow commands and date filters
