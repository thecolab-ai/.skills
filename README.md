# thecolab-ai/.skills

Community-contributed AI skills for useful New Zealand-specific data and workflows.

Point your agent at real NZ infrastructure, public datasets, market data, industry feeds, transport APIs, pricing sources, weather services, and other useful local information.

## What is this?

Think Folding@home, but for spare AI tokens. Instead of donating idle compute, the community contributes skills that make New Zealand-specific data actually usable by AI agents.

Every skill in this repo is a drop-in connector. Clone the repo, install the skill, and your agent gains access to real NZ-relevant data without you having to reverse-engineer the source.

## Try it in 30 seconds

```bash
git clone https://github.com/thecolab-ai/.skills
cd .skills

# NZ fuel prices, supply, and vessels
python3 skills/fuelclock-nz/scripts/cli.py summary

# Latest NZ news
python3 skills/nz-news/scripts/cli.py headlines

# Auckland Transport real-time (needs AT API key)
python3 skills/at-transport/scripts/cli.py alerts
```

No auth needed for `fuelclock-nz`, `metservice-nz`, or `nz-news`. `at-transport` requires a free API key from [dev-portal.at.govt.nz](https://dev-portal.at.govt.nz).

## About this repository

This repo is intentionally structured like a proper skills library.

It includes:
- `skills/` for real contributed skills
- `spec/` for the Agent Skills spec link plus our repo stance
- `template/` for a basic manual starting point
- `templates/` for richer scaffold variants (minimal, cli-workflow, tool-wrapper)
- `scripts/` for repo tooling like generation and validation (Python stdlib, no install needed)

We are borrowing the shape of the best public skills repos, but not copying their skill content.

## Available skills

| Skill | Description |
|-------|-------------|
| [at-transport](skills/at-transport/SKILL.md) | Query live Auckland Transport (AT) public transport data — stops, departures, service alerts, vehicle positions, routes, and network status. Use when the task involves Auckland buses, trains, ferries, or real-time transit information. |
| [auckland-bin-schedule](skills/auckland-bin-schedule/SKILL.md) | Query Auckland Council rubbish, recycling, and food scraps collection days for Auckland properties using the public collection-day website flow. Use when the task involves Auckland bin day, rubbish/recycling schedules, food scraps collection, address lookup, or property-id based collection checks. No account login required. |
| [bookme-nz](skills/bookme-nz/SKILL.md) | Query Bookme NZ public read-only deal/search endpoints for discounted activities, experiences, tours, restaurants, and last-minute things to do. Use when the task involves Bookme.co.nz deals, cheap activities by region/category, hot deals, cheapest current offers, restaurant discounts, or machine-readable public Bookme deal data. No login, booking, checkout, or account credentials required. |
| [briscoes-nz](skills/briscoes-nz/SKILL.md) | Query Briscoes NZ public product search, sale-flagged products, SKU detail, and store-finder endpoints through a lightweight no-login CLI. Use when the task involves Briscoes NZ homewares product lookup, current online prices, sale/deal snapshots, product SKUs, store locations, or machine-readable Briscoes public data. Read-only; no cart, account, checkout, or order actions. |
| [bunnings](skills/bunnings/SKILL.md) | Query Bunnings NZ public product search, pricing, product detail, category browse, store locator, and redemption/specials pages through a lightweight no-login CLI, with optional Bunnings AU support via --country au. Use when the task involves Bunnings New Zealand product lookup, live prices, SKUs, store details, category browsing, promotional/redemption offers, or machine-readable Bunnings product data. Read-only; no cart, checkout, account, or login actions. |
| [doc-nz](skills/doc-nz/SKILL.md) | Query Department of Conservation (DOC) New Zealand public huts, campsites, Great Walk booking availability, current alerts, and track pages through a lightweight read-only CLI. Use when the task involves DOC huts, campsites, Great Walks, availability calendars, track alerts, or DOC place status in New Zealand. |
| [eventfinda-nz](skills/eventfinda-nz/SKILL.md) | Search and inspect public Eventfinda New Zealand event listings from the no-login website pages. Use when the task involves finding NZ events by location, category, or keyword, getting Eventfinda event URLs, venues, dates, public session times, ticket badges, images, or JSON-LD detail from public event pages. |
| [fuelclock-nz](skills/fuelclock-nz/SKILL.md) | Query New Zealand fuel price, supply, vessel, geopolitical risk market, and recent headline data from fuelclock.nz. Use when the task involves NZ petrol or diesel prices, fuel supply security, days of supply remaining, MSO status, incoming fuel tankers, shipping market risk signals, or recent NZ fuel news. No authentication required. |
| [gaspy-nz](skills/gaspy-nz/SKILL.md) | Query Gaspy NZ public crowd-sourced fuel price statistics through a lightweight no-login CLI. Use when the task involves Gaspy crowd-sourced NZ fuel price snapshots, national observed averages, top cheapest 91 stations, station/brand counts, or recent confirmation totals. Read-only; no login or price reporting. |
| [homes-nz](skills/homes-nz/SKILL.md) | Query homes.co.nz public read-only NZ residential property estimate, sales history, suburb estimate trend, and nearby comparable-property endpoints through a lightweight no-login CLI. Use when the task involves HomesEstimate/HEV lookup, council/property attributes, historical sale records, or nearby comparable homes. No login or account credentials required for supported read-only commands. |
| [kmart](skills/kmart/SKILL.md) | Query Kmart NZ and AU public read-only product search, SKU lookup, specials-style product metadata, and store-location sitemap data through a lightweight no-login CLI. Use when the task involves Kmart NZ or AU product lookup, prices, product SKUs, clearance/promotional snapshots, store URL discovery, or machine-readable Kmart product data. Read-only; no login, cart, checkout, or account actions. |
| [metservice-nz](skills/metservice-nz/SKILL.md) | Query New Zealand weather data from the MetOcean API (MetService's data arm). Use when the task involves NZ weather forecasts, current conditions, marine/wave data, wind, rain, or atmospheric conditions for New Zealand locations. Requires METOCEAN_API_KEY. |
| [mitre10-nz](skills/mitre10-nz/SKILL.md) | Query Mitre 10 NZ public product search, specials, store locator, and product detail endpoints through a lightweight no-login CLI. Use when the task involves Mitre 10 NZ product lookup, online hardware prices, catalogue specials, store locations, product codes, or machine-readable Mitre 10 product data. Read-only; no cart, checkout, account, or order actions. |
| [newworld-nz](skills/newworld-nz/SKILL.md) | Query New World NZ stores, product categories, product search results, specials, and store-specific grocery prices using the public website's guest-token APIs. Use when the task involves New World NZ product lookup, Papakura or other store prices, specials, category browsing, or product ID decoration. No account login required. |
| [nz-airports](skills/nz-airports/SKILL.md) | Query live public New Zealand airport arrivals and departures data for supported airports through a lightweight read-only CLI. Use when the task involves current flight board data for Auckland, Christchurch, Queenstown, or Wellington airports, or live ADS-B aircraft positions near Auckland Airport. |
| [nz-buses](skills/nz-buses/SKILL.md) | Query Wellington-region Metlink bus data through a lightweight read-only CLI for stops, routes, arrivals, service alerts, and vehicle positions. Use for Wellington buses only; do not use for Wellington trains, ferries, cable car, or Auckland Transport. |
| [nz-cinemas](skills/nz-cinemas/SKILL.md) | Query live New Zealand cinema locations, now-playing movies, and session times across Event Cinemas, HOYTS, Reading Cinemas, Rialto, and HOYTS Berkeley Mission Bay through a lightweight read-only CLI. Use when the task involves NZ movie showtimes, cinema lookup, or machine-readable cinema session data. Read-only; no booking, login, seat, ticket, cart, or payment actions. |
| [nz-council](skills/nz-council/SKILL.md) | Query NZ council-area event listings and public recreation facilities through a lightweight read-only CLI. Use for Auckland, Wellington, or Christchurch what's-on events, Eventfinda council-area events, Auckland Council pools/leisure centres, Wellington pools/recreation centres, pool hours, and public lane availability snapshots. Not for rates, consents, rubbish, recycling, parking fines, bookings, logins, or payments. |
| [nz-electricity](skills/nz-electricity/SKILL.md) | Query public New Zealand electricity-market and lines-company outage data through a lightweight no-login CLI. Use when the task involves current NZ wholesale regional spot prices, grid demand, current grid carbon intensity, historical nodal wholesale prices, monthly generation output by fuel type, or public outage records from supported NZ lines companies. Read-only; uses public EM6 JSON feeds, Electricity Authority EMI CSV/report datasets, and distributor outage feeds. |
| [nz-ferries](skills/nz-ferries/SKILL.md) | Query public NZ ferry operator sailing schedules, fare/availability snapshots, and service alerts through a lightweight read-only CLI. Use for Cook Strait Interislander/Bluebridge sailings, SeaLink Waiheke/Great Barrier vehicle ferries, and NZ ferry operator alerts. Does not duplicate Auckland Transport GTFS live ferry tracking; use at-transport for AT Metro ferry real-time positions/departures. |
| [nz-healthpoint](skills/nz-healthpoint/SKILL.md) | Query Healthpoint NZ public health-service directory pages through a lightweight read-only CLI. Use when the task involves finding New Zealand pharmacies, GPs, urgent care, hospitals, dentists, specialists, locations, contact details, opening hours, or services listed on healthpoint.co.nz. Read-only; not for bookings, triage, referrals, or medical advice. |
| [nz-news](skills/nz-news/SKILL.md) | Aggregate RSS feeds from major New Zealand news websites. Use when the task involves NZ news, current events in New Zealand, what's happening in NZ, NZ headlines, or searching NZ stories by topic, timeframe, or source. No authentication required. |
| [nz-road-closures](skills/nz-road-closures/SKILL.md) | Query NZTA / Waka Kotahi Journey Planner state-highway road closures, roadworks, incidents, highway routes, regions, and traffic cameras through a lightweight no-login CLI. Use when the task involves New Zealand state highway journey conditions or machine-readable NZTA road-event data. Read-only; no alerts, accounts, or reporting actions. |
| [nz-trains](skills/nz-trains/SKILL.md) | Query Wellington Metlink train lines through a lightweight read-only CLI using GTFS and GTFS-RT data. Use when the task involves Johnsonville, Kapiti, Hutt Valley, Melling, or Wairarapa Line stations, arrivals, delays, alerts, or live train positions. Requires METLINK_API_KEY. |
| [nz-tv-guide](skills/nz-tv-guide/SKILL.md) | Query live New Zealand TV guide and EPG listings through a lightweight read-only CLI, focused on Sky NZ and Sky Sport with Freeview/TVNZ linear fallback where useful. Use when the task asks when a sport, show, channel, or movie is on TV in New Zealand, what channel it is on, or what is playing now or tonight. Read-only; no streaming, login, recording, account, purchase, or booking actions. |
| [nzbn-register](skills/nzbn-register/SKILL.md) | Search and lookup public New Zealand Business Number (NZBN) Register business/entity records through the NZBN website's read-only public proxy. Use when the task involves NZ business identity lookup, exact NZBN details, company/entity status, trading names, public addresses, websites, or source-register identifiers. No account login or API subscription key required for supported read-only commands. |
| [nzx](skills/nzx/SKILL.md) | Query NZX public delayed market data through a lightweight no-login CLI. Use when the task involves New Zealand Exchange listed share prices, S&P/NZX index levels, NZSX movers, historical daily OHLC-style performance, dividends, or ticker/company lookup. Read-only; no account, portfolio, order, or trading actions. |
| [paknsave-nz](skills/paknsave-nz/SKILL.md) | Query PAK'nSAVE NZ stores, product categories, product search results, specials, and store-specific grocery prices using the public website's guest-token APIs. Use when the task involves PAK'nSAVE NZ product lookup, Papakura or other store prices, specials, category browsing, or product ID decoration. No account login required. |
| [stats-nz](skills/stats-nz/SKILL.md) | Query public Stats NZ population, CPI, migration, GDP, time-series, and CSV catalogue data through a lightweight no-login CLI. Use when the task involves official New Zealand statistics from Stats NZ, Infoshare-derived CSV releases, population estimates or projections, CPI, GDP, or migration. Read-only; no API key or browser session. |
| [the-warehouse-nz](skills/the-warehouse-nz/SKILL.md) | Query The Warehouse NZ public read-only product search, specials, product detail, and store finder endpoints through a lightweight no-login CLI. Use when the task involves The Warehouse NZ product lookup, prices, specials, product SKUs, store locations, opening hours, or machine-readable Warehouse product/store data. Read-only; no cart, checkout, wishlist, account, or order actions. |
| [trademe-nz](skills/trademe-nz/SKILL.md) | Query Trade Me NZ public read-only listing/search endpoints for marketplace, property, rentals, motors, jobs, flatmates, regions, categories, and listing details. Use when the task involves Trade Me market research, listing lookup, property/rental scans, used-car scans, job searches, or machine-readable public listing data. No login or app credentials required for supported read-only commands. |
| [woolworths-nz](skills/woolworths-nz/SKILL.md) | Query Woolworths NZ public product search, specials, browse, and SKU detail endpoints through a lightweight no-login CLI. Use when the task involves Woolworths NZ product lookup, online grocery prices, specials, product SKUs, category browsing, or machine-readable Woolworths product data. Read-only; no trolley or checkout actions. |

## Skill sets

- [./skills](./skills) - Real skills contributed to this repo
- [./spec](./spec/agent-skills-spec.md) - Agent Skills spec and repo-specific stance
- [./template](./template/SKILL.md) - Minimal starter template
- [./templates](./templates) - Opinionated scaffold variants for different skill types

## Skill Development Guidelines

All skills in this repository use **Python** as the canonical entrypoint.

- **Entrypoint:** Every skill must have `scripts/cli.py` with `#!/usr/bin/env python3` as its first line.
- **Python stdlib preferred.** Use `urllib.request`, `json`, `re`, `xml.etree.ElementTree`, `html.parser`, `argparse`, and the standard library where possible. If a third-party dependency is truly necessary, declare it in a `requirements.txt` in the skill directory or via inline `# /// script` PEP 723 metadata.
- **TypeScript/Node skills are not accepted.** Any existing TS skills must be ported to Python before merging. Do not add new TypeScript or Node-based skill helpers.
- **Every skill must have:** `SKILL.md`, `scripts/cli.py`, and a `references/` directory if external API documentation is needed.
- **`--json` flag** for machine-readable output, following the pattern in existing Python skills.
- **`die()` function** that prints the error to stderr and exits non-zero.

## Contributing

We’ve made this repo opinionated on purpose.

Don’t freestyle the structure. Generate a scaffold, fill it in properly, then validate it before you open a PR.

### Quick start

```bash
git clone https://github.com/thecolab-ai/.skills
cd .skills

# No install step required — this repo has zero Node.js dependencies.
# Everything is Python stdlib.

python3 scripts/new_skill.py my-nz-skill --variant minimal
python3 scripts/validate_skill.py skills/my-nz-skill

# Run smoke tests (Python, no extra deps)
python3 skills/paknsave-nz/scripts/smoke_test.py
python3 skills/newworld-nz/scripts/smoke_test.py
python3 skills/briscoes-nz/scripts/smoke_test.py
python3 skills/trademe-nz/scripts/smoke_test.py
python3 skills/nzbn-register/scripts/smoke_test.py
python3 skills/eventfinda-nz/scripts/smoke_test.py
python3 skills/woolworths-nz/scripts/smoke_test.py
python3 skills/auckland-bin-schedule/scripts/smoke_test.py
```

### Available scaffold variants

- `minimal` for narrow one-file skills
- `cli-workflow` for multi-step skills with `references/` and `scripts/`
- `tool-wrapper` for skills centered around a specific CLI or API client

### Canonical skill folder structure

```text
skills/
  my-nz-skill/
    SKILL.md
    references/
    scripts/
      cli.py
    assets/
```

Only create the directories the skill actually needs.

### Contribution rules

- Skills should target useful NZ-specific data or workflows
- Public and open data is great, but not the only valid source
- If auth is required, document it clearly in `SKILL.md`, including:
  - How to obtain access
  - Required environment variables
  - Whether there’s a free tier
  - Example `.env` entry
- Skills that scrape public websites or consume open RSS feeds should note rate limits, caching expectations, and source stability concerns
- `description` must say what the skill does and when to use it
- Keep `SKILL.md` lean and operational
- Move deep detail into `references/`
- Put deterministic helpers in `scripts/cli.py` using Python stdlib
- Do not add per-skill `README.md`, `CHANGELOG.md`, or junk notes

Full guide: [CONTRIBUTING.md](CONTRIBUTING.md)

## Good areas to cover

- Government and public datasets
- Transport and logistics feeds
- Weather, marine, and environmental data
- Retail and pricing data
- Property, mapping, and local infrastructure data
- Industry-specific NZ information sources
- Other useful NZ-centric APIs or data workflows

## Community

Built by the [TheColab](https://thecolab.ai) community, New Zealand's AI builders' collective.

Join us at the next weekly catchup.
