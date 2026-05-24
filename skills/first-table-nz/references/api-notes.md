# First Table NZ API notes

## Source

- Website: `https://www.firsttable.co.nz/`
- Public city pages: e.g. `https://www.firsttable.co.nz/auckland`
- GraphQL endpoint observed from frontend bundles: `https://stellate.firsttable.net/graphql`

The skill intentionally uses public, unauthenticated, read-only surfaces only.

## Discovery notes

The Next.js city pages embed `__NEXT_DATA__` with city metadata:

- city id/title/slug/timezone
- restaurant count
- diner options and sessions
- sub-city/suburb links
- restaurant tag metadata

The frontend bundles expose a read-only GraphQL client with these headers:

- `Content-Type: application/json`
- `stage: Live`
- `origin: https://www.firsttable.co.nz/`
- `x-graphql-client-name: Website`
- `x-graphql-client-version: https://www.firsttable.co.nz/`

No member token is needed for the read-only queries used here.

## Queries implemented

- `AllRestaurantIds` returns restaurant ids for a region, optional sessions, dates, tags, suburbs, ids, and people count.
- `RestaurantDetails` returns public restaurant profile fields: title, slug, rating, review summary, region/suburb, cuisines/tags, session types, diner limits, prices, images, and flags.
- `AllAvailabilitySearch` returns public availability/search slot data for restaurant ids, date, and people count.

## Read-only boundary

Do not add commands for these frontend operations without explicit review, because they are account/booking mutations or member flows:

- `createFullPriceBooking`
- `refreshToken`
- `memberAddFavourite`
- `memberRemoveFavourite`
- `cancelAvailabilitySearch` or any other mutation except if proven harmless and needed for a read-only cache refresh
- sign-up/login/payment/checkout/member updates

## Stability caveats

- This is an unofficial website-derived connector; endpoint fields and enum names can change.
- Session enum inputs are uppercase in GraphQL (`DINNER` etc.) but detail payloads return lower-case strings (`dinner`). The CLI accepts lower-case and uppercases GraphQL variables.
- Availability data includes upstream `dataStatus` and `syncExpires`; stale/cached flags should be shown to users when relevant.
- `search` fetches restaurant ids first, then details for a bounded prefix (`--fetch-limit`) to keep live calls modest.
- City discovery is best-effort from known NZ city slugs plus public page verification.

## Live verification examples

Verified during creation:

```bash
python3 skills/first-table-nz/scripts/cli.py city auckland --json
python3 skills/first-table-nz/scripts/cli.py search sushi --city auckland --limit 3 --json
python3 skills/first-table-nz/scripts/cli.py detail 1142 --json
python3 skills/first-table-nz/scripts/cli.py availability 1142,1698 --date 2026-05-25 --people 2 --available-only --json
```

Representative live detail at creation time: restaurant id `1142` resolved to `FISH Restaurant` on `/auckland/city-centre/fish-restaurant` with rating/review fields and booking price snapshots.
