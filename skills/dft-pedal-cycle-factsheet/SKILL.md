---
name: dft-pedal-cycle-factsheet
description: "Read the Department for Transport 2025 Great Britain pedal-cycle road casualty factsheet tables. Use when the task needs the official pedal-cycle ODS worksheets, casualty counts, rates, percentages, units, or missing-data shorthand from that factsheet. Resolves the workbook from the GOV.UK release and does not fetch pedestrian, motorcycle, or e-scooter factsheets."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "transport"
  thecolab.source_owner: "Department for Transport"
  thecolab.source_type: "official"
  thecolab.auth: "none"
  thecolab.access_mode: "public-download"
  thecolab.data_class: "public"
  thecolab.writes: "false"
  thecolab.browser: "false"
  thecolab.risk: "low"
  thecolab.cache_ttl: "none"
  thecolab.schema_version: "1"
  thecolab.skill_type: "public-download"
  thecolab.pack: "nz-public-data"
  thecolab.source_url: "https://www.gov.uk/government/statistics/reported-road-casualties-great-britain-vulnerable-road-user-factsheets/reported-road-casualties-great-britain-pedal-cycle-factsheet-2025"
  thecolab.allowed_domains: "www.gov.uk,assets.publishing.service.gov.uk"
  thecolab.last_verified: "2026-10-11"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# DfT pedal-cycle factsheet

Read the official 2025 Great Britain pedal-cycle casualty workbook. The command
resolves the current ODS from the GOV.UK release, then lists worksheet titles
and a bounded preview. It does not download pedestrian, motorcycle, or
e-scooter factsheets.

Use `scripts/cli.py`. Every data command accepts `--json`. Read
`references/source-notes.md` for units, missing-data shorthand, licence, and
error codes. Parser fixtures live in `tests/fixtures/`. Run
`scripts/test_contract.py` and `scripts/smoke_test.py`.

| Command | Behaviour |
|---|---|
| `tables` | One factsheet page, the parent statistics release only when that page does not already link the ODS, then one pedal-cycle workbook |
| `--sheet NAME` | Keep every worksheet title, and preview only the named sheet |
| `--limit N` | Preview at most N numeric cells and N semantic cells. N is 1 to 100; the default is 25 |
| `--fixture PATH` | Parse a local ODS and do not use the network |

```bash
python3 scripts/cli.py tables --json
python3 scripts/cli.py tables --sheet Table_1 --limit 8 --json
python3 scripts/cli.py tables --fixture tests/fixtures/pedal-cycle-sample.ods --json
```

JSON uses `meta` and `results`. `meta.source_url` is the resolved ODS URL for a
live read and the factsheet page for a fixture. `meta.latest_data` is the
table-of-contents first-publication date when every row states the same date.
Numeric `value` is the ODS decimal token. `display` is the formatted text,
which may be rounded or use thousands separators. Blank cells are omitted.
`[x]` is missing data, `[note N]` is a note marker, and a trailing `(unit)` on
a column header is that column's unit.
