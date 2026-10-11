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
2. Use `datasets --gauge AUCT` to see which year and sensor pairs exist. Sensors `40` and `41` are both published for Auckland; do not treat them as interchangeable. Scott Base (`SCOT`) and Cape Roberts (`ROBT`) publish sensor `00`.
3. Use `files` to page the daily archive, then `readings` for the daily zip named by `--date`. A finished year can also list one annual zip, a day-of-year zip such as `AUCT_40_2009_085-365.zip`, or a month zip such as `SCOT_00_2026_01-03.zip`. Those bundles are labeled in `archive_bundles` and are not downloaded.
4. Pass `--json` for the `meta` / `results` envelope. Read [references/api-notes.md](references/api-notes.md) before interpreting a height or a date.

## Commands

```bash
python3 skills/linz-tide-gauges-nz/scripts/cli.py gauges
python3 skills/linz-tide-gauges-nz/scripts/cli.py datasets --gauge AUCT --json
python3 skills/linz-tide-gauges-nz/scripts/cli.py files --gauge AUCT --year 2026 --sensor 40 --limit 20 --json
python3 skills/linz-tide-gauges-nz/scripts/cli.py readings --gauge AUCT --date 2026-01-01 --sensor 40 --limit 60 --json
```

`--date` selects the daily zip whose filename day-of-year is that calendar date. It does not join the previous or next zip into one civil day. For every gauge except Scott Base, the CSV clock is UTC, and a published file may also contain the adjacent UTC date. `observed_at` is copied from the CSV. Scott Base gauge text labels the same field as NZST, so those stamps use a fixed UTC+12 offset and are not rewritten as Zulu. `--limit` defaults to 60 readings or 20 files. A published file with no rows on the requested page still reports `matched_count`. A gauge, dataset, or filename date that LINZ does not publish returns `query_status: no_match` and an empty `results` array. Timeouts, blocks, and non-JSON outages are errors with empty `results`, not matches.

Heights are copied as decimal strings. They are unquality-controlled metres above gauge zero (TG0), not chart datum and not tide predictions. Sensor 40 and sensor 41 are separate series. On 2026-01-01 at 00:00 UTC, Auckland sensor 40 reads 5.002 m and sensor 41 reads 4.777 m. Cape Roberts daily rows may also carry the gauge text's sample count, sea-water temperature, and atmospheric pressure. A raw CSV fixture has no sensor column, so its sensor value is only the requested label and `sensor_verified` is false. File `modified` dates are archive dates, not observation times. `latest_data` on `readings` is the last minute in that daily file, which can fall on the adjacent calendar date. A published file can contain fewer than 1,440 minutes.

## Checks

Parser fixtures and adversarial cases live under `tests/fixtures/` and `scripts/test_contract.py`. `scripts/smoke_test.py` repeats those checks, then makes a few bounded live requests. Licence, clock, and sensor limits are in `references/api-notes.md` and `references/source-notes.md`.
