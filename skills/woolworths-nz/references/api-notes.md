# Woolworths NZ API notes

This skill is an unofficial lightweight wrapper around public Woolworths NZ product endpoints used by `woolworths.co.nz`.

## Source and auth

- Website: `https://www.woolworths.co.nz`
- Product API: `https://www.woolworths.co.nz/api/v1/products`
- Product detail: `https://www.woolworths.co.nz/api/v1/products/{sku}`
- Auth model for this skill: none for read-only product search/detail requests

No username, password, account cookie, private token, or browser session is required for the implemented read-only operations.

## Endpoint families used

- `GET /api/v1/products?target=search&search={query}&inStockProductsOnly=false&size={limit}` for product search
- `GET /api/v1/products?target=specials&search={query?}&size={limit}` for specials
- `GET /api/v1/products?target=browse&categoryId={id}&size={limit}` for known numeric category ids
- `GET /api/v1/products/{sku}` for exact SKU details

The CLI sends the same lightweight browser-ish headers as the web app (`x-requested-with`, `x-ui-ver`, `referer`, `origin`, `user-agent`) but does not store credentials or cookies.

## Why this differs from `mcinteerj/woolies-nz-cli`

The upstream project supports login and trolley mutation by driving Camoufox for authentication, saving credentials/cookies, then calling authenticated cart endpoints. That is powerful but heavy: third-party dependencies, browser download, account credentials, cookie state, and mutation risk.

This TheColab skill is intentionally more performant and lighter for agent workflows:

- Python stdlib only
- no package install
- no browser automation
- no login or credential storage
- no cart/checkout mutation
- fast read-only product queries suitable for comparisons and reports

## Stability and safety

- Treat prices as live online snapshots, not historical facts.
- Club/personalised/account-specific prices may differ for logged-in users.
- Endpoint shapes and required headers can change without notice because this is not an official public API.
- Avoid high-volume scraping; use narrow queries and small limits unless broader coverage is explicitly required.
- Do not use this skill for cart mutation, checkout, order placement, or account actions.
- Do not commit credentials, cookies, screenshots with private data, or raw browser captures.
