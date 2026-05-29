# The Warehouse NZ API notes

This skill is an unofficial lightweight wrapper around public The Warehouse NZ storefront endpoints used by `thewarehouse.co.nz`.

## Source and auth

- Website: `https://www.thewarehouse.co.nz`
- Search/specials fragment endpoint: `https://www.thewarehouse.co.nz/search/updategrid`
- Product detail endpoint: `https://www.thewarehouse.co.nz/on/demandware.store/Sites-twl-Site/default/Product-Show?pid={sku}`
- Store finder endpoint: `https://www.thewarehouse.co.nz/on/demandware.store/Sites-twl-Site/default/Stores-FindStores`
- Auth model for supported commands: none

No username, password, account cookie, private token, or browser session is required for the default read-only operations. Optional `--browser` mode uses CloakBrowser only when requested, for the same public endpoints/pages, to reduce false CI/headless edge-blocking on public read-only workflows.

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

## Optional CloakBrowser mode

Repo-wide convention: `docs/browser-assisted-skills.md`. CloakBrowser upstream: <https://github.com/CloakHQ/CloakBrowser>.

`--browser` launches a headless CloakBrowser context with server-safe Chromium args, opens the public homepage to establish same-site browser context, and then performs read-only `fetch()` calls to the same search/specials/product/store endpoints. It does not log in, mutate carts, hold stock, add wishlist items, select delivery slots, or proceed toward checkout.

If CloakBrowser is not installed and `--browser --json` is requested, the CLI returns:

```json
{
  "error": "cloakbrowser_not_installed",
  "recommendation": "Recommend that the user installs CloakBrowser or reruns without --browser for the direct public HTTP path."
}
```

If the upstream returns CAPTCHA, queue, or challenge content, browser mode reports `browser_blocked`; agents should retry later or use the default direct public HTTP path when it works, not attempt to bypass the challenge.

## Stability and safety

- Treat prices, specials, availability, and store hours as live snapshots, not historical facts.
- MarketClub, personalised, region-specific, delivery, or logged-in prices may differ from the unauthenticated public view.
- Endpoint shapes and markup attributes can change without notice because this is not a formal public API.
- Avoid high-volume scraping and dataset redistribution; keep queries narrow and human-scale.
- Do not use this skill for cart mutation, checkout, wishlist changes, account actions, payments, or order placement.
- Do not commit cookies, tokens, screenshots with private data, raw browser captures, JS bundles, HARs, or HTML dumps.
