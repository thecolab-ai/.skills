---
name: jetstar-flights
description: "Search public Jetstar New Zealand one-way fare-cache flight availability through a no-login Node CLI. Use when the task involves Jetstar route/date fare snapshots, low-fare availability, flight IDs, prices, or machine-readable current Jetstar availability. Read-only; no login, Club Jetstar account, booking, seat hold, payment, manage-booking, or checkout actions."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "transport"
  thecolab.source_owner: "Jetstar"
  thecolab.source_type: "commercial"
  thecolab.auth: "none"
  thecolab.access_mode: "html-readonly"
  thecolab.data_class: "public"
  thecolab.writes: "false"
  thecolab.browser: "false"
  thecolab.risk: "low"
  thecolab.cache_ttl: "24h"
  thecolab.schema_version: "1"
  thecolab.skill_type: "html-readonly"
  thecolab.pack: "nz-commercial-web"
  thecolab.source_url: "https://www.jetstar.com/nz/en/home"
  thecolab.allowed_domains: "digitalapi.jetstar.com,www.jetstar.com"
  thecolab.last_verified: "2026-07-19"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
  thecolab.javascript_exception: "legacy-cli-wrapped-by-python-pending-port"
---

# Jetstar Flights

## Goal

Query live public Jetstar fare-cache availability through a deterministic CLI with human-readable and JSON output.

## Use this when

- A user asks to search current Jetstar flights by origin, destination, and date
- A user wants a public fare snapshot for Jetstar NZ, domestic, or trans-Tasman routes
- A workflow needs low-fare availability, flight IDs, departure/arrival times, or sold-out flags
- An agent is comparing public airline availability without logging in or holding seats

## Do not use this for

- Booking, payment, seat selection, bundle selection, checkout, Club Jetstar login, manage-booking, refund/change actions, or passenger details
- Private/authenticated booking data or member-only account data
- High-volume scraping, fare-history warehousing, or bypassing Jetstar controls
- Claims about final payable totals beyond the public fare-cache snapshot returned by Jetstar

## Preferred workflow

1. Ask for or infer IATA airport codes and a specific departure date.
2. Run `scripts/cli.mjs search ORIGIN DESTINATION YYYY-MM-DD` with a narrow `--days` window.
3. Use `--limit` for concise human output or `--json` for agent chaining.
4. Treat results as live fare-cache snapshots: accuracy and prices can change quickly.
5. Send users to Jetstar if they want to complete a booking themselves.

## CLI

Run from the repository root with Node.js 18+:

```bash
node skills/jetstar-flights/scripts/cli.mjs search <origin> <destination> <date> [flags]
```

Examples:

```bash
node skills/jetstar-flights/scripts/cli.mjs search AKL WLG 2026-07-13 --days 7
node skills/jetstar-flights/scripts/cli.mjs search AKL CHC 2026-07-13 --json
node skills/jetstar-flights/scripts/cli.mjs search WLG AKL 2026-08-04 --adults 2 --limit 5
```

### Flags

- `--days N` — number of days to search from the start date, default `1`, max `31`
- `--adults N` — adult passenger count used for fare-cache lookup, default `1`
- `--limit N` — max rows in human output
- `--json` — emit machine-readable JSON

## Resources

- CLI entrypoint: `scripts/cli.mjs`
- Live smoke test: `scripts/smoke_test.sh`
- API/source notes: `references/api-notes.md`

## Notes

- No API key, OAuth app credentials, username, password, cookie, browser automation, or Playwright dependency is required for supported read-only commands.
- The CLI calls Jetstar's public fare-cache endpoint using browser-compatible headers and the public `en-NZ` culture.
- The CLI deliberately stops at fare-cache search results; it does not select bundles, hold seats, create a cart, or start checkout.
- Keep usage narrow and respectful.
