---
name: nz-council
description: Query NZ council-area event listings and public recreation facilities through a lightweight read-only CLI. Use for Auckland, Wellington, Christchurch, Rotorua, New Plymouth, Napier, Hastings, Hamilton, Whangarei, Palmerston North, or Tauranga what's-on events; Eventfinda council-area events; Auckland Council pools/leisure centres; Wellington City pools/recreation centres; Rotorua Lakes pools and aquatic facilities; New Plymouth pools; Napier and Hastings aquatic facilities; Hamilton Pools facilities; Whangarei Aquatic Centre; Palmerston North swimming facilities; Wellington region pools and aquatic centres for Hutt City, Porirua, Upper Hutt, and Kāpiti Coast; Tauranga pools/aquatic centres; pool hours; and public lane availability snapshots where exposed. Not for rates, consents, rubbish, recycling, parking fines, bookings, logins, or payments.
---

# NZ Council

## Goal

Use a small read-only CLI to look up two NZ council public-information domains:

- council-area events and what's-on listings
- council recreation facilities, especially pools, leisure centres, gyms, hours, contact details, pool details, and public lane availability where exposed

This v1 is deliberately narrow. It is not a general council-services skill.

## Use this when

- The user asks what is on in Auckland, Wellington, Christchurch, Rotorua, New Plymouth, Napier, Hastings, Hamilton, Whangarei, Palmerston North, Tauranga, or across NZ council areas.
- The user asks for council-listed concerts, markets, exhibitions, kids' activities, festivals, or free events.
- The user asks for public pools, leisure centres, gyms, recreation centres, hours, pool contact details, pool facilities, or pool lane availability.
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
5. Use Wellington City recreation commands for basic Wellington pool/recreation-centre listings; open linked WCC pages if exact opening times are needed.
6. Use `pools --council rot --json` or `pool "Rotorua Aquatic" --json` for Rotorua Lakes aquatic facilities.
7. Use `pools --council npl --json` for New Plymouth public pool listings, including Todd Energy Aquatic Centre and selected seasonal/community pools.
8. Use `pools --council npr --json` for Napier Aquatic Centre / Onekawa Pools.
9. Use `pools --council has --json` for Hastings aquatic recreation facilities, including Splash Planet and Aquatics Hastings pools.
10. Use `pools --council ham --json` or `pool "Waterworld" --json` for Hamilton Pools facilities, including Waterworld, Gallagher Aquatic Centre, and current seasonal partner pools.
11. Use Wellington region council codes for aquatic facilities beyond Wellington City: `hutt`, `porirua`, `uhutt`, and `kapiti`.
12. Use `pools --council whg --json` or `pool "ASB Leisure" --json` for Whangarei Aquatic Centre. ASB Leisure is treated as a legacy/search alias for the current Ewing Road aquatic-centre source.
13. Use `pools --council chc --json`, `facilities --council chc --type pool --json`, or `pool "Jellie Park" --json` for Christchurch Recreation and Sport facilities. The CLI reads public recandsport CCC endpoints and public facility pages; it does not book sessions or use authenticated portals.
14. Use `pools --council pmn --json` or `pool "Lido" --json` for Palmerston North council-listed swimming facilities, with PNCC details and public CLM hours where linked.
15. Use `pools --council tga --json` or `facilities --council tga --type pool --json` for Tauranga City Council aquatic centres operated by Bay Venues, including current closed-status notes where exposed.

## CLI

Run from this skill directory or point directly at the script:

```bash
python3 skills/nz-council/scripts/cli.py --help
```

Every data command supports `--json`.

## Commands

