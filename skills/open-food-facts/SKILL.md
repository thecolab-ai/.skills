---
name: open-food-facts
description: "Look up a food product by barcode on Open Food Facts, and run a bounded country or category search. Use for keyless public product name, brand, quantity, category and country facts. Do not use for Open Products Facts, product photos, personal nutrition advice, or database dumps."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "food"
  thecolab.source_owner: "Open Food Facts"
  thecolab.source_type: "community"
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
  thecolab.source_url: "https://world.openfoodfacts.org"
  thecolab.allowed_domains: "world.openfoodfacts.org"
  thecolab.last_verified: "2026-10-11"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# Open Food Facts

Look up one food product by barcode, or one page of country/category matches.
Reads stay on `world.openfoodfacts.org`. This skill does not query Open Products
Facts, download photos, write products, or mirror the database.

Use `scripts/cli.py`. Every data command accepts `--json`. Human text is the
default. Read `references/source-notes.md` for the verified envelope, rate
limits, and licence.

## Commands

```bash
python3 scripts/cli.py product 3017624010701
python3 scripts/cli.py product 00012345678905 --json
python3 scripts/cli.py search --country new-zealand --category yogurts --limit 5 --json
```

`product` takes an 8 to 14 digit barcode and keeps leading zeros in the request.
A missing product is an empty `results` array, not an outage. Fields the source
omits are listed in `missing_fields` and are not invented.

`search` calls the documented v2 structured search only. Pass `--country`,
`--category`, or both. `--limit` is 1 to 10 and selects the first page only.
There is no full-text search command.

## Boundaries

- Product read uses API v3. Search uses API v2 because v3 has no structured search.
- Published Nutri-Score and NOVA values are product attributes, not personal advice.
- Images are out of scope. ODbL share-alike and CC BY-SA photo terms are in
  `references/source-notes.md`.
- One command makes one request. Product reads are documented at 15 per minute
  per IP, and search at 10 per minute per IP.

## Resources

- `scripts/cli.py` — canonical command entrypoint
- `scripts/test_contract.py` — deterministic contract and parser fixtures
- `scripts/smoke_test.py` — fixture checks and a bounded live probe
- `references/source-notes.md` — source envelope, licence, and error semantics
