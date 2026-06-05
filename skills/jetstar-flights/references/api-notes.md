# Source notes

## Public source

Jetstar's public website uses the public fare-cache availability endpoint exposed via `digitalapi.jetstar.com`:

```text
GET https://digitalapi.jetstar.com/v1/farecache/flights/batch/availability-with-fareclasses
```

The endpoint returns fare-cache snapshots grouped by route and date. The public site labels these with an accuracy percentage, so treat them as availability/fare snapshots rather than a final checkout quote.

## Parameters used

The CLI sends:

- origin/destination IATA airport codes
- start/end date window
- outbound direction
- passenger count
- `includeSoldOut=true`
- `includeFees=true`
- `culture: en-NZ`

It does not send account identifiers, payment data, passenger names, booking references, Club Jetstar credentials, cookies, selected bundles, selected seats, or cart state.

## Implementation note

Node 18+ `fetch` works reliably against the Jetstar public endpoint in environments where Python `urllib` and `curl` can stall on the same Akamai-backed host. Keep the CLI in Node unless the edge behaviour changes.

## Boundaries

Supported:

- public one-way fare-cache search
- flight ID, departure/arrival, price, currency, sold-out flag, stop count, fare classes
- human and JSON output

Not supported:

- login, member/account data, bundle/seat selection, cart creation, booking, payment, manage-booking, refunds/changes
- high-volume scraping or historical fare databases

If Jetstar changes the fare-cache endpoint or required parameters, update `scripts/cli.mjs` and the smoke test together.
