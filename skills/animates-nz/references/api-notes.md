# Animates NZ API and parser notes

Verified against public pages on 2026-07-18. This is an unofficial read-only connector; upstream HTML and Magento internals are not a public stability contract.

## Sources

- Website: `https://www.animates.co.nz/`
- Search: `GET /rest/default/V1/search` with Magento `quick_search_container` criteria
- Detail: `GET /catalog/product/view/id/<id>` or a public `.html` product URL
- Authentication: none for implemented requests

The search response supplies ranked product entity IDs. It can include large aggregation buckets, so the CLI caps the response at 1,000,000 bytes, requests at most 10 IDs, and does not emit raw data. Each selected ID is resolved through a public product page and accepted only when Product JSON-LD contains a name and price.

## JSON-LD fields

Observed Product fields include `@id`, `name`, `sku`, `mpn`, `image`, `category`, `brand`, `description`, and `offers`. The Offer commonly supplies `url`, `price`, `priceCurrency`, and schema.org `availability`. Parsers tolerate list/dict offers, missing optional fields, HTML entities, malformed unrelated JSON-LD, and `@graph` wrappers.

## Output contract

Every successful command includes `retailer`, `command`, `source_url`, and UTC `retrieved_at`. Product records include normalized name, SKU, brand, price, currency, availability, image, description, and their detail source URL. A search that returns IDs but no parseable products is an error, not an empty success.

## Safety and stability

- GET only; no cart, checkout, account, payment, Petpoints, prescription, booking, grooming, hire, or mutation endpoints.
- Default timeout: 10 seconds. Detail HTML cap: 1,000,000 bytes. Search cap: 1,000,000 bytes. Search result cap: 10.
- One search can make one search request plus one detail request per selected ID.
- Prices and availability are live online snapshots, not guaranteed store stock or price history.
- If Magento or JSON-LD changes, update fixture assertions before loosening parsing.
