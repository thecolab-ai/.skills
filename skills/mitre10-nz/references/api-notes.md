# Mitre 10 NZ API notes

This skill is an unofficial lightweight wrapper around public Mitre 10 NZ product and store endpoints used by `mitre10.co.nz`.

## Source and auth

- Website: `https://www.mitre10.co.nz`
- OCC API host: `https://ccapi.mitre10.co.nz`
- OCC base site: `/occ/v2/mitre10`
- Algolia app id: `CQ00O09OXX`
- Algolia search-only key: `edc61cb5be5216c9cc02459f13e33729`
- Product Algolia index: `retail_products_relevance`
- Auth model for this skill: none for read-only product search/detail/store requests

No username, password, account cookie, private token, or browser session is required for the implemented read-only operations. The Algolia key is a public browser search-only key exposed by the site configuration and may rotate.

## Endpoint families used

- `POST https://cq00o09oxx-dsn.algolia.net/1/indexes/*/queries` for product search and specials
- `GET https://ccapi.mitre10.co.nz/occ/v2/mitre10/products/{code}?fields=FULL&lang=en&curr=NZD` for exact product details
- `GET https://ccapi.mitre10.co.nz/occ/v2/mitre10/stores?fields=FULL&pageSize={limit}&lang=en&curr=NZD` for the all-store listing
- `GET https://ccapi.mitre10.co.nz/occ/v2/mitre10/geolocation/store-locator?fields=FULL&page={page}&pageSize={limit}&locationQuery={region}&lang=en&curr=NZD` for location-filtered stores

The captured HARs also showed supporting OCC endpoints such as:

- `GET /occ/v2/mitre10/cms/pages?...` for page CMS data
- `GET /occ/v2/mitre10/breadcrumbs/{page}` for breadcrumb metadata
- `GET /occ/v2/mitre10/c/postcodegroupid-postcode?postCode=7400`
- `GET /occ/v2/mitre10/geolocation/update-store?fields=FULL&staticStoreCode=53`
- `POST /occ/v2/mitre10/config/properties` for public web configuration, including `mitre10.algolia.index.config`
- `POST /occ/v2/mitre10/messageItem/getAllMessageItems`

## Algolia request shape

The CLI sends one Algolia multi-query request:

```json
{
  "requests": [
    {
      "indexName": "retail_products_relevance",
      "params": "analyticsTags=...&clickAnalytics=true&facets=...&filters=online%3Atrue%20AND%20availableNationWide%3Atrue&hitsPerPage=10&page=0&query=drill&ruleContexts=..."
    }
  ]
}
```

Search filters:

- `online:true AND availableNationWide:true`

Specials filters:

- `online:true AND availableNationWide:true AND prices.onNationalPromo:true`

## Headers

The CLI uses a small browser-compatible header set:

- `Accept: application/json, text/plain, */*`
- `Content-Type: application/json` for POSTs
- `Origin: https://www.mitre10.co.nz`
- `Referer: https://www.mitre10.co.nz/`
- `User-Agent: Mozilla/5.0 ... Chrome ... Safari/537.36`

Live tests with Python stdlib requests did not require cookies or a Cloudflare challenge. If OCC starts returning a 403, retry with the same `Accept`, `User-Agent`, `Origin`, and `Referer` headers and verify the endpoint in a browser capture before changing the skill.

## Commands and endpoints

- `search <query>` calls Algolia `retail_products_relevance` with the normal online/nationwide filters
- `specials [query]` calls Algolia `retail_products_relevance` with the promotional price filter
- `product <code>` calls OCC `products/{code}`
- `stores` calls OCC `stores`
- `stores --region <text>` calls OCC `geolocation/store-locator`

## Stability and safety

- Treat prices and stock flags as live online snapshots, not historical facts.
- Store-specific, Club, personalised, delivery, and account-specific pricing may differ for logged-in users.
- Algolia public search-only credentials and index names can rotate without notice.
- OCC endpoint fields can change because this is not an official public API contract.
- Avoid high-volume scraping; use narrow queries and small limits unless broader coverage is explicitly required.
- Do not use this skill for cart mutation, checkout, order placement, account actions, or authenticated data.
- Do not commit credentials, cookies, screenshots with private data, HAR files, JavaScript bundles, or raw browser captures.
