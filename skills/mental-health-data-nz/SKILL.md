---
name: mental-health-data-nz
description: Use when Codex needs New Zealand mental-health regulatory data from ODMHAS reports, seclusion/restraint summaries, MH&A KPI Programme indicator metadata, inpatient inspection counts, District Inspector sources, or source caveats for public mental-health transparency work. Read-only, keyless, and stdlib-only.
---

# Mental Health Data NZ

## Goal

Discover and extract public New Zealand mental-health regulatory data from Manatu Hauora / Health NZ sources without login, API keys, browser automation, or invented PDF-derived rows.

The skill focuses on:

- Office of the Director of Mental Health and Addiction Services (ODMHAS) regulatory reports
- Seclusion/restraint summary tables that are available in report DOCX files
- MH&A KPI Programme public indicator and dashboard metadata
- Section 95 inquiry, section 99 inspection, and District Inspector source discovery
- Clear blocked/manual-export states for PDF-only, chart-only, sign-in, or bot-protected sources

## Use this when

- A user asks for NZ seclusion/restraint trend sources, annual report URLs, or extractable seclusion summary rows
- A workflow needs ODMHAS report metadata, PDF/DOCX links, publication dates, and source caveats
- A user asks about MH&A KPI indicators such as wait times, seclusion, 7-day follow-up, 28-day readmission, whanau engagement, or continuity of care
- A user needs public metadata for KPI dashboards where the dashboard data itself requires registration/sign-in
- A user asks for inpatient inspection, section 95 inquiry, section 99 inspection, or District Inspector regulatory sources

## Do not use this for

- Clinical advice, diagnosis, treatment recommendations, or crisis support
- Private, identifiable, unpublished, or authenticated health records
- PRIMHD custom exports from protected dashboard tools
- Circumventing Cloudflare, CloudFront, CAPTCHA, registration, or sign-in requirements
- Extracting chart-only PDF values unless an official machine-readable or DOCX table is available

## Preferred workflow

1. Run `scripts/cli.py odmhas-reports --json` to list known and discoverable ODMHAS regulatory reports.
2. Run `scripts/cli.py seclusion --year 2023 --json` for extractable DOCX seclusion tables and caveats.
3. Add `--district <name>` when a district/regional service filter is needed; check caveats because adult district event/rate charts may be chart-only.
4. Run `scripts/cli.py kpi list --json` to enumerate public MH&A KPI indicator metadata.
5. Run `scripts/cli.py kpi get <indicator> --json` for a specific indicator page, dashboard links, evidence-review links, and registration caveats.
6. Run `scripts/cli.py inpatient-inspections --year 2023 --json` for section 95/99 table rows and related inspection/District Inspector sources.
7. Run `scripts/cli.py sources --json` or `datasets --json` for source catalogue notes.
8. Include source URLs, extraction status, and caveats in user-facing answers.

## CLI

Run with:

```bash
python3 skills/mental-health-data-nz/scripts/cli.py <command> [flags]
```

## Commands

- `odmhas-reports [--limit N] [--json]` - list ODMHAS regulatory reports with page/PDF/DOCX links
- `seclusion --year YEAR [--district TEXT] [--json]` - extract seclusion summary tables from report DOCX where available
- `kpi list [--json]` - list MH&A KPI Programme public indicators and metadata pages
- `kpi get INDICATOR [--json]` - inspect one KPI indicator page and dashboard/resource links
- `kpi-sources [--json]` - shortcut for KPI source metadata
- `inpatient-inspections [--year YEAR] [--json]` - extract section 95/99 count rows and inspection source links
- `datasets [--json]` / `sources [--json]` - list official source surfaces and caveats

Examples:

```bash
python3 skills/mental-health-data-nz/scripts/cli.py odmhas-reports --json
python3 skills/mental-health-data-nz/scripts/cli.py seclusion --year 2023 --json
python3 skills/mental-health-data-nz/scripts/cli.py seclusion --year 2023 --district Canterbury --json
python3 skills/mental-health-data-nz/scripts/cli.py kpi list --json
python3 skills/mental-health-data-nz/scripts/cli.py kpi get seclusion --json
python3 skills/mental-health-data-nz/scripts/cli.py inpatient-inspections --year 2023 --json
python3 skills/mental-health-data-nz/scripts/cli.py sources --json
```

## Resources

- CLI entrypoint: `scripts/cli.py`
- Smoke test: `scripts/smoke_test.py`
- Source notes and caveats: `references/api-notes.md`

## Notes

- The CLI uses Python standard library modules only (`argparse`, `urllib`, `html.parser`, `zipfile`, `xml.etree.ElementTree`, and `json`).
- Network calls default to a 10-second timeout.
- Health publication pages may return 403 from some hosts; the CLI retains known direct DOCX/PDF report URLs and reports the blocked discovery state.
- KPI dashboards expose public metadata pages, but the data dashboards can require registration/sign-in; the CLI treats those as metadata-only unless a public export is present.
