---
name: nz-emergency-alerts
description: "Query official New Zealand CAP emergency alerts by location, region, agency and severity, aggregating NEMA Emergency Mobile Alerts and MetService severe weather watches/warnings. Use for current official alert retrieval; absence is not proof of safety."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "emergency"
  thecolab.source_owner: "National Emergency Management Agency and MetService"
  thecolab.source_type: "official"
  thecolab.auth: "none"
  thecolab.access_mode: "public-api"
  thecolab.data_class: "public"
  thecolab.writes: "false"
  thecolab.browser: "false"
  thecolab.risk: "low"
  thecolab.cache_ttl: "5m"
  thecolab.schema_version: "1"
  thecolab.skill_type: "public-api"
  thecolab.pack: "nz-public-data"
  thecolab.source_url: "https://www.civildefence.govt.nz/about/news-and-events/news-and-events/cap-feed-for-emergency-mobile-alert-is-now-live"
  thecolab.allowed_domains: "www.civildefence.govt.nz, alerthub.civildefence.govt.nz, alerts.metservice.com"
  thecolab.last_verified: "2026-07-22"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# NZ Emergency Alerts

Use the read-only Python CLI to retrieve and filter records exposed by the official first-party source.
Every command supports `--json`, bounded requests, stable exit codes, source URLs and retrieval timestamps.

## Commands

```bash
# list active official alert resources
python3 scripts/cli.py active --json
# match alerts near a point using published CAP geometry
python3 scripts/cli.py near --lat VALUE --lon VALUE --json
# filter alerts by region
python3 scripts/cli.py region NAME --json
# filter alerts by issuing agency
python3 scripts/cli.py agency NAME --json
# filter alerts by CAP severity
python3 scripts/cli.py severity LEVEL --json
# find an alert by CAP identifier
python3 scripts/cli.py alert ID --json
# show official feed health and freshness resources
python3 scripts/cli.py feed-status --json
```

Add `--limit N` (1–100) to bound any command. Human output is the default.

## Coverage and interpretation

- Aggregates two official CAP publishers: NEMA's Emergency Mobile Alert feed (NEMA,
  CDEM Groups, Health, Police, MPI, FENZ) and MetService's severe weather
  watches/warnings/advisories. Each alert row carries a `feed` field.
- Only issuing-agency feeds are treated as alerts.
- No alert in this result does not prove absence of danger.
- Preserve the issuing agency's instructions and timestamps.

The CLI reads both official public CAP index feeds (NEMA Atom, MetService RSS), follows the
complete bounded set of allowlisted linked CAP entries per feed before applying the result
`--limit`, and parses identifiers, update/cancel relationships, agency, status, event,
effective/expiry times, instructions and geometry. `near` validates latitude/longitude ranges
before network access, then uses published polygons and circles. Feed health reports age and
staleness per feed; if one feed is unavailable the other still answers with an explicit warning.
An empty current feed is not presented as proof of safety.

## Resources

- `scripts/cli.py` — canonical command entrypoint
- `scripts/test_contract.py` — deterministic repository contract audit
- `scripts/smoke_test.py` — parser fixture and bounded live probe
- `tests/fixtures/cap-atom.xml` — CAP namespaces, lifecycle and geometry fixture
- `references/source-notes.md` — feasibility, provenance and source limits
