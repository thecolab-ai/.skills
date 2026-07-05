---
name: nz-angel-investment
description: Queries New Zealand angel and seed investment publication sources from NZGCP Young Company Finance, NZGCP annual/ecosystem reports, and Angel Association NZ member and investment-publication pages. Use when the task involves NZ early-stage capital, angel investment, seed funding, Young Company Finance deal or investment counts, Aspire/Elevate reporting, investor directories, Angel Market reports, or source-backed publication discovery; read-only and no API key required.
---

# NZ Angel Investment

## Goal

Discover and lightly structure New Zealand angel/seed investment sources from NZGCP and Angel Association NZ without requiring API keys or paid Dealroom access.

## Use this when

- A user asks for NZ Young Company Finance releases, deal counts, invested dollars, or companies funded.
- A workflow needs NZGCP annual reports, Dealroom ecosystem reports, Aspire/Elevate reporting, or a source URL for early-stage capital evidence.
- A user asks for Angel Association NZ members, angel networks, investor regions, or investment publications such as Angel Market reports.
- A task needs machine-readable JSON from public NZ angel/seed investment source pages.

## Do not use this for

- Querying the paid Dealroom database/API, logging into investor platforms, or bypassing access controls.
- Legal, financial, investment, or fundraising advice. Return source-backed facts and caveats instead.
- Treating PDF chart/table values as final where the CLI reports `source_discovery_only`; manually verify the linked publication before citing.

## CLI

```bash
python3 skills/nz-angel-investment/scripts/cli.py ycf list --json
python3 skills/nz-angel-investment/scripts/cli.py ycf list --discover --json
python3 skills/nz-angel-investment/scripts/cli.py ycf get 2025 --json
python3 skills/nz-angel-investment/scripts/cli.py nzgcp-reports --kind annual_report --json
python3 skills/nz-angel-investment/scripts/cli.py investors --region Auckland --limit 10 --json
python3 skills/nz-angel-investment/scripts/cli.py publications --json
python3 skills/nz-angel-investment/scripts/cli.py sources --json
```

Commands:

- `ycf list [--discover] [--limit N] [--json]` - returns curated Young Company Finance releases and, with `--discover`, refreshes links from the NZGCP startup investment report page.
- `ycf get <period-or-alias> [--json]` - returns one YCF release. `2025` includes curated headline metrics from NZGCP YCF Autumn 2026; other releases are source-discovery records until metrics are manually extracted.
- `nzgcp-reports [--kind KIND] [--limit N] [--json]` - lists NZGCP report PDFs, including annual reports and Dealroom ecosystem reports. Uses the NZGCP report page plus curated known report URLs.
- `investors [--query TEXT] [--region REGION] [--limit N] [--json]` - reads the Angel Association NZ public members directory and returns investor/member cards with name, regions, focus/tagline, URL, email when listed, and locations.
- `publications [--kind KIND] [--limit N] [--json]` - discovers Angel Association NZ investment publications from the investment-publications page and WordPress download records.
- `sources` / `datasets` - returns the source catalogue, access notes, and caveats.

## Operational Notes

The CLI is intentionally conservative because the important figures live in PDFs and image-heavy report pages. It prefers source discovery, curated known reports, and explicit caveats over brittle stdlib-only PDF chart parsing.

Network failures, bad JSON, rate limits, or upstream outages return `upstream_unavailable` and exit code 2 for JSON commands. Not-found periods return a JSON `not_found` error with exit code 1.

## Resources

- CLI: `scripts/cli.py`
- Smoke test: `scripts/smoke_test.py`
- Source and extraction notes: `references/api-notes.md`
