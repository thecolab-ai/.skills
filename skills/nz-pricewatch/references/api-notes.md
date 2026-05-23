# NZ Pricewatch API notes

This skill is an unofficial lightweight wrapper around public PriceSpy NZ pages used by `pricespy.co.nz`.

## Source and auth

- Primary website: `https://pricespy.co.nz`
- Search page: `GET /search?query={query}&category={category_id?}`
- Product page: `GET /product.php?p={product_id}`
- Categories page: `GET /categories`
- Auth model for this skill: none for supported read-only requests

No username, password, account cookie, private token, browser session, cart, checkout flow, or retailer account is required for implemented commands.

## Endpoint families used

- `GET /search?query=...` returns a Next.js/RSC page. Product cards are embedded in `self.__next_f.push(...)` chunks as `productCardData` objects.
- `GET /search?category=107` returns PriceSpy's modern search page for category sampling.
- `GET /product.php?p={id}` returns product detail. It exposes Schema.org `Product` JSON-LD, merchant `offerRows`, and price-history `historyItems` in embedded RSC chunks.
- `GET /categories` returns public category links such as `/category.php?k=107` for TVs and `/category.php?k=103` for Mobile Phones.

## Useful embedded fields

Search product cards:

- `product.id`, `product.name`, `product.brandName`
- `product.productLink`, `product.logo`
- `product.category.categoryName`, `product.category.categoryId`
- `product.coreProperties`, `product.storeCount`, `product.priceDrop`
- `offer.price`, `offer.storeName`, `offer.storeId`, `offer.stockStatus`, `offer.offerLink`

Product detail:

- Schema.org `Product.name`, `brand.name`, `offers.lowPrice`, `offers.highPrice`, `offers.offerCount`, `additionalProperty`
- `offerRows[].shop.name`, `shopId`, `shopOfferId`, `price.amount`, `stockStatus`, `condition`, `deal.percentage`
- `historyItems[].shopName`, `shopId`, `shopOfferId`, `date`, `price`, `active`

## Price history handling

PriceSpy's embedded `historyItems[].price` values are integer cents. The CLI converts them to NZD dollar amounts.

The product page currently embeds enough history points for recent movement checks. `history --days N` filters those points by date and reports a lowest-price movement summary:

- first lowest observed price in the window
- latest current lowest price from the offer list
- absolute and percent change
- direction: `down`, `up`, `stable`, or `unknown`

This is not a full historical archive export. It is sufficient for questions like "has this model dropped in the last month?" when the public page includes recent points.

## Discovery notes

PriceSpy NZ is a React/Next.js app with Cloudflare in front. Browser sniffing at `127.0.0.1:5100` showed that search and product data are mostly server-rendered in the public HTML/RSC payload rather than exposed through a clean standalone search API. The only simple XHR observed during search was `GET /api/search-suggestions?q=...`, which is useful for autocomplete but not enough for product price comparison.

PriceMe NZ (`priceme.co.nz`) returned a Cloudflare challenge (`403`, `cf-mitigated: challenge`) to plain public CLI requests during discovery. Because this skill must remain no-login and lightweight, PriceMe is not wired in.

GetPrice NZ (`getprice.co.nz`) was reachable, but PriceSpy provided the stronger NZ electronics/appliance aggregation plus product-level price history. GetPrice is left as a future fallback, not a current source.

## Stability and safety

- Treat results as live public snapshots; retailers can change prices, stock, promotions, shipping, and availability at any time.
- PriceSpy is an upstream comparison source, not the seller of record. Click through to the retailer before purchasing.
- The RSC field names are not a formal API contract and can change without notice.
- Keep usage narrow and human-scale. Do not crawl full categories or redistribute scraped datasets.
- Do not commit cookies, account data, HARs, JavaScript bundles, screenshots with private data, or raw browser captures.
