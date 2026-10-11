---
name: port-of-auckland
description: "Fetch Port of Auckland expected vessel arrivals and live truck turn times for freight demand and congestion analysis. Discover related keyless NZ port sources, fetch Tauranga expected arrivals and road queues, and summarise current port activity."
license: MIT
compatibility: "Requires Python 3.10+ with Pacific/Auckland timezone data and network access for live data; stdlib only"
metadata:
  thecolab.category: "transport"
  thecolab.source_owner: "Port of Auckland Ltd; Port of Tauranga Limited"
  thecolab.source_type: "official"
  thecolab.auth: "none"
  thecolab.access_mode: "public CSV download and bounded read-only HTML"
  thecolab.data_class: "public"
  thecolab.writes: "false"
  thecolab.browser: "false"
  thecolab.risk: "medium"
  thecolab.cache_ttl: "5m default; 1h maximum; robots 24h"
  thecolab.schema_version: "1"
  thecolab.skill_type: "html-readonly"
  thecolab.pack: "nz-public-data"
  thecolab.source_url: "https://poal.co.nz/operations/schedules/arrivals/download"
  thecolab.allowed_domains: "poal.co.nz,www.poal.co.nz,www.port-tauranga.co.nz"
  thecolab.last_verified: "2026-10-08"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# Auckland and Tauranga port snapshots

Use for freight-demand context at Auckland and Tauranga: expected vessel calls,
truck turnaround snapshots and road queue counts. These operational signals do not establish
truck counts, cargo tonnage or causation of road congestion.

Run from the repository root:

```bash
python3 skills/port-of-auckland/scripts/cli.py sources --json
python3 skills/port-of-auckland/scripts/cli.py arrivals --from 2026-10-08 --to 2026-10-16 --vessel maersk --json
python3 skills/port-of-auckland/scripts/cli.py truck-turns --from 2026-10-08 --to 2026-10-08 --json
python3 skills/port-of-auckland/scripts/cli.py summary --json
python3 skills/port-of-auckland/scripts/cli.py arrivals --port tauranga --json
python3 skills/port-of-auckland/scripts/cli.py truck-turns --port tauranga --json
python3 skills/port-of-auckland/scripts/cli.py summary --port tauranga --max-age 0 --json
python3 scripts/run_skill.py port-of-auckland arrivals --vessel maersk
```

1. Use `sources` to find exact catalogue URLs and supported fetch commands. It reads
   the bundled registry; entries without a fetch command are discovery links only.
2. Fetch `arrivals` for the current expected-arrivals list. `--vessel` matches a
   case-insensitive substring. Each row is a vessel call; keep berth-shift rows.
3. Fetch `truck-turns` for the published snapshot. Auckland returns turn durations
   in seconds with rolling-window and observation times. Tauranga returns the
   published road queue count; it has no numeric turn duration in this HTML.
4. Use `summary` for call counts, distinct vessel names, counts by NZ date, and the
   truck snapshot. Each of its two records retains its own source provenance.

`--from` and `--to` are inclusive YYYY-MM-DD NZ calendar dates, filtered locally
on arrival or truck observation date. They filter the **current snapshot**; they
cannot request historical data. A date range without observations returns an empty
`results` array. `--port` defaults to `auckland`. No source supplies coordinates,
so spatial filtering and GeoJSON are not offered.

Data commands emit `meta` and `results` with `--json`; `scripts/provenance.py`
provides the shared envelope. Unknown data licences are omitted. Auckland arrivals
have no source update timestamp: do not treat future ETAs as `latest_data`.
Truck and Tauranga timestamps are explained in [source notes](references/source-notes.md).

Successful snapshots cache under the skill's ignored `.cache/` directory for
300 seconds. `--max-age 0` refreshes; callers may select 0–3600 seconds. Cached
results retain the original `retrieved_at`; expired results are never served
on upstream failure. Robots rules cache for up to 24 hours independently.

Every network request has a 10-second timeout and a 4 MB body bound, and is limited
to declared hosts. The CLI checks robots.txt before fetching a fresh feed; HTTP 404
means no restrictions are published. Other access failures remain errors. Respect
source terms and rate limits; do not bulk poll, scrape disallowed paths, fetch
camera images, automate exports or bypass access blocks. Public access does not
establish a reuse licence.

Validate with `scripts/test_contract.py` and run `scripts/smoke_test.py` for the
synthetic parser fixtures and four bounded live probes. Network outages are skips;
parser or schema changes fail. See [source notes](references/source-notes.md) and
[the source registry](references/sources.json) for exact URLs and limitations.
