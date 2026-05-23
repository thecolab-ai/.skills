---
name: nz-ferries
description: Query public NZ ferry operator sailing schedules, fare/availability snapshots, and service alerts through a lightweight read-only CLI. Use for Cook Strait Interislander/Bluebridge sailings, SeaLink Waiheke/Great Barrier vehicle ferries, Fullers360/AT Metro Auckland ferry schedules and alerts, and NZ ferry operator alerts. Does not duplicate Auckland Transport GTFS live vehicle tracking; use at-transport for AT Metro ferry real-time positions.
---

# NZ Ferries

## Goal

Query live public ferry schedule and alert surfaces across major NZ ferry operators through a small deterministic CLI with human-readable and JSON output, without browser automation, login, booking, or payment.

This skill is deliberately separate from `at-transport`:

- `nz-ferries` = sailing schedules, fare snapshots, availability signals, and service alerts across NZ ferry operators
- `at-transport` = live Auckland Metro public transport data, including ferry `route_type=4` vehicle positions and stop departures

## Use this when

- A user asks for Cook Strait ferry sailings between Wellington and Picton
- A user wants a combined Interislander + Bluebridge view for a travel date
- A user asks for SeaLink Waiheke Island or Great Barrier Island vehicle/passenger ferry times
- A user asks for Fullers360/AT Metro Auckland ferry schedules such as Devonport, Waiheke, Half Moon Bay, Hobsonville, Bayswater, Birkenhead, Northcote, Pine Harbour, West Harbour, or Rangitoto
- A user asks for the next Devonport ferry, the last Waiheke ferry tonight, or current Auckland ferry cancellations
- A user wants current ferry operator service alerts, reminders, delays, cancellations, or weather notices
- A workflow needs lightweight machine-readable ferry sailing data from public operator surfaces

## Do not use this for

- Booking, payment, checkout, login, account, ticket, refund, or booking-management actions
- Live Auckland Transport ferry vehicle positions or full AT public transport stop-departure workflows; use `at-transport`
- High-volume scraping or building a historical ferry timetable dataset
- Fullers360/AT Metro ferry real-time vehicle tracking; that is already covered by AT GTFS-RT in `at-transport`
- Guaranteed availability claims; public schedule/booking-slot surfaces can change after the CLI query

## Preferred workflow

1. Run `scripts/cli.py` with the narrowest subcommand that answers the task
2. Use `cook-strait` for Wellington/Picton planning because it combines Interislander and Bluebridge
3. Use `sailings <route> --operator <operator>` when a specific ferry company is known
4. Use `next <route>` for the next upcoming sailings from the current NZ time
5. Use `alerts` before presenting travel advice for a date-sensitive trip
6. Use `--json` for agent chaining, comparisons, or structured reports
7. Mention the source operator and that results are public read-only snapshots

## CLI

Run with:

```bash
python3 skills/nz-ferries/scripts/cli.py <command> [flags]
```

## Commands

- `operators [--json]` - list supported ferry operators and coverage
- `routes [--operator OPERATOR] [--json]` - list route IDs and aliases
- `sailings <route> [--date YYYY-MM-DD] [--operator OPERATOR] [--json]` - sailings on a date
- `next <route> [--operator OPERATOR] [--limit N] [--json]` - next few upcoming sailings from now
- `alerts [--operator OPERATOR] [--json]` - current public service alerts/reminders
- `cook-strait [--date YYYY-MM-DD] [--direction wellington-picton|picton-wellington|both] [--operator OPERATOR] [--json]` - combined Cook Strait view

## Examples

```bash
python3 skills/nz-ferries/scripts/cli.py operators
python3 skills/nz-ferries/scripts/cli.py routes --operator sealink --json
python3 skills/nz-ferries/scripts/cli.py cook-strait --date 2026-05-24 --json
python3 skills/nz-ferries/scripts/cli.py sailings wellington-picton --operator interislander --date 2026-05-24
python3 skills/nz-ferries/scripts/cli.py sailings wellington-picton --operator bluebridge --date 2026-05-24 --json
python3 skills/nz-ferries/scripts/cli.py sailings auckland-waiheke --operator sealink --date 2026-05-24
python3 skills/nz-ferries/scripts/cli.py sailings auckland-devonport --operator fullers --date 2026-05-24
python3 skills/nz-ferries/scripts/cli.py sailings auckland-waiheke --operator fullers --date 2026-05-24 --json
python3 skills/nz-ferries/scripts/cli.py next auckland-devonport --operator fullers
python3 skills/nz-ferries/scripts/cli.py next auckland-waiheke --operator sealink --limit 5
python3 skills/nz-ferries/scripts/cli.py alerts --operator fullers
python3 skills/nz-ferries/scripts/cli.py alerts --json
```

## Notes

- Upstream sources: SeaLink (`sealink.co.nz`), Interislander/KiwiRail (`interislander.co.nz`), Bluebridge/StraitNZ (`bluebridge.co.nz`), Fullers360 (`fullers.co.nz` and `pim-mobile.fullers.co.nz` for discovery context), and Auckland Transport public GTFS/GTFS-RT for Fullers/AT Metro ferry schedules and alerts.
- SeaLink uses a public schedule endpoint that returns sailing times, ferry names, availability/status, remaining passenger spaces, and fare snapshots for a query basket. The CLI uses one car+driver and one adult only to expose public fare/availability fields; it does not create or mutate bookings.
- Interislander uses the public ferry timetable page and public disruption endpoint. The timetable page publishes departure times and says crossings take about 3.5 hours, so arrival times are estimated from that duration.
- Bluebridge uses the public timetable and service-alert pages. The CLI filters known day restrictions such as "not available on weekends" from the published timetable notes.
- Fullers360 app and website timetable endpoints were reverse-engineered, but direct stdlib requests hit Radware/hCaptcha validation. The shipped Fullers implementation uses AT's public static GTFS zip for scheduled sailings and AT GTFS-RT service alerts for cancellations and disruptions.
- Fullers fare snapshots are not implemented because the Fullers website/app fare/timetable fragments are browser-gated from direct CLI fetches.
- No operator account cookie, browser session, booking mutation, or payment action is required. The AT alert feed uses a public AT API subscription key with an `AT_API_KEY` environment override.
- Endpoint shapes can change without notice because these are public website surfaces rather than official stable APIs.
- API and stability notes: `references/api-notes.md`
- CLI entrypoint: `scripts/cli.py`
