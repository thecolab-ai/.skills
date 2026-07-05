---
name: gets-procurement-nz
description: Discover New Zealand public procurement opportunities and award notices from GETS, MBIE open-data metadata, and procurement.govt.nz significant-service-contract sources. Use when Codex needs keyless NZ government tender searches, current GETS notices, RFx detail by ID, recent completed/award notices, procurement source URLs, or significant service contract dashboard summaries.
---

# GETS Procurement NZ

## Goal

Find public New Zealand government procurement notices and related procurement transparency sources without an API key.

## Use this when

- A user asks for current NZ government tenders, ROI/NOI/RFP/RFQ notices, or GETS RFx IDs
- A workflow needs a deterministic search over public GETS notices
- A user has an RFx ID and wants the public notice details
- A task needs recent GETS completed/award notices by agency
- A task needs the official open-data/source URLs for GETS award CSVs or significant service contracts

## Do not use this for

- Downloading restricted tender documents or responding to tenders
- Bypassing GETS registration, RealMe, CAPTCHAs, or access controls
- Treating the public significant-service-contract dashboard as a contract-by-contract register

## CLI

```bash
python3 skills/gets-procurement-nz/scripts/cli.py tenders list --status open --json
python3 skills/gets-procurement-nz/scripts/cli.py tenders search "cleaning services" --json
python3 skills/gets-procurement-nz/scripts/cli.py tender get 34247421 --json
python3 skills/gets-procurement-nz/scripts/cli.py awards --agency "Auckland Transport" --json
python3 skills/gets-procurement-nz/scripts/cli.py datasets sources --json
python3 skills/gets-procurement-nz/scripts/cli.py ssc summary --json
```

Commands:

- `tenders list [--status open|late|closed|completed|awarded] [--keyword TEXT] [--page N] [--limit N] [--json]` - list public GETS notices. Open page 1 uses the GETS RSS feed.
- `tenders search QUERY [--page N] [--limit N] [--json]` - search public GETS notices.
- `tender get RFX_ID_OR_URL [--json]` - fetch public notice detail.
- `awards [--agency NAME] [--pages N] [--limit N] [--json]` - scan recent GETS completed/award notice pages.
- `datasets sources [--json]` - list official source feeds, pages, downloadable datasets, and caveats.
- `ssc summary [--json]` - summarise the public procurement.govt.nz significant-service-contract dashboard workbook.

All network calls have a timeout and report clear errors to stderr. Data commands support `--json`.

## Resources

- CLI: `scripts/cli.py`
- Smoke test: `scripts/smoke_test.py`
- Source notes and caveats: `references/api-notes.md`
