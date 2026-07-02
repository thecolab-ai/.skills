---
name: class4-grants-nz
description: Query New Zealand Class 4 gambling grants and Granted.govt.nz public data from DIA/data.govt.nz. Use when the task involves pokie-machine grant funding, gaming-machine profits, grant recipients, Class 4 societies/funders, grant categories, regional/TLA grant totals, accepted or declined grant applications, or discovering the related venues and gaming-machine quarterly datasets. Read-only and no API key required.
---

# Class 4 Grants NZ

## Goal

Query public Department of Internal Affairs Class 4 gambling grants data, the Granted.govt.nz source dataset, and related data.govt.nz discovery metadata through a deterministic no-login CLI.

## Use this when

- A user asks about NZ Class 4 grants, pokie grants, gaming-machine profit grants, or Granted.govt.nz data
- A workflow needs grant rows filtered by year, status, society/funder, recipient, category, region, or territorial local authority
- A user wants top funders, recipients, or grant categories from the Class 4 grants CSV
- A task needs source links for the Class 4 grants dataset, venue/gaming-machine quarterly lists, or DIA society website list

## Do not use this for

- Applying for a grant, logging into society portals, submitting forms, or changing any funding record
- Real-time venue/gaming-machine counts beyond the public quarterly file links
- Legal or regulatory advice about gambling compliance
- Bulk mirroring the full data catalogue beyond the task at hand

## CLI

```bash
python3 skills/class4-grants-nz/scripts/cli.py datasets --json
python3 skills/class4-grants-nz/scripts/cli.py preview --limit 5
python3 skills/class4-grants-nz/scripts/cli.py grants --year 2024 --status Accepted --region Auckland --limit 10 --json
python3 skills/class4-grants-nz/scripts/cli.py funders --year 2024 --limit 10
python3 skills/class4-grants-nz/scripts/cli.py recipients --society "Pub Charity" --limit 10 --json
python3 skills/class4-grants-nz/scripts/cli.py categories --year 2024 --field Category_1
python3 skills/class4-grants-nz/scripts/cli.py society-websites --json
```

Commands:

- `datasets [--json]` - discover the grants CSV and venue/gaming-machine quarterly list datasets from data.govt.nz CKAN
- `preview [--limit N] [--json]` - show the first rows of the Class 4 grants CSV
- `grants [filters] [--limit N] [--json]` - filter grant application rows and report matched totals
- `funders [filters] [--limit N] [--sort FIELD] [--json]` - aggregate by society/funder
- `recipients [filters] [--limit N] [--sort FIELD] [--json]` - aggregate by final recipient organisation
- `categories [filters] [--field Category_1|Category_2] [--limit N] [--json]` - aggregate by grant category
- `society-websites [--limit N] [--json]` - list DIA-published society website links

Shared filters for grants/aggregate commands: `--query`, `--year`, `--status Accepted|Declined`, `--society`, `--recipient`, `--category`, `--region`, and `--tla`.

## Resources

- CLI: `scripts/cli.py`
- Smoke test: `scripts/smoke_test.py`
- Source notes: `references/api-notes.md`
