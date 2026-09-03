---
name: nzta-highway-info
description: "Query current official NZTA state-highway events, travel-time signs, traffic cameras, and variable-message signs. Use for bounded live highway-condition lookups; read-only and not a complete safety source."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "transport"
  thecolab.source_owner: "NZ Transport Agency Waka Kotahi"
  thecolab.source_type: "official"
  thecolab.auth: "none"
  thecolab.access_mode: "public-api"
  thecolab.data_class: "public"
  thecolab.writes: "false"
  thecolab.browser: "false"
  thecolab.risk: "low"
  thecolab.cache_ttl: "none"
  thecolab.schema_version: "1"
  thecolab.skill_type: "public-api"
  thecolab.pack: "nz-public-data"
  thecolab.source_url: "https://catalogue.data.govt.nz/dataset/nzta-highway-information1"
  thecolab.allowed_domains: "catalogue.data.govt.nz,trafficnz.info,services.arcgis.com,www.journeys.nzta.govt.nz"
  thecolab.last_verified: "2026-09-03"
  thecolab.health: "degraded"
  thecolab.maintainer: "@adam91holt"
---

# NZTA Highway Info

## Goal

Run bounded, read-only lookups against NZ Transport Agency Waka Kotahi's public
Traffic and Travel API v4 for current state-highway events, traffic-camera
metadata and image URLs, displayed travel times, and variable-message signs.

This is a situational-information aid, not a complete or safety-critical source.
Conditions can change after retrieval. For a critical journey, confirm against
the official NZTA Journey Planner, roadside signs, closures, emergency services,
and relevant local council sources.

## Use this when

- A user asks about current NZ state-highway incidents, hazards, closures, or works
- A user needs public NZTA traffic-camera status or current image URLs
- A user asks what a variable-message sign currently displays
- A user wants displayed travel-time estimates from Traffic Information
  Management (TIM) signs
- A workflow needs bounded JSON with explicit source and retrieval freshness

## Do not use this for

- A claim that a route is safe, passable, complete, or incident-free
- Local-road or council-road completeness
- Turn-by-turn routing, tolls, licensing, accounts, alerts, or reporting incidents
- Historical analysis; the source is a current operational snapshot
- Automated congestion classification. The reliable TIM feed has displayed
  minutes but no free-flow baseline, so this skill deliberately does not infer it
- Downloading or archiving camera images; the CLI returns official image URLs only

Use `nz-road-closures` when its Journey Planner-oriented event and route workflow
is the better fit. Use this skill for the direct Traffic and Travel v4 feeds,
including VMS and TIM data.

## Workflow

1. Start with the narrowest command and a small `--limit`.
2. Add `--region` and `--query` to filter locally, case-insensitively.
3. Treat `source.retrieved_at` as fetch time, not proof that every item was updated
   then. Prefer item update fields where present.
4. Repeat the safety/completeness warning for travel decisions.
5. Use `--json` for agent chaining; inspect `complete`, `truncated`, `source_count`,
   and `warnings` rather than reporting only the returned list.
6. If the source times out, is blocked, or changes schema, report that state; do
   not convert it into an empty successful result.

## Commands

Run from the repository root.

```bash
python3 skills/nzta-highway-info/scripts/cli.py events --region Wellington --event-type incident --limit 10 --json
```

`events` returns current road-event metadata, including event timestamps when the
source supplies them. `--event-type` is a case-insensitive substring because the
official vocabulary can change.

```bash
python3 skills/nzta-highway-info/scripts/cli.py travel-times --region Auckland --limit 10 --json
```

`travel-times` returns enabled and disabled TIM sign records plus displayed
numeric destination minutes. `congestion_status` remains `null`; do not turn
these values into congestion claims without a defensible baseline.

```bash
python3 skills/nzta-highway-info/scripts/cli.py cameras --region Canterbury --query SH1 --limit 10 --json
```

`cameras` returns metadata, operational flags, and official `image_url`,
`thumbnail_url`, and `view_url` values when supplied. The API provides no reliable
per-camera image timestamp.

```bash
python3 skills/nzta-highway-info/scripts/cli.py vms --region Wellington --active-only --limit 10 --json
```

`vms` decodes `[nl]` and `[np]` markers into `message_lines` and exposes message
update times where present. A displayed message is advisory information, not a
substitute for signs and directions encountered on the road.

```bash
python3 skills/nzta-highway-info/scripts/cli.py regions --limit 20 --json
```

`regions` lists official API region ids and names for discovery. All commands
also support human-readable output when `--json` is omitted.

## Bounds and failures

- Every network call uses a 10-second timeout.
- Responses are capped at 4 MB.
- `--limit` defaults to 20 and is capped at 100.
- Filtering and limits are local after one bounded nationwide endpoint fetch.
- Exit `2`: invalid input; `4`: blocked/rate-limited; `5`: upstream unavailable;
  `6`: schema/parser failure.
- The JSON envelope always exposes the exact endpoint, catalogue/WADL links,
  retrieval time, counts, truncation state, completeness disclaimer, and warnings.

## Freshness and completeness

- `source.retrieved_at` is generated by this client in UTC.
- `source.latest_item_update_at` is the latest available event, VMS, or TIM item
  timestamp; it can be `null`.
- Cameras have retrieval freshness only because the source omits an image-update
  timestamp.
- `complete` is always `false`: the upstream service does not promise exhaustive
  safety coverage, and local roads require other authorities.

## Resources

- Source proof, WADL resources, ArcGIS cross-check, and live-health caveats:
  `references/source-notes.md`
- Normalised JSON fields and parser decisions: `references/result-contract.md`
- Deterministic parser tests: `scripts/test_cli.py`
- Repository contract test: `scripts/test_contract.py`
- Outage-aware fixture/live smoke: `scripts/smoke_test.py`
