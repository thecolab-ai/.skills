---
name: safeswim-nz
description: Query Auckland SafeSwim public beach water quality, swimming conditions, sewage overflow alerts, and hour-by-hour forecast data through a no-login REST API. Use when the task involves Auckland beach safety, water quality (GREEN/AMBER/RED), swimming conditions, sewage alerts, beach facilities, or per-beach forecasts. Read-only.
---

# SafeSwim NZ

## Goal

Query live Auckland SafeSwim beach water-quality and swimming-condition data with a deterministic CLI and JSON output.

## Use this when

- A user asks whether it's safe to swim at an Auckland beach today
- A user wants water quality status (GREEN/AMBER/RED/BLACK) for Auckland beaches
- A user asks about sewage overflow alerts or beach hazards
- A user wants hour-by-hour swimming forecasts (water temp, wind, UV, tide height)
- A user needs a list of nearby beaches with swim-quality filtering
- A workflow needs machine-readable beach safety data

## Do not use this for

- River or lake water quality; use `lawa-nz` for freshwater sites
- Tide predictions alone; use `nz-tides-surf` for LINZ tide tables
- Surf conditions; use `nz-tides-surf` for SwellMap surf data
- Beaches outside the Auckland SafeSwim coverage area
- Historical water-quality records beyond what the live API returns

## Preferred workflow

1. Run `scripts/cli.py list` to discover Auckland beaches (optionally filtered by search or distance)
2. Use `detail <slug>` for a specific beach with hour-by-hour forecast data
3. Use `nearby <lat> <lon>` to find beaches close to a location
4. Use `--json` for agent chaining, alerts, or structured reports
5. Mention that SafeSwim data is live and can change rapidly after rainfall events

## CLI

Run with:

```bash
python3 skills/safeswim-nz/scripts/cli.py <command> [flags]
```

### Commands

- `list [--search TEXT] [--limit N] [--json]` — list all Auckland beaches with quality status, patrol info
- `detail <slug> [--json]` — full detail for a beach: forecasts, tags, alerts, facilities
- `nearby <lat> <lon> [--radius N] [--min-quality GREEN|AMBER|RED] [--limit N] [--json]` — beaches near a location ordered by distance

Examples:

```bash
python3 skills/safeswim-nz/scripts/cli.py list --search takapuna --limit 5
python3 skills/safeswim-nz/scripts/cli.py detail takapunabeach --json
python3 skills/safeswim-nz/scripts/cli.py nearby -36.8485 174.7633 --radius 10 --min-quality AMBER
```

## Resources

- CLI entrypoint: `scripts/cli.py`
- Smoke test: `scripts/smoke_test.py`
- API notes: `references/api-notes.md`

## Notes

- No API key, username, password, cookie, or browser automation is required
- The SafeSwim API is public and read-only at `safeswim.org.nz/api`
- Water quality can change rapidly after rainfall — treat results as current snapshots
- GREEN = safe to swim, AMBER = caution, RED = unsafe, BLACK = sewage overflow
- Not all beaches provide the full forecast array; some data arrays may be sparse
- SafeSwim covers Auckland region only (East Coast, West Coast, Hauraki Gulf islands)
- The CLI fetches the full location list once and filters in-process; repeated hits within a second reuse the cached fetch
