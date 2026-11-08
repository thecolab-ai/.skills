# Animates NZ API and parser notes

Verified against public pages on 2026-07-18. This is an unofficial read-only connector; upstream HTML and Magento internals are not a public stability contract.

## Sources

- Website: `https://www.animates.co.nz/`
- Search: `GET /rest/default/V1/search` with Magento `quick_search_container` criteria
- Search fallback: `GET /sitemap.xml` (sitemap index), then the product sitemap it lists (`/media/sitemapproduct.xml`, about 5,700 products, ~14 MB XML or ~0.5 MB gzipped), streamed
- Detail: `GET /catalog/product/view/id/<id>` or a public `.html` product URL
- Authentication: none for implemented requests

The search response supplies ranked product entity IDs. It can include large aggregation buckets, so the CLI caps the response at 1,000,000 bytes, requests at most 10 IDs, and does not emit raw data. Each selected ID is resolved through a public product page and accepted only when Product JSON-LD contains a name and price.

### Sitemap fallback (since 30 October 2026)

From the 30 October 2026 nightly smoke run onwards, the Magento quick search answers HTTP 200 with `total_count: 0` and no items for every query (for example "dog food"), while product pages still serve Product JSON-LD. The nightly passed on 29 October with the same CLI, so this is an upstream change. When the Magento search returns no IDs, `search` streams the public product sitemap. It keeps entries whose URL slug or image title contains every query word (case-insensitive, with a simple plural match), stops at `--limit` matches, and verifies each match through its product page as above. The payload reports `search_source: "sitemap_fallback"`, keeps the Magento `total` (0), lists both URLs in `source_urls`, and adds warnings. These say that the order is sitemap order, not relevance ranking, and give how many entries were scanned and matched. With Magento results, `search_source` is `"magento_search"` and the sitemap is not read. robots.txt allows the sitemap and `.html` product pages; it disallows `/catalogsearch/`, so the HTML search page is not used. The wire body is capped at 16,000,000 bytes, the decompressed XML at 48,000,000 bytes and a single `<url>` entry at 1,000,000 bytes.

## JSON-LD fields

Observed Product fields include `@id`, `name`, `sku`, `mpn`, `image`, `category`, `brand`, `description`, and `offers`. The Offer commonly supplies `url`, `price`, `priceCurrency`, and schema.org `availability`. Parsers tolerate list/dict offers, missing optional fields, HTML entities, malformed unrelated JSON-LD, and `@graph` wrappers.

## Output contract

Every successful command includes `retailer`, `command`, `source_url`, and UTC `retrieved_at`. Product records include normalized name, SKU, brand, price, currency, availability, image, description, and their detail source URL. A search that returns IDs but no parseable products is an error, not an empty success.

## Safety and stability

- GET only; no cart, checkout, account, payment, Petpoints, prescription, booking, grooming, hire, or mutation endpoints.
- Default timeout: 10 seconds. Detail HTML cap: 1,000,000 bytes. Search cap: 1,000,000 bytes. Search result cap: 10.
- One search can make one search request plus one detail request per selected ID; the sitemap fallback adds two sitemap requests.
- Prices and availability are live online snapshots, not guaranteed store stock or price history.
- If Magento or JSON-LD changes, update fixture assertions before loosening parsing.
