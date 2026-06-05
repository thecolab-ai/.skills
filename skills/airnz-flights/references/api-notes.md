# Source notes

## Browser-sniffed fare search

A browser capture of Air New Zealand's public booking search found this anonymous no-login flow:

```text
GET  https://flightbookings.airnewzealand.co.nz/vbook/actions/ext-search?...route/date/passenger params...
POST https://flightbookings.airnewzealand.co.nz/vbook/ajax/bui/flights/search
GET  https://flightbookings.airnewzealand.co.nz/vbook/actions/selectitinerary
```

When the POST is accepted, the `selectitinerary` HTML contains embedded `legOptions` JSON with fare products such as `Seat`, `Seat + Bag`, `flexi change`, and `flexi refund`, including adult price, currency, booking class, flight number, aircraft, departure/arrival, and selling-out markers.

The CLI now attempts this sniffed read-only fare path first and parses `legOptions` when available. It does **not** select any fare ID, hold seats, send passenger details, log in, create a cart/booking, or proceed to checkout.

## Optional CloakBrowser mode

For headless servers and anti-bot-sensitive public web workflows, the CLI supports optional browser-assisted mode.

Repo-wide convention: `docs/browser-assisted-skills.md`. CloakBrowser upstream: <https://github.com/CloakHQ/CloakBrowser>.

```bash
python3 skills/airnz-flights/scripts/cli.py AKL WLG 2026-06-15 --browser --json
```

`--browser` launches CloakBrowser in headless mode with server-safe Chromium args (`--no-sandbox`, `--disable-dev-shm-usage`), loads the public Air NZ booking search page, submits the same read-only search mutation in the page context, and parses the resulting `selectitinerary` page. This can reduce false request-auth/CAPTCHA responses compared with bare HTTP clients.

CloakBrowser is optional. The script imports it only when `--browser` is requested. If it is missing, `--browser --json` returns:

```json
{
  "error": "cloakbrowser_not_installed",
  "recommendation": "Recommend that the user installs CloakBrowser or runs without --browser for the fallback path."
}
```

Agents should surface that as an installation recommendation rather than silently falling back and implying browser mode was used.

## Request-auth/CAPTCHA caveat

The same Air NZ fare-search POST can return:

```json
{"type":"REDIRECT","redirectUrl":"/vbook/actions/captcha", ...}
```

That is a real Air NZ request-authentication boundary. The skill must not bypass CAPTCHA or automate solving it. If fare search is challenged, the CLI falls back to the public timetable source below and clearly marks `fare_search_blocked: true` in JSON.

## Public timetable fallback

Air New Zealand exposes a public timetable search page at:

```text
https://www.airnewzealand.co.nz/flight-schedules
```

That page calls a same-origin JSON feed:

```text
GET https://www.airnewzealand.co.nz/feeds/flight-timetables
```

The fallback opens the public timetable page in Playwright and calls the same feed from the browser context. This is necessary because the same public feed can return empty results to bare non-browser clients while returning schedule data to the website.

## Parameters used

The CLI sends:

- origin/destination IATA airport codes
- departure date
- adult passenger count for the fare-search attempt
- direct-only flag for filtering returned rows
- locale `en_NZ` for the timetable fallback

It does not send account identifiers, payment data, passenger names, booking references, Airpoints credentials, selected fare IDs, or checkout/cart state.

## Boundaries

Supported:

- public one-way fare snapshot when Air NZ accepts the anonymous browser-style search
- fare product labels and adult prices from embedded `legOptions` JSON
- public timetable fallback when fare search is challenged
- flight number, departure/arrival times, duration, stop/leg details
- booking-search handoff URL for the user to open themselves
- human and JSON output

Not supported:

- CAPTCHA bypass, login, booking creation, fare selection, payment, Airpoints, seat selection, fare holds, manage-booking, refunds/changes
- high-volume scraping or historical schedule/fare databases
- claims about final payable totals; returned prices are snapshots before selection/checkout

If Air NZ changes `/vbook/ajax/bui/flights/search`, `selectitinerary`, `/feeds/flight-timetables`, or the public page behaviour, update `scripts/cli.py` and the smoke test together.
