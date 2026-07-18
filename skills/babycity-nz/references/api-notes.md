# babycity NZ API notes

Unofficial, read-only access to public storefront routes on `https://www.babycity.co.nz`.

## Verified sources

- Predictive product search: `GET /search/suggest.json?q={query}&resources[type]=product&resources[limit]={1..10}`
- Handle detail: `GET /products/{handle}.js`
- Store information: `GET /pages/store-locator`
- Public catalogue route also observed: `GET /products.json?limit={n}`; the CLI does not crawl it because predictive search is narrower.

All routes were verified without authentication. The CLI sends a descriptive User-Agent, uses HTTPS GET only, and defaults to a 10-second timeout.

## Output semantics

Search prices are decimal NZD strings normalised to numbers. Product `.js` prices are integer cents normalised to NZD decimal numbers. Every result includes the final `source_url` and UTC `retrieved_at`; prices are snapshots at that time, not price history.

`available_online` and each variant's availability reflect Shopify's online storefront. They do not represent stock at a babycity shop. The `stores` command returns official page metadata but does not infer inventory.

## Limits and failure modes

Search accepts 1–10 results in one request. Product lookup accepts a strict handle or `/products/<handle>` URL and performs one request. Redirects must remain on the configured storefront host. HTTP, timeout, DNS, malformed JSON, and unexpected response-shape failures produce concise stderr messages without tracebacks.

## Safety

No POST, PUT, PATCH, DELETE, cart, checkout, account, payment, booking, prescription, order, or other mutation is implemented. Public storefront formats may change without notice; keep lookups narrow and do not redistribute a catalogue scrape.