```bash
python3 skills/nz-council/scripts/cli.py events [--council akl|wlg|chc|rot|npl|npr|has|ham|whg|pmn|tga] [--from DATE] [--to DATE] [--category SLUG] [--free] [--limit N] [--json]
python3 skills/nz-council/scripts/cli.py event <id-or-url> [--json]

python3 skills/nz-council/scripts/cli.py pools [--council akl|wlg|chc|rot|npl|npr|has|ham|hutt|porirua|uhutt|kapiti|whg|pmn|tga] [--region central|east|north|south|west] [--limit N] [--json]
python3 skills/nz-council/scripts/cli.py pool <name> [--council akl|wlg|chc|rot|npl|npr|has|ham|hutt|porirua|uhutt|kapiti|whg|pmn|tga] [--json]
python3 skills/nz-council/scripts/cli.py facilities [--council akl|wlg|chc|rot|npl|npr|has|ham|hutt|porirua|uhutt|kapiti|whg|pmn|tga] [--type pool|gym|leisure-centre|library] [--region central|east|north|south|west] [--limit N] [--json]
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
python3 skills/nz-council/scripts/cli.py pools --council npr --json
python3 skills/nz-council/scripts/cli.py pools --council has --json
python3 skills/nz-council/scripts/cli.py pool "Onekawa" --json
python3 skills/nz-council/scripts/cli.py pool "Splash Planet" --json
python3 skills/nz-council/scripts/cli.py pools --council ham --json
python3 skills/nz-council/scripts/cli.py pool "Waterworld" --json
python3 skills/nz-council/scripts/cli.py pools --council hutt --json
python3 skills/nz-council/scripts/cli.py pool "Naenae Pool" --council hutt --json
python3 skills/nz-council/scripts/cli.py pools --council kapiti --json
python3 skills/nz-council/scripts/cli.py pools --council whg --json
python3 skills/nz-council/scripts/cli.py pool "ASB Leisure" --json
python3 skills/nz-council/scripts/cli.py pools --council chc --json
python3 skills/nz-council/scripts/cli.py pool "Jellie Park" --json
python3 skills/nz-council/scripts/cli.py pools --council pmn --json
python3 skills/nz-council/scripts/cli.py pool "Lido" --json
python3 skills/nz-council/scripts/cli.py pools --council tga --json
python3 skills/nz-council/scripts/cli.py pool "Baywave" --json
python3 skills/nz-council/scripts/cli.py pool "Baywave" --council tga --json
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
- Wellington City pools and recreation centres use public `wellington.govt.nz` listing pages.
- Rotorua Lakes pools and aquatic facilities use public `rotorualakescouncil.nz` recreation and park pages plus the CLM Rotorua Aquatic Centre operator pages.
- New Plymouth pools use NPDC public pages for Todd Energy Aquatic Centre, Inglewood Pool, and Waitara Pool; Bell Block uses the public Methanex Bell Block Aquatic Centre site.
- Hamilton pools use `hamiltonpools.co.nz`, a Hamilton City Council site, for Waterworld, Gallagher Aquatic Centre, and seasonal partner pool listings. The current Hamilton Pools source does not list Founders Memorial Theatre Pool as an active pool.
- Hutt City pools use the Hutt City Pools and Fitness public site. Direct HTTP is Cloudflare-challenged in some environments, so the CLI probes direct HTTP first and can fall back to the local Chrome DevTools endpoint at `127.0.0.1:5100`.
- Porirua Arena Aquatics uses the public Te Rauparaha Arena aquatic pages.
- Upper Hutt H2O Xtream uses public H2O Xtream pages. Some direct requests are Akamai-denied in Python, so the CLI can use the same local CDP fallback.
- Kāpiti Coast pools use public Kāpiti Coast Aquatics pages.
- Whangarei recreation uses the current WDC parks/recreation landing page plus CLM's Whangarei Aquatic Centre pages. The old `wdc.govt.nz/Services/Sport-and-recreation/Pools-and-leisure` path returned a WDC 404 during discovery, and `asbleisurecentre.co.nz` did not resolve.
- Palmerston North swimming facilities use the PNCC `Parks-recreation/Swimming-pools` listing page, linked PNCC detail pages, and public CLM contact pages for opening hours where PNCC links them.
- Tauranga pools use Tauranga City Council's swimming-pools page plus `taurangapools.co.nz` / Bay Venues location and detail pages; Mount Hot Pools uses `mounthotpools.co.nz` for current closure and pool detail text. The CLI tries direct fetch first and falls back to a local CDP endpoint at `127.0.0.1:5100` only when a fetched page looks bot-walled.
- Napier aquatic recreation uses Napier City Council's current Napier Aquatic Centre page. The centre is also commonly known as Onekawa Pools.
- Hastings aquatic recreation uses Hastings District Council's current swimming-pools page plus linked Aquatics Hastings and Splash Planet public pages. Frimley Pool is retained as a closed facility because HDC's current page records the September 2024 closure decision.
- Christchurch recreation and sport facilities use public `recandsport.ccc.govt.nz` filter endpoints plus linked facility detail pages for pools, gyms, centre details, opening-state text, and public swim/lane summaries where exposed.
- Christchurch supplemental pool entries use public He Puna Taimoana and Wharenui Sports Centre pages when those facilities are not returned by the recandsport listing endpoint.
