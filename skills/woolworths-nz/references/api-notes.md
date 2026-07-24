# Woolworths NZ API notes

This is an unofficial wrapper around endpoints currently used by `woolworths.co.nz`.

## Source and authentication

- Website/API origin: `https://www.woolworths.co.nz`
- Public product lookup requires no account.
- Personal endpoints use the website's authenticated cookie session and XSRF token.
- Sign-in starts at `GET /api/v1/bff/initiate-oidc-signin?redirectUrl=...`, passes through Woolworths IAM/Auth0, and returns to the website BFF.
- Because the Auth0 identifier step can present a browser challenge, raw credential POSTs are not a supported login method. The optional Camoufox helper performs the normal browser flow.
- Only resulting Woolworths cookies are persisted with mode `0600`; credentials remain in environment variables. The cache is atomically created and bound to a SHA-256 hash of the normalised username so it cannot be silently reused for different supplied credentials.

## Public product endpoints

- `GET /api/v1/products?target=search&search={query}&inStockProductsOnly=false&size={limit}`
- `GET /api/v1/products?target=specials&size={limit}`
- `GET /api/v1/products?target=browse&categoryId={id}&size={limit}`
- `GET /api/v1/products/{sku}`

## Personal read endpoints

- `GET /api/v1/bff/get-user` — validate the website session
- `GET /api/v1/shoppers/my/past-orders` — paged order history (`page`, `dateFilter`)
- `GET /api/v1/shoppers/my/past-orders/{orderId}`
- `GET /api/v1/shoppers/my/past-orders/{orderId}/items`
- `GET /api/v1/shoppers/my/past-orders/items` — products from all past orders
- `GET /api/v1/shoppers/my/favourites`
- `GET /api/v1/shoppers/my/saved-lists`
- `GET /api/v1/shoppers/my/saved-lists/{listId}/items`
- `GET /api/v1/trolleys/my`

## Tax-invoice SKU enrichment

Woolworths' tax-invoice PDF contains the financially authoritative line
description, ordered/supplied quantities, unit price, and amount, but not a
catalogue SKU. The matching past-order items response contains current product
metadata and SKUs, but its price fields are not necessarily the historical paid
price.

`invoice-items` therefore:

1. Parses and verifies the PDF's Order Confirmation/Invoice Number against the
   requested order ID.
2. Parses item rows from the PDF's `Ref`, `Description`, `Ordered`, `Supplied`,
   `Unit Price`, and `Amount` table.
3. Fetches `GET /api/v1/shoppers/my/past-orders/{orderId}/items`.
4. Performs a one-to-one, normalised product-name match and emits a confidence,
   method, and ambiguity flag for every joined row.

The invoice remains the source for historical quantity/price fields. The API
response is used only for SKU/current catalogue identity. Low-confidence rows
are left unmatched. The parser requires a text-based Woolworths invoice PDF and
the optional `pdfplumber` package.

## Saved-list writes

- `POST /api/v1/shoppers/my/saved-lists`
  - Empty: `{"listName":"...","addFromListSource":"Unspecified"}`
  - Optional `addFromListSource`: `Trolley`, `FavouritesAllItems`, `MySavedList`, `PastOrders`, or `PastOrdersMasterAllItems`
  - `sourceListId` is included for a source list or order.
- `DELETE /api/v1/shoppers/my/saved-lists/{listId}`
- `POST /api/v1/shoppers/my/saved-lists/{listId}/items/{sku}`
  - `{"itemsToAdd":[{"sku":"705692","quantity":1}]}`
- `DELETE /api/v1/shoppers/my/saved-lists/{listId}/items/{sku}`

## Trolley writes

- `POST /api/v1/trolleys/my/items`
  - `{"sku":"705692","quantity":2,"pricingUnit":"Each"}`
  - The same endpoint sets a target quantity; quantity zero removes a product.
- `DELETE /api/v1/trolleys/my/items` — clear the trolley.

`Each` values should be whole counts. `Kg` supports weights. The skill does not expose checkout, place-order, payment, delivery-slot, active-order, account/profile, or loyalty mutation endpoints.

## Request headers and refresh

Requests use the web app's `x-requested-with`, `x-ui-ver`, `referer`, `origin`, and user-agent headers. Mutations also send the decoded `XSRF-TOKEN` cookie as `x-xsrf-token`. A definitive 401/403 rejection causes one browser login refresh and one retry. A safe GET that unexpectedly returns non-JSON may also refresh once. A mutation with an indeterminate non-JSON response is never replayed automatically.

## Stability and safety

- Treat prices as live online snapshots.
- Endpoint shapes can change because these are website APIs, not a documented public developer API.
- Avoid high-volume scraping.
- Never commit credentials, cookie caches, screenshots containing personal data, or live account fixtures.
- Never commit downloaded invoices, parsed invoice rows, or enriched order output; deterministic tests use synthetic products and table words.
- Use synthetic fixtures for tests and a unique temporary list/product for explicitly authorised live mutation tests.
- List/trolley changes must reflect an explicit user request. Order placement and checkout are always out of scope.
