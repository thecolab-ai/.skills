---
name: education-counts-nz
description: Query Education Counts teacher workforce and initial teacher education public sources for New Zealand teacher supply research. Use when the task involves ITE enrolments/completions, teacher numbers, teacher entry/leaving, teacher turnover, teacher demand and supply projections, workbook URLs, or source caveats for Ministry of Education teacher workforce data.
---

# Education Counts NZ

## Goal

Discover and extract public Ministry of Education Education Counts teacher workforce and ITE data with a read-only CLI.

## Use This When

- A user asks for NZ teacher supply, teacher workforce, or initial teacher education statistics
- A workflow needs current Education Counts workbook/PDF links and release dates
- Another tool needs machine-readable rows from a public Education Counts workbook
- A user needs source caveats for rounded, provisional, or bot-blocked Education Counts data

## Do Not Use This For

- School directory lookup; use an NZ schools or Education Counts directory-specific skill
- Individual teacher records, private workforce data, or Teaching Council registration checks
- Generic tertiary enrolment statistics unrelated to initial teacher education
- Authenticated Ministry systems or any attempt to bypass CAPTCHA/request-auth blocks

## Preferred Workflow

1. Run `scripts/cli.py list --json` to inspect supported dataset families and known source pages.
2. Use `resources --dataset <name> --json` to discover workbook/PDF links from the live page when the page is reachable.
3. Use the focused commands for common teacher supply tasks:
   - `ite-enrolments --from 2005 --to 2025 --json`
   - `teacher-numbers --resource headcount --from 2020 --to 2025 --json`
   - `teacher-movement --kind entering --measure numbers --from 2020 --to 2025 --json`
   - `teacher-turnover --measure rates --from 2020 --to 2024 --json`
   - `tds --year 2025 --json`
4. Use `workbook --url URL --sheet SHEET --json` for a direct public workbook URL or a downloaded file.
5. When the Education Counts site returns HTTP 403/429, report the returned `blocked` status and source URL rather than treating the source as missing.

## CLI

Run with:

```bash
python3 skills/education-counts-nz/scripts/cli.py <command> [flags]
```

Commands:

- `list [--json]` - list supported teacher workforce dataset families and source pages
- `resources --dataset NAME [--json]` - discover current links from an Education Counts page
- `ite-enrolments [--from YEAR] [--to YEAR] [--json]` - discover and parse first-time domestic ITE enrolment workbook rows
- `ite-completions [--from YEAR] [--to YEAR] [--json]` - discover/preview first ITE completion sources when available
- `teacher-numbers --resource headcount|ftte|pivot|school [--from YEAR] [--to YEAR] [--json]` - fetch teacher number workbook rows
- `teacher-movement --kind entering|leaving --measure numbers|rates [--from YEAR] [--to YEAR] [--json]` - fetch entry/leaving workbook rows
- `teacher-turnover --measure numbers|rates|pivot [--from YEAR] [--to YEAR] [--json]` - fetch turnover workbook rows
- `tds [--year YEAR] [--json]` - discover Teacher Demand and Supply Planning Projection publication pages from the live series page
- `workbook --url URL [--sheet NAME] [--from YEAR] [--to YEAR] [--limit N] [--json]` - parse a public XLSX workbook directly

## Resources

- CLI entrypoint: `scripts/cli.py`
- Smoke test: `scripts/smoke_test.py`
- Source notes and dataset caveats: `references/api-notes.md`

## Notes

- The CLI is read-only, keyless, and uses Python standard library modules only.
- XLSX workbooks are parsed with `zipfile` and `xml.etree.ElementTree`; PDFs are listed as source documents but not text-parsed.
- Education Counts pages can return HTTP 403 to HTTP clients. The CLI sends browser-like headers, then classifies 403/429 as `blocked` and keeps source metadata available.
- Figures from Education Counts may be rounded or revised; keep `source_url`, `fetched_at`, and release notes with any reported numbers.
