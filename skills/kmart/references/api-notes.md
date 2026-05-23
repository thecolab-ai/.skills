# Kmart API notes

This skill is an unofficial lightweight wrapper around public Kmart NZ and AU product search metadata and public store-location sitemaps.

## Source and auth

- NZ website: `https://www.kmart.co.nz`
- AU website: `https://www.kmart.com.au`
- Product search host: `https://ac.cnstrc.com`
- NZ Constructor.io key exposed by the web app: `key_EyiTrcbGw7IFH3wR`
- AU Constructor.io key exposed by the web app: `key_GZTqlLr41FS2p7AY`
- Auth model for supported commands: none

No username, password, account cookie, private token, browser session, or package install is required for the implemented read-only operations.

## Endpoint families used

- `GET https://ac.cnstrc.com/search/{query}?key={key}&num_results_per_page={limit}&page={page}&section=Products` for product search
- The same Constructor.io search endpoint with an exact SKU query for `product <sku>`, filtered client-side to exact `variation_id`, `id`, or `apn`
- `GET https://www.kmart.co.nz/store-detail/{locationId}/` for NZ official store-detail page discovery from verified current location IDs
- `GET https://www.kmart.com.au/sitemap/au/storelocation-sitemap.xml` for AU store-detail URL discovery

Constructor product records include fields such as `variation_id`, `id`, `Brand`, `price`, `prices`, `SavePrice`, `badges`, `variant_badges`, `Seller`, `Size`, `Colour`, `image_url`, `url`, and product descriptions. The CLI normalises those fields into stable JSON keys.

## Discovery note

Kmart NZ and AU share frontend infrastructure. The Next.js runtime config exposes GraphQL endpoints at:

- `https://api.kmart.co.nz/gateway/graphql`
- `https://api.kmart.com.au/gateway/graphql`

The public web bundle includes store/location GraphQL operations such as `getNearestLocations`, `getLocationDetail`, `getProductAvailability`, and `getPostcodeSuggestions`. Direct non-browser GraphQL calls returned Akamai access-denied responses during discovery, so this skill does not rely on GraphQL.

Product search and SKU lookup worked consistently through the public Constructor.io search host with only browser-like headers and the public keys exposed by the Kmart web app.

## Specials model

No dedicated unauthenticated Kmart specials endpoint was verified. The `specials` command performs a product search, defaulting to `sale`, and filters results by public product metadata:

- `clearance` flags
- `SavePrice` text
- `badges` or `variant_badges` containing clearance, sale, or special text
- price entries with a non-`list` `type`, such as `promo`

Treat this as a live promotional/clearance snapshot, not a complete catalogue of all Kmart specials. Constructor currently redirects the bare `clearance` search term to a category page rather than returning products, so the CLI falls back to `sale` for no-result clearance/specials redirects.

## Store-location caveat

The AU store sitemap returned AU store-detail URLs as expected. The NZ store sitemap was reachable but exposed shared/AU-style location slugs such as `airport-west` and `albury` under the `kmart.co.nz` domain. The `stores` command therefore does not use the NZ store sitemap. For NZ, it uses verified official Kmart NZ store-detail IDs and parses the live store-detail pages for shown results. Use store output for public URL discovery and lightweight metadata, not as a canonical trading-hours or stock-availability source.

## Stability and safety

- Treat prices as live online snapshots, not historical facts.
- Product availability, seller, and promotional metadata can change without notice.
- Endpoint shapes and public keys can change because these are not formally supported public APIs.
- Avoid high-volume scraping; use narrow queries and small limits unless broader coverage is explicitly required.
- Do not use this skill for login, OnePass, cart mutation, checkout, payment, order placement, reviews, or account actions.
- Do not commit HAR captures, JS bundles, HTML dumps, cookies, credentials, or screenshots with private information.
