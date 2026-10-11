---
name: worksafe-nz
description: "Query WorkSafe New Zealand aggregated workplace incidents, concerns, serious harm notifications and fatalities. Use for construction-sector safety context, regional notification trends and industry comparisons."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "government"
  thecolab.source_owner: "WorkSafe New Zealand"
  thecolab.source_type: "official"
  thecolab.auth: "none"
  thecolab.access_mode: "public-download"
  thecolab.data_class: "public"
  thecolab.writes: "false"
  thecolab.browser: "false"
  thecolab.risk: "low"
  thecolab.cache_ttl: "24h"
  thecolab.schema_version: "1"
  thecolab.skill_type: "public-download"
  thecolab.pack: "nz-public-data"
  thecolab.source_url: "https://data.worksafe.govt.nz/"
  thecolab.allowed_domains: "data.worksafe.govt.nz,data-centre-public.s3.ap-southeast-2.amazonaws.com,www.worksafe.govt.nz"
  thecolab.last_verified: "2026-10-08"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# WorkSafe NZ

Use the keyless `scripts/cli.py` to fetch public workplace harm exports. All
filters run locally. Every data command supports `--json` with a `meta`/`results`
provenance envelope. Python 3.10+ standard library only.

```bash
python3 skills/worksafe-nz/scripts/cli.py sources --json
python3 skills/worksafe-nz/scripts/cli.py datasets --json
python3 skills/worksafe-nz/scripts/cli.py incidents --industry Construction --region Auckland --from 2025-01 --to 2025-12 --json
python3 skills/worksafe-nz/scripts/cli.py incidents --dataset concerns --industry Construction --limit 5 --json
python3 skills/worksafe-nz/scripts/cli.py incidents --dataset injuries_serious_harm --json
python3 skills/worksafe-nz/scripts/cli.py incidents --dataset serious_harm --json
python3 skills/worksafe-nz/scripts/cli.py fatalities --year 2025 --industry Construction --json
python3 skills/worksafe-nz/scripts/cli.py fatalities --industry Construction --industry-match any-level --json
python3 skills/worksafe-nz/scripts/cli.py summary --by industry --region Auckland --json
python3 skills/worksafe-nz/scripts/cli.py summary --dataset fatalities --by year --json
```

- `sources`: discover current CSV URLs and page update dates, including the
  separate historical HSE serious-harm file.
- `datasets`: download all five exports and report row counts, summed counts,
  first and latest CSV months. These counts may differ from dashboard labels.
- `incidents`: grouped notification rows, defaulting to notifiable incidents.
  `--dataset` also selects `concerns`, `injuries_serious_harm` (HSWA), or
  `serious_harm` (historical HSE). Default `--limit 100`; `--limit 0` returns all.
  Metadata gives matched rows, summed count and truncation explicitly.
- `fatalities`: counts grouped by year, top-level industry and region. Optional
  `--year` and `--industry` filters. No individual fatality records are returned.
- `summary --by industry|region|year`: sums notification counts or fatality rows
  for one `--dataset` (default `incidents`), with optional industry, region and
  inclusive `--from YYYY-MM --to YYYY-MM` filters.

Industry filters match the exact top-level industry name without case sensitivity
by default (`--industry-match top-level`). Use `--industry-match any-level` on
`incidents`, `fatalities` or `summary` to search substrings across all industry
levels and AFF2017 groups. This broader search can include other sectors, such
as Mining's Construction Material Mining, in a search for Construction.
Region filters use local government regions, not
WorkSafe operational zones. Construction provides W1 C&D sector safety context;
these exports contain no material inventories or building locations.

Every command accepts `--max-age SECONDS` (default 86400, `0` forces a refresh).
Downloads are cached in the skill's `.cache/` directory; expired caches are not
used on upstream failure. Cache writes are internal and optional. Each HTTP
request has a 10-second timeout. JSON failures use stable exit codes 2, 4, 5 or 6.

Treat notifications as reported events, not a census of harm or near misses.
Notification dates can differ from occurrence dates. Read
[references/source-notes.md](references/source-notes.md) for endpoint details,
fatality lag, licence uncertainty and breaks in comparability. Region labels do
not include coordinates, so bounding boxes and GeoJSON are not supported.

Run `scripts/test_contract.py` for offline parser, cache and output checks;
`scripts/smoke_test.py` checks synthetic fixtures and bounded live commands.
`tests/fixtures/` contains synthetic values in the source CSV and HTML shapes.
