# PB Tech NZ public source notes

PB Tech returns HTTP 403 to bare `urllib`/curl requests, but public pages load normally with browser-compatible request headers. The CLI uses a standard desktop Chrome-like header set and a PB Tech referer. No login, cookie, CAPTCHA, or cart session is required for supported read-only commands.

Verified public pages:

- Search/category: `https://www.pbtech.co.nz/search?sf=<query>` redirects/serves category or search result pages with embedded product cards.
- Product detail: `https://www.pbtech.co.nz/product/<CODE>` or full product URLs expose title, price, stock summary, MPN/part attributes, image, and category breadcrumbs in HTML.
- Stores: `https://www.pbtech.co.nz/stores` exposes store cards with names, addresses, phones, hours, detail links, and Google Maps direction links.

Useful HTML markers:

- Product card links: `data-product-code`, `data-scarabitem`, `product/<CODE>/...`
- Product title/subtitle: `h2.np_title` and `h3.np_title`
- Prices: `div.ginc ... span.full-price` or split `price-dollar`/`price-cents`
- Stock summary: `div.js-stock-info` with `data-stock-pb` and `data-stock-other`; text includes shipping and pickup counts.
- Store cards: `div.stores` with `data-coord`, `h3.store-name`, address subtitle, phone, hours, and `stores/<slug>` detail link.

Network sweep notes:

- Browser traffic showed mostly static JS/CSS/images, analytics, recommendations, and the lazy product endpoint `code/ajax_display_products_pdo.php`.
- The initial product data needed for a robust no-auth skill is already present in public HTML; the CLI deliberately avoids cart, wishlist, account, and checkout endpoints.

Boundary: public read-only retail data. Do not add cart, checkout, wishlist, sign-in, quote, or stock reservation actions.
