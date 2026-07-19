---
name: airnz-flights
description: "Search public Air New Zealand fare snapshots and timetable fallback data through a lightweight no-login CLI. Use when the task involves Air NZ route/date fare snapshots, fare products, flight numbers, departure/arrival times, duration, stops, or machine-readable current flight data. Optional --browser mode uses CloakBrowser when installed and returns cloakbrowser_not_installed when unavailable. Read-only; no login, Airpoints, seat holds, booking, payment, manage-booking, or checkout actions."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "transport"
  thecolab.source_owner: "Air New Zealand"
  thecolab.source_type: "commercial"
  thecolab.auth: "none"
  thecolab.access_mode: "html-readonly"
  thecolab.data_class: "public"
  thecolab.writes: "false"
  thecolab.browser: "true"
  thecolab.risk: "medium"
  thecolab.cache_ttl: "24h"
  thecolab.schema_version: "1"
  thecolab.skill_type: "html-readonly"
  thecolab.pack: "nz-commercial-web"
  thecolab.source_url: "https://www.airnewzealand.co.nz/flight-schedules"
  thecolab.allowed_domains: "flightbookings.airnewzealand.co.nz,www.airnewzealand.co.nz"
  thecolab.last_verified: "2026-07-19"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# Air New Zealand Flights

## Goal

Query live public Air New Zealand fare snapshots when the anonymous browser-style search is accepted, with a public timetable fallback when Air NZ returns request-auth/CAPTCHA.

## Use this when

- A user asks to search current Air New Zealand flights by origin, destination, and date
- A user wants a public timetable snapshot for NZ domestic or Air NZ-served routes
- A workflow needs flight times, flight numbers, duration, stops, or booking-search handoff URLs
- An agent is comparing public airline availability without logging in or holding seats

## Do not use this for

- Booking, payment, seat selection, fare holds, checkout, Airpoints login, manage-booking, refund/change actions, or passenger details
- Private/authenticated booking data
- High-volume scraping, fare-history warehousing, or bypassing Air NZ controls
- Claims about final payable totals; prices, when returned, are pre-checkout fare snapshots only

## Preferred workflow

1. Ask for or infer IATA airport codes and a specific departure date.
2. Run `scripts/cli.py ORIGIN DESTINATION YYYY-MM-DD` with the narrowest useful query.
3. Prefer `--browser` on headless servers or anti-bot-sensitive workflows when CloakBrowser is installed; if it is not installed, the CLI returns `cloakbrowser_not_installed` so the agent can recommend installation.
4. Use `--direct` if only direct services are useful.
5. Use `--limit` for concise human output or `--json` for agent chaining.
6. Treat results as live snapshots: fares/schedules can change without notice.
7. If JSON includes `fare_search_blocked: true`, Air NZ returned request-auth/CAPTCHA and the CLI has fallen back to schedules only.
8. Send users to the returned booking search URL if they want to complete a booking themselves.

## CLI

Run from the repository root:

```bash
python3 skills/airnz-flights/scripts/cli.py <origin> <destination> <date> [flags]
```

Examples:

```bash
python3 skills/airnz-flights/scripts/cli.py AKL WLG 2026-07-13 --limit 5
python3 skills/airnz-flights/scripts/cli.py AKL WLG 2026-07-13 --browser --limit 5
python3 skills/airnz-flights/scripts/cli.py AKL CHC 2026-07-13 --browser --json
python3 skills/airnz-flights/scripts/cli.py WLG ZQN 2026-08-04 --direct
```

### Flags

- `--direct` — direct flights only
- `--adults N` — adult passenger count for the fare-search attempt
- `--browser` — use optional CloakBrowser headless mode; if unavailable, returns `cloakbrowser_not_installed` for agents to surface as an installation recommendation
- `--limit N` — max rows in human output
- `--json` — emit machine-readable JSON

## Resources

- CLI entrypoint: `scripts/cli.py`
- Live smoke test: `scripts/smoke_test.sh`
- API/source notes: `references/api-notes.md`

## Notes

- Python Playwright is required for the timetable fallback because Air NZ's same public timetable feed can return empty results to bare non-browser clients while returning the public schedule in a normal browser context.
- The CLI first attempts the browser-sniffed anonymous fare-search flow (`/vbook/ajax/bui/flights/search` → `selectitinerary`) and parses embedded `legOptions` prices when Air NZ accepts the request.
- If Air NZ returns request-auth/CAPTCHA, the CLI falls back to `/feeds/flight-timetables` and marks `fare_search_blocked: true`.
- `--browser` is optional, not mandatory. It imports CloakBrowser only when requested, so normal validation/smoke runs still work on clean hosts.
- If `--browser --json` is requested and CloakBrowser is missing, the CLI returns a machine-readable `cloakbrowser_not_installed` error plus an installation recommendation instead of pretending the browser path ran.
- The CLI deliberately stops before fare selection; it does not create a booking session, hold seats, or progress to checkout.
- Keep usage narrow and respectful.
