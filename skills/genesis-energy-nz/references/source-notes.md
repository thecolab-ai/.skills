# Source notes

- Authentication: mixed
- Last verified: 2026-10-31 (deterministic synthetic checks only; live health gated)

## Origin and licensing

Publisher: Genesis Energy. Primary website: https://myaccount.genesisenergy.co.nz.
The code derives its sign-in sequence and electricity/gas field mapping from
[the upstream Genesis client](https://github.com/JoelBrenstrum/ha-genesisenergy)
at commit `9a3a0e5edf94f29f23448595b47fdac81d549c92`, with subsequent authentication,
privacy and interval-handling improvements. The original MIT copyright and licence
are preserved in `../LICENSE`. This contribution uses a synchronous stdlib client.
The code licence does not grant reuse rights over private account data. No public data reuse licence is asserted.

## Authentication and outbound traffic

`GENESIS_EMAIL` and `GENESIS_PASSWORD` are user-supplied environment variables,
loaded only inside a validated data command. No actual credentials are bundled.
`thecolab.auth: mixed` describes email/password sign-in followed by an in-memory
OAuth bearer token; it does not imply a keyless public mode.

Allowed hosts:

- `auth.genesisenergy.co.nz`: website B2C sign-in pages, CSRF assertions and POST
  authorization-code exchange. Passwords and codes are sent only in POST bodies.
- `web-api.genesisenergy.co.nz`: the fixed electricity and natural-gas usage endpoints.
- `myaccount.genesisenergy.co.nz`: documented website and exact OAuth callback
  target. The callback is parsed, never fetched.

The OAuth client ID in `scripts/genesis.py` is the public Genesis website
application identifier, not a user-specific API key or secret. Login has a private
cookie jar; stdlib CookieJar preserves transaction-cookie values without aiohttp's
quoted-cookie behaviour. TLS verification is enabled. Redirects are followed
manually only within the exact authentication origin, with a five-hop limit.
The code-bearing callback must match the fixed scheme, host and path.
Environment proxies are disabled for account requests; there is no proxy fallback.
Requests have a 30-second timeout and a 2 MiB response limit. Tokens, cookies and
passwords are never written to disk. The process obtains a fresh token per run;
it does not refresh, persist, or retry rejected tokens. The sign-in sequence asks
for the website's `offline_access` scope, but any returned refresh token is discarded.
There is no support for MFA or CAPTCHA: stop if interaction is required.

## Fuel read surfaces

Each invocation reads exactly one fuel. Electricity is the default; gas is only
queried after explicit `--fuel gas`. There is no automatic service discovery,
requirement to have both fuels, fallback between fuels, or combined cost total.

- Electricity: `POST https://web-api.genesisenergy.co.nz/v2/private/electricity/site-usage`.
  JSON body: `startDate`, `endDate` (inclusive ISO NZ dates), `intervalType: HOURLY`.
  POST here is a read, not an account mutation.
- Natural gas: `GET https://web-api.genesisenergy.co.nz/v2/private/naturalgas/advanced/usage`.
  The same three fields are query parameters. The bearer token stays in the
  Authorization header, never the URL. Transport only accepts the exact gas
  path, GET method and three query keys; no arbitrary endpoint or extra key.

These are website endpoints rather than a documented public developer API;
provider changes can break compatibility. Implicit site selection is inherited;
no account/site identifier is extracted or exposed.

The upstream client observed approximately 100 electricity and 120 gas rows per response.
Use inclusive two-date chunks (at most 49 hours across autumn DST), at least one
second apart. At most 31 days / 16 usage requests per invocation; no automatic
network retries. Any failed chunk aborts without partial output. A response with
100 or more rows (a conservative cap for either fuel), invalid/conflicting rows,
or rows outside its requested dates
is a schema failure. Silent omissions below that limit remain detectable only as
missing coverage. More frequent polling cannot make delayed meter data live.

The gas endpoint may reject dates beyond its latest supplied readings, even when
those dates are already in the past. Gas HTTP 400/404/422 becomes exit 7 with a
static account-or-date-unavailable message, not an inferred diagnosis or zero
usage. The response cannot reliably distinguish a missing gas service from
unsupported dates or a changed endpoint. Use earlier dates or check the service.
Auth rejection (401/403), rate limits (429), outages, and malformed data retain
separate errors. A gas failure never triggers an electricity request. Empty
`usage: []` produces `no_readings` with null totals; it is not proof of no service.


Only `usage[].startDate`, `usage[].kw` and `usage[].costNZD` are read. All other
fields are discarded. Aware whole-hour timestamps are normalised to UTC, deduped,
validated against each chunk and then displayed with NZ offsets. Only completed
intervals are returned. Decimal strings preserve numeric precision in JSON.
The interpretation of `kw` as interval kWh for both fuels follows upstream and
needs an owner comparison against My Account, especially for gas units; `costNZD` is usage cost with unknown tax/fixed-fee
coverage. Never extrapolate a tariff, claim a full bill, or label delayed data live.

Coverage counts every hour in the requested calendar dates using UTC arithmetic,
including 23/25-hour NZ DST days. Totals are labelled `observed_*`; they remain
partial if `coverage` is `incomplete`. Empty periods have null totals. The current
hour, future hours today, and provider lag are missing, not zeros.

## Output and failures

JSON uses `meta` / `results`. Provenance names Genesis Energy and the fixed
credential-free endpoint of the selected fuel. `meta.fuel` identifies that fuel. `retrieved_at` records completion of the
fetch (attempt time on failure); `latest_data` is the latest supplied completed
interval **start**, not the fetch time. All range totals carry coverage counts.
The common repository runner wraps this direct envelope unchanged in its data field.

Exit codes: 2 invalid input, 3 missing credentials, 4 blocked/rejected/rate-limited,
5 transport/service failure, 6 response/schema failure, 7 gas account/date range unavailable. Errors contain static
messages, never response bodies, exception text, personal fields or arbitrary
headers. A short numeric Retry-After delay is preserved when supplied.

## Verification boundary

Last deterministic verification: 2026-10-31. Fixtures are hand-authored and marked
synthetic. Contract/smoke tests exercise simulated sign-in, cookie handling,
redirect rejection, field selection, bounded requests, DST, gaps and safe failures.
Tests include explicit/default fuel isolation, gas GET/query handling, missing
service, empty readings, delayed-date failure, outages and safe gas errors.
They never use network or personal credentials. Source health stays `gated`:
neither fuel in this extracted stdlib client has been verified against a real account.
An owner-authorised private comparison is needed to establish current login,
site selection, units and cost semantics. No live account data is required in CI.
