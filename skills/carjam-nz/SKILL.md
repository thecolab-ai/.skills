---
name: carjam-nz
description: Query CarJam NZ public/basic vehicle information pages through a lightweight no-login CLI. Use when the task involves New Zealand vehicle plate, VIN, or chassis lookup, make/model/year/colour, public registration/WOF/licence snippets, odometer snippets, or CarJam source URLs. Read-only; no paid report purchase, owner lookup, login, account, or write actions.
---

# CarJam NZ

## Goal

Query public/basic CarJam NZ vehicle information from the no-login HTML report page through a deterministic Python CLI.

## Use this when

- A user asks for public CarJam details for a New Zealand plate, VIN, or chassis
- A user wants a quick make/model/year/colour/plate/VIN summary
- A workflow needs machine-readable public vehicle metadata with source URLs
- A user wants to know which fields are report-gated versus visible for free

## Do not use this for

- Paid CarJam report purchase, checkout, subscription, login, or account actions
- Owner name/address lookup, personal information extraction, or bypassing report gates
- Updating stolen status, reminders, watchlists, or any write/mutation flow
- Treating public snippets as official legal advice; direct users to NZTA/Waka Kotahi or CarJam for authoritative/current status

## Preferred workflow

1. Run `scripts/cli.py lookup <plate>` for one vehicle
2. Add `--json` for structured output or chaining
3. Use `--raw` only when the task needs all parsed public fields rather than the concise summary
4. Use `batch` for a small set of plates; keep the default delay to avoid hammering the public site
5. Clearly distinguish public/basic fields from paid/report-gated fields shown as `Get Report`, `May be in Report`, or `Subscribe`

## CLI

Run with:

```bash
python3 skills/carjam-nz/scripts/cli.py <command> [flags]
```

### Commands

- `lookup <identifier> [--type plate|vin|chassis] [--json] [--raw]` — lookup one vehicle
- `batch <identifier...> [--type plate|vin|chassis] [--sleep seconds] [--fail-fast] [--json]` — compact summaries for multiple identifiers

Examples:

```bash
python3 skills/carjam-nz/scripts/cli.py lookup ABC123
python3 skills/carjam-nz/scripts/cli.py lookup ABC123 --json
python3 skills/carjam-nz/scripts/cli.py lookup 7A8CJ0P0797205527 --type vin --json
python3 skills/carjam-nz/scripts/cli.py batch ABC123 KMM42 --json
```

## Resources

- CLI entrypoint: `scripts/cli.py`
- Live smoke test: `scripts/smoke_test.py`
- Source/stability notes: `references/api-notes.md`

## Notes

- No API key, username, password, account cookie, browser automation, or paid report purchase is required for supported commands
- This skill parses public HTML, not a published API; CarJam page structure can change
- Some fields are intentionally report-gated by CarJam and are preserved as locked/gated rather than bypassed
