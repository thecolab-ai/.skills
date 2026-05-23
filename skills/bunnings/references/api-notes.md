# Bunnings API notes

This skill is an unofficial lightweight wrapper around read-only Bunnings NZ/AU JSON endpoints used by `bunnings.co.nz` and `bunnings.com.au`.

## Source and auth

- NZ website: `https://www.bunnings.co.nz`
- AU website: `https://www.bunnings.com.au`
- NZ guest client: `budp_guest_user_nz`
- AU guest client: `budp_guest_user_au`
- Public API client header: `clientId: mHPVWnzuBkrW7rmt56XGwKkb5Gp9BJMk`

No username, password, cart, checkout, account cookie, or browser is required at runtime. The CLI reproduces the browser's guest bootstrap with stdlib `urllib`, caches the token briefly, and sends it as `Authorization: Bearer {token}` on `_apis` calls.

## Guest bootstrap flow

CDP discovery showed that the site loads `/static/guest.html`, whose `/scripts/guest.js` posts an OAuth fragment token back to the parent frame. The Next.js bundle creates the hidden iframe URL:

```text
GET https://authorisation.api.bunnings.co.nz/connect/authorize
  ?response_type=token
  &scope=chk:exec cm:access ecom:access chk:pub vch:public bsk:pub
  &client_id=budp_guest_user_nz
  &redirect_uri=https://www.bunnings.co.nz/static/guest.html
  &nonce={18 hex chars}
  &acr_values=adtid:{uuid1}

302 /Account/Login?ReturnUrl=...
302 /ExternalLogin/Challenge?scheme=localloopback&returnUrl=...
302 /ExternalLogin/Callback
302 /connect/authorize/callback?...
302 https://www.bunnings.co.nz/static/guest.html#access_token={jwt}&expires_in=432000&...
```

AU uses the same flow with `authorisation.api.bunnings.com.au`, `budp_guest_user_au`, and `https://www.bunnings.com.au/static/guest.html`.

The observed token TTL is `432000` seconds, or 5 days. The CLI caches conservatively for at most 1 hour by default (`BUNNINGS_GUEST_TOKEN_CACHE_SECONDS` can reduce or raise that cap) and refreshes with a 5 minute skew.

## Runtime headers

All `_apis` calls use browser-like read-only headers:

- `Authorization: Bearer {guest token}`
- `clientId: mHPVWnzuBkrW7rmt56XGwKkb5Gp9BJMk`
- `country: NZ|AU`
- `locale: en_NZ|en_AU`
- `currency: NZD|AUD`
- `locationCode: 9489` for NZ, `6400` for AU
- `X-region: NI_Zone_9` for NZ, `VICMetro` for AU
- `stream: RETAIL`
- `userId: anonymous`
- `sessionid` and `correlationid` UUIDs

## Endpoints used

- `POST /_apis/v1/coveo/search`
  - Used by `search` and `browse`.
  - Search body is a parameterized Coveo request with `q`, `aq`, `cq`, `fieldsToInclude`, store, region, country, currency, and `pipeline: Variant_Product`.
  - Category browse adds `@supercategoriescode==({category-code})` and leaves `q` empty.
- `GET /_apis/v1/products/{sku}?fields=FULL`
  - Product title, brand, description, features, images, category, ratings.
- `GET /_apis/v2/products/{sku}/priceInfo`
  - Product price and formatted currency.
- `POST /_apis/v2/products/{sku}/fulfillment`
  - Body: `{"includeVariantStock": false, "locationCode": "{defaultStore}", "storeRadius": "200000"}`.
  - Default-store stock and fulfilment availability.
- `GET /_apis/v1/item-api/locations?locationCode={storeCode}&productCode={sku}`
  - Aisle and bay locations when present.
- `GET /_apis/v1/stores/country/{NZ|AU}?fields=FULL`
  - Store list, addresses, phone/email, hours, services, coordinates, map URLs.

## Page-state fallback

`specials` still reads `GET /campaign/redemption-offers` and extracts products from public Next.js page state. CDP discovery did not show a clean read-only redemption-offers `_apis` feed equivalent to the product/search/store endpoints.

## Stability and safety

- Treat prices, stock, store hours, and promotions as live snapshots.
- Product price and stock are default-store snapshots unless the CLI is extended to select another store.
- Bunnings may alter API fields, Coveo request requirements, or token bootstrap details without notice.
- Do not use this skill for cart mutation, checkout, order placement, project list mutation, account actions, login, or authenticated trade/customer data.
- Do not commit credentials, cookies, raw authenticated captures, HARs, screenshots, or browser artefacts.
