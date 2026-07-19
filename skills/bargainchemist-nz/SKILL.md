---
name: bargainchemist-nz
description: "Query Bargain Chemist NZ public product search, suggestions, and Shopify product JSON through a lightweight no-login CLI. Use when the task involves Bargain Chemist NZ product lookup, current online prices, availability, product handles, or machine-readable public product data. Read-only; no cart, checkout, account, prescription, or order actions."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "retail"
  thecolab.source_owner: "Bargain Chemist"
  thecolab.source_type: "commercial"
  thecolab.auth: "none"
  thecolab.access_mode: "html-readonly"
  thecolab.data_class: "public"
  thecolab.writes: "false"
  thecolab.browser: "false"
  thecolab.risk: "low"
  thecolab.cache_ttl: "24h"
  thecolab.schema_version: "1"
  thecolab.skill_type: "html-readonly"
  thecolab.pack: "nz-commercial-web"
  thecolab.source_url: "https://www.bargainchemist.co.nz"
  thecolab.allowed_domains: "services.mybcapps.com,www.bargainchemist.co.nz"
  thecolab.last_verified: "2026-07-19"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# Bargain Chemist NZ

## Goal

Query live Bargain Chemist NZ product data through a small deterministic CLI with human-readable and JSON output, without browser automation or account login.

## Use this when

- A user asks for Bargain Chemist NZ product prices or availability
- A user wants to search Bargain Chemist products by keyword
- A user has a Bargain Chemist product handle or URL and wants public product details
- A workflow needs lightweight machine-readable Bargain Chemist public product data

## Do not use this for

- Non-Bargain Chemist retailers
- Authenticated account, loyalty, personalised, cart, checkout, prescription, order, delivery, or payment actions
- Redistributing scraped Bargain Chemist product data as a dataset
- Medical advice, medicine suitability, or historical pricing claims

## Preferred workflow

1. Run `scripts/cli.py` with the narrowest subcommand that answers the task.
2. Use `search` for keyword product lookup and `suggest` for typeahead-style discovery.
3. Use `product` when a product handle or Bargain Chemist product URL is known.
4. Use `--json` for agent chaining, comparisons, alerts, or structured reports.
5. Mention that prices and availability are live public website snapshots from an unofficial read-only wrapper.

## CLI

Run with:

```bash
python3 skills/bargainchemist-nz/scripts/cli.py <command> [flags]
```

Commands:

- `search <term> [--limit N] [--page N] [--json]` - Boost Commerce product search
- `suggest <term> [--limit N] [--json]` - Boost Commerce search suggestions and product suggestions
- `product <handle-or-url> [--json]` - Shopify product JSON for one product handle

Examples:

```bash
python3 skills/bargainchemist-nz/scripts/cli.py search panadol --limit 5
python3 skills/bargainchemist-nz/scripts/cli.py suggest vitamins --limit 5 --json
python3 skills/bargainchemist-nz/scripts/cli.py product panadol-liquid-caps-16s --json
```

## Resources

- CLI entrypoint: `scripts/cli.py`
- Live smoke test: `scripts/smoke_test.py`
- API and safety notes: `references/api-notes.md`

## Notes

- The implemented commands use only Python stdlib and unauthenticated public GET requests.
- Search and suggest use Bargain Chemist's Boost Commerce endpoints; product detail uses Shopify `products/<handle>.js`.
- Do not use this skill for cart, checkout, account, prescription, payment, or order mutations.
