---
name: comcom-connectivity-map
description: Inspect Commerce Commission Telecommunications Connectivity Map public metadata, provider-list workbooks, annual monitoring report links, and source caveats for rural broadband coverage research. Use when the task involves ComCom connectivity map data, rural broadband coverage, provider supplied coverage, annual telecommunications monitoring reports, or distinguishing coverage from address-level orderability.
---

# ComCom Connectivity Map

## Goal

Inspect public Commerce Commission Telecommunications Connectivity Map sources
with a standard-library, keyless CLI. The skill reports what can be fetched
directly, what is only available as a linked PDF/workbook, and when a source is
blocked rather than dead.

## Use This When

- A user asks about rural broadband coverage, fixed wireless coverage, or
  provider-supplied connectivity-map data in New Zealand.
- A For Good workflow needs repeatable source metadata for ComCom
  Telecommunications Connectivity Map research.
- You need the annual telecommunications monitoring report years and source
  URLs.
- You need ComCom's provider-list workbook metadata and a small row preview.
- You need to distinguish public coverage-map evidence from practical
  availability or orderability at a specific address.

## Do Not Use This For

- General ComCom case/news/report search; use `nz-comcom`.
- Broadband performance testing; use ComCom Measuring Broadband New Zealand
  sources through a more specific workflow.
- Address-level service checks, private provider APIs, orderability decisions,
  login portals, or attempts to bypass CAPTCHA/request-auth blocks.
- PDF text/table extraction. The CLI links annual report PDFs but does not parse
  their tables.

## Workflow

1. Run `scripts/cli.py list-years --json` to discover annual monitoring report
   years and source URLs.
2. Run `coverage-summary --year YYYY --json` for map metadata, the current
   coverage-date statement, methodology caveats, and the matching annual report
   link when available.
3. Run `providers --year YYYY --json` to fetch the public provider-list workbook
   metadata and preview rows.
4. Run `layer-metadata --year YYYY --json` to report public GIS/map layer URLs
   directly discoverable from the ComCom page, or a `not_discovered` state when
   the page only exposes the embedded map.
5. If JSON returns `blocked_by_upstream`, report that as bot/Incapsula-style
   blocking. If it returns `dead_link`, treat that separately as a broken source.

## CLI

```bash
python3 skills/comcom-connectivity-map/scripts/cli.py list-years --json
python3 skills/comcom-connectivity-map/scripts/cli.py coverage-summary --year 2025 --json
python3 skills/comcom-connectivity-map/scripts/cli.py providers --year 2025 --limit 25 --json
python3 skills/comcom-connectivity-map/scripts/cli.py layer-metadata --year 2025 --json
```

## Output Notes

- `fetch_method` is `direct_http` when the public ComCom page or workbook was
  fetched without a browser or API key.
- `coverage_date` comes from ComCom's page text, not from private provider
  systems.
- `provider_list` is a workbook link/preview, not a full address-level coverage
  export.
- `layer-metadata` only reports URLs visible from public page HTML. If none are
  present, it returns `status: not_discovered` rather than guessing.
- Source details and caveats are in `references/source-notes.md`.

## Resources

- CLI entrypoint: `scripts/cli.py`
- Smoke test: `scripts/smoke_test.py`
- Source notes: `references/source-notes.md`
