# Petstock NZ public catalogue notes

Verified against public Petstock NZ surfaces on 2026-07-18. This is an unofficial read-only connector; the frontend configuration, index fields, and JSON-LD are not stability contracts.

## Verified sources

- Storefront: `https://www.petstock.co.nz/`
- Product pages: `GET https://www.petstock.co.nz/products/<handle>`
- Search transport: `POST https://hx85npq0xp-dsn.algolia.net/1/indexes/*/queries`
- Public application ID: `HX85NPQ0XP`
- Shipped read-only frontend API key: embedded in Petstock's public Next.js frontend bundle; its live ACL exposes only `search`, `listIndexes`, and `settings`, with no indexing, deletion, key-management, or other mutation permission
- Product index: `product_prod`
- Variant index: `product_prod_all_variants`
- Authentication/login: none for implemented requests

The live `product_prod` index returned Petstock NZ product records whose constructed handles resolved to `petstock.co.nz` and whose corresponding Product JSON-LD offers used `NZD`. The CLI sends only bounded search requests to the two verified product indexes. It does not call settings, index listing, browse-key generation, indexing, mutation, account, cart, checkout, payment, vet, or booking endpoints.

## Observed catalogue fields

Records include retailer `sku`/`objectID`, title, vendor, handle, description, categories, image, size/colour, `price`, `originalPrice`, sale flags, online stock, fulfilment eligibility, `subscriptionAvailable`, `subscriptionPrice`, loyalty programme metadata, and Everyday Rewards point estimates.

Terminology is deliberately strict:

- `sku` stays a retailer SKU even when it is all digits.
- No separately labelled or independently validated GTIN/EAN/UPC/barcode field was observed, so `gtin` and `barcode` are null.
- `subscriptionPrice` is reported as an Autoship conditional price, not a member price.
- No distinct public member-price field was verified; the member-price object is explicitly unavailable.
- Loyalty redemption/earning metadata and Everyday Rewards points are rewards signals, not prices.

## Product JSON-LD

Public product pages expose `Product` JSON-LD with name, brand, description, images, aggregate rating, and a list of `Offer` objects. Offers expose NZD price, schema.org availability, and canonical Petstock variant URLs. The variant URL suffix is used only to associate an offer with a retailer SKU; it is not relabelled as a barcode.

The `product` command combines that source-page evidence with bounded exact-SKU filtered queries to `product_prod_all_variants`, then also requires each record's handle to match. This avoids silently truncating variants behind fuzzy product-name search limits. It fails rather than returning partial success when Product JSON-LD, canonical offer URLs, NZD prices, or exact catalogue variants cannot be established.

## Output contract

Every successful command includes `retailer`, `command`, `source_url`, and UTC `retrieved_at`.

- `search`: bounded product results, total/page metadata, NZD currency, and identifier semantics.
- `product`: public JSON-LD detail/offers plus exact-SKU, exact-handle variants from the catalogue index.
- `price-snapshot`: per-variant standard, original, sale, Autoship, unavailable member-price, rewards, and online availability fields.
- `availability`: per-variant public online stock and home-delivery/click-and-collect eligibility flags.

## Safety and stability

- HTTPS only. Storefront hosts are `petstock.co.nz` and `www.petstock.co.nz`; the only API host is `hx85npq0xp-dsn.algolia.net`.
- Redirects and final response URLs must remain on the originating allowlist; userinfo and non-443 ports are rejected.
- Default timeout: 10 seconds; maximum: 60 seconds.
- Response cap: 2,000,000 bytes. Search result cap: 24. Page cap: 50.
- Search and product parsers fail closed on malformed JSON, missing hit arrays, missing Product JSON-LD, non-NZD offers, or missing exact-SKU/exact-handle variants.
- Prices, rewards, and availability are live observations. Confirm them on the source page before purchase.
