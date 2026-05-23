---
name: nz-council
description: Query NZ council-area event listings and public recreation facilities through a lightweight read-only CLI. Use for Auckland, Wellington, Christchurch, Rotorua, or New Plymouth what's-on events, Eventfinda council-area events, Auckland Council pools/leisure centres, Wellington pools/recreation centres, Rotorua Lakes pools and aquatic facilities, New Plymouth pools, pool hours, and public lane availability snapshots. Not for rates, consents, rubbish, recycling, parking fines, bookings, logins, or payments.
---

# NZ Council

## Goal

Use a small read-only CLI to look up two NZ council public-information domains:

- council-area events and what's-on listings
- council recreation facilities, especially pools, leisure centres, gyms, hours, and public lane availability where exposed

This v1 is deliberately narrow. It is not a general council-services skill.

## Use this when

- The user asks what is on in Auckland, Wellington, Christchurch, Rotorua, New Plymouth, or across NZ council areas.
- The user asks for council-listed concerts, markets, exhibitions, kids' activities, festivals, or free events.
- The user asks for public pools, leisure centres, gyms, recreation centres, hours, or pool lane availability.
- You need a quick JSON feed for council-area events or recreation facility listings without browser automation.

## Do not use this for

- Rates, consents, LIMs, rubbish, recycling, bins, water, dog registration, parking fines, permits, or complaints.
- Booking classes, reserving lanes, buying tickets, joining gyms, payments, account logins, or changing bookings.
- Private events, private gyms, hotels, non-council venues, or non-public recreation data.
- Emergency alerts or Department of Conservation data; use a more specific NZ public-data skill for those.

## Preferred workflow

1. Start with `events` for what's-on questions. Eventfinda public pages are the primary cross-NZ source because the official Eventfinda REST API requires authentication.
2. Use `event <id>` only with an event URL/path returned by `events --json`.
3. Use `pools --council akl --json` for Auckland pool lists with parsed hours.
4. Use `pool "Tepid Baths" --json` for a single Auckland pool, including public lane availability when Auckland Leisure exposes it.
5. Use Wellington recreation commands for basic Wellington pool/recreation-centre listings; open linked WCC pages if exact opening times are needed.
6. Use `pools --council rot --json` or `pool "Rotorua Aquatic" --json` for Rotorua Lakes aquatic facilities.
7. Use `pools --council npl --json` for New Plymouth public pool listings, including Todd Energy Aquatic Centre and selected seasonal/community pools.
8. Treat Christchurch recreation as discovered but not fully wired in v1; the public council page is protected/vendor-backed.

## CLI

Run from this skill directory or point directly at the script:

```bash
python3 skills/nz-council/scripts/cli.py --help
```

Every data command supports `--json`.

## Commands

```bash
python3 skills/nz-council/scripts/cli.py events [--council akl|wlg|chc|rot|npl] [--from DATE] [--to DATE] [--category SLUG] [--free] [--limit N] [--json]
python3 skills/nz-council/scripts/cli.py event <id-or-url> [--json]

python3 skills/nz-council/scripts/cli.py pools [--council akl|wlg|chc|rot|npl] [--region central|east|north|south|west] [--limit N] [--json]
python3 skills/nz-council/scripts/cli.py pool <name> [--council akl|wlg|chc|rot|npl] [--json]
python3 skills/nz-council/scripts/cli.py facilities [--council akl|wlg|chc|rot|npl] [--type pool|gym|leisure-centre|library] [--region central|east|north|south|west] [--limit N] [--json]
```

## Examples

```bash
python3 skills/nz-council/scripts/cli.py events --council akl --from 2026-05-23 --to 2026-05-24 --limit 5 --json
python3 skills/nz-council/scripts/cli.py events --council wlg --from 2026-05-24 --to 2026-05-24 --limit 5 --json
python3 skills/nz-council/scripts/cli.py event /2026/some-event/auckland --json

python3 skills/nz-council/scripts/cli.py pools --council akl --region central --json
python3 skills/nz-council/scripts/cli.py pool "Tepid Baths" --json
python3 skills/nz-council/scripts/cli.py facilities --council wlg --type pool --json
python3 skills/nz-council/scripts/cli.py pools --council rot --json
python3 skills/nz-council/scripts/cli.py pool "Rotorua Aquatic" --json
python3 skills/nz-council/scripts/cli.py pools --council npl --json
python3 skills/nz-council/scripts/cli.py pool "Todd Energy" --json
```

## Resources

- CLI: `scripts/cli.py`
- API notes: `references/api-notes.md`

## Notes

- Events use public Eventfinda website pages at `eventfinda.co.nz`; the documented Eventfinda REST API at `api.eventfinda.co.nz/v2` returned `401 Incorrect authentication details supplied` without credentials.
- Auckland Council events are discoverable on OurAuckland at `ourauckland.aucklandcouncil.govt.nz/events`; v1 uses Eventfinda for a single cross-council event path.
- Wellington City events point users to an Eventfinda calendar, so the same public Eventfinda event path is used for Wellington.
- Christchurch City Council's direct events page was protected by an Incapsula challenge during discovery, so Christchurch event queries use Eventfinda public pages.
- Auckland pools and leisure facilities use `aucklandleisure.co.nz` public location pages and the public Auckland Leisure portal resource-availability page when present.
- Wellington pools and recreation centres use public `wellington.govt.nz` listing pages.
- Rotorua Lakes pools and aquatic facilities use public `rotorualakescouncil.nz` recreation and park pages plus the CLM Rotorua Aquatic Centre operator pages.
- New Plymouth pools use NPDC public pages for Todd Energy Aquatic Centre, Inglewood Pool, and Waitara Pool; Bell Block uses the public Methanex Bell Block Aquatic Centre site.
- Christchurch recreation and sport pages were observed at `recandsport.ccc.govt.nz`, but the useful dynamic data is vendor-backed and is documented rather than wired in v1.
