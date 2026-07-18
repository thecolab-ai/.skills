# Baby Factory NZ API and parser notes

Verified against public pages on 2026-07-18. This is an unofficial read-only connector; embedded page state and JSON-LD are not a public stability contract.

## Sources

- Website: `https://www.babyfactory.co.nz/`
- Search: `GET /search?q=<term>&page=<n>`
- Detail: `GET /<product-slug>`
- Authentication: none for implemented requests

Search HTML embeds a `window.category` JSON object. Observed fields include `items`, `totalitems`, `totalpages`, and `currentpage`. Product items contain a style-colour object, variants, prices, sale indicators, URL keys, and images. The CLI extracts that object defensively, normalizes at most 20 results, and never emits raw page state.

## JSON-LD fields

Detail pages expose Product JSON-LD with name, description, brand, image, SKU and one or more offers. Offers commonly include price, currency, availability, and SKU. Parsers tolerate list/dict offers, missing optional fields, malformed unrelated blocks, HTML entities, and `@graph` wrappers.

## Output contract

Every successful command includes `retailer`, `command`, `source_url`, and UTC `retrieved_at`. Search results expose normalized style, brand, colour, current/regular prices, sale state, variants, image, and product URL. Product and price-snapshot require a product name and public price; incomplete detail is an error.

## Safety and stability

- GET only; no cart, checkout, account, payment, booking, hire, registry, order, stock reservation, or mutation endpoints.
- Default timeout: 10 seconds. HTML cap: 1,200,000 bytes. Search result cap: 20.
- Prices are live online observations, not guaranteed store stock or price history.
- Product safety information is not advice; verify manuals, recalls, and manufacturer guidance separately.
