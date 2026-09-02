# Woolworths NZ API notes

This is an unofficial wrapper around endpoints currently used by `woolworths.co.nz`.

## Source and authentication

- Website/API origin: `https://www.woolworths.co.nz`
- Public product lookup requires no account.
- Personal endpoints use the website's authenticated cookie session and XSRF token.
- Sign-in starts at `GET /api/v1/bff/initiate-oidc-signin?redirectUrl=...`, passes through Woolworths IAM/Auth0, and returns to the website BFF.
- Because the Auth0 identifier step can present a browser challenge, raw credential POSTs are not a supported login method. The optional Camoufox helper performs the normal browser flow.
- Only resulting Woolworths cookies are persisted with mode `0600`; credentials remain in environment variables. The cache is atomically created and bound to a SHA-256 hash of the normalised username so it cannot be silently reused for different supplied credentials.

## Current public product GraphQL

All current product calls use `POST /api/graphql?op-name={operation}` with a JSON
GraphQL envelope and the matching `WNZX-Operation-Name` header.

- `ProductSearch` with `CompositeSearchInput`
  - `byKeyword` for keyword search
  - `byCategoryKey` for category browse
  - `byProductPromotionSpecials` for specials
- `GetAllCategories` with optional `categoryKey`
- `GetProductDetails` with `key`

The CLI selects catalogue identity, descriptions, imagery, category hierarchy,
price and promotion fields, and purchase units. It does not send account cookies
for these public calls.

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
  - Empty: first verify `GET /api/v1/trolleys/my` has no products, then send `{"listName":"...","addFromListSource":"Trolley"}`. The current site returns HTTP 500 for the otherwise-valid `Unspecified` enum and exposes trolley-backed creation in its UI.
  - Optional `addFromListSource`: `Trolley`, `FavouritesAllItems`, `MySavedList`, `PastOrders`, or `PastOrdersMasterAllItems`
  - `sourceListId` is included for a source list or order.
- `DELETE /api/v1/shoppers/my/saved-lists/{listId}`
- `POST /api/v1/shoppers/my/saved-lists/{listId}/items/{sku}`
  - `{"itemsToAdd":[{"sku":"705692","quantity":1}]}`
  - The same upsert endpoint backs both `list-add` and the explicit
    `list-update` target-quantity command; they use separate CLI handlers.
- `DELETE /api/v1/shoppers/my/saved-lists/{listId}/items/{sku}`

## Current trolley GraphQL

- `CustomerCart` reads the signed-in user's trolley.
- `SetCartLineItemQuantity` accepts
  `{"input":{"cartLineItemQuantityUpdates":[{"variantKey":"705692-EA","quantity":2}]}}`.
  The quantity is a target quantity. The CLI reserves zero for the guarded
  `cart-remove --yes` path; `cart-update` accepts positive quantities only.
- `ClearCart` removes all products and still requires the CLI's `--yes` guard.

The CLI accepts either a catalogue SKU or the returned `variant_key`. If a plain
SKU is supplied, it resolves `GetProductDetails` and selects the variant matching
`--unit Each|Kg` before writing. An exact variant key is required when unit data
cannot disambiguate the product. Mutation responses are parsed as authoritative
trolley snapshots and GraphQL `errors` fail closed.

`Each` values should be whole counts. `Kg` supports weights. The skill does not expose checkout, place-order, payment, delivery-slot, active-order, account/profile, or loyalty mutation endpoints.

## Request headers and refresh

Requests use the web app's `content-type`, cache-control, `x-requested-with`,
`x-ui-ver`, `referer`, `origin`, and user-agent headers. Authenticated response
cookies are merged only for the Woolworths domain and atomically persisted in
the private, account-bound cache. Before a mutation, a safe authenticated GET
refreshes those cookies; mutations also send the decoded `XSRF-TOKEN` cookie as
`x-xsrf-token`. A definitive 401/403 rejection causes one browser login refresh
and one retry. A safe GET that unexpectedly returns non-JSON may also refresh
once. A mutation with an indeterminate non-JSON response is never replayed
automatically.

## Stability and safety

- Treat prices as live online snapshots.
- Endpoint shapes can change because these are website APIs, not a documented public developer API.
- Avoid high-volume scraping.
- Never commit credentials, cookie caches, screenshots containing personal data, or live account fixtures.
- Never commit downloaded invoices, parsed invoice rows, or enriched order output; deterministic tests use synthetic products and table words.
- Use synthetic fixtures for tests and a unique temporary list/product for explicitly authorised live mutation tests.
- List/trolley changes must reflect an explicit user request. Order placement and checkout are always out of scope.
