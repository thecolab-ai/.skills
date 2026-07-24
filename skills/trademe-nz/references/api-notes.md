# Trade Me NZ API notes

The Python CLI wraps public Trade Me endpoints. Seller work uses the ordinary
Trade Me website through the Browser skill.

## Source and auth

- Website: `https://www.trademe.co.nz`
- API base: `https://api.trademe.co.nz/v1`
- Public auth model: none
- Seller auth model: normal website sign-in completed by the user in the browser

The CLI never accepts a username, password, cookie, developer credential, or
session token. Browser-backed seller work does not inspect or export the
browser's authentication state.

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

## Seller boundary

Seller inventory and actions are not implemented as API calls. The CLI emits a
browser task with a verified website starting route. The skill reads and
interacts with visible website state in the user's normal signed-in session.
See `browser-workflow.md`.

## Discovery note

The legacy uppercase paths such as `/v1/Search/General.json` returned `401` unless app credentials were supplied. The lowercase modern web paths, e.g. `/v1/search/general`, returned public JSON with browser-like headers and no OAuth credentials.

## Stability and safety

- Treat results as live snapshots, not historical facts.
- Listings can change, close, sell, or disappear at any time.
- Endpoint shapes and filter names can change without notice because this is not a formally supported public skill API.
- Avoid high-volume scraping and dataset redistribution; keep queries narrow and human-scale.
- Do not commit account data or complete listing forms.
- Never inspect or export cookies, browser storage, request authorization
  headers, session tokens, or passwords.
- Stop on the website's final review screen and require action-time
  confirmation for every seller mutation.
