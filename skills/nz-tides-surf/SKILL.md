---
name: nz-tides-surf
description: "Query New Zealand LINZ tide predictions and SwellMap surf forecasts through a lightweight read-only CLI. Use when the task involves NZ tide times, next high/low tide, surf forecasts, swell trend, or choosing the best nearby surf break for a drive."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "environment"
  thecolab.source_owner: "Toitū Te Whenua LINZ and SwellMap"
  thecolab.source_type: "mixed"
  thecolab.auth: "none"
  thecolab.access_mode: "public-api"
  thecolab.data_class: "public"
  thecolab.writes: "false"
  thecolab.browser: "false"
  thecolab.risk: "low"
  thecolab.cache_ttl: "24h"
  thecolab.schema_version: "1"
  thecolab.skill_type: "public-api"
  thecolab.pack: "nz-public-data"
  thecolab.source_url: "https://www.linz.govt.nz"
  thecolab.allowed_domains: "developer.metservice.com,niwa.co.nz,static.charts.linz.govt.nz,www.linz.govt.nz,www.surfline.com,www.swellmap.com"
  thecolab.last_verified: "2026-07-19"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# NZ Tides + Surf

## Goal

Query live New Zealand tide and surf forecast data through a small deterministic CLI with human-readable and JSON output, without login, browser automation, account cookies, or API keys.

The main workflow is answering "is Piha worth a drive tomorrow morning?" by combining official LINZ tide predictions with SwellMap surf ratings, wave height, swell period, swell direction, and wind.

## Use this when

- A user asks for tide times at a New Zealand port or surf beach
- A user asks for the next high tide or low tide
- A user asks for a surf forecast at a known NZ break
- A user wants to compare breaks in Auckland, Coromandel, Gisborne, or Wellington
- A workflow needs machine-readable tide/surf rows for trip planning

## Do not use this for

- Safety-critical boating, swimming, or surf rescue decisions without checking the source sites directly
- Maritime warnings, official weather watches, or severe weather alerts
- Authenticated Surfline features, subscriptions, cameras, or personalised forecasts
- MetOcean/MetService point marine API data when an API key is available; use `metservice-nz` for that
- Historical tide or surf analysis beyond the published forecast/table windows

## Preferred workflow

1. Run `scripts/cli.py` with the narrowest subcommand that answers the task
2. Use `tides` or `next-tide` for official LINZ tide predictions
3. Use `surf` for a specific break forecast
4. Use `best-break` when the user asks where to drive tomorrow morning
5. Use `breaks` to see the curated surf breaks and their companion LINZ tide ports
6. Use `--json` for agent chaining, comparisons, and reports
7. Mention that surf ratings are SwellMap forecast snapshots and tide rows are official LINZ predictions

## CLI

Run with:

```bash
python3 skills/nz-tides-surf/scripts/cli.py <command> [flags]
```

## Commands

- `ports [--json]` - list available LINZ tide ports and common surf aliases
- `tides <port> [--date YYYY-MM-DD] [--days N] [--json]` - LINZ tide predictions for a port or surf alias
- `next-tide <port> [--json]` - next high tide and next low tide from now
- `breaks [--json]` - list known NZ surf breaks and companion LINZ tide ports
- `surf <break> [--days N] [--json]` - SwellMap forecast for a named NZ surf break
- `best-break [--region auckland|coromandel|gisborne|wgtn] [--date YYYY-MM-DD] [--json]` - compare the region's morning forecast rows and pick the best average rating
- `marine <area> [--json]` - NIWA marine handoff note; no no-key NIWA wave endpoint was confirmed, so use `metservice-nz marine` for key-backed MetOcean marine data

## Examples

```bash
python3 skills/nz-tides-surf/scripts/cli.py tides Auckland --date 2026-05-24
python3 skills/nz-tides-surf/scripts/cli.py tides Piha --date 2026-05-24 --json
python3 skills/nz-tides-surf/scripts/cli.py next-tide "Mt Maunganui" --json
python3 skills/nz-tides-surf/scripts/cli.py surf Piha --days 3
python3 skills/nz-tides-surf/scripts/cli.py surf Raglan --days 3 --json
python3 skills/nz-tides-surf/scripts/cli.py best-break --region auckland --json
python3 skills/nz-tides-surf/scripts/cli.py breaks
```

## Supported surf aliases

Common surf questions are mapped to the closest practical source:

- `Piha`, `Muriwai`, `Bethells`, `Karekare` - SwellMap Auckland West Coast forecasts, LINZ Anawhata tide companion
- `Raglan`, `Manu Bay`, `Raglan Bar`, `Mussel Rock` - SwellMap Raglan forecasts, LINZ Raglan tides
- `Mt Maunganui`, `Mount Maunganui`, `Tay Street` - SwellMap Tay Street forecast, LINZ Moturiki Island tides
- `Lyall Bay`, `Breaker Bay`, `Makara`, `Plimmerton` - Wellington surf forecasts, LINZ Wellington tides
- `Whangamata`, `Hot Water Beach`, `Kuaotunu`, `Whitianga` - Coromandel surf forecasts, nearby LINZ tide companions

## Resources

- CLI entrypoint: `scripts/cli.py`
- API and stability notes: `references/api-notes.md`
- Related key-backed marine skill: `skills/metservice-nz/`

## Notes

- LINZ source: `https://www.linz.govt.nz/products-services/tides-and-tidal-streams/tide-predictions`, using `https://www.linz.govt.nz/api/v1/tp` and `https://static.charts.linz.govt.nz/tide-tables/maj-ports/csv/...`.
- SwellMap source: `https://www.swellmap.com/surf-forecasts/new-zealand`, using the public no-login Next.js forecast payload embedded in each surf forecast page.
- MetService/MetOcean source: `https://developer.metservice.com/docs/api-catalog/point-forecast-api/`; the existing `metservice-nz` skill already covers key-backed marine/wave variables.
- NIWA source: `https://niwa.co.nz`; a no-key NIWA public marine wave forecast endpoint was not confirmed during implementation, so this skill does not duplicate the `metservice-nz marine` command.
- Surfline source investigated: `https://www.surfline.com/surf-report`; direct CLI requests to Surfline's public JSON/search surface returned Cloudflare challenge HTML in this environment, so SwellMap is the working no-login surf source.
- Magicseaweed is discontinued; no live Magicseaweed source is wired.
- All times are emitted in `Pacific/Auckland`.
- Endpoint shapes can change without notice because SwellMap and Surfline surfaces are public website implementation details rather than formal public APIs.
- Do not commit HAR captures, screenshots, cookies, raw browser profiles, or bulky JavaScript bundles when updating this skill.
