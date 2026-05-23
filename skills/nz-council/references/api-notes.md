# NZ Council API Notes

Discovery date: 2026-05-23.

## Scope

This skill only covers:

- council-area event listings and event details
- public recreation facilities, especially pools, leisure centres, gyms, hours, and lane availability snapshots

It does not cover rates, consents, rubbish/recycling, parking, fines, bookings, payments, or authenticated services.

## Events

### Eventfinda public pages

Implemented as the primary event source.

- List Auckland: `https://www.eventfinda.co.nz/whatson/events/auckland`
- List Wellington: `https://www.eventfinda.co.nz/whatson/events/wellington`
- List Christchurch: `https://www.eventfinda.co.nz/whatson/events/christchurch`
- List all NZ: `https://www.eventfinda.co.nz/whatson/events/new-zealand`
- Category form: `https://www.eventfinda.co.nz/{category}/events/{location}`
- Pagination: `?page=N`
- Detail: event URL/path returned by list pages

List pages expose event cards with title, detail URL/path, location, start date, display date text, category, image, and badges. Detail pages expose JSON-LD event objects, places, offers, and sessions.

Freshness: live website scrape. Eventfinda controls listing order and update cadence.

### Eventfinda REST API

Checked first because it is the cleanest documented source, but it is not usable anonymously.

- Endpoint tested: `https://api.eventfinda.co.nz/v2/events.json?rows=1`
- Result: `401 Incorrect authentication details supplied`
- Notes: official REST API requires credentials/basic auth. The CLI uses public website pages instead.

### Auckland Council / OurAuckland

- Source checked: `https://ourauckland.aucklandcouncil.govt.nz/events/`
- Result: static, parseable card HTML.
- v1 status: not wired, because Eventfinda provides one cross-council path and Auckland Council also uses Eventfinda plus own listings.

### Wellington City events

- Source checked: `https://wellington.govt.nz/events`
- Result: direct request returned 403 during discovery.
- Related public path: Wellington's event navigation points to an Eventfinda calendar.
- v1 status: wired through Eventfinda public pages for Wellington.

### Christchurch City events

- Source checked: `https://ccc.govt.nz/news-and-events/events`
- Result: Incapsula challenge page during discovery.
- v1 status: wired through Eventfinda public pages for Christchurch.

## Recreation Facilities

### Auckland Leisure locations

Implemented for Auckland pools and facilities.

- Listing page: `https://www.aucklandleisure.co.nz/locations/`
- AJAX listing endpoint: `https://www.aucklandleisure.co.nz/umbraco/surface/LocationListing/RenderLocationListing`
- Headers used: `X-Requested-With: XMLHttpRequest`, `Referer: https://www.aucklandleisure.co.nz/locations/`

Useful filters observed:

- Facility `1119`: Gym
- Facility `1126`: Swimming pool
- Facility `1121`: Sauna/steam
- Facility `1122`: Spa pool
- Facility `1123`: Sports courts
- Facility `1124`: Stadium
- Facility `1389`: Swimming lessons
- Area `1134`: Central
- Area `1138`: East
- Area `1141`: North
- Area `1144`: South
- Area `1147`: West

Card schema parsed:

```json
{
  "name": "Tepid Baths",
  "id": "tepid-baths",
  "council": "akl",
  "source": "aucklandleisure",
  "source_url": "https://www.aucklandleisure.co.nz/locations/tepid-baths/",
  "address": "100 Customs Street West, Central Auckland",
  "operator": "Auckland Council",
  "status": null
}
```

Detail pages expose:

- name and meta description
- `Hours` section with labelled text blocks such as `Centre hours`
- address, phone, email
- pool/facility feature cards
- public portal links, including `ResourceAvailability/{id}` where available

### Auckland Leisure lane availability

Implemented for single-pool detail when the pool page links to ResourceAvailability.

- Example: `https://portal.aucklandleisure.co.nz/ResourceAvailability/8`
- Public payload: Vue/Phoenix-style attributes `:items="..."` and `:date-strings="..."`
- Date strings observed for rolling seven-day windows.
- Values are parsed as available lane/resource counts per 15-minute slot.

Availability schema emitted:

```json
{
  "date": "2026-05-23",
  "resources": [
    {
      "name": "Tepid Baths - Lane Pool",
      "intervals": [
        {"start": "7:00 AM", "end": "8:30 AM", "available_lanes": 7}
      ]
    }
  ]
}
```

Freshness: live page scrape at command time. The portal labels data as changing frequently; users should verify before travel.

### Wellington City pools and recreation centres

Implemented as basic facility listings.

- Pools: `https://wellington.govt.nz/recreation/facilities-and-centres/swimming-pools`
- Recreation centres: `https://wellington.govt.nz/recreation/facilities-and-centres/recreation-centres`

Observed pools:

- Wellington Regional Aquatic Centre
- Freyberg Pool
- Karori Pool
- Keith Spry Pool
- Tawa Pool
- Thorndon Pool
- Khandallah Pool

Observed recreation centres:

- Karori Recreation Centre
- Kilbirnie Recreation Centre
- Nairnville Recreation Centre
- Tawa Recreation Centre

Schema parsed:

```json
{
  "name": "Freyberg Pool",
  "id": "freyberg-pool",
  "type": "pool",
  "council": "wlg",
  "source": "wellington-city-council",
  "source_url": "https://wellington.govt.nz/recreation/facilities-and-centres/swimming-pools/freyberg-pool",
  "description": "..."
}
```

Freshness: live static listing page. Opening hours remain on linked detail pages in v1.

### Christchurch recreation and sport

Discovered, documented, not wired in v1.

- Public entry: `https://recandsport.ccc.govt.nz/`
- The source is public and references a Perfect Gym-backed client portal.
- The original council recreation page `https://ccc.govt.nz/recreation` returned an Incapsula challenge during discovery.

Reason not wired: useful schedules/facility state appear vendor-backed and need more careful endpoint mapping. The CLI returns a clear v1 note for Christchurch recreation commands instead of scraping challenge pages or authenticated surfaces.
