---
name: energy-hardship-nz
description: Query New Zealand energy-hardship evidence from MBIE energy-hardship measure reports, Stats NZ Household Expenditure Statistics household energy and electricity expenditure tables, and Electricity Authority disconnection dashboard/source metadata. Use for NZ energy poverty, electricity affordability, domestic-energy burden, 2M or 10 percent hardship proxy research, HES energy expenditure, MBIE five hardship measures, and disconnections for non-payment caveats.
---

# Energy Hardship NZ

## Overview

Read-only CLI for repeatable access to public New Zealand energy-hardship
sources. It uses Python 3 standard library only, no API key, no browser, and no
cache. It prefers public CSV/HTML/source metadata and returns explicit
`blocked` or `partial` states where the public source is an XLSX/PDF/dashboard
that cannot be fully parsed without dependencies or browser context.

## Commands

Run commands through `scripts/cli.py`. Every command accepts `--json`.

| Command | Purpose |
| --- | --- |
| `datasets` | List MBIE, Stats NZ HES, and Electricity Authority source releases and access status |
| `measures --year-ended YYYY` | Return MBIE national five-measure snapshot where available |
| `burden --breakdown income-decile|income-quintile --year YYYY` | Return feasible HES household energy/electricity expenditure data and explain unavailable income breakdowns |
| `disconnections --from YYYY-MM --to YYYY-MM` | Return EA disconnection dashboard/source metadata, or counts if a public machine feed is later found |
| `sources` | Print detailed source URLs, parsing constraints, and caveats |

## Examples

```bash
python3 scripts/cli.py datasets --json
python3 scripts/cli.py measures --year-ended 2024 --json
python3 scripts/cli.py burden --breakdown income-quintile --year 2023 --json
python3 scripts/cli.py disconnections --from 2021-10 --to 2021-12 --json
python3 scripts/cli.py sources
```

## Notes

- MBIE's current public page identifies the December 2025 report covering the
  year ended June 2024 and its XLSX workbook. Some environments receive a 403
  from MBIE's direct HTML/document URLs; the CLI reports that as a source access
  block and still returns documented 2024 national summary measures.
- Stats NZ's year ended June 2023 HES release provides a ZIP of CSV data and an
  XLSX codebook. The CLI includes a small stdlib XLSX reader only for simple
  code-table cells.
- The HES public CSV used here has national weekly expenditure for electricity,
  gas, and other domestic fuels, but not a public income-decile/quintile burden
  table. The `burden` command labels that limitation directly.
- Electricity Authority publishes the disconnections dashboard as a Sigma embed
  and documents public Azure Blob dataset access. The current disconnection
  folder is metadata/PDF-only for this CLI's stdlib parser.
- Source detail, confidence interval caveats, and workbook constraints are in
  `references/api-notes.md`.
- Run `python3 scripts/smoke_test.py` to verify the live data path.

## Resources

- CLI: `scripts/cli.py`
- Smoke test: `scripts/smoke_test.py`
- Source notes: `references/api-notes.md`
