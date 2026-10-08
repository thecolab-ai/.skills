---
name: auckland-bin-schedule
description: "Query Auckland Council rubbish, recycling, and food scraps collection days for Auckland properties using the public collection-day website flow. Use when the task involves Auckland bin day, rubbish/recycling schedules, food scraps collection, address lookup, or property-id based collection checks. No account login required."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "public-data"
  thecolab.source_owner: "Auckland Council"
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
  thecolab.source_url: "https://www.aucklandcouncil.govt.nz/en/rubbish-recycling/rubbish-recycling-collections/rubbish-recycling-collection-days.html"
  thecolab.allowed_domains: "experience.aucklandcouncil.govt.nz,www.aucklandcouncil.govt.nz"
  thecolab.last_verified: "2026-10-08"
  thecolab.health: "gated"
  thecolab.maintainer: "@adam91holt"
---

# Auckland Bin Schedule

## Goal

Query live Auckland Council household and commercial rubbish, recycling, and food scraps collection schedules through a small deterministic CLI with human-readable and JSON output.

## Use this when

- A user asks when Auckland bins go out
- A user wants the next rubbish, recycling, or food scraps collection date for an Auckland address
- A user needs to list matching Auckland Council properties for an address query
- A workflow needs machine-readable Auckland Council collection schedule data

## Do not use this for

- Councils outside Auckland
- Private collection schedules not shown on Auckland Council's page
- Historical collection claims beyond the current dates shown by Council
- Changing Council services, lodging requests, or account/property actions

## Preferred workflow

1. Run `scripts/cli.py schedule` with the exact address when known
2. Use `lookup` (or the legacy `--list`) to inspect candidates when the address is unresolved
3. Use `--property-id` when an Auckland Council property/rating id is already known
4. Use `--json` for agent chaining, comparisons, alerts, or structured reports
5. Summarise household collection first unless the user asks about commercial collection
6. Mention that public holidays can shift collection dates and the CLI reflects the current Council page

## CLI

Run with:

```bash
python3 skills/auckland-bin-schedule/scripts/cli.py schedule <address...> [flags]
python3 skills/auckland-bin-schedule/scripts/cli.py lookup <address...> --json
```

### Commands / flags

- `<address...>` — Auckland property address to search, e.g. `12 Tawa Road Onehunga`
- `--list` — list matching properties only
- `--property-id <id>` — fetch a known Auckland Council property/rating id directly
- `--limit <N>` — address lookup result limit (1–100); a full page requires refinement
- `--json` — emit JSON

Examples:

```bash
python3 skills/auckland-bin-schedule/scripts/cli.py --list "12 Tawa Road Onehunga"
python3 skills/auckland-bin-schedule/scripts/cli.py "12 Tawa Road Onehunga"
python3 skills/auckland-bin-schedule/scripts/cli.py "12 Tawa Road Onehunga" --json
python3 skills/auckland-bin-schedule/scripts/cli.py --property-id 12343300679 --json
```

## Resources

- CLI entrypoint: `scripts/cli.py`
- Deterministic matching/CLI tests: `scripts/test_contract.py`
- Live smoke test: `scripts/smoke_test.py`
- Fixtures: `tests/fixtures/address-cases.json` (explicitly synthetic regressions) and
  `tests/fixtures/blocked-live.html` (real HTTP 406 response)
- API and stability notes: `references/api-notes.md`

## Notes

- No API key, username, password, cookie, or private credential is required
- The CLI fetches the current public bearer token from Auckland Council's collection-day page at runtime
- Treat dates as live current Council snapshots, not historical facts
- Some properties show private service or property-manager messages instead of Council collection dates
- Auto-selection requires an exact number and suffix, street name and type, and suburb when
  supplied. Common street abbreviations and Mt/Mount in suburbs are normalised. Units remain
  distinct; an unspecified unit requires confirmation even if one unit is returned.
- Multiple exact candidates, incomplete addresses, no exact match, and a full result page return
  `matches` and `exact_matches` with `status` (`ambiguous`, `no_exact_match`, or `search_limit`).
  The CLI fetches no schedule in these states. Refine the address or use a confirmed property id.
- The previous address-only and `--list` invocations remain supported.
- JSON schedules, candidate results and errors include source provenance. Council's data licence
  is unconfirmed (`licence: null`); collection dates are future service dates, not data update dates.
