# Auckland Bin Schedule API notes

This skill is an unofficial wrapper around public Auckland Council collection-day surfaces used by the website.

## Source and auth

- Collection-day page: `https://www.aucklandcouncil.govt.nz/en/rubbish-recycling/rubbish-recycling-collections/rubbish-recycling-collection-days.html`
- Address/property lookup: `https://experience.aucklandcouncil.govt.nz/nextapi/property?query={query}&pageSize={limit}`
- Collection result page: `https://www.aucklandcouncil.govt.nz/en/rubbish-recycling/rubbish-recycling-collections/rubbish-recycling-collection-days/{property_id}.html`
- Auth model: public short-lived bearer token embedded in the collection-day page

No username, password, account cookie, API key, or private credential is required.

## Endpoint/page families used

- The search page is fetched first to extract the current public bearer token
- The `nextapi/property` endpoint returns matching Auckland Council property ids and addresses
- The property-specific collection-day HTML page contains the current next collection dates and frequency text

## Stability and safety

- Treat dates as live current snapshots from Auckland Council, not historical data.
- Public holidays can shift collection dates; trust the next dates on the Council page over a normal rhythm.
- Some addresses return multiple units/properties; use `lookup` or `--list` to inspect candidates.
  The CLI never falls back to the first fuzzy result. It compares number, suffix, street name,
  normalised street type and any supplied suburb. It selects only one exact property, with a
  specified unit when needed, and only when the search page is not full.
- Central/commercial properties may show private service or property-manager messages instead of Council collection dates.
- Endpoint/page shapes can change without notice because this is not an official API.
- Avoid high-volume scraping; use narrow address queries and small limits.
- Council caps `pageSize` at 20; `--limit` accepts 1–20 and rejects larger input before fetching.
- Parsed addresses sent upstream omit punctuation, city and postcode, expand street types and
  normalise leading Mt/Mount and St/Saint names in both street and suburb.
- Do not use this skill for account changes, service requests, or non-Auckland council schedules.

## Verification and fixtures (8 October 2026)

Verified live 2026-10-08 by Hawk from omarchy: `schedule "12 Tawa Road Onehunga"` resolves
exactly and smoke reports one meaningful live assertion. This fix lane still receives HTTP 406
from the collection-day page on the same date; it reports an explicit blocked result, not a
source-schema failure. The existing blocked fixture retains that network-specific evidence.
The current public page token is fetched only at runtime and is never printed or stored.
No new live property/schedule capture is bundled because data reuse terms remain unconfirmed.

The address fixture is explicitly synthetic: ids are test-only identifiers, and the regression
addresses come from the supplied 7 October review. Tests cover the incorrect Dominion Street
candidate, correct singleton, suffix and number mismatches, wrong suburb, abbreviated street
type, multiple suburbs, units, missing address components, empty results, duplicate records and
bounded result-page ambiguity, unsupported number ranges, St Heliers/St Johns/St Marys Bay,
Mt Eden Road and postcode/punctuation normalisation. A blocked live probe reports gated,
not healthy. HTTP 400/401/404/405/410/422 responses remain hard source failures rather than skips.
