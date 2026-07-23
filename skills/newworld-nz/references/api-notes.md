# New World NZ API notes

This skill is an unofficial wrapper around the public catalogue and personal-account web APIs used by `newworld.co.nz`. Account history remains read-only; explicit shopping-list and cart-product management are supported.

## Source and auth

- Website: `https://www.newworld.co.nz`
- Edge API: `https://api-prod.newworld.co.nz/v1/edge`
- Club+ login: `https://login.clubplus.co.nz` and `https://api-prod.clubplus.co.nz/retail-fsl-online-edge`
- Public auth model: short-lived guest bearer token from `POST /api/user/get-current-user`
- Personal auth model: Club+ password login, optional MFA, one-time secure-code exchange, then a New World access token plus rotating Club+ refresh token
- Guest token cache: `~/.cache/newworld-cli/guest-token.json`
- Personal token cache: `~/.cache/newworld-cli/auth.json` with file mode `0600`
- Default store: New World Papakura, `ef977d89-f3d8-4e8b-8a48-b895ded38646`

Public commands require no private credential. Personal commands read `NEWWORLD_USERNAME` and `NEWWORLD_PASSWORD` from the environment. The password is never cached.

## Endpoint families used

- `GET /store` for stores
- `GET /store/{storeId}/categories` for category trees
- `POST /search/paginated/products` for search and specials
- `POST /store/{storeId}/decorateProducts` for exact product IDs

## Personal endpoint families

- `GET /order/paged` for paginated online and in-store order history
- `GET /order/{orderId}` for one online order
- `GET /order/instore?orderId={orderId}` for one in-store order
- `POST /order/previousPurchases` for previously purchased products
- `GET /list` for saved lists
- `GET /list/{listId}` for one saved list
- `PUT /list` to create an empty saved list
- `POST /list/{listId}/rename` to rename a saved list
- `DELETE /list/{listId}` to delete a saved list
- `POST /list/{listId}/update-product` to add a product, change its quantity, or remove it with quantity `0`
- `GET /cart` to retrieve the current cart
- `POST /cart` with `products[]` to set product quantities; quantity `0` removes a product

The skill deliberately exposes no checkout, payment, timeslot, fulfilment, profile, favourite, or order mutation. List deletion and list/cart product removal require the CLI's explicit `--yes` guard.

Cart product payloads use `productId`, `sale_type`, and target `quantity`. `cart-add` first reads the cart and increments the target; `cart-update` sets it directly. `WEIGHT` quantities are grams, while `UNITS` quantities are item counts. Bare numeric product IDs are normalised to `KGM` variants for `WEIGHT` and `EA` variants for `UNITS`; an exact supplied variant ID is preserved.

## Token lifecycle

1. Fetch a short-lived Apigee bootstrap bearer from Club+'s public same-origin credential route.
2. Submit the environment-provided email/password with a stable generated device UUID.
3. If required, verify the six-digit MFA code with the returned half-access token and `phvToken`.
4. Request a New World `MNW` secure token and post it with browser fingerprints to New World's `/api/user/login/sso` route.
5. Cache only the New World bearer, rotating Club+ refresh token, expiry hints, and device UUID.
6. Refresh through Club+, obtain another one-time secure token, and repeat the New World SSO exchange. A raw `NEWWORLD_REFRESH_TOKEN` override can instead use New World's Edge refresh route.

## Stability and safety

- Live-verified on 2026-07-24 with a temporary list create/rename/add/update/remove/delete cycle and a cart add/update/remove cycle; both were read back after each mutation and the original list/cart state was restored.
- Treat prices as live store-specific snapshots, not historical facts.
- Treat authenticated output and token files as personal secrets.
- Endpoint shapes can change without notice because this is not an official API.
- If a request fails, retry once with `token --refresh` or delete the token cache before assuming the product is unavailable.
- For personal commands, use `auth refresh` and then `auth login` before treating an endpoint as unavailable.
- Perform a list or cart mutation only when the account holder explicitly requests that exact change.
- Keep `--yes` on list deletion and list/cart product removal, and do not use a zero quantity through an update command to bypass it.
- Avoid high-volume scraping; use narrow queries and small limits unless the user explicitly needs broader coverage.
