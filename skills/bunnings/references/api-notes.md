# Bunnings API notes

This skill is an unofficial lightweight wrapper around public Bunnings NZ/AU page data used by `bunnings.co.nz` and `bunnings.com.au`.

## Source and auth

- NZ website: `https://www.bunnings.co.nz`
- AU website: `https://www.bunnings.com.au`
- Auth model for supported commands: none

No username, password, account cookie, private token, or browser session is required for the implemented read-only operations. The CLI sends a browser-like `User-Agent`, `Accept`, `Accept-Language`, and `Referer`.

## Endpoint families used

- `GET /search/products?q={query}` for product search. Product results are embedded in `__NEXT_DATA__` as a hydrated Coveo search result.
- `GET /products/{category-path}` for category browse. Category children and product results are embedded in `__NEXT_DATA__`.
- `GET /{product-slug}_p{sku}` for product detail. The hydrated data includes `retail-product`, `product-retail-price`, `product-fulfilment`, and `product-aisle-item-location` query records when available.
- `GET /stores` for public store-region and store-detail links.
- `GET /stores/{region}/{store-slug}` for store detail, address, phone, opening hours, services, map URL, and coordinates.
- `GET /campaign/redemption-offers` for redemption/promotion products. Products are embedded in page state under related-product blocks.

The Next.js data route form, such as `/_next/data/{buildId}/search/products.json?q=drill&rest=products`, also returned public JSON during discovery. The CLI intentionally parses the HTML page state instead so it does not need to maintain a changing `buildId`.

## Browser-sniffed endpoints not used by the CLI

Browser traffic also showed these JSON/XHR calls:

- `GET /_apis/v1/stores/country/NZ?fields=FULL`
- `GET /_apis/v2/products/{sku}/priceInfo`
- `POST /_apis/v2/products/{sku}/fulfillment`
- `GET /_apis/v1/item-api/locations?locationCode={storeCode}&productCode={sku}`

Those calls returned `200` in the live browser session but plain stdlib requests returned `401` without the browser's guest/session authorization flow. They are documented for future discovery, but this lightweight CLI does not mint guest tokens and does not call them.

## Stability and safety

- Treat prices, stock, store hours, and promotions as live snapshots.
- Product price and stock are default-store snapshots unless the page data changes the selected store context.
- Search and category pages usually hydrate the first 36 product results; keep `--limit` within that practical first-page boundary.
- Bunnings may alter its Next.js state shape, Coveo fields, or promotion page layout without notice.
- Cloudflare/Bunnings allowed the public page reads with a browser-like user agent during testing; if stdlib requests begin failing, re-check the browser traffic and update the notes before changing the CLI.
- Do not use this skill for cart mutation, checkout, order placement, project list mutation, account actions, or authenticated trade/customer data.
- Do not commit credentials, cookies, raw authenticated captures, or screenshots with private data.
