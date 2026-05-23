# The Warehouse NZ API notes

This skill is an unofficial lightweight wrapper around public The Warehouse NZ storefront endpoints used by `thewarehouse.co.nz`.

## Source and auth

- Website: `https://www.thewarehouse.co.nz`
- Search/specials fragment endpoint: `https://www.thewarehouse.co.nz/search/updategrid`
- Product detail endpoint: `https://www.thewarehouse.co.nz/on/demandware.store/Sites-twl-Site/default/Product-Show?pid={sku}`
- Store finder endpoint: `https://www.thewarehouse.co.nz/on/demandware.store/Sites-twl-Site/default/Stores-FindStores`
- Auth model for supported commands: none

No username, password, account cookie, private token, or browser session is required for the implemented read-only operations.

## Endpoint families used

- `GET /search/updategrid?q={query}&start={offset}&sz=32` for product search. The response is an HTML product-grid fragment with product data in `data-gtm-product` / `data-ga-product` attributes.
- `GET /search/updategrid?cgid=specials&q={query?}&start={offset}&sz=32` for specials. The optional `q` parameter filters within the specials category.
- `GET /on/demandware.store/Sites-twl-Site/default/Product-Show?pid={sku}` for product detail. The response includes schema.org Product JSON-LD and ecommerce detail metadata.
- `GET /on/demandware.store/Sites-twl-Site/default/Stores-FindStores?region={NZ-region-code}` for stores. Omitting `region` returns all public stores; region codes include `NZ-AUK`, `NZ-CAN`, and the other region codes exposed by the store finder page.

The site runs on Salesforce Commerce Cloud / Demandware (`Sites-twl-Site`). The implemented surface uses the public storefront controller endpoints rather than authenticated SLAS/SCAPI calls.

## Discovery notes

- The page HTML references Demandware storefront controllers such as `Product-Show`, `Search-SetSearchRegion`, and `Stores-FindStores`.
- The search JavaScript uses `/search/updategrid` and `/search/update` fragments for pagination, refinements, and infinite-scroll updates.
- The store locator JavaScript reads `data-find-stores-url="/on/demandware.store/Sites-twl-Site/default/Stores-FindStores"` and expects JSON with `stores.stores`.
- Product detail pages expose enough public JSON-LD for exact SKU lookup, while product-list pages expose concise product metadata in HTML data attributes.

## Stability and safety

- Treat prices, specials, availability, and store hours as live snapshots, not historical facts.
- MarketClub, personalised, region-specific, delivery, or logged-in prices may differ from the unauthenticated public view.
- Endpoint shapes and markup attributes can change without notice because this is not a formal public API.
- Avoid high-volume scraping and dataset redistribution; keep queries narrow and human-scale.
- Do not use this skill for cart mutation, checkout, wishlist changes, account actions, payments, or order placement.
- Do not commit cookies, tokens, screenshots with private data, raw browser captures, JS bundles, HARs, or HTML dumps.
