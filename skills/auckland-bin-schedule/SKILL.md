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
  thecolab.health: "healthy"
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
2. Use `lookup` (or the legacy `--list`) to inspect scored, numbered candidates when the address is unresolved
3. Repeat the address query with `schedule --pick N` to explicitly select a candidate, or use `--property-id` for a known Council property/rating id
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
- `--limit <N>` — address lookup result limit (1–20, the Council cap); a full page requires refinement
- `--pick <N>` — explicitly select the 1-based candidate number from the ranked list; schedule only
- `--json` — emit JSON

Examples:

```bash
python3 skills/auckland-bin-schedule/scripts/cli.py --list "12 Tawa Road Onehunga"
python3 skills/auckland-bin-schedule/scripts/cli.py "12 Tawa Road Onehunga"
python3 skills/auckland-bin-schedule/scripts/cli.py "12 Tawa Road Onehunga" --json
python3 skills/auckland-bin-schedule/scripts/cli.py --property-id 12343300679 --json
python3 skills/auckland-bin-schedule/scripts/cli.py lookup "1 Dominion Road, Mount Eden" --json
python3 skills/auckland-bin-schedule/scripts/cli.py schedule "1 Dominion Road, Mount Eden" --pick 1 --json
```

## Resources

- CLI entrypoint: `scripts/cli.py`
- Deterministic matching/CLI tests: `scripts/test_contract.py`
- Live smoke test: `scripts/smoke_test.py`
- Fixtures: `tests/fixtures/address-cases.json` (explicitly synthetic regressions) and
  `tests/fixtures/property-search.json` (synthetic API items); `tests/fixtures/blocked-live.html` (existing HTTP 406 response)
- API and stability notes: `references/api-notes.md`

## Notes

- No API key, username, password, cookie, or private credential is required
- The CLI fetches the current public bearer token from Auckland Council's collection-day page at runtime
- Treat dates as live current Council snapshots, not historical facts
- Some properties show private service or property-manager messages instead of Council collection dates
- Auto-selection requires an exact number and suffix, street name and type, and an explicitly
  supplied suburb. Common street abbreviations, Mt/Mount and leading St/Saint names are normalised.
  Parsed queries sent upstream omit commas, city and postcode. Units remain
  distinct; an unspecified unit requires confirmation even if one unit is returned.
- Multiple exact candidates, incomplete addresses, no exact match, and a full result page return
  `matches` and `exact_matches` with `status` (`ambiguous`, `no_exact_match`, or `search_limit`).
  The CLI fetches no schedule in these states unless `--pick N` explicitly selects a candidate.
  Refine the address, choose a numbered candidate or use a confirmed property id.
- Candidates include `candidate_number`, `match_score` (0–100), `match_components` and
  `exact_match` (membership in `exact_matches`) and `auto_selectable` (full component equality,
  including an explicit suburb and matching unit). Automatic selection also requires a unique
  exact candidate and a non-full result page. Scores are component equality weights, not probabilities.
  See API notes for omitted suburb/unit matching.
  Picks can select a non-exact candidate and return `status: picked`; inspect its full address.
  Repeat the same query and limit when picking; live upstream changes can change the list.
- The previous address-only and `--list` invocations remain supported.
- JSON uses `meta` provenance and a `results` array. Candidate `status`, `matches` and
  `exact_matches` sit in `results[0]`; errors use empty `results` and `error: {code, type, message}`.
  Council data licence is unconfirmed and omitted; collection dates are future service dates,
  not data update dates.
