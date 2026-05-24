# Bargain Chemist NZ API notes

This skill is an unofficial lightweight wrapper around public read-only endpoints used by `bargainchemist.co.nz`.

## Source and auth

- Website: `https://www.bargainchemist.co.nz/`
- Boost Commerce search endpoint: `https://services.mybcapps.com/bc-sf-filter/search`
- Boost Commerce suggest endpoint: `https://services.mybcapps.com/bc-sf-filter/search/suggest`
- Shopify product JSON endpoint: `https://www.bargainchemist.co.nz/products/{handle}.js`
- Shopify shop id in Boost requests: `bargain-chemist.myshopify.com`
- Auth model for supported commands: none

No username, password, account cookie, private token, cart id, prescription flow, or browser session is required for the implemented read-only operations.

## Endpoint families used

### Product search

`GET https://services.mybcapps.com/bc-sf-filter/search`

Observed query parameters:

```text
_=pf
shop=bargain-chemist.myshopify.com
page=1
limit=12
sort=relevance
locale=en
event_type=init
pg=search_page
build_filter_tree=true
q=<term>
product_available=true
variant_available=true
return_all_currency_fields=false
currency=NZD
country=NZ
```

Useful observed response fields:

- `total_product`
- `total_page`
- `products[]`
- product fields including `id`, `title`, `handle`, `price_min`, `price_max`, `available`, `vendor`, `product_type`, `body_html`, `images`, `images_info`, and `variants[]`

Product page URL pattern:

```text
https://www.bargainchemist.co.nz/products/<handle>
```

### Suggestions

`GET https://services.mybcapps.com/bc-sf-filter/search/suggest`

Observed query parameters:

```text
shop=bargain-chemist.myshopify.com
locale=en
q=<term>
re_run_if_typo=true
event_type=suggest
pg=search_page
return_all_currency_fields=false
recent_search=<term>
enable_default_result=false
```

Observed response fields include `total_product`, `products[]`, `suggestions`, `collections`, `pages`, `did_you_mean`, and `all_empty`.

### Product detail

`product <handle-or-url>` uses Shopify's public product JSON route:

```text
GET https://www.bargainchemist.co.nz/products/{handle}.js
```

Live read-only checks confirmed this endpoint for handles returned by Boost search, such as `panadol-liquid-caps-16s`. The response includes Shopify product fields such as `id`, `title`, `handle`, `vendor`, `type`, `available`, `price`, `variants[]`, `images`, and `featured_image`. Prices from this route are integer cents and are normalized to NZD decimal values by the CLI.

If Shopify product JSON is unavailable for a handle, the CLI attempts a read-only Boost search fallback and returns an exact handle match when present. The fallback is documented in the JSON response with `fallback`.

## CLI output shape

The CLI normalizes product records into:

- `id`
- `title`
- `handle`
- `url`
- `source_url`
- `price_min`
- `price_max`
- `available`
- `vendor`
- `product_type`
- `body_html`
- `variants`
- `images`

Top-level JSON includes `source`, `source_url`, `query` or `handle`, `total_product`, and `results`. Use `--raw` only when the caller needs the original API payload for debugging.

## Safety boundary

- Treat prices and availability as live public website snapshots, not historical facts.
- Medicine availability is not medical advice and does not imply suitability, dosage, or safety for a person.
- Endpoint shapes and public storefront behavior can change without notice because this is not a formal public API.
- Keep requests narrow and human-scale; do not build high-volume scrapers or redistribute product data as a dataset.
- Do not use this skill for cart mutation, checkout, order placement, prescription uploads, account actions, delivery actions, payment actions, or logged-in/personalised workflows.
- Do not commit credentials, cookies, raw HAR captures, private screenshots, browser session data, or checkout/account/prescription payloads.
