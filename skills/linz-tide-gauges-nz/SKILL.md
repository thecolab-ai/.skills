---
name: linz-tide-gauges-nz
description: "Query official LINZ tide-gauge sea-level observations. Use for Auckland Devonport (AUCT) and other published LINZ gauge codes, daily UTC minute heights, sensor datasets, and file listings. Not tide predictions."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "environment"
  thecolab.source_owner: "Toitū Te Whenua Land Information New Zealand (LINZ)"
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
  thecolab.source_url: "https://sealevel-data.linz.govt.nz/index.html?tidegauge=AUCT"
  thecolab.allowed_domains: "sealevel-data.linz.govt.nz"
  thecolab.last_verified: "2026-10-11"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# LINZ tide gauges

Read published LINZ tide-gauge observations from `scripts/cli.py`. The primary case is Auckland Devonport Naval Base, gauge `AUCT`. The same official list also publishes other gauge codes. This is not the LINZ tide-prediction service.

## Workflow

1. Use `gauges` to confirm a code is published.
2. Use `datasets --gauge AUCT` to see which year and sensor pairs exist. Sensors `40` and `41` are both published for Auckland; do not treat them as interchangeable.
3. Use `files` to page the daily archive, then `readings` for one UTC day.
4. Pass `--json` for the `meta` / `results` envelope. Read [references/api-notes.md](references/api-notes.md) before interpreting a height or a date.

## Commands

```bash
python3 skills/linz-tide-gauges-nz/scripts/cli.py gauges
python3 skills/linz-tide-gauges-nz/scripts/cli.py datasets --gauge AUCT --json
python3 skills/linz-tide-gauges-nz/scripts/cli.py files --gauge AUCT --year 2026 --sensor 40 --limit 20 --json
python3 skills/linz-tide-gauges-nz/scripts/cli.py readings --gauge AUCT --date 2026-01-01 --sensor 40 --limit 60 --json
```

`--date` is the UTC day in the daily filename and CSV, not a New Zealand local day. `--limit` defaults to 60 readings or 20 files. A published day with no rows on the requested page still reports `matched_count`. A gauge, dataset, or UTC day that LINZ does not publish returns `query_status: no_match` and an empty `results` array. Timeouts, blocks, and non-JSON outages are errors with empty `results`, not matches.

Heights are copied as decimal strings. They are unquality-controlled sensor metres. File `modified` dates are archive dates, not observation times. `latest_data` on `readings` is the last UTC minute in that daily file.

## Checks

Parser fixtures and adversarial cases live under `tests/fixtures/` and `scripts/test_contract.py`. `scripts/smoke_test.py` repeats those checks, then makes a few bounded live requests. Licence, clock, and sensor limits are in `references/api-notes.md` and `references/source-notes.md`.
