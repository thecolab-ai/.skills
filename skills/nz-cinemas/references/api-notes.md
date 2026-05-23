# NZ Cinemas API notes

This skill is an unofficial lightweight wrapper around public read-only endpoints used by New Zealand cinema websites.

## Source and auth

No username, password, member cookie, private token, browser profile, or seat/booking state is required for the implemented commands.

Endpoint families used:

- Event Cinemas: `https://www.eventcinemas.co.nz`
- HOYTS: `https://www.hoyts.co.nz` plus `https://apim-aea.hoyts.co.nz/cinemaapi-nz-live/api`
- Reading Cinemas: `https://readingcinemas.co.nz` plus `https://prod-api.readingcinemas.com.au`
- Rialto: `https://www.rialto.co.nz`
- Berkeley Mission Bay: exposed by HOYTS as cinema id `1013`

## Event Cinemas

- Cinema list: `GET https://www.eventcinemas.co.nz/Cinemas`
- Sessions: `GET https://www.eventcinemas.co.nz/Cinemas/GetSessions?cinemaIds={id}&date={YYYY-MM-DD}`
- JSON-LD sessions by cinema: `GET https://www.eventcinemas.co.nz/api/cinemas/JsonLd?cinemaId={id}`

The implemented CLI parses cinema ids from the public `/Cinemas` page and uses `/Cinemas/GetSessions` for movies and sessions. The endpoint returns a `Success` wrapper with `Data.Movies[]`, `Data.Dates[]`, and nested `CinemaModels[].Sessions[]`.

Observed cinema ids include `502` Queen Street, `504` Albany, `509` St Lukes, `520` Newmarket, and other Event NZ sites.

## HOYTS

- Cinema list: `GET https://apim-aea.hoyts.co.nz/cinemaapi-nz-live/api/cinemas`
- Now showing movies: `GET https://apim-aea.hoyts.co.nz/cinemaapi-nz-live/api/movies/now-showing`
- All sessions: `GET https://apim-aea.hoyts.co.nz/cinemaapi-nz-live/api/sessions`
- Sessions by cinema: `GET https://apim-aea.hoyts.co.nz/cinemaapi-nz-live/api/sessions/{cinemaId}`

No API key was required during verification. Movie records use a website id plus one or more Vista ids in `vistaId`; session records use the Vista id in `movieId`.

Berkeley Mission Bay is present in the HOYTS cinema list as id `1013`, slug `berkeley-mission-bay`. The CLI exposes a `--chain berkley` alias that filters HOYTS data to that cinema.

## Reading Cinemas

- Public settings/bootstrap: `GET https://prod-api.readingcinemas.com.au/settings/2`
- Cinema list: `GET https://prod-api.readingcinemas.com.au/getcinemas?countryId=2`
- Films/sessions: `GET https://prod-api.readingcinemas.com.au/films?countryId=2&cinemaId={slug}&status=nowShowing&sort=true`
- Minimal movies for a cinema: `GET https://prod-api.readingcinemas.com.au/films?countryId=2&cinemaId={slug}&status=getMovies`

Most Reading API endpoints return `Unauthorized` without a bearer token. The public `settings/2` bootstrap returns a short-lived Cognito access token used by the website before login; the CLI fetches it in memory and sends it as `Authorization: Bearer ...`.

The implemented CLI uses only read-only `GET` endpoints. Ticketing, member, payment, concession, and order endpoints are intentionally not implemented.

## Rialto

- Cinema list: `GET https://www.rialto.co.nz/Cinemas`
- Sessions: `GET https://www.rialto.co.nz/Cinemas/GetSessions?cinemaIds={id}&date={YYYY-MM-DD}`
- JSON-LD sessions by cinema: `GET https://www.rialto.co.nz/api/cinemas/JsonLd?cinemaId={id}`

Rialto uses the same EVT/Vista-style shape as Event Cinemas. Observed public cinema ids are `750` Dunedin and `751` Newmarket.

## Refresh and stability

- Event and Rialto session responses are live website snapshots and can change throughout the day.
- HOYTS public API responses are live and include sessions across several days.
- Reading sessions are live and require a fresh public settings token; token expiry is short, so the CLI does not persist it.
- All endpoints are website implementation details, not formal public APIs. If one fails, re-sniff the public site traffic and update this note before changing command behavior.

## Auth-walled or intentionally omitted

- Booking, seat maps, ticket type pricing, checkout, refunds, account, loyalty, voucher, gift card, concession ordering, and payment endpoints are out of scope.
- Reading exposes many ticketing endpoints after the public token bootstrap, but they are not used because this skill is read-only.
- No HARs, JavaScript bundles, screenshots, cookies, or browser storage captures are needed or stored by this skill.
