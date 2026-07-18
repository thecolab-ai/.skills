---
name: petstock-nz
description: Query Petstock NZ's public Algolia catalogue and product JSON-LD for bounded product search, current standard and Autoship prices, public offers, rewards signals, and online availability. Use when comparing Petstock NZ products or checking a known product handle, URL, or SKU. Read-only; no account, cart, checkout, payment, vet, booking, or other mutations.
---

# Petstock NZ

## Goal

Retrieve current public Petstock NZ catalogue, product, offer, price, and availability evidence without login or browser automation.

## Use this when

- Searching Petstock NZ products by keyword
- Checking a known product handle, public URL, or retailer SKU
- Comparing standard and conditional Autoship prices
- Capturing current online availability, delivery, and click-and-collect eligibility
- Reading public rewards signals without treating them as a member discount

## Do not use this for

- Account, cart, checkout, payment, order, Autoship enrolment, rewards redemption, vet, booking, prescription, or other mutations
- Veterinary advice or product-suitability decisions
- Store-specific stock promises, historical-price claims, bulk scraping, or GTIN/barcode lookup

## Workflow

1. Use `search` for bounded discovery from Petstock's shipped public read-only Algolia frontend configuration.
2. Use `product` with a result URL, handle, or numeric SKU for Product JSON-LD offers plus exact-SKU, exact-handle catalogue variants.
3. Use `price-snapshot` to keep standard, sale, Autoship, member-price, and rewards concepts separate.
4. Use `availability` for public online and fulfilment flags. These are snapshots, not reservations.
5. Add `--json` for agent chaining. Every successful command includes `source_url` and UTC `retrieved_at`.

## CLI

```bash
python3 skills/petstock-nz/scripts/cli.py search "dog food" --limit 5 --json
python3 skills/petstock-nz/scripts/cli.py product orijen-original-dog-food --json
python3 skills/petstock-nz/scripts/cli.py price-snapshot 122731000059 --json
python3 skills/petstock-nz/scripts/cli.py availability https://www.petstock.co.nz/products/orijen-original-dog-food --json
```

The global `--timeout N` option goes before the command and defaults to 10 seconds.

## Interpretation rules

- `sku` is the retailer-supplied identifier. Numeric shape alone does not make it a GTIN, UPC, EAN, or barcode; those fields remain null because no independently labelled barcode field was verified.
- `price_nzd` is the current public standard/sale price in the catalogue record.
- `autoship.price_nzd` is a conditional recurring-order offer, not a standard or member price.
- `member_price` remains unavailable unless a distinct public member-price field is verified.
- Rewards programme eligibility and Everyday Rewards point estimates are not cash prices or guaranteed entitlements.
- Confirm price, availability, eligibility, and product suitability on the source page before acting.

## Safety

- Uses Python standard library only and unauthenticated read-only requests.
- Calls only the shipped non-mutating Algolia frontend configuration and public Petstock product pages.
- HTTPS origins, ports, credentials, redirects, response sizes, result counts, pages, and timeouts are bounded.
- Missing or malformed search/product data fails closed with a clean error.

## Resources

- CLI: `scripts/cli.py`
- Fixture and outage-aware live checks: `scripts/smoke_test.py`
- Verified surface and field notes: `references/api-notes.md`
