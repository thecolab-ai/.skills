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
- List New Plymouth: `https://www.eventfinda.co.nz/whatson/events/new-plymouth`
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

### Rotorua Lakes pools and aquatic facilities

Implemented as a static public facility source, based on Rotorua Lakes Council recreation and park pages plus the Rotorua Aquatic Centre operator site.

- Rotorua Lakes recreation entry: `https://www.rotorualakescouncil.nz/parks-lakes-recreation`
- Rotorua Aquatic Centre council page: `https://www.rotorualakescouncil.nz/parks-lakes-recreation/recreational-venues/aquatic-centre`
- Rotorua Aquatic Centre operator pages:
  - `https://www.clmnz.co.nz/rotorua-aquatic-centre/`
  - `https://www.clmnz.co.nz/rotorua-aquatic-centre/pools/`
  - `https://www.clmnz.co.nz/rotorua-aquatic-centre/contact/`
- Direct checks of `rotoruaaquaticcentre.co.nz` and `www.rotoruaaquaticcentre.co.nz` did not resolve during discovery; the council page links to the CLM operator path above.
- Butcher's Pool council page: `https://www.rotorualakescouncil.nz/parks-lakes-recreation/park-reserves/butchers-pool`
- Kuirau Park council page: `https://www.rotorualakescouncil.nz/parks-lakes-recreation/park-reserves/kuirau-park`
- Council OIA cross-check: `https://www.rotorualakescouncil.nz/our-council/officialinformation/official-information-requests?item=id%3A2qgeujsul17q9sfg7ls7`

Observed facilities:

- Rotorua Aquatic Centre
- Butcher's Pool
- Kuirau Park foot pools and paddling pool

Rotorua Aquatic Centre fields are sourced from the council page and CLM operator pages:

```json
{
  "name": "Rotorua Aquatic Centre",
  "id": "rotorua-aquatic-centre",
  "type": "pool",
  "council": "rot",
  "source": "rotorua-lakes-council",
  "address": "Kuirau Park, 18 Tarewa Rd, Rotorua 3010",
  "operator": "Community Leisure Management (CLM)",
  "hours_summary": "Monday - Sunday: 6:00am - 9:00pm",
  "features": ["Outdoor 50m heated pool", "Indoor 25m heated pool", "Indoor learner pool", "Gym"]
}
```

Butcher's Pool is listed separately because the public park-reserve page describes it as a free hot mineral pool and says Rotorua Lakes Council manages the changing rooms and toilets. The CLI includes the linked safety notes that the pool is unsupervised and users should keep their head above water.

Kuirau Park is included as a public council-managed park water facility because the council page lists foot pools and a paddling pool among park facilities. It is not treated as a lane-swimming pool.

Freshness: static source records derived from public pages. Rotorua Aquatic Centre's CLM pages expose current lane availability links through Perfect Gym-backed pages; v1 links those pages but does not scrape the dynamic availability payload.

### New Plymouth pools

Implemented as source-backed public pool records.

- Community pools: `https://www.npdc.govt.nz/leisure-and-culture/community-swimming-pools/`
- Todd Energy Aquatic Centre: `https://www.npdc.govt.nz/leisure-and-culture/todd-energy-aquatic-centre/`
- Inglewood Pool: `https://www.npdc.govt.nz/leisure-and-culture/community-swimming-pools/inglewood-pool/`
- Waitara Pool: `https://www.npdc.govt.nz/leisure-and-culture/community-swimming-pools/waitara-pool/`
- Methanex Bell Block Aquatic Centre: `https://www.bellblockaquaticcentre.co.nz/`

Observed NPDC/Bell Block records:

- Todd Energy Aquatic Centre, 8-10 Tisch Avenue, New Plymouth. NPDC publishes current opening hours, phone, location, and facilities such as indoor and outdoor pools, hydroslides, sauna, spa, and fitness centre.
- Methanex Bell Block Aquatic Centre, 10 Murray Street, Bell Block. The public pool site exposes LocalBusiness JSON-LD and visible opening hours; it lists a 25 metre six-lane indoor pool and a seasonal outdoor pool.
- Inglewood Pool, corner of Elliot and Rata Streets, Inglewood. NPDC describes a six-lane outdoor pool and toddlers' pool; the page was closed for the season during discovery.
- Waitara Pool, 1 Leslie Street, Waitara. NPDC describes a 33m six-lane outdoor pool, learners' pool, toddlers' pool, and 4m deep dive pool; the page was closed for the season during discovery.

Freshness: source-backed static records in the CLI with source URLs for verification. Seasonal pool status and Todd Energy daily opening times can change, so users should verify the linked public pages before travel.

### Napier City aquatic facilities

Implemented as a static council-backed facility record.

- Current council page: `https://www.napier.govt.nz/napier/facilities/napier-aquatic-centre/`
- Requested legacy-style path checked first: `https://www.napier.govt.nz/services/swimming-pools`
- Result for requested path on 2026-05-23: public Napier "Page not Found" response, no bot wall.

