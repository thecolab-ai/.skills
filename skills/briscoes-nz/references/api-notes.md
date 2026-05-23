# Briscoes NZ API notes

This skill is an unofficial lightweight wrapper around public read-only endpoints used by `briscoes.co.nz`.

## Source and auth

- Website: `https://www.briscoes.co.nz`
- Search provider: Klevu, discovered from Magento `storeConfig`
- Klevu search endpoint: `https://{klevu_search_url}/cs/v2/search`
- Magento GraphQL endpoint: `https://www.briscoes.co.nz/graphql`
- Auth model for supported commands: none

No username, password, account cookie, private token, browser session, or cart id is required for the implemented read-only operations.

## Discovery summary

The Briscoes storefront is an Adobe Commerce/Magento PWA. Homepage and bundle inspection showed Magento/PWA chunks, Adobe Commerce services, Klevu search/listing chunks, and Magento GraphQL operations. No Algolia, Coveo, Shopify storefront API, or public custom REST product-search surface was found for the supported workflows.

Useful live configuration query:

```graphql
query KlevuData {
  storeConfig {
    store_code
    klevu_search_url
    klevu_search_js_api_key
    quick_search_placeholder
  }
}
```

At discovery time this returned store code `briscoes`, Klevu host `aucs34.ksearchnet.com`, and public Klevu JS API key `klevu-173190000117617559`. The CLI fetches this config live before Klevu search calls rather than treating the values as secrets.

## Endpoint families used

- `POST /graphql` with `storeConfig { klevu_search_url klevu_search_js_api_key }` to discover the live Klevu search config
- `POST https://{klevu_search_url}/cs/v2/search` with a `SEARCH` record query for product keyword search
- `POST /graphql` with `products(filter: { sku: { eq: $sku } })` for exact SKU detail and Magento price-range data
- `POST /graphql` with `findStore` for public store-finder locations

Klevu search records include useful fields such as `sku`, `productplu`, `name`, `brand`, `price`, `salePrice`, `basePrice`, `currency`, `url`, `image`, `inStock`, `isDiscountPrice`, `category`, and `breadcrumb`.

## Specials framing

Briscoes did not expose a dedicated "specials" JSON endpoint in the discovered public workflow. The website's sale-heavy catalogue is represented in Klevu product records and Magento categories.

The CLI implements `specials` as a sale/deal-flagged search view:

- Klevu `isDiscountPrice` equals `Yes`
- current sale price is below base price when both values are present
- category labels contain sale, clearance, or deal terms

Klevu search records often expose the current sale price but not the original crossed-out price. For this reason, `specials` treats Klevu as discovery only, then fetches each candidate SKU through Magento `products(filter: { sku: { eq } })` and returns only products whose `price_range.minimum_price.final_price` is below `regular_price`. Use `product <sku> --json` for exact Magento `price_range` discount details after selecting a SKU.

## Stability and safety

- Treat prices and availability as live online snapshots, not historical facts.
- In-store prices, member/personalised offers, delivery availability, and clearance availability may differ.
- Endpoint shapes, Klevu field names, and required headers can change without notice because this is not an official public API.
- Avoid high-volume scraping; use narrow queries and small limits unless broader coverage is explicitly required.
- Do not use this skill for cart mutation, checkout, order placement, account actions, gift registry actions, or payment actions.
- Do not commit credentials, cookies, screenshots with private data, HAR captures, JS bundles, or raw HTML dumps.
