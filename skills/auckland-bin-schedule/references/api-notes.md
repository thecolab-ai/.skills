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
- Some addresses return multiple units/properties; use `--list` when the first match may be wrong.
- Central/commercial properties may show private service or property-manager messages instead of Council collection dates.
- Endpoint/page shapes can change without notice because this is not an official API.
- Avoid high-volume scraping; use narrow address queries and small limits.
- Do not use this skill for account changes, service requests, or non-Auckland council schedules.
