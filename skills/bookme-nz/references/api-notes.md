# Bookme NZ API notes

This skill is an unofficial lightweight wrapper around public Bookme NZ deal endpoints used by `bookme.co.nz`.

## Source and auth

- Website: `https://www.bookme.co.nz`
- Activity/restaurant deal API: `https://www.bookme.co.nz/things-to-do/json/home/getdeals`
- Activity text search API: `https://www.bookme.co.nz/things-to-do/json/{region}/activities-text-search/{query}/hot-deals`
- Detail pages: public `https://www.bookme.co.nz/things-to-do/{region}/activity/{slug}/{id}` and `https://www.bookme.co.nz/restaurants/{region}/{slug}/{id}` pages
- Auth model for this skill: none for supported read-only requests

No username, password, account cookie, private token, browser session, booking flow, or checkout token is required for implemented commands.

## Endpoint families used

- `GET /things-to-do/json/home/getdeals?region={slug}&begin={n}&end={n}&filter=featured|discount|low|high&classification=Activities&requiredeals=true`
- `GET /things-to-do/json/home/getdeals?...&activityTypeDetails={category_id}` for activity category filters
- `GET /things-to-do/json/home/getdeals?...&classification=Dining&subclassification=breakfast|lunch|dinner&restaurantDate=&restaurantDateYear=2026&requiredeals=true` for restaurant deals
- `GET /things-to-do/json/{region}/activities-text-search/{query}/hot-deals` for public keyword search
- Public detail pages expose Schema.org `Product` JSON-LD plus inline `window.productPricePoints` and `window.possiblePrices` arrays used to infer current discounted option prices

## Useful response fields

- `deal_id`, `deal_name`, `activity_ref`, `href`
- `price_raw`, `deal_price`, `deal_cents`
- `deal_saving`, usually `Save $...` for activity discounts
- `reduction_raw` and `deal_reduction`, used as the authoritative discount percent
- `deal_date_from`, `deal_date_to`, `deal_spaces`
- `review_rating`, `review_count`, `review_percentage`
- `coupon` for restaurant coupon-style deals
- `soldOut`, `deal_sold_out`, `isComingSoon`
- `list_complete` for pagination

## Discovery note

Bookme activity pages server-render the first deal cards, but the live site also loads and filters results through `bookme-home-min.js`. The useful public call discovered there is:

```text
/things-to-do/json/home/getdeals?region=auckland&begin=0&end=25&filter=featured&classification=Activities&requiredeals=false
```

Restaurant pages render empty `deals_list` containers and populate them with the same `getdeals` endpoint using `classification=Dining` plus `subclassification`.

The search box calls:

```text
/things-to-do/json/{region}/activities-text-search/{query}/hot-deals
```

## Discount handling

Discount commands intentionally require `reduction_raw > 0`. Bookme can return cards with `deal_saving` values such as `Price guarantee` or reservation-only copy; those are useful listings but are not current price reductions and are excluded from `deals`, `cheapest`, `hot`, and `search` results.

Normal price is calculated as `price_raw + parsed Save $...` when `deal_saving` contains a dollar saving. Detail pages can provide richer normal-price comparisons through `window.productPricePoints`.

## Stability and safety

- Treat all fields as live snapshots; same-day prices, spaces, dates, and discounts can change quickly.
- Endpoint shapes and filter names can change without notice because this is not a formally supported public API.
- Keep usage narrow and human-scale.
- Do not use this skill for booking, checkout, payment, login, favourites, account actions, voucher redemption, or operator management.
- Do not commit cookies, account data, HARs, JavaScript bundles, HTML dumps, or screenshots with private information.
