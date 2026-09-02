---
name: customs-tariff-nz
description: "Search and look up official New Zealand Customs tariff classifications, rates, levies and formula records. Use for source-backed tariff research, not definitive landed-cost calculations or legal advice."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "trade"
  thecolab.source_owner: "New Zealand Customs Service"
  thecolab.source_type: "official"
  thecolab.auth: "none"
  thecolab.access_mode: "public-download"
  thecolab.data_class: "public"
  thecolab.writes: "false"
  thecolab.browser: "false"
  thecolab.risk: "medium"
  thecolab.cache_ttl: "none"
  thecolab.schema_version: "1"
  thecolab.skill_type: "public-download"
  thecolab.pack: "nz-public-data"
  thecolab.source_url: "https://www.customs.govt.nz/business/tariffs/tariff-classifications-and-rates/"
  thecolab.allowed_domains: "www.customs.govt.nz"
  thecolab.last_verified: "2026-09-02"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# Customs Tariff NZ

Use the read-only Python CLI to search the current official CusMod tariff data archive. Every result reports the archive's own update timestamp, retrieval time, source URL and interpretation caveats.

## Commands

```bash
# Search active classifications by words or a tariff-code prefix
python3 scripts/cli.py search "roasted coffee" --json
python3 scripts/cli.py search 0901 --as-of 2026-09-02 --limit 20 --json

# Look up one 10-digit tariff item and join its active rates and levies
python3 scripts/cli.py lookup 09.01.21.00.00 --json

# Inspect levy-formula coefficients by exact code, or explicitly use prefix mode
python3 scripts/cli.py formula 2 --json
python3 scripts/cli.py formula 2 --prefix --limit 20 --json
```

Human-readable output is the default. Add `--json` to every data command for stable machine-readable output. `--limit` accepts 1–100, `--as-of` accepts `YYYY-MM-DD`, and every live request has a 10-second timeout.

## Interpretation guardrails

- Treat classifications, rate formula codes, factors, levy codes and levy coefficients as source records—not a landed-cost quotation.
- Do not calculate or present definitive duty, levy, GST, freight, insurance, concession, preference or valuation outcomes from these fields alone.
- A classification can depend on composition, use, origin and legal notes. Confirm material decisions with New Zealand Customs or a qualified customs broker.
- The archive is intended for specialised broker software, is updated every 24 hours, and includes historical rows; commands filter rows against `--as-of`.
- `formula` exposes raw levy-formula coefficients. It does not turn them into payable amounts or infer units.
- The tariff archive does not include the separate concession archive and does not establish eligibility for preferential rates.

## Resources

- `scripts/cli.py` — canonical command entrypoint
- `scripts/customs_tariff.py` — bounded archive fetcher and parser
- `scripts/test_contract.py` — deterministic repository contract audit
- `scripts/smoke_test.py` — synthetic parser assertions and bounded live probe
- `tests/fixtures/tariff-synthetic.tar.gz` — deterministic CC0 synthetic archive fixture
- `references/source-notes.md` — provenance, schema, formula context and source limitations
