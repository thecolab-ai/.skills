# Eventfinda NZ API and website notes

This skill is an unofficial lightweight wrapper around public Eventfinda New Zealand website pages. It does not use account login, cookies, ticket purchasing flows, or private organiser/customer data.

## Source and auth

- Public website: `https://www.eventfinda.co.nz`
- Public listing examples:
  - `https://www.eventfinda.co.nz/whatson/events/new-zealand`
  - `https://www.eventfinda.co.nz/whatson/events/auckland`
  - `https://www.eventfinda.co.nz/search?q=music`
- Event detail pages include Schema.org JSON-LD in `<script type="application/ld+json">` blocks
- Official developer API host tested: `https://api.eventfinda.co.nz/v2`
- Auth model for this skill: none for the implemented public website requests

No username, password, account cookie, browser session, or API key is required for the implemented commands.

## Official developer API caveat

The Eventfinda developer API exists separately from the public website pages and is Basic-auth gated. During verification, this unauthenticated request:

```text
GET https://api.eventfinda.co.nz/v2/events.json?rows=1
=> 401 Incorrect authentication details supplied.
```

Because the `.skills` repo favours immediately usable public/read-only skills where possible, this skill does not require Eventfinda API credentials. If authenticated developer API access becomes available later, add it as an explicit credential-backed mode rather than silently changing the no-auth commands.

## Endpoint/page families used

### Listings

The CLI reads Eventfinda HTML listing cards from public pages:

- Upcoming events by location: `/whatson/events/{location}`
- Upcoming events by category/location: `/{category}/events/{location}`
- Keyword search: `/search?q={query}`

Cards currently expose enough public data for discovery:

- internal Eventfinda event id from the `_efC(...)` tracking call when present
- title and canonical event URL/path
- venue/location text
- start timestamp from the microformat `value-title` attribute
- human date text
- category
- card image URL
- public badges such as sold-out/ticket status badges

### Event detail pages

Detail pages currently include Schema.org JSON-LD objects for:

- `Place` venue/address/geo data
- `Offer` ticket/price metadata visible in the page
- one or more `*Event` objects, typically one per session/date

The CLI resolves the first event's place/offers and aggregates unique sessions into `event.sessions[]`.

## Stability and safety

- This is public website parsing, not a formal stable third-party API contract.
- Markup can change. Run `scripts/smoke-test.ts` or a live `upcoming` + `event` poke before production use.
- Avoid high-volume scraping, full-site replication, or rapid polling.
- Do not automate ticket purchases, checkout, account actions, or private organiser/customer workflows.
- Treat results as live public snapshots; venues, dates, prices, and availability can change.
