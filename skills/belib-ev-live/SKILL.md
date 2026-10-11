---
name: belib-ev-live
description: "Look up live Belib electric-vehicle charge-point availability in Paris. Use when the task needs current Belib point status, charge-point identifiers, or Paris locations from the Ville de Paris open data feed. This is Paris Belib, not the New Zealand EECA charger register."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data. Python standard library only."
metadata:
  thecolab.category: "transport"
  thecolab.source_owner: "Direction de la Voirie et des Déplacements - Ville de Paris"
  thecolab.source_type: "official"
  thecolab.auth: "none"
  thecolab.access_mode: "keyless OpenDataSoft Explore API v2.1 records"
  thecolab.data_class: "public"
  thecolab.writes: "false"
  thecolab.browser: "false"
  thecolab.risk: "low"
  thecolab.cache_ttl: "none"
  thecolab.schema_version: "1"
  thecolab.skill_type: "public-api"
  thecolab.pack: "nz-public-data"
  thecolab.source_url: "https://parisdata.opendatasoft.com/explore/dataset/belib-points-de-recharge-pour-vehicules-electriques-disponibilite-temps-reel/"
  thecolab.allowed_domains: "parisdata.opendatasoft.com"
  thecolab.last_verified: "2026-10-11"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# Belib live availability in Paris

Read current Belib charge-point status from the Ville de Paris real-time
availability dataset. This is Paris, not New Zealand. `eeca-ev-chargers-nz` is
a different register and does not call this host.

Use `scripts/cli.py`. Field definitions, the ODbL notice, and the freshness
rule are in `references/source-notes.md`.

```bash
python3 skills/belib-ev-live/scripts/cli.py availability --limit 1 --json
python3 skills/belib-ev-live/scripts/cli.py availability --limit 5 --require-current --json
python3 skills/belib-ev-live/scripts/cli.py availability --limit 5 --bbox=2.25,48.82,2.42,48.90 --format geojson
python3 skills/belib-ev-live/scripts/cli.py availability --limit 1 --id 'FR*V75*E9012*06*3' --json
```

`availability` requests the newest points first (`last_updated` descending).
`--limit` is required and accepts 1 to 20. There is no offset and no occupancy
history. `--id` is an exact charge-point id. `--bbox` is
`minLon,minLat,maxLon,maxLat` in WGS84; a leading minus needs the equals form.
The box is applied upstream as point containment before the page is cut.
`--format geojson` returns a FeatureCollection and does not need `--json`.

`--require-current` fails unless the newest returned `last_updated` is within
3 hours of retrieval and not more than 15 minutes in the future. Without that
flag the command still returns the page and sets `meta.current`.

Each live command reads dataset metadata first and returns records only when
the licence is still the Open Database License (ODbL). JSON `meta` carries the
records URL, publisher, retrieval time, licence, attribution, and the newest
`last_updated` in the page as `latest_data`. Status text stays in the source
wording. Null `code_insee_commune` stays null. A commune code other than
Paris `75056` is an error.

`--fixture` reads a local records document inside this skill and does not use
the network. It is the offline parser path. The CLI has no URL argument.
Redirects that leave `parisdata.opendatasoft.com` are rejected.

Empty `results` means the filter matched nothing. Invalid arguments fail before
any request. Non-JSON, truncated JSON, HTTP 429, HTTP 503, and timeouts are
errors. A 429 keeps the upstream `Retry-After` value.

Validate with `scripts/test_contract.py` and `scripts/smoke_test.py`.
