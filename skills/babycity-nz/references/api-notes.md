# babycity NZ API notes

Unofficial, read-only access to public storefront routes on `https://www.babycity.co.nz`.

## Verified sources

- Product search: `GET /shop?search={query}` (public storefront HTML; parse product cards from the results grid)
- Product detail: `GET /shop/{canonical-handle}` (public storefront HTML; canonical product URLs now live under `/shop/<slug>-<id>`)
- Store information: `GET /pages/store-locator`
- Search cards expose canonical `/shop/<slug>-<id>` anchors; the CLI preserves those canonical shop URLs instead of reconstructing legacy `/products/...` paths.

All routes were verified without authentication. The CLI sends a descriptive User-Agent, uses HTTPS GET only, and defaults to a 10-second timeout.

## Output semantics

Search-card and product-detail prices are decimal NZD values parsed from the public HTML storefront and normalised to numbers without cents conversion. Every result includes the final `source_url` and UTC `retrieved_at`; prices are snapshots at that time, not price history.

`available_online` and each variant's availability reflect the public online storefront. They do not represent stock at a babycity shop. The `stores` command returns official page metadata but does not infer inventory.

## Limits and failure modes

Search accepts 1–10 results in one request. Product lookup accepts a strict handle or canonical `/shop/<slug>` URL and performs one request; legacy `/products/<handle>` inputs are normalized when possible. Redirects must remain on the configured storefront host. HTTP, timeout, DNS, malformed JSON, and unexpected response-shape failures produce concise stderr messages without tracebacks.

## Safety

No POST, PUT, PATCH, DELETE, cart, checkout, account, payment, booking, prescription, order, or other mutation is implemented. Public storefront formats may change without notice; keep lookups narrow and do not redistribute a catalogue scrape.
