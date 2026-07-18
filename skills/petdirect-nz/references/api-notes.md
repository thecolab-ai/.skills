# Petdirect NZ API and parser notes

Verified against public pages on 2026-07-18. This is an unofficial read-only connector; embedded state and JSON-LD are not a public stability contract.

## Sources

- Website: `https://petdirect.co.nz/`
- Search: `GET /search?q=<term>&page=<n>`
- Detail: `GET /p/<slug>/`
- Authentication: none for implemented requests

Search HTML embeds `window.__SERVER_STATE__`. The CLI extracts only the first object before `window.__LOCATION__`, locates the first result set under `initialResults`, caps the page at 2,700,000 bytes, returns at most 24 normalized hits, and never emits raw state. Observed hits contain `objectID`, `name`, `brandName`, `bcCustomUrl`, `cheapestVariant`, `variants`, images, categories, and ratings. Monetary search-state values are integer cents.

## JSON-LD fields

Detail pages expose ProductGroup JSON-LD with `productGroupID`, `sku`, `name`, `url`, `brand`, `image`, `description`, and `hasVariant`; variants expose offers with price, currency, and availability. The parser also accepts Product JSON-LD, list/dict offers, malformed unrelated blocks, and `@graph` wrappers.

## Output contract

Every successful command includes `retailer`, `command`, `source_url`, and UTC `retrieved_at`. Search returns normalized results and bounded variant arrays. Product and price-snapshot fail if no product name or public price can be established. Member and promotional prices are labelled from public state but may be conditional.

## Safety and stability

- GET only; no cart, checkout, account, payment, Pet Perks, subscription, prescription, booking, order, stock reservation, or mutation endpoints.
- Default timeout: 10 seconds. Search cap: 2,700,000 bytes. Detail cap: 1,500,000 bytes. Result cap: 24.
- Prices and availability are live online observations, not guaranteed stock or price history.
- Search state is large and duplicated in current HTML; keep extraction bounded and never add raw-output flags.
