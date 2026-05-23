---
name: nz-healthpoint
description: Query Healthpoint NZ public health-service directory pages through a lightweight read-only CLI. Use when the task involves finding New Zealand pharmacies, GPs, urgent care, hospitals, dentists, specialists, locations, contact details, opening hours, or services listed on healthpoint.co.nz. Read-only; not for bookings, triage, referrals, or medical advice.
---

# Healthpoint NZ

## Goal

Query live Healthpoint NZ directory pages through a small deterministic CLI with human-readable and JSON output, without login, booking actions, browser automation, or medical advice.

## Use this when

- A user asks for a nearby or open pharmacy in New Zealand
- A user wants urgent care / Accident & Medical / A&E clinic locations
- A user asks whether a listed GP, pharmacy, dentist, or clinic appears open
- A user wants hospitals or Health NZ / Te Whatu Ora public service locations
- A user needs service contact details, addresses, opening hours, listed services, or fees from Healthpoint
- A workflow needs lightweight machine-readable Healthpoint directory data

## Do not use this for

- Emergencies, triage, diagnosis, medical advice, or deciding whether care is clinically appropriate
- Booking, cancelling, changing, or paying for appointments
- Login, patient portals, referrals, enrolment forms, prescription requests, or provider-admin actions
- ED wait times, queue lengths, or capacity claims; Healthpoint does not reliably expose current ED wait times
- Bulk scraping or republishing Healthpoint as a dataset

## Preferred workflow

1. Run `scripts/cli.py` with the narrowest subcommand that answers the task
2. Use `pharmacies --open-now` or `open-now --type pharmacy` for current open-pharmacy checks
3. Use `urgent-care --region <region>` for Accident & Urgent Medical Care providers
4. Use `search <query> --type <type> --region <region>` for named practices or service-type lookups
5. Use `practice <id>` when a result id/path/url is known and detailed hours, address, services, or fees are needed
6. Use `hospitals --region <region> --ed-only` when the user specifically asks about hospitals with listed Emergency Departments
7. Use `--json` for agent chaining, comparisons, and reports

## CLI

Run with:

```bash
python3 skills/nz-healthpoint/scripts/cli.py <command> [flags]
```

## Commands

- `categories [--json]` - list supported Healthpoint branches and regions
- `search [query] [--type pharmacy|gp|urgent-care|hospital|dentist|...] [--region REGION] [--near ADDRESS] [--lat LAT --lng LNG] [--open-now] [--open-saturday] [--open-sunday] [--open-weekends] [--limit N] [--json]` - search services or typed branch listings
- `practice <id-or-path-or-url> [--json]` - fetch one detail page with address, phone, hours, services, fees, and ED indicator where available
- `open-now [--type TYPE] [--region REGION] [--near ADDRESS] [--limit N] [--json]` - currently open services; defaults to pharmacies
- `urgent-care [--region REGION] [--near ADDRESS] [--open-now] [--limit N] [--json]` - Accident & Urgent Medical Care providers
- `pharmacies [--region REGION] [--near ADDRESS] [--open-now] [--open-late] [--limit N] [--json]` - pharmacies; `--open-late` verifies detail hours open after 9pm where available
- `hospitals [--region REGION] [--ed-only] [--limit N] [--json]` - public hospital locations, enriched from detail pages with an Emergency Department indicator

## Examples

```bash
python3 skills/nz-healthpoint/scripts/cli.py pharmacies --near "Queen Street Auckland" --open-now --limit 5 --json
python3 skills/nz-healthpoint/scripts/cli.py open-now --type pharmacy --region "Central Auckland" --limit 5
python3 skills/nz-healthpoint/scripts/cli.py urgent-care --region Wellington --json
python3 skills/nz-healthpoint/scripts/cli.py search "Thorndon Medical Centre" --json
python3 skills/nz-healthpoint/scripts/cli.py search dentist --type dentist --region Wellington --open-saturday --json
python3 skills/nz-healthpoint/scripts/cli.py hospitals --region Auckland --ed-only --json
python3 skills/nz-healthpoint/scripts/cli.py practice pharmacy/pharmacy/medicines-to-midnight --json
```

## Notes

- Safety disclaimer: For emergencies call 111. For Healthline call 0800 611 116. This skill is for finding services, NOT medical advice.
- Upstream source: Healthpoint NZ (`healthpoint.co.nz`), New Zealand's national directory of health services
- Healthpoint states that directory details are supplied by service providers; hours, fees, services, and contacts can be incomplete or stale
- `--open-now` sends Healthpoint's public `openNow=true` filter and also parses the returned opening-status text against current `Pacific/Auckland` time
- `search --open-saturday` uses Healthpoint's weekend filter where available; `--open-sunday` and `--open-weekends` pass through the matching public branch filters
- `pharmacies --open-late` uses Healthpoint's `openLate` filter, then checks detail hours for closing times after 9pm where available; Healthpoint's own open-late checkbox is broader than 9pm
- Nearby searches use Healthpoint's public `/nearme.do` geocoder and choose the best city/region text match unless exact `--lat --lng` is supplied
- Auckland is split by Healthpoint into North, East, Central, West, and South Auckland; passing `--region Auckland` searches all five subregions
- No API key, username, password, account cookie, private token, or browser session is required for implemented read-only commands
- Endpoint shapes and HTML markup can change without notice because this is an unofficial wrapper around public website surfaces
- API and stability notes: `references/api-notes.md`
- CLI entrypoint: `scripts/cli.py`