Observed facility:

- Napier Aquatic Centre, also matched by `Onekawa`, `Onekawa Aquatic Centre`, and `Onekawa Pools`

Useful fields emitted:

```json
{
  "name": "Napier Aquatic Centre",
  "id": "napier-aquatic-centre",
  "type": "pool",
  "council": "npr",
  "source": "napier-city-council",
  "source_url": "https://www.napier.govt.nz/napier/facilities/napier-aquatic-centre/",
  "address": "Maadi Road, Onekawa, Napier",
  "operator": "Napier City Council",
  "status": "open year-round"
}
```

Freshness: facility identity and council source URL are static in the CLI; users should open the linked council/centre page for current open times before travel.

### Hastings District aquatic facilities

Implemented as static council-backed facility records, including linked Aquatics Hastings and Splash Planet pages.

- Current council swimming-pools page: `https://www.hastingsdc.govt.nz/hastings/facilities/swimming-pools/`
- Requested legacy-style path checked first: `https://www.hastingsdc.govt.nz/our-community/recreation-and-sport/swimming-pools`
- Result for requested path on 2026-05-23: public Hastings "Page not found" response, no bot wall.
- Splash Planet council page: `https://www.hastingsdc.govt.nz/hastings/facilities/splash-planet/`
- Aquatics Hastings facilities page: `https://www.aquaticshastings.co.nz/facilities`

Observed current council-run Aquatics Hastings pools:

- Flaxmere Pool / Swim Heretaunga
- Clive War Memorial Pool
- Havelock North Village Pool / Village Pool

Other Hastings aquatic recreation records:

- Splash Planet, listed by HDC as a water theme park at 1001 Grove Road
- Frimley Pool, retained as a closed facility because the current HDC page notes the September 2024 closure decision
- Hawke's Bay Regional Aquatic Centre, included for `Hastings Aquatic Centre` lookup as the separate Hastings aquatic centre; its own public site says it is owned and operated by the Hawke's Bay Community Fitness Centre Trust, not Aquatics Hastings

Useful fields emitted:

```json
{
  "name": "Splash Planet",
  "id": "splash-planet",
  "type": "water-park",
  "council": "has",
  "source": "hastings-district-council",
  "source_url": "https://www.hastingsdc.govt.nz/hastings/facilities/splash-planet/",
  "address": "1001 Grove Road, Hastings",
  "operator": "Hastings District Council"
}
```

Freshness: facility identity, status notes, and source URLs are static in the CLI. Flaxmere, Clive, Village Pool, Splash Planet, and the regional aquatic centre source pages publish current hours and seasonal changes.

### Hamilton Pools

Implemented for Hamilton pool facilities.

- Council navigation page: `https://hamilton.govt.nz/search?Search=pool`
- Hamilton Pools home: `https://www.hamiltonpools.co.nz/`
- Waterworld: `https://www.hamiltonpools.co.nz/facilities/waterworld`
- Gallagher Aquatic Centre: `https://www.hamiltonpools.co.nz/facilities/gallagher-aquatic-centre`
- Partner pools: `https://www.hamiltonpools.co.nz/facilities/partner-pools`
- Contact: `https://www.hamiltonpools.co.nz/contact`

Observed active Hamilton Pools facility pages:

- Waterworld
- Gallagher Aquatic Centre
- Partner Pools

Observed seasonal partner pools:

- Te Rapa Primary School Pool
- Fairfield College Pool
- Hillcrest Normal School Pool
- Hamilton Boys High School Pool

The Hamilton City Council page path suggested during discovery,
`https://hamilton.govt.nz/our-services/parks-and-recreation/pools`, returned the council
page-not-found template. Current Hamilton City Council navigation links to
`https://www.hamiltonpools.co.nz/` as the Hamilton Pools source. The suggested
`https://www.h2oxtream.com/` source was checked and belongs to Upper Hutt, not Hamilton.

Founders Memorial Theatre Pool was checked against the current Hamilton Pools facility
paths and Hamilton City Council search. The current official sources did not list it as an
active Hamilton pool; council search results instead reference Founders Theatre site news
and redevelopment decisions.

Main facility schema emitted:

```json
{
  "name": "Waterworld",
  "id": "waterworld",
  "type": "pool",
  "council": "ham",
  "source": "hamilton-pools",
  "source_url": "https://www.hamiltonpools.co.nz/facilities/waterworld",
  "address": "Garnett Avenue, Te Rapa, Hamilton 3200",
  "phone": "07 958 5860",
  "email": "hamiltonpools@hcc.govt.nz",
  "hours": [
    {"label": "Monday - Friday", "text": "Kids & Toddler Pool: 8.00am to 8.00pm; ..."}
  ],
  "pool_details": ["25m lane-swimming pool", "50m lane-swimming pool", "Hydroslide"]
}
```

