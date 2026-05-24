---
name: wellington-bin-schedule
description: Query Wellington City Council rubbish and recycling collection days using a WCC street ID. Use when the task involves Wellington bin day, rubbish/recycling schedules, or kerbside collection for a Wellington address. Requires a WCC street ID (found by searching your address on the WCC collection-day page). No account login required.
---

# Wellington Bin Schedule

## Goal

Query live Wellington City Council household rubbish and recycling collection schedules through a deterministic CLI with human-readable and JSON output.

Wellington combines **rubbish and recycling (glass crate) on the same collection day** — there is no separate recycling week.

## Use this when

- A user asks when Wellington bins go out
- A user wants the next rubbish or recycling collection date for a Wellington street
- A workflow needs machine-readable Wellington City Council collection schedule data

## Do not use this for

- Councils outside Wellington City (try Auckland, Christchurch, or other council skills)
- Food scraps / organics collection (Wellington does not offer kerbside organics)
- Commercial or private collection schedules not shown on WCC's page
- Finding a street ID — the user must obtain this from the WCC website

## Preferred workflow

1. Ask the user for their WCC street ID if not provided (they can find it at `https://wellington.govt.nz/rubbish-recycling-and-waste/when-to-put-out-your-rubbish-and-recycling`)
2. Run `scripts/cli.py --street-id <id>` with an optional street name for display
3. Use `--json` for agent chaining, comparisons, alerts, or structured reports
4. Note that **rubbish and recycling are collected together** in Wellington

## CLI

Run with:

```bash
python3 skills/wellington-bin-schedule/scripts/cli.py --street-id <id> [street name...] [flags]
```

### Arguments

- `--street-id <id>` — **(required)** WCC street ID (numeric), e.g. `6317`
- `street name` — optional display name, e.g. `Awa Road, Karaka Bays`
- `--json` — emit JSON

Examples:

```bash
python3 skills/wellington-bin-schedule/scripts/cli.py --street-id 6317
python3 skills/wellington-bin-schedule/scripts/cli.py --street-id 6317 "Awa Road, Karaka Bays"
python3 skills/wellington-bin-schedule/scripts/cli.py --street-id 6317 --json
```

## Finding your street ID

1. Visit `https://wellington.govt.nz/rubbish-recycling-and-waste/when-to-put-out-your-rubbish-and-recycling`
2. Search for your street name
3. The street ID appears in the URL parameter `?streetId=` after selecting your street
4. Use that ID with `--street-id`

## Resources

- CLI entrypoint: `scripts/cli.py`
- API and stability notes: `references/api-notes.md`

## Notes

- No API key, username, password, or cookie is required
- Rubbish and recycling are **always collected on the same day** in Wellington
- Wellington does not have a kerbside food scraps / organics collection
- Dates are current Council snapshots, not historical records
- Public holidays may shift collection dates — the CLI reflects the current Council page
- The street autocomplete API requires ASP.NET authentication and is not accessible programmatically
- Treat dates as live current snapshots, not guaranteed future schedules
