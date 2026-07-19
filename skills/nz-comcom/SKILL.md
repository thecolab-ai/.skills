---
name: nz-comcom
description: "Search New Zealand Commerce Commission cases, news, decisions, and reports from comcom.govt.nz. Use when the task involves the Commerce Commission (ComCom), the case register (merger clearances, cartel, consumer credit, fair trading), market studies, regulated industries (electricity, gas, telco, fibre, airports, dairy, grocery, fuel), media releases, or finding ComCom report/decision PDFs. Keyless, read-only; no login."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "public-data"
  thecolab.source_owner: "Commerce Commission"
  thecolab.source_type: "official"
  thecolab.auth: "none"
  thecolab.access_mode: "public-api"
  thecolab.data_class: "public"
  thecolab.writes: "false"
  thecolab.browser: "false"
  thecolab.risk: "low"
  thecolab.cache_ttl: "24h"
  thecolab.schema_version: "1"
  thecolab.skill_type: "public-api"
  thecolab.pack: "nz-public-data"
  thecolab.source_url: "https://www.comcom.govt.nz"
  thecolab.allowed_domains: "www.comcom.govt.nz"
  thecolab.last_verified: "2026-07-19"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# NZ Commerce Commission

Search and read public material from the **New Zealand Commerce Commission**
(comcom.govt.nz) — the competition, consumer, and economic-regulation authority.
Keyless, read-only; no login, account, or API key.

## Use this when

- A user wants to **search ComCom** for a topic, decision, or report
- A user asks about the **case register** — merger/acquisition clearances,
  cartel and fair trading enforcement, consumer credit cases, their status/outcome
- A user wants **market studies** or **regulated-industry** material (electricity,
  gas, telco, fibre, airports, dairy, grocery, retail fuel)
- A user wants recent **media releases / decisions / report announcements**
- A user wants the **document/report PDFs** attached to a case or page

## Do not use this for

- Ministers / government press releases — use `nz-ministers`
- Bills before Parliament — use `nz-parliament`
- Company registration / directors — use `companies-office-nz` or `nzbn-register`
- Filing complaints or any write/login action (read-only)

## Commands

```bash
cli=skills/nz-comcom/scripts/cli.py

# Site-wide search across cases, decisions, reports, guidelines
python3 $cli search "grocery market study"
python3 $cli search "interchange fees" --limit 10 --json

# Case register entries (recent, or filtered by keyword)
python3 $cli cases
python3 $cli cases --keyword finance --json

# News, media releases, and report announcements
python3 $cli news
python3 $cli news --year 2026 --json

# Read one page/case and list its documents (report PDFs)
python3 $cli page /case-register/case-register-entries/asb-bank-ltd/
python3 $cli page https://www.comcom.govt.nz/about-us/our-role/competition-studies/ --json
```

### Arguments

- `search <query>` — `--limit N`, `--json`
- `cases` — `-k/--keyword TEXT`, `--limit N`, `--json`
- `news` — `--year YYYY`, `--limit N`, `--json`
- `page <url|path>` — `--limit N` (max documents), `--json`

## Resources

- CLI entrypoint: `scripts/cli.py`
- Smoke test: `scripts/smoke_test.py`
- Endpoints, card parsing, and document extraction: `references/api-notes.md`

## Notes

- Data are live snapshots scraped from the server-rendered comcom.govt.nz site.
- `search`/`cases`/`news` return result cards (title, URL, summary/status); use
  `page` to drill into a result and collect its report/decision PDFs.
- `--json` on every command gives machine-readable output for agent chaining.
- Use NZ English in any summaries built from the output (organisation, colour).