Partner pool schema uses the same facility shape and includes `status`, seasonal
`hours`, `hours_note`, `contact_note`, and visible fee rows where the partner-pools page
publishes them. As of discovery, Hamilton Pools says all partner pools are closed for the
season as of 29 March 2026.

Freshness: live static pages at command time. Hamilton Pools controls opening hours,
facility notices, and partner-pool seasonal updates.

### Wellington region aquatic facilities

Implemented for the following council codes:

- `hutt`: Hutt City Council / Hutt City Pools and Fitness
- `porirua`: Porirua City Council / Te Rauparaha Arena
- `uhutt`: Upper Hutt City Council / H2O Xtream
- `kapiti`: Kāpiti Coast District Council / Kāpiti Coast Aquatics

The CLI stores a small public-page catalogue for these aquatic facilities so that list/detail commands return name, address, hours, contact details, and pool details in a consistent schema. Each command still probes the relevant public source URL at runtime. The probe tries direct HTTP first and falls back to Chrome DevTools Protocol at `http://127.0.0.1:5100` when direct access is bot-walled or denied.

#### Hutt City pools

Implemented facilities:

- Huia Pool + Fitness: `https://pools.huttcity.govt.nz/our-pools/huia-pool`
- Te Ngaengae Pool + Fitness, with `Naenae Pool` as an alias: `https://pools.huttcity.govt.nz/our-pools/te-ngaengae-pool`
- Stokes Valley Pool + Fitness: `https://pools.huttcity.govt.nz/our-pools/stokes-valley-pool`
- McKenzie Baths Summer Pool: `https://pools.huttcity.govt.nz/our-pools/mckenzie-baths-summer-pool`

Direct HTTP result during discovery: Cloudflare challenge. CDP fallback at `127.0.0.1:5100` returned the public pages in the test environment.

#### Porirua Arena Aquatics

Implemented facility:

- Arena Aquatic Centre: `https://terauparaha-arena.co.nz/aquatics/visit-arena-pool/`

Direct HTTP result during discovery: public page loaded.

Data captured:

- Address: Te Rauparaha Arena Aquatics, 17 Parumoana Street, Porirua
- Contact: `(04) 237 1521`, `aquaticsbooking@poriruacity.govt.nz`
- Hours: Monday-Friday 5.30am-9pm; Saturday-Sunday and public holidays 8am-7pm; Anzac Day noon-7pm
- Pool details: lane pool, leisure pool, toddlers pool, lazy river, wave pool, hydroslide, spa pools, sauna, steam room, cafe

#### Upper Hutt H2O Xtream

Implemented facility:

- H2O Xtream Aquatic Centre: `https://www.h2oxtream.com/Facility/hours-and-prices`

Direct Python HTTP result during discovery: Akamai `403 Access Denied`. CDP fallback returned the public page.

Data captured:

- Address: 26 Brown Street, Upper Hutt
- Contact: `(04) 527 2113`, `h2oxtream@uhcc.govt.nz`
- Hours: Monday-Friday 5.30am-9pm; Saturday 8am-7pm; Sunday 8am-6.30pm; Women's Only Swim Night Sunday 7pm-9pm; most public holidays 8am-7pm
- Pool details: 25m lane pool, leisure pool, wave pool, Rapid River Ride, hydroslides, junior leisure area, spa, sauna, steam room

#### Kāpiti Coast Aquatics

Implemented facilities:

- Coastlands Aquatic Centre: `https://www.kapiticoastaquatics.co.nz/our-pools/coastlands-aquatic-centre/`
- Waikanae Pool: `https://www.kapiticoastaquatics.co.nz/our-pools/waikanae-pool/`
- Ōtaki Pool: `https://www.kapiticoastaquatics.co.nz/our-pools/otaki-pool/`

Direct HTTP result during discovery: public pages loaded.

Data captured:

- Coastlands: 10 Brett Ambler Way, Paraparaumu; 04 296 4746; main pool, programmes pool, toddler pool, hydroslide, flying fox, spa/sauna
- Waikanae: 52 Ngarara Road, Waikanae; 04 296 4789; seasonal outdoor 33.5m pool, toddler pool, hydroslide, BBQ/gazebo bookings
- Ōtaki: Haruātai Park, 200 Mill Road, Ōtaki; 06 364 5542; 33.5m lane pool, toddler pool, spa/sauna, slippery slope, splashpad
- Shared email: `swim@kapiticoast.govt.nz`

### Christchurch recreation and sport

Discovered, documented, not wired in v1.

- Public entry: `https://recandsport.ccc.govt.nz/`
- The source is public and references a Perfect Gym-backed client portal.
- The original council recreation page `https://ccc.govt.nz/recreation` returned an Incapsula challenge during discovery.

Reason not wired: useful schedules/facility state appear vendor-backed and need more careful endpoint mapping. The CLI returns a clear v1 note for Christchurch recreation commands instead of scraping challenge pages or authenticated surfaces.
