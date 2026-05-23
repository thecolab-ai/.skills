# Trade Me NZ API notes

This skill is an unofficial wrapper around public read-only Trade Me web API endpoints used by the modern site.

## Source and auth

- Website: `https://www.trademe.co.nz`
- API base: `https://api.trademe.co.nz/v1`
- Auth model for supported commands: none

No username, password, account cookie, OAuth app credentials, private token, or browser session is required for the implemented read-only operations.

## Endpoint families used

- `GET /v1/search/general` for marketplace search
- `GET /v1/search/property/residential` for residential sale search
- `GET /v1/search/property/rental` for rentals
- `GET /v1/search/motors/used` and `/v1/search/motors/new` for motors
- `GET /v1/search/jobs` for jobs
- `GET /v1/search/flatmates` for flatmates
- `GET /v1/search/property/commercialsale` and `/commerciallease` for commercial property
- `GET /v1/search/property/rural` and `/retirement` for rural/retirement property
- `GET /v1/listings/{listing_id}` for public listing detail
- `GET /v1/categories` for public category tree
- `GET /v1/localities/regions` for region/district/suburb hierarchy

## Discovery note

The legacy uppercase paths such as `/v1/Search/General.json` returned `401` unless app credentials were supplied. The lowercase modern web paths, e.g. `/v1/search/general`, returned public JSON with browser-like headers and no OAuth credentials.

## Stability and safety

- Treat results as live snapshots, not historical facts.
- Listings can change, close, sell, or disappear at any time.
- Endpoint shapes and filter names can change without notice because this is not a formally supported public skill API.
- Avoid high-volume scraping and dataset redistribution; keep queries narrow and human-scale.
- Do not use this skill for bidding, buying, selling, watchlists, saved searches, messages, or account actions.
- Do not commit cookies, account data, raw authenticated captures, or screenshots with private information.
