---
name: christchurch-bin-schedule
description: Query Christchurch City Council kerbside collection schedules (rubbish, recycling, organics). Use when the task involves Christchurch bin days, kerbside collection for a Christchurch address, or CCC three-bin schedules. Supports address search (name → RatingUnitID) or direct RatingUnitID lookup. No account required.
---

# Christchurch Bin Schedule

## Goal

Query live Christchurch City Council household kerbside collection schedules through a deterministic CLI with human-readable and JSON output.

Christchurch uses a **three-bin system** under the national standardisation:
- **Red bin** — Rubbish (fortnightly)
- **Yellow bin** — Recycling (fortnightly)
- **Green bin** — Organics (weekly, where available)

All three bin types are typically collected on the **same day of the week**, though they rotate on different fortnightly schedules.

## Use this when

- A user asks when Christchurch bins go out
- A user wants the next rubbish, recycling, or organics collection date for a Christchurch address
- A workflow needs machine-readable CCC collection schedule data

## Do not use this for

- Councils outside Christchurch City / Banks Peninsula (try Auckland, Wellington, or other council skills)
- Inner-city bag collections (not supported by this endpoint)
- Banks Peninsula community collection points (not individual property-level)
- Commercial or private collection schedules
- Finding a RatingUnitID without an address — the user must provide either an address or a known RatingUnitID

## Preferred workflow

1. Accept an address string or a known RatingUnitID from the user
2. If an address is given, resolve it to a RatingUnitID via the CCC address suggest API
3. Fetch the collection schedule from the CCC getProperty endpoint
4. Filter to current/future `out_of_date=False` collections
5. Present the regular schedule (day of week) and upcoming collection dates
6. Use `--json` for agent chaining, comparisons, alerts, or structured reports

## CLI

Run with:

```bash
python3 skills/christchurch-bin-schedule/scripts/cli.py "53 Hereford Street"
python3 skills/christchurch-bin-schedule/scripts/cli.py --rating-unit-id 86089
python3 skills/christchurch-bin-schedule/scripts/cli.py "53 Hereford Street" --json
```

### Arguments

- `address` — street address to search, e.g. `"53 Hereford Street"`
- `--rating-unit-id` — CCC RatingUnitID (numeric), skips address lookup
- `--json` — emit JSON

### Finding your RatingUnitID

1. Visit `https://ccc.govt.nz/services/rubbish-and-recycling/collections/`
2. Search for your address
3. The RatingUnitID can be found by inspecting the network request to `/getProperty?ID=`
4. Alternatively, use this skill with your address and it will resolve the ID automatically

## Resources

- CLI entrypoint: `scripts/cli.py`
- API and stability notes: `references/api-notes.md`

## Notes

- No API key, username, password, or cookie is required
- Christchurch uses the national-standard three-bin system (red/yellow/green)
- The `getProperty` endpoint is protected by Incapsula bot detection — it works reliably from residential NZ IPs but may block datacenter/VPN IPs with 403
- The address suggest endpoint (opendata.ccc.govt.nz) has no bot protection and works universally
- Dates are current Council snapshots, not historical records
- Public holidays may shift collection dates — the CLI reflects the current Council data
- Treat dates as live current snapshots, not guaranteed future schedules
- Organic collections are marked as `Week A` / `Week B` — the `next_planned_date` reflects the actual collection date
