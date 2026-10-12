---
name: paris-road-counters
description: "Read Ville de Paris permanent road-counter arc-hours from comptages routiers permanents. Use for hourly one-direction flow (débit) and loop occupancy (taux d'occupation), with ODbL attribution. Do not use for the historical archive, the Lambert referential, Belib chargers, or New Zealand traffic counts."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "transport"
  thecolab.source_owner: "Direction de la Voirie et des Déplacements - Ville de Paris"
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
  thecolab.source_url: "https://opendata.paris.fr/explore/dataset/comptages-routiers-permanents/information/"
  thecolab.allowed_domains: "opendata.paris.fr"
  thecolab.last_verified: "2026-10-11"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# Paris road counters

Read hourly permanent-counter arc records from Ville de Paris. Each row is one
arc (`iu_ac`) for one hour, in the amont to aval direction only. `q` is vehicles
in that hour. `k` is the percent of the hour the loop was occupied. They are
not interchangeable, and neither is a two-way or network total.

The code in this skill is MIT. The records are ODbL. Attribute the publisher.
A database made from the records must stay under the Open Database License.

Use `scripts/cli.py`. Both commands accept `--json`. `--format geojson` is
machine-readable without `--json`. Read
[references/source-notes.md](references/source-notes.md) before aggregating.

```bash
python3 scripts/cli.py dataset --json
python3 scripts/cli.py counts --limit 1 --json
python3 scripts/cli.py counts --limit 1 --flow observed --json
python3 scripts/cli.py counts --limit 5 --arc 4596 --from 2026-10-10T22:00:00 --to 2026-10-11T00:00:00 --json
python3 scripts/cli.py counts --limit 5 --bbox=2.35,48.85,2.36,48.86 --format geojson
```

- `dataset` reads catalogue licence, publisher, Europe/Paris timezone, hourly
  granularity and the catalogue row count. It returns no counter rows.
- `counts` reads at most 20 records from `comptages-routiers-permanents` after
  confirming the live licence is ODbL. `--limit` is required.
- `--from` and `--to` are Europe/Paris hour-ending stamps
  `YYYY-MM-DDTHH:00:00`, inclusive, at most 48 stamps, with no UTC offset.
- `--bbox` is WGS84 `minLon,minLat,maxLon,maxLat`. Filtering is upstream point
  containment of `geo_point_2d`, not line intersection. For a negative
  longitude use `--bbox=...`.
- `--flow observed` keeps rows with a counted `q`. `--flow missing` keeps rows
  where `q` was not counted. Null stays null.
- `--traffic-state` and `--arc-state` take the published French labels exactly.
- `--fixture` replays local tests and does not call the network.

`t_1h` is the end of the counted hour in Europe/Paris. The stamp
`2019-01-01T01:00:00` covers 00:00 to 01:00 that morning.
`derived_period_start` is those preceding 60 minutes. Do not read `t_1h` as
UTC or as the start of the hour.

Null `q` means the loop did not produce a vehicle count. Occupancy-only
stations are normal. Do not replace null with zero. `etat_barre` other than
`Ouvert` is not an open-road count. `Inconnu` is not fluid traffic.

This skill does not read the historical counter dataset, the Lambert-93
referential, or any host other than `opendata.paris.fr`.

Run `scripts/test_contract.py` for the offline contract. Run
`scripts/smoke_test.py` for fixture checks and one bounded live probe.
