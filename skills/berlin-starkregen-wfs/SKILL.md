---
name: berlin-starkregen-wfs
description: "Read Berlin Starkregen flood model areas from the official Geoportal Berlin WFS. Use for Starkregengefahrenkarte feature types and bounded Modellgebiete names such as Neukölln. Does not download velocity-layer geometry."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "environment"
  thecolab.source_owner: "Senatsverwaltung für Stadtentwicklung, Bauen und Wohnen Berlin"
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
  thecolab.source_url: "https://gdi.berlin.de/services/wfs/ua_srgk"
  thecolab.allowed_domains: "gdi.berlin.de"
  thecolab.last_verified: "2026-10-11"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# Berlin Starkregen WFS

Read model-area names from the official Starkregengefahrenkarte WFS with the
Python CLI in `scripts/cli.py`. Velocity-layer geometry is listed by `types`
and is not downloaded.

## Commands

```bash
python3 skills/berlin-starkregen-wfs/scripts/cli.py types --json
python3 skills/berlin-starkregen-wfs/scripts/cli.py areas --count 1 --json
```

- `types` sends one GetCapabilities request and returns each feature type name,
  title, default CRS, and whether this skill can query it.
- `areas` sends one GetFeature request for `ua_srgk:a_modellgebiete`. `--count`
  defaults to 1 and cannot exceed 8. The service had 8 model areas when last
  verified. The command does not follow the WFS next link.
- Only `ua_srgk:a_modellgebiete` has `query` `areas`. The three
  Fließgeschwindigkeit types stay `query` `none`.

JSON output is `{"meta": {...}, "results": [...]}`. `meta` includes
`source_url`, `publisher`, `retrieved_at`, `licence`, and the Quellenvermerk
`attribution`. Area rows include id, name, CRS, and an envelope in source-CRS
metres. They do not include polygon coordinates. `latest_data` is omitted
because the feature does not state a survey date. The WFS `timeStamp` is a
response time and is not a data vintage.

## Limits and failures

Each command waits at most 10 seconds, stays on `gdi.berlin.de`, and refuses a
redirect to any other host. Capabilities are capped at 256 KiB and a model-area
response at 1 MiB. An empty body, malformed XML, an exception report, a missing
name, or a page that ignores `--count` is a schema failure. A well-formed
collection with `numberMatched` 0 is an empty result. A hits-style collection
that matches areas but returns none is a schema failure, not an empty success.
Licence or access text that is no longer the confirmed CC BY 4.0 statement
fails closed.

Exit codes follow `docs/contracts.md`: 2 invalid input, 4 blocked or
rate-limited, 5 upstream unavailable, 6 schema failure, 7 over the byte cap.

Read `references/source-notes.md` for the licence sentence, the observed area
names, and the dataset page that was not read. Run `scripts/test_contract.py`
for deterministic checks and `scripts/smoke_test.py` for the bounded live probe.
