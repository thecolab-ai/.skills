---
name: nz-cinemas
description: Query live New Zealand cinema locations, now-playing movies, and session times across Event Cinemas, HOYTS, Reading Cinemas, Rialto, and HOYTS Berkeley Mission Bay through a lightweight read-only CLI. Use when the task involves NZ movie showtimes, cinema lookup, or machine-readable cinema session data. Read-only; no booking, login, seat, ticket, cart, or payment actions.
---

# NZ Cinemas

## Goal

Query live New Zealand cinema locations, current movies, and session times through a small deterministic CLI with human-readable and JSON output, without browser automation, login, or booking actions.

## Use this when

- A user asks what movies are showing at a New Zealand cinema
- A user wants session times for a movie in New Zealand
- A user asks for locations for Event Cinemas, HOYTS, Reading Cinemas, Rialto, or Berkeley Mission Bay
- A workflow needs lightweight machine-readable NZ cinema showtime data
- A user needs a fast read-only alternative to browser-driven cinema lookup

## Do not use this for

- Booking tickets, selecting seats, placing orders, refunds, payments, member accounts, vouchers, or loyalty actions
- Cinemas outside New Zealand
- Historical showtime claims unless another dataset provides history
- High-volume scraping or republishing cinema schedules as a dataset
- Price comparisons; the implemented endpoints focus on movies, cinemas, and sessions

## Preferred workflow

1. Run `scripts/cli.py` with the narrowest subcommand that answers the task
2. Use `cinemas` to resolve a cinema name, slug, or source id
3. Use `movies --cinema <name>` before `sessions` when the movie id is unknown
4. Use `sessions <movie-id> --date YYYY-MM-DD --cinema <name>` for showtimes
5. Use `nowplaying --cinema <name>` for a same-day cinema view
6. Use `--json` for agent chaining, comparisons, or structured reports
7. Mention that showtimes are live unofficial snapshots and can change at the source

## CLI

Run with:

```bash
python3 skills/nz-cinemas/scripts/cli.py <command> [flags]
```

### Commands

- `cinemas [--chain event|hoyts|reading|rialto|berkley] [--region text] [--json]` - list cinema locations
- `movies [--chain event|hoyts|reading|rialto|berkley] [--cinema <name-or-id>] [--date YYYY-MM-DD] [--limit N] [--json]` - current movies playing
- `sessions <movie-id> [--chain event|hoyts|reading|rialto|berkley] [--date YYYY-MM-DD] [--cinema <name-or-id>] [--limit N] [--json]` - showtimes for a movie id, title, slug, or alternate source id
- `nowplaying [--chain event|hoyts|reading|rialto|berkley] [--cinema <name-or-id>] [--date YYYY-MM-DD] [--limit N] [--json]` - sessions playing on a date

Examples:

```bash
python3 skills/nz-cinemas/scripts/cli.py cinemas --chain hoyts --region Auckland
python3 skills/nz-cinemas/scripts/cli.py movies --chain hoyts --cinema "Berkeley Mission Bay" --json
python3 skills/nz-cinemas/scripts/cli.py nowplaying --chain reading --cinema LynnMall --json
python3 skills/nz-cinemas/scripts/cli.py sessions "Star Wars" --chain event --cinema "Queen Street" --date 2026-05-24
python3 skills/nz-cinemas/scripts/cli.py sessions HO00008315 --chain hoyts --cinema "Berkeley Mission Bay" --json
```

## Resources

- CLI entrypoint: `scripts/cli.py`
- API and stability notes: `references/api-notes.md`

## Notes

- No username, password, account cookie, private token, or browser session is required
- The Reading Cinemas site exposes a public short-lived bearer token from its no-login settings endpoint; the CLI fetches it fresh and does not persist it
- `berkley` maps to HOYTS Berkeley Mission Bay, because the public current site exposes it through HOYTS rather than a separate Berkley API
- Event Cinemas and Rialto share the same EVT/Vista-style session endpoint shape
- Endpoint shapes can change; verify with a small live query before relying on large workflows
- Booking URLs are returned only as source references; do not automate booking, cart, seat, payment, refund, or account flows
