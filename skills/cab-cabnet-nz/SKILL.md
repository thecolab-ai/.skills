---
name: cab-cabnet-nz
description: Use when Codex needs to discover Citizens Advice Bureau NZ public client-enquiry evidence, CABNET source availability, advice category taxonomy, or report-backed enquiry trend caveats for New Zealand social-need analysis; wraps keyless cab.org.nz and data.govt.nz discovery and reports explicit blocked states when aggregated CABNET counts are not publicly exported.
---

# CAB CABNET NZ

## Overview

Use this read-only CLI to inspect public Citizens Advice Bureau NZ material
related to CABNET client-enquiry evidence. CAB has not exposed an unauthenticated
structured export of national CABNET enquiry counts; the skill makes that
blocked state explicit instead of inventing data.

The CLI uses only Python 3 standard library modules and keyless public
endpoints on `cab.org.nz` and `catalogue.data.govt.nz`.

## Commands

Run commands from this skill directory with `python3 scripts/cli.py`.
Every command accepts `--json`.

- `sources --query "welfare report" --json` discovers public CAB pages/reports,
  checks data.govt.nz, and confirms unauthenticated CABNET reporting endpoints
  are forbidden.
- `categories --query tenancy --json` returns the public CAB website advice
  taxonomy from `assets/data/categories.json`. This is not a confirmed CABNET
  enquiry taxonomy or enquiry volume table.
- `enquiries --year 2025 [--category benefits] --json` returns an explicit
  `structured_export_unavailable` blocked state because no public machine-readable
  CABNET enquiry-count export is reachable.
- `trends --category "food assistance" --json` returns report-backed trend
  caveats where a public CAB spotlight report discusses that category, but does
  not fabricate chart values that are only visible in PDFs/images.

## Examples

```bash
python3 scripts/cli.py sources --query "welfare report" --json
python3 scripts/cli.py categories --query tenancy --json
python3 scripts/cli.py enquiries --year 2025 --category benefits --json
python3 scripts/cli.py trends --category "budgeting and debt" --json
```

## Notes

- Use `sources` first when a user asks whether CABNET data is public.
- Treat `categories` counts as article counts in CAB's public rights/advice
  website, not client enquiry counts.
- If CAB later publishes CSV/XLSX/JSON enquiry exports, update
  `scripts/cli.py` to parse that export directly and revise
  `references/api-notes.md`.
- Source and format details are in `references/api-notes.md`.
- Run `python3 scripts/smoke_test.py` for the live smoke test.
