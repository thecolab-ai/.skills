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

# NZ supermarket stores and pricing history
python3 skills/grocer-nz/scripts/cli.py stores --query Papakura

# Auckland Transport real-time (needs AT API key)
python3 skills/at-transport/scripts/cli.py alerts
```

No auth is needed for `fuelclock-nz` or `nz-news`. `at-transport` requires a
free API key from [dev-portal.at.govt.nz](https://dev-portal.at.govt.nz), and
`metservice-nz` requires a MetOcean API key.

## Optional browser-assisted mode

Most skills use direct public HTTP/API calls. Some modern sites only expose useful public data reliably inside a real browser context, especially on headless servers. Those skills may offer an explicit `--browser` flag.

Recommended runtime: [CloakBrowser](https://github.com/CloakHQ/CloakBrowser). Full convention: [docs/browser-assisted-skills.md](docs/browser-assisted-skills.md).

Recommended convention:

- `--browser` should use CloakBrowser when it is installed.
- CloakBrowser must be optional: normal validation and non-browser smoke tests should still run on clean hosts.
- If CloakBrowser is missing, the CLI should return a clear `cloakbrowser_not_installed` error so the agent can recommend installing it instead of silently pretending browser mode ran.
- Browser-assisted skills must stay read-only and stop before login, checkout, payment, booking, cart mutation, or protected account actions.
- CAPTCHA, request-auth, and bot challenges are blocked states, not puzzles to defeat; return an explicit blocked flag or clear error and use a public fallback when one exists.

## Access policy

Skills prefer official APIs, feeds, and downloads that respond to public, unauthenticated requests. The shared [`lib/nzfetch.py`](lib/nzfetch.py) helper makes one direct request first and, when a user has configured a proxy, may make a bounded set of retries for blocked responses, rate limits, truncated reads, or recognised challenge pages. Proxy settings are optional secrets loaded from the environment; skills must never commit, print, or include them in errors.

If the bounded attempts cannot retrieve the public resource, the skill must return an explicit blocked or rate-limited outcome rather than an empty success. The repository does not provide CAPTCHA solving, authentication bypass, protected-token forgery, account operation, checkout, booking, payment, or transaction automation. Full contributor guidance is in [CONTRIBUTING.md](CONTRIBUTING.md), and source operators can request removal, attribution, rate changes, or a different supported integration through [COMPLAINTS.md](COMPLAINTS.md).

## About this repository

This repo is intentionally structured like a proper skills library.

It includes:
- `skills/` for real contributed skills
- `spec/` for the Agent Skills spec link plus our repo stance
- `templates/` for the five source/workflow scaffold variants
- `scripts/` for scaffolding, validation, contracts, pack installation, and catalogue generation
- `skills.json` and `packs/` for generated discovery and trust-based installation manifests

We are borrowing the shape of the best public skills repos, but not copying their skill content.

## Install a trust pack

The default `nz-public-data` pack contains only public read-only connectors. It
excludes commercial websites, personal data, paid providers, internal
publishing workflows, and artifact writers. Preview an installation before
copying it into an explicit skills directory:

```bash
python3 scripts/install_pack.py nz-public-data \
  --target /absolute/path/to/agent-skills \
  --dry-run

python3 scripts/install_pack.py nz-public-data \
  --target /absolute/path/to/agent-skills
```

The six generated manifests and their trust models are documented in
[`docs/packs.md`](docs/packs.md). Existing users can continue using the legacy
`nz-skills` aggregate while migrating to a narrower pack.

## For businesses whose APIs we touch

If you operate a service that one of these skills connects to and you'd prefer we didn't, email **adam@thecolab.ai** with the skill name and a brief reason. We action good-faith requests from the affected operator promptly, usually within 5 working days. Full process in [COMPLAINTS.md](COMPLAINTS.md).

But before you do, hear us out on why we built this.

These skills access endpoints that respond to unauthenticated public requests. Requests may use an optional user-configured proxy with bounded retries, as described in the access policy above. We don't bypass authentication, solve CAPTCHAs, forge protected tokens, or operate accounts and transactions. Users of these skills are responsible for complying with the terms of service of the underlying provider. What we've done is make public data legible to AI agents, so a Kiwi using an LLM can actually get useful answers about NZ fuel prices, bus times, pharmacy stock, or property data without us all reinventing the same wrapper a thousand times.

The thing is, agents are going to access this data either way. The only question is whether they do it well, with one clean shared connector, or badly, with ten thousand half-broken scrapers hammering your servers. We think one clean connector is better for everyone, you included.

If you're a business looking at this and thinking "how do we actually want AI agents to interact with our data" rather than "how do we stop them", that's a conversation worth having. We do that work. Email **adam@thecolab.ai** or [open an issue](https://github.com/thecolab-ai/.skills/issues/new) and we'll help you design the right surface: a proper agent-ready API, sensible rate limits, an auth model that fits, the lot. The businesses that figure this out early will own their corner of the agent economy. The ones that don't will get scraped anyway, just less efficiently.

## Available skills

<!-- BEGIN GENERATED SKILLS TABLE: run python3 scripts/generate_catalogue.py -->
| Skill | Trust pack | Source owner | Description |
|---|---|---|---|
| [airnz-flights](skills/airnz-flights/SKILL.md) | `nz-commercial-web` | Air New Zealand | Search public Air New Zealand fare snapshots and timetable fallback data through a lightweight no-login CLI. Use when the task involves Air NZ route/date fare snapshots, fare products, flight numbers, departure/arrival times, duration, stops, or machine-readable current flight data. Optional --browser mode uses CloakBrowser when installed and returns cloakbrowser_not_installed when unavailable. Read-only; no login, Airpoints, seat holds, booking, payment, manage-booking, or checkout actions. |
| [akahu-personal](skills/akahu-personal/SKILL.md) | `nz-personal-data` | Akahu | Query personal transactional bank-account data — account lists, balances, settled/pending transactions, account-specific transaction history, and private JSON/CSV exports — from Akahu, a New Zealand open-banking provider. Use when the task involves personal bank data exports, NZ account balances, transaction analysis, cashflow/spending categorisation, or inspecting authenticated Personal App banking data. Requires user-provided AKAHU_APP_TOKEN and AKAHU_USER_TOKEN; never smoke-test against real personal data in CI. |
| [animates-nz](skills/animates-nz/SKILL.md) | `nz-commercial-web` | Animates New Zealand | Use when looking up Animates NZ products, current public prices, availability, or product details. Queries bounded public Magento search results and parses product-page JSON-LD through a read-only Python CLI; no cart, checkout, account, payment, prescription, booking, grooming, or other mutations. |
| [at-transport](skills/at-transport/SKILL.md) | `nz-public-data` | Auckland Transport | Query live Auckland Transport (AT) public transport data — stops, departures, service alerts, vehicle positions, routes, and network status. Use when the task involves Auckland buses, trains, ferries, or real-time transit information. |
| [auckland-bin-schedule](skills/auckland-bin-schedule/SKILL.md) | `nz-public-data` | Auckland Council | Query Auckland Council rubbish, recycling, and food scraps collection days for Auckland properties using the public collection-day website flow. Use when the task involves Auckland bin day, rubbish/recycling schedules, food scraps collection, address lookup, or property-id based collection checks. No account login required. |
| [baby-factory-nz](skills/baby-factory-nz/SKILL.md) | `nz-commercial-web` | The Baby Factory | Use when searching Baby Factory NZ products, checking current public sale prices, or reading product details and offers. Parses bounded public search-page state and product JSON-LD through a read-only Python CLI; no cart, checkout, account, payment, booking, hire, registry, or other mutations. |
| [baby-on-the-move-nz](skills/baby-on-the-move-nz/SKILL.md) | `nz-commercial-web` | Baby On The Move | Query Baby On The Move NZ's public Shopify product search, product details, current online price snapshots, variant availability, and verified store-locations page. Use when comparing Baby On The Move products, looking up a product handle or URL, or finding official store information. Read-only; no cart, checkout, account, payment, fitting booking, hire, or other mutations. |
| [babycity-nz](skills/babycity-nz/SKILL.md) | `nz-commercial-web` | babycity | Query babycity NZ's public Shopify product search, product details, current online price snapshots, variant availability, and verified store-locator page. Use when comparing babycity products, looking up a product handle or URL, or finding official babycity store information. Read-only; no cart, checkout, account, payment, booking, or other mutations. |
| [bargainchemist-nz](skills/bargainchemist-nz/SKILL.md) | `nz-commercial-web` | Bargain Chemist | Query Bargain Chemist NZ public product search, suggestions, and Shopify product JSON through a lightweight no-login CLI. Use when the task involves Bargain Chemist NZ product lookup, current online prices, availability, product handles, or machine-readable public product data. Read-only; no cart, checkout, account, prescription, or order actions. |
| [biosecurity-nz](skills/biosecurity-nz/SKILL.md) | `nz-public-data` | Ministry for Primary Industries | Searches New Zealand biosecurity public data from the Official NZ Pest Register, PIER import requirements metadata, data.govt.nz CKAN records, and MPI active-response pages. Use when checking whether an organism is regulated, unwanted, or notifiable in NZ; finding pest synonyms/statuses; resolving import commodity requirement links; listing current biosecurity responses; or documenting source/access caveats. |
| [bookme-nz](skills/bookme-nz/SKILL.md) | `nz-commercial-web` | Bookme | Query Bookme NZ discounted activities, experiences, tours, restaurants, and last-minute deals. Supports hot deals, cheapest offers, regional/category search, and deal detail. No login, booking, or payment. |
| [briscoes-nz](skills/briscoes-nz/SKILL.md) | `nz-commercial-web` | Briscoe Group | Query Briscoes NZ homewares product search, sale/deal snapshots, SKU detail, and store-finder. Use for Briscoes product lookup, prices, sale products, or store locations. No cart or account. |
| [bunnings](skills/bunnings/SKILL.md) | `nz-commercial-web` | Bunnings | Query Bunnings NZ product search, prices, SKUs, store details, category browse, and redemption specials via no-login CLI. Optional --country au for Bunnings Australia. Read-only; no cart, checkout, or account actions. |
| [cab-cabnet-nz](skills/cab-cabnet-nz/SKILL.md) | `nz-public-data` | Citizens Advice Bureau New Zealand | Use when Codex needs to discover Citizens Advice Bureau NZ public client-enquiry evidence, CABNET source availability, advice category taxonomy, or report-backed enquiry trend caveats for New Zealand social-need analysis; wraps keyless cab.org.nz and data.govt.nz discovery and reports explicit blocked states when aggregated CABNET counts are not publicly exported. |
| [carjam-nz](skills/carjam-nz/SKILL.md) | `nz-commercial-web` | CarJam | Query CarJam NZ public/basic vehicle information pages through a lightweight no-login CLI. Use when the task involves New Zealand vehicle plate, VIN, or chassis lookup, make/model/year/colour, public registration/WOF/licence snippets, odometer snippets, or CarJam source URLs. Read-only; no paid report purchase, owner lookup, login, account, or write actions. |
| [charities-services-nz](skills/charities-services-nz/SKILL.md) | `nz-public-data` | Charities Services | Query Charities Services New Zealand public OData for registered charities, organisation metadata, public officer roles, sectors/activity taxonomy, annual-return financials, and grant-making signals. Use when the task involves NZ charity lookup, charity registration numbers, grant-making charities, GrantsPaidWithinNZ, annual returns, Charities Register summaries, officers, or schema discovery from odata.charities.govt.nz. Read-only and no API key required. |
| [chemistwarehouse-nz](skills/chemistwarehouse-nz/SKILL.md) | `nz-commercial-web` | Chemist Warehouse | Query Chemist Warehouse NZ public searchapiv2 suggestion, product search, category listing, and product detail endpoints through a lightweight no-login CLI. Use for live NZ pharmacy product names, prices, categories, product IDs, ratings, and machine-readable Chemist Warehouse NZ data. Read-only; no cart, checkout, account, prescription, order, or payment mutations. |
| [child-poverty-nz](skills/child-poverty-nz/SKILL.md) | `nz-public-data` | Stats NZ | Query official New Zealand child poverty statistics from Stats NZ — the nine Child Poverty Reduction Act measures (BHC/AHC low-income lines, material hardship, severe material hardship, DEP-17 deprivation), national rates and child numbers 2007-2025 with confidence intervals, and breakdowns by region, ethnicity (Māori, Pacific, European, Asian) and disability. Use for tasks about NZ child poverty rates, kids in hardship or deprivation, poverty by region or ethnic group, annual change, or finding the latest Stats NZ child-poverty release. |
| [christchurch-bin-schedule](skills/christchurch-bin-schedule/SKILL.md) | `nz-public-data` | Christchurch City Council | Query Christchurch City Council kerbside collection schedules (rubbish, recycling, organics). Use when the task involves Christchurch bin days, kerbside collection for a Christchurch address, or CCC three-bin schedules. Supports address search (name → RatingUnitID) or direct RatingUnitID lookup. No account required. |
| [class4-grants-nz](skills/class4-grants-nz/SKILL.md) | `nz-public-data` | Department of Internal Affairs | Query New Zealand Class 4 gambling grants and Granted.govt.nz public data from DIA/data.govt.nz. Use when the task involves pokie-machine grant funding, gaming-machine profits, grant recipients, Class 4 societies/funders, grant categories, regional/TLA grant totals, accepted or declined grant applications, or discovering the related venues and gaming-machine quarterly datasets. Read-only and no API key required. |
| [colab-course-publisher](skills/colab-course-publisher/SKILL.md) | `thecolab-internal` | TheColabAI | Use when Codex needs to create, edit, publish, package, or validate The Colab CourseViewerPlatform course content, including tenant course repos, course.json, blueprint.json, module manifests, markdown lessons, quizzes, generated educational images, HTML widgets, and live CourseViewerPlatform content checks. |
| [comcom-connectivity-map](skills/comcom-connectivity-map/SKILL.md) | `nz-public-data` | Commerce Commission | Inspect Commerce Commission Telecommunications Connectivity Map public metadata, provider-list workbooks, annual monitoring report links, and source caveats for rural broadband coverage research. Use when the task involves ComCom connectivity map data, rural broadband coverage, provider supplied coverage, annual telecommunications monitoring reports, or distinguishing coverage from address-level orderability. |
| [companies-office-nz](skills/companies-office-nz/SKILL.md) | `nz-public-data` | New Zealand Companies Office | Search and inspect New Zealand Companies Register records through read-only public website endpoints. Use when the task involves NZ company lookup by name, company number, or NZBN; company status, incorporation date, entity type; director names and appointment dates; shareholder allocations and percentages; registered addresses; filing history and public documents; or any company governance data not covered by the NZBN Register skill. No login, API key, or account required. Read-only. |
| [data-govt-nz](skills/data-govt-nz/SKILL.md) | `nz-public-data` | New Zealand Government Chief Data Steward | Search and inspect New Zealand Government open-data catalogue datasets, organisations, resources, and datastore records through the public CKAN API at catalogue.data.govt.nz. Use when the task involves finding NZ public datasets, agencies, downloadable resources, CSV/API links, metadata, or data.govt.nz catalogue records. Read-only and no API key required. |
| [dataforseo](skills/dataforseo/SKILL.md) | `paid-data-connectors` | DataForSEO | Query DataForSEO for SEO + market-validation data — Google SERP rank checks, keyword search volume, keyword discovery (semantic ideas, related-search expansion, search-intent classification), domain/competitor analytics, backlinks, and App Store / Play data (which apps rank + review mining). Use when checking where a site ranks, finding or discovering what people search for, validating demand and competition for an app/business idea, analysing a domain or its competitors, auditing backlinks, or mining competitor app reviews for pain points. Requires DATAFORSEO_USERNAME (or DATAFORSEO_LOGIN) and DATAFORSEO_PASSWORD. Every call spends DataForSEO credits. |
| [deprivation-nz](skills/deprivation-nz/SKILL.md) | `nz-public-data` | University of Otago | Look up New Zealand small-area socioeconomic deprivation (NZDep2023) by SA1/SA2 code, place name, decile, or SA3 region - the standard index of relative poverty, material hardship, and disadvantage used for health, housing, school decile, child poverty, and funding analysis. No API key or login required. |
| [dimples-nz](skills/dimples-nz/SKILL.md) | `nz-commercial-web` | Dimples | Query Dimples NZ's public Shopify product search, product details, current online price snapshots, variant availability, and verified store-locator page. Use when comparing Dimples products, looking up a product handle or URL, or finding official Dimples Auckland and Christchurch store information. Read-only; no cart, checkout, account, payment, booking, or other mutations. |
| [doc-nz](skills/doc-nz/SKILL.md) | `nz-public-data` | Department of Conservation | Query Department of Conservation (DOC) New Zealand public huts, campsites, Great Walk booking availability, current alerts, and track pages through a lightweight read-only CLI. Use when the task involves DOC huts, campsites, Great Walks, availability calendars, track alerts, or DOC place status in New Zealand. |
| [drinking-water-register-nz](skills/drinking-water-register-nz/SKILL.md) | `nz-public-data` | Taumata Arowai | Query public Hinekōrako drinking-water supplier, supply, service-area and document records. Use for registration discovery; registration is not proof of current water safety. |
| [education-counts-nz](skills/education-counts-nz/SKILL.md) | `nz-public-data` | Ministry of Education | Query Education Counts teacher workforce and initial teacher education public sources for New Zealand teacher supply research. Use when the task involves ITE enrolments/completions, teacher numbers, teacher entry/leaving, teacher turnover, teacher demand and supply projections, workbook URLs, or source caveats for Ministry of Education teacher workforce data. |
| [eeca-ev-chargers-nz](skills/eeca-ev-chargers-nz/SKILL.md) | `nz-public-data` | Energy Efficiency and Conservation Authority | Query EECA New Zealand public EV charger dashboard CSVs and data.govt.nz metadata, including public charger units, co-funded charger pipeline rows, EV metrics by district or region, BEVs per charger, charging kW, site counts, and source caveats. Use for NZ EV infrastructure, EVRoam-derived charger coverage, charging equity, public co-funding, and For Good transport research. |
| [elections-nz](skills/elections-nz/SKILL.md) | `nz-public-data` | Electoral Commission | Query official New Zealand election results, electorate voting, turnout and published finance resources from the Electoral Commission. |
| [energy-hardship-nz](skills/energy-hardship-nz/SKILL.md) | `nz-public-data` | MBIE, Stats NZ, and Electricity Authority | Query New Zealand energy-hardship evidence from MBIE energy-hardship measure reports, Stats NZ Household Expenditure Statistics household energy and electricity expenditure tables, and Electricity Authority disconnection dashboard/source metadata. Use for NZ energy poverty, electricity affordability, domestic-energy burden, 2M or 10 percent hardship proxy research, HES energy expenditure, MBIE five hardship measures, and disconnections for non-payment caveats. |
| [ero-school-reports-nz](skills/ero-school-reports-nz/SKILL.md) | `nz-public-data` | Education Review Office | Find and retrieve official Education Review Office school reports with section or page provenance. Use for report evidence, not rankings. |
| [eventfinda-nz](skills/eventfinda-nz/SKILL.md) | `nz-commercial-web` | Eventfinda | Search and inspect public Eventfinda New Zealand event listings from the no-login website pages. Use when the task involves finding NZ events by location, category, or keyword, getting Eventfinda event URLs, venues, dates, public session times, ticket badges, images, or JSON-LD detail from public event pages. |
| [fenz-incidents-nz](skills/fenz-incidents-nz/SKILL.md) | `nz-public-data` | Fire and Emergency New Zealand | Query official Fire and Emergency New Zealand operational reports and annual incident datasets by place, type and period. |
| [find-experts-nz](skills/find-experts-nz/SKILL.md) | `nz-public-data` | OpenAlex and contributing directories | Discover New Zealand experts by topic across public sources — the OpenAlex and Crossref scholarly graphs, Wikidata, ORCID, and university "Find an Expert" directories (University of Auckland, Massey). Use when you need a citable candidate shortlist of who could speak to a research question — expert matching, "find an expert", verifying a finding, or building an SME/advisory candidate list. Returns ephemeral shortlists from public data only — discovery is not consent and output is never a contact list. |
| [first-table-nz](skills/first-table-nz/SKILL.md) | `nz-commercial-web` | First Table | Query First Table NZ restaurants, 50%-off early-table deals, city/suburb discovery, cuisine search, and availability slots. Read-only; no booking, login, or payment. |
| [fma-nz](skills/fma-nz/SKILL.md) | `nz-public-data` | Financial Markets Authority | Query FMA warnings/alerts and licensed provider pages for NZ crowdfunding, peer-to-peer lending, and financial-advice sources. Search alerts, list/register providers by type, and return source-backed JSON payloads for machine-readable workflows. |
| [fuelclock-nz](skills/fuelclock-nz/SKILL.md) | `nz-public-data` | FuelClock | Query NZ fuel prices, supply, inbound tankers, MSO status, geopolitical shipping risk markets, and NZ fuel headlines from fuelclock.nz. No authentication required. |
| [fyi-oia-nz](skills/fyi-oia-nz/SKILL.md) | `nz-public-data` | FYI and mySociety | Query FYI.org.nz OIA/LGOIMA public authorities and request records through a read-only Alaveteli API surface, including request metadata, authority lookups, request timelines, and request search. |
| [gaspy-nz](skills/gaspy-nz/SKILL.md) | `nz-commercial-web` | Gaspy | Query Gaspy NZ public crowd-sourced fuel price statistics through a lightweight no-login CLI. Use when the task involves Gaspy crowd-sourced NZ fuel price snapshots, national observed averages, top cheapest 91 stations, station/brand counts, or recent confirmation totals. Read-only; no login or price reporting. |
| [geonet-nz](skills/geonet-nz/SKILL.md) | `nz-public-data` | GeoNet | Query GeoNet New Zealand public earthquake, volcano alert, and GeoNet news endpoints through a lightweight no-login CLI. Use when the task involves recent NZ earthquakes, felt/MMI-filtered quakes, earthquake detail by publicID, volcanic alert levels, volcanic activity bulletins, or GeoNet public geohazard updates. Read-only; no authentication required. |
| [gets-procurement-nz](skills/gets-procurement-nz/SKILL.md) | `nz-public-data` | New Zealand Government Electronic Tenders Service | Discover New Zealand public procurement opportunities and award notices from GETS, MBIE open-data metadata, and procurement.govt.nz significant-service-contract sources. Use when Codex needs keyless NZ government tender searches, current GETS notices, RFx detail by ID, recent completed/award notices, procurement source URLs, or significant service contract dashboard summaries. |
| [grocer-nz](skills/grocer-nz/SKILL.md) | `nz-commercial-web` | Grocer.nz | Query grocer.nz public NZ supermarket price data — store lookup, product search, current per-store prices, and historical product price rows from public DuckDB/parquet assets. Use for NZ grocery/supermarket pricing across Woolworths, New World, PAK'nSAVE, Fresh Choice, and related stores. Read-only; no login or private user data. |
| [gwrc-hilltop-nz](skills/gwrc-hilltop-nz/SKILL.md) | `nz-public-data` | Greater Wellington Regional Council | Query Greater Wellington Regional Council Hilltop environmental monitoring time series through a lightweight no-login CLI: rainfall gauges, river and stream levels and flows, monitoring site lists with coordinates, and per-site measurement catalogues. Use when the task involves Wellington-region rainfall totals, current river levels, flood-watch context, or Hilltop time-series data. Read-only; no authentication required. |
| [healthcert-rest-homes-nz](skills/healthcert-rest-homes-nz/SKILL.md) | `nz-public-data` | Ministry of Health | Query Ministry of Health certified aged-care rest-home provider data, facility pages, audit-report links, and certification caveats. Use when the task involves NZ rest-home certification, aged-care provider beds, legal entities, auditors, certificate end dates, audit report metadata, corrective-action page availability, or source caveats for bot-protected Ministry facility pages. |
| [homes-nz](skills/homes-nz/SKILL.md) | `nz-commercial-web` | Homes.co.nz | Query homes.co.nz NZ residential property estimates (HomesEstimate/HEV), sales history, suburb trends, and nearby comparable properties. No login required. |
| [household-hardship-nz](skills/household-hardship-nz/SKILL.md) | `nz-public-data` | Stats NZ | Query New Zealand household material hardship, child and family poverty, income adequacy, housing affordability and rent burden, low-income household counts, and the Gini coefficient of income inequality from the Stats NZ Household Economic Survey "Household Wellbeing" release on data.govt.nz. Use for questions about NZ deprivation, cost-of-living stress, who is struggling to afford housing, hardship by region or ethnicity (including Maori households), or income inequality figures with confidence intervals. |
| [interest-co-nz](skills/interest-co-nz/SKILL.md) | `nz-commercial-web` | interest.co.nz | Query interest.co.nz public mortgage-rate tables through a lightweight no-login HTML parser. Use when the task involves current New Zealand mortgage rates, bank home-loan rates, variable/floating rates, fixed terms from 6 months to 5 years, special LVR rows, or comparing advertised mortgage rates across NZ lenders. Read-only; no application, lead, login, or quote submission. |
| [ird-wff-rates-nz](skills/ird-wff-rates-nz/SKILL.md) | `nz-public-data` | Inland Revenue | Query Inland Revenue Working for Families, Best Start, Minimum Family Tax Credit, In-Work Tax Credit, and FamilyBoost public rate/threshold parameters. Use when the task involves NZ family entitlement pre-check inputs, WFF tax-credit rates, abatement thresholds/rates, Best Start rules, FamilyBoost income caps, or official IRD eligibility source links. Read-only, no login or API key; optional source probes handle IRD availability gracefully. |
| [jetstar-flights](skills/jetstar-flights/SKILL.md) | `nz-commercial-web` | Jetstar | Search public Jetstar New Zealand one-way fare-cache flight availability through a no-login Node CLI. Use when the task involves Jetstar route/date fare snapshots, low-fare availability, flight IDs, prices, or machine-readable current Jetstar availability. Read-only; no login, Club Jetstar account, booking, seat hold, payment, manage-booking, or checkout actions. |
| [justice-data-nz](skills/justice-data-nz/SKILL.md) | `nz-public-data` | Ministry of Justice | Query New Zealand Ministry of Justice data tables for finalised charges, convictions, sentencing outcomes, family-violence offences, and youth justice statistics. Use when Codex needs official MoJ justice statistics, workbook URLs, or JSON rows from public no-key justice data tables. |
| [kmart](skills/kmart/SKILL.md) | `nz-commercial-web` | Kmart | Query Kmart NZ and AU product search, prices, SKU lookup, clearance/promotional snapshots, and store-location data. Read-only; no login, cart, checkout, or account actions. |
| [lawa-nz](skills/lawa-nz/SKILL.md) | `nz-public-data` | Land Air Water Aotearoa | Query Land Air Water Aotearoa (LAWA) public river-quality sites, swimming sites, and river indicator summaries through no-login Umbraco JSON endpoints. Use when the task involves NZ river quality, macroinvertebrate/community index data, E. coli/nutrient indicator bands, swim-site listings, or LAWA environmental monitoring site discovery. Read-only. |
| [legacy-aquatics-nz](skills/legacy-aquatics-nz/SKILL.md) | `nz-commercial-web` | Legacy Aquatics | Query Legacy Aquatics NZ public WooCommerce category, product-search, and product-page HTML through a no-login read-only CLI. Use when a task needs current aquarium or reptile product discovery and source detail; never for cart, checkout, account, payment, hire, or husbandry advice. |
| [legislation-nz](skills/legislation-nz/SKILL.md) | `nz-public-data` | New Zealand Parliamentary Counsel Office | Resolves, searches, and checks New Zealand Acts, Bills, secondary legislation, sections, point-in-time versions, and update feeds from official legislation.govt.nz and PCO sources. Use when a task needs NZ legislation text, exact section citations, current in-force status, amendments since a date, current Bills, or source caveats. |
| [linz-data-service](skills/linz-data-service/SKILL.md) | `nz-public-data` | Toitū Te Whenua LINZ | Search and inspect LINZ Data Service public Koordinates catalogue layers, tables, services, licences, tags, and download/view capabilities through no-login JSON endpoints. Use when the task involves Toitū Te Whenua LINZ datasets such as addresses, parcels, imagery, hydrography, roads, property, or geospatial layers. Read-only; no API key needed for catalogue metadata. |
| [linz-title-memorials](skills/linz-title-memorials/SKILL.md) | `nz-public-data` | Toitū Te Whenua LINZ | Use when researching NZ Records of Title memorials, Building Act 2004 s73/s74 natural-hazard title entries, or LINZ/Landonline title memorial aggregate counts. Inspects public LINZ/LDS metadata safely, explains public-data and privacy limits, and generates aggregate-only OIA request templates; does not expose title, owner, address, or small-cell data. |
| [mbie-jobs-online-nz](skills/mbie-jobs-online-nz/SKILL.md) | `nz-public-data` | Ministry of Business, Innovation and Employment | Query official MBIE Jobs Online advertised-vacancy trends by occupation, industry, region and skill level with methodology context. |
| [medsafe-recalls-nz](skills/medsafe-recalls-nz/SKILL.md) | `nz-public-data` | Medsafe | Search official Medsafe medicine and medical-device recalls and safety communications. Use for product, batch, hazard and action retrieval; not medical advice. |
| [mental-health-data-nz](skills/mental-health-data-nz/SKILL.md) | `nz-public-data` | Ministry of Health | Use when Codex needs New Zealand mental-health regulatory data from ODMHAS reports, seclusion/restraint summaries, MH&A KPI Programme indicator metadata, inpatient inspection counts, District Inspector sources, or source caveats for public mental-health transparency work. Read-only, keyless, and stdlib-only. |
| [metservice-nz](skills/metservice-nz/SKILL.md) | `nz-public-data` | MetOcean Solutions | Query New Zealand weather data from the MetOcean API (MetService's data arm). Use when the task involves NZ weather forecasts, current conditions, marine/wave data, wind, rain, or atmospheric conditions for New Zealand locations. Requires METOCEAN_API_KEY. |
| [mitre10-nz](skills/mitre10-nz/SKILL.md) | `nz-commercial-web` | Mitre 10 New Zealand | Query Mitre 10 NZ product search, specials, store locator, and product detail. Use for Mitre 10 NZ product lookup, hardware prices, catalogue specials, product codes, or store locations. No cart or account. |
| [mot-fleet-statistics-nz](skills/mot-fleet-statistics-nz/SKILL.md) | `nz-public-data` | Ministry of Transport | Query New Zealand Ministry of Transport annual fleet statistics workbooks for VKT, fleet composition, and light-fleet fuel or powertrain counts. Use when the task involves NZ vehicle kilometres travelled, annual fleet statistics, Ministry fleet workbook tables, EV-transition research, fuel counts, or source caveats for bot-protected transport data. |
| [msd-benefits-nz](skills/msd-benefits-nz/SKILL.md) | `nz-public-data` | Ministry of Social Development | Query official New Zealand MSD benefit statistics - Jobseeker Support, Sole Parent Support, Supported Living Payment, Youth Payment, NZ Superannuation and Veteran's Pension recipient numbers by quarter, gender, ethnicity, age group, and Work and Income region. Use for working-age benefit numbers, main benefit counts, welfare/superannuation recipient breakdowns, and benefit trends. No API key or browser session required. |
| [nature-baby-nz](skills/nature-baby-nz/SKILL.md) | `nz-commercial-web` | Nature Baby | Query Nature Baby NZ's public Shopify product search, product details, current online price snapshots, variant availability, and verified store-details page. Use when comparing Nature Baby products, looking up a product handle or URL, or finding official Nature Baby store information. Read-only; no cart, checkout, account, payment, booking, or other mutations. |
| [newworld-nz](skills/newworld-nz/SKILL.md) | `nz-commercial-web` | Foodstuffs New Zealand | Query New World NZ stores, product categories, product search results, specials, and store-specific grocery prices using the public website's guest-token APIs. Use when the task involves New World NZ product lookup, Papakura or other store prices, specials, category browsing, or product ID decoration. No account login required. |
| [nz-ai-policy](skills/nz-ai-policy/SKILL.md) | `nz-public-data` | Department of Internal Affairs | Map and brief official New Zealand AI policy guidance — public-service AI framework, responsible GenAI guidance, procurement, privacy, algorithm governance, AI strategy, and source-backed agency checklists. Use when the task involves NZ public-sector AI policy citations, compliance review, proposal evidence, AI governance questions, or agency GenAI policy drafting. |
| [nz-airports](skills/nz-airports/SKILL.md) | `nz-commercial-web` | Participating New Zealand airport operators | Query live public New Zealand airport arrivals and departures data for supported airports through a lightweight read-only CLI. Use when the task involves current flight board data for Auckland, Christchurch, Queenstown, or Wellington airports, or live ADS-B aircraft positions near Auckland Airport. |
| [nz-angel-investment](skills/nz-angel-investment/SKILL.md) | `nz-public-data` | New Zealand Growth Capital Partners and Angel Association NZ | Queries New Zealand angel and seed investment publication sources from NZGCP Young Company Finance, NZGCP annual/ecosystem reports, and Angel Association NZ member and investment-publication pages. Use when the task involves NZ early-stage capital, angel investment, seed funding, Young Company Finance deal or investment counts, Aspire/Elevate reporting, investor directories, Angel Market reports, or source-backed publication discovery; read-only and no API key required. |
| [nz-buses](skills/nz-buses/SKILL.md) | `nz-public-data` | Metlink | Query Wellington-region Metlink bus data through a lightweight read-only CLI for stops, routes, arrivals, service alerts, and vehicle positions. Use for Wellington buses only; do not use for Wellington trains, ferries, cable car, or Auckland Transport. |
| [nz-case-law](skills/nz-case-law/SKILL.md) | `nz-public-data` | Courts of New Zealand | Search publicly available official New Zealand judgments by citation, court, party, judge, date and subject. Retrieval only; coverage is not exhaustive and this is not legal advice. |
| [nz-cinemas](skills/nz-cinemas/SKILL.md) | `nz-commercial-web` | Participating New Zealand cinema operators | Query NZ cinema locations, now-playing movies, and session times across Event Cinemas, HOYTS, Reading Cinemas, Rialto, and Berkeley Mission Bay. Read-only; no booking, ticket, or payment. |
| [nz-comcom](skills/nz-comcom/SKILL.md) | `nz-public-data` | Commerce Commission | Search New Zealand Commerce Commission cases, news, decisions, and reports from comcom.govt.nz. Use when the task involves the Commerce Commission (ComCom), the case register (merger clearances, cartel, consumer credit, fair trading), market studies, regulated industries (electricity, gas, telco, fibre, airports, dairy, grocery, fuel), media releases, or finding ComCom report/decision PDFs. Keyless, read-only; no login. |
| [nz-consultations](skills/nz-consultations/SKILL.md) | `nz-public-data` | New Zealand Government | List open New Zealand central-government consultations, agencies, topics, deadlines and official submission links. Read-only; does not submit responses. |
| [nz-council](skills/nz-council/SKILL.md) | `nz-public-data` | Participating councils and public venue operators | Query NZ council events and public recreation facilities (pools, leisure centres) for Auckland, Wellington, Christchurch, Rotorua, Hamilton, Dunedin, and 10 other NZ council areas. Optional --browser mode uses CloakBrowser for public pages that direct HTTP cannot fetch. Not for rates, consents, payments, or bookings. |
| [nz-electricity](skills/nz-electricity/SKILL.md) | `nz-public-data` | Electricity Authority and participating market operators | Query NZ electricity market data: EM6 wholesale spot prices, grid demand, carbon intensity, historical nodal prices, monthly generation by fuel type, distributed-generation solar uptake, gentailer energy-margin source status, and NZ lines-company outage records. No login or API key. |
| [nz-emergency-alerts](skills/nz-emergency-alerts/SKILL.md) | `nz-public-data` | National Emergency Management Agency | Query official New Zealand CAP emergency alerts by location, region, agency and severity. Use for current official alert retrieval; absence is not proof of safety. |
| [nz-family-support](skills/nz-family-support/SKILL.md) | `nz-public-data` | Inland Revenue | Map New Zealand family support entitlement questions to official IRD, MSD, and WINZ sources without calculating eligibility. Use when the task involves Working for Families, Best Start, FamilyBoost, childcare help, Accommodation Supplement, MSD/WINZ handoffs, or finding the right official checker or programme page. Read-only; no private data collection, applications, or entitlement decisions. |
| [nz-ferries](skills/nz-ferries/SKILL.md) | `nz-public-data` | Participating New Zealand ferry operators | Query NZ ferry schedules, fare snapshots, and service alerts: Cook Strait Interislander/Bluebridge, SeaLink Waiheke/Great Barrier, Fullers360/AT Metro Auckland ferries. Optional --browser mode probes Fullers public timetable pages with CloakBrowser while keeping AT GTFS fallback. Read-only; no booking or payment. Use at-transport for AT Metro real-time positions. |
| [nz-food-recalls](skills/nz-food-recalls/SKILL.md) | `nz-public-data` | Ministry for Primary Industries | Search official MPI food recalls by product, brand, allergen, hazard, batch and date. Use for source-backed current and historical food-recall checks. |
| [nz-gazette](skills/nz-gazette/SKILL.md) | `nz-public-data` | New Zealand Gazette | Search and retrieve authoritative New Zealand Gazette notices by keyword, identifier, date, category and legislation. Retrieval only; not legal advice. |
| [nz-grants](skills/nz-grants/SKILL.md) | `nz-public-data` | Department of Internal Affairs and participating funders | Query New Zealand grant opportunities and grant-distribution history from DIA/Granted.govt.nz Class 4 gambling grants and CommunityMatters fund pages. Use when the task involves current NZ community grant opportunities, CommunityMatters fund criteria/source pages, pokie/Class 4 grant recipient history, funders, half-year periods, recipients, or Territorial Local Authority grant totals. Read-only and no API key required; upstream bot protection may require graceful retry or skip. |
| [nz-hansard](skills/nz-hansard/SKILL.md) | `nz-public-data` | New Zealand Parliament | Search official New Zealand parliamentary debates, speeches and oral-question transcripts by speaker, date, topic, bill and sitting. |
| [nz-healthpoint](skills/nz-healthpoint/SKILL.md) | `nz-commercial-web` | Healthpoint | Query Healthpoint NZ health-service directory: NZ pharmacies, GPs, urgent care, hospitals, dentists, and specialists. Returns locations, contact details, opening hours, and services. No booking or login. |
| [nz-libraries](skills/nz-libraries/SKILL.md) | `nz-public-data` | Participating New Zealand public libraries | Query selected New Zealand public library catalogues, branch locations, hours, book details, and public availability through a lightweight read-only CLI. Use when the task involves finding books in major NZ public library networks or checking which branches currently show copies. |
| [nz-local-government-data](skills/nz-local-government-data/SKILL.md) | `nz-public-data` | Stats NZ, Department of Internal Affairs, and Office of the Auditor-General | Discover and preview official New Zealand local government finance, performance, and statistics datasets from Stats NZ/data.govt.nz, DIA local council downloads, DIA council performance metrics, and OAG local-government insight sources. Use when the task involves council profiles, rates revenue, local authority statistics, comparing councils, finding machine-readable local-government datasets, or identifying official source gaps. Read-only, no login or API key required. |
| [nz-ministers](skills/nz-ministers/SKILL.md) | `nz-public-data` | New Zealand Government | Query New Zealand government ministers, their portfolios, and their press releases from beehive.govt.nz. Use when the task involves NZ ministers, who holds a portfolio (health, finance, energy, etc.), a minister's bio, or all the releases/speeches by a given minister, plus the latest government announcements. The latest-releases feed is keyless; per-minister data uses an optional --browser (CloakBrowser) bootstrap to clear bot protection, then cached cookies for plain HTTP. Read-only; no login or account. |
| [nz-mps-electorates](skills/nz-mps-electorates/SKILL.md) | `nz-public-data` | New Zealand Parliament | Query official current New Zealand MP, electorate, party, portfolio, role, committee and public office contact records. |
| [nz-news](skills/nz-news/SKILL.md) | `nz-commercial-web` | Participating New Zealand news publishers | Aggregate RSS feeds from major New Zealand news websites. Use when the task involves NZ news, current events in New Zealand, what's happening in NZ, NZ headlines, or searching NZ stories by topic, timeframe, or source. No authentication required. |
| [nz-parliament](skills/nz-parliament/SKILL.md) | `nz-public-data` | New Zealand Parliament | Track New Zealand Parliament bills and their legislative progress from the public bills.parliament.nz API. Use when the task involves NZ bills, legislation before Parliament, a bill's status or stage (first reading, select committee, etc.), who introduced a bill, government vs member's bills, or searching bills by keyword. Keyless, read-only; no login. Covers bills only (not MP directory, votes, Hansard, or petitions). |
| [nz-police-data](skills/nz-police-data/SKILL.md) | `nz-public-data` | New Zealand Police | Query official anonymised New Zealand Police victimisation, proceedings and offence statistics with suppression and interpretation context. |
| [nz-pricewatch](skills/nz-pricewatch/SKILL.md) | `nz-commercial-web` | PriceSpy | Query PriceSpy NZ for NZ electronics and appliance price comparison: cheapest prices, merchant offers, price history, and trending products. No login, cart, or account required. |
| [nz-product-recalls](skills/nz-product-recalls/SKILL.md) | `nz-public-data` | Product Safety New Zealand | Search official Product Safety New Zealand non-food consumer-product recalls by product, supplier, category, hazard and date. |
| [nz-road-closures](skills/nz-road-closures/SKILL.md) | `nz-public-data` | NZ Transport Agency Waka Kotahi | Query NZTA / Waka Kotahi state-highway road closures, roadworks, incidents, traffic cameras, routes, and regions. Use for NZ state highway conditions. Read-only; no alerts, accounts, or reporting. |
| [nz-schools](skills/nz-schools/SKILL.md) | `nz-public-data` | Ministry of Education | Query official Ministry of Education school directory, roll, location and enrolment-zone resources. Use for source-backed school lookup, not rankings. |
| [nz-select-committees](skills/nz-select-committees/SKILL.md) | `nz-public-data` | New Zealand Parliament | Track official New Zealand select committees, open submissions, business, public evidence and reports. Read-only; does not submit on a user's behalf. |
| [nz-tides-surf](skills/nz-tides-surf/SKILL.md) | `nz-public-data` | Toitū Te Whenua LINZ and SwellMap | Query New Zealand LINZ tide predictions and SwellMap surf forecasts through a lightweight read-only CLI. Use when the task involves NZ tide times, next high/low tide, surf forecasts, swell trend, or choosing the best nearby surf break for a drive. |
| [nz-trains](skills/nz-trains/SKILL.md) | `nz-public-data` | Metlink | Query Wellington Metlink train lines through a lightweight read-only CLI using GTFS and GTFS-RT data. Use when the task involves Johnsonville, Kapiti, Hutt Valley, Melling, or Wairarapa Line stations, arrivals, delays, alerts, or live train positions. Requires METLINK_API_KEY. |
| [nz-tv-guide](skills/nz-tv-guide/SKILL.md) | `nz-commercial-web` | Sky New Zealand and participating broadcasters | Query NZ TV guide and EPG for Sky NZ, Sky Sport, ESPN, Trackside, and Freeview/TVNZ. Use for NZ sport showtimes, movie schedules, and what's on now or tonight. Read-only; no streaming or account actions. |
| [nzbn-register](skills/nzbn-register/SKILL.md) | `nz-public-data` | New Zealand Business Number | Search and lookup public NZBN Register NZ business records: NZBN identity, company/entity status, trading names, addresses, and source-register identifiers. No login or API key required. |
| [nzpost](skills/nzpost/SKILL.md) | `nz-public-data` | NZ Post | Query NZ Post public APIs for parcel tracking, PostShop/parcel-collect/postbox location search, and address/postcode lookup. No authentication required. Use when the task involves tracking an NZ Post parcel, finding a nearby PostShop or parcel-collect point, looking up a New Zealand delivery address or postcode, or fetching complete tracking history for a domestic or international tracking number. |
| [nzta-crash-data-nz](skills/nzta-crash-data-nz/SKILL.md) | `nz-public-data` | NZ Transport Agency Waka Kotahi | Query NZTA/Waka Kotahi Crash Analysis System public crash statistics from the no-key ArcGIS FeatureServer and data.govt.nz CKAN mirror. Use when the task involves New Zealand road deaths, serious injuries, crash severity by region or TLA, yearly road-toll counts, or public CAS crash indicator fields such as weather, light, road surface, vehicle type, roadside objects, and roadworks. |
| [nzx](skills/nzx/SKILL.md) | `nz-commercial-web` | NZX | Query NZX public delayed market data through a lightweight no-login CLI. Use when the task involves New Zealand Exchange listed share prices, S&P/NZX index levels, NZSX movers, historical daily OHLC-style performance, dividends, or ticker/company lookup. Read-only; no account, portfolio, order, or trading actions. |
| [oia-statistics-nz](skills/oia-statistics-nz/SKILL.md) | `nz-public-data` | Public Service Commission | Query New Zealand Public Service Commission six-monthly OIA compliance statistics with per-period and per-agency views, including timeliness, extensions, transfers, refusals, proactive publication, and Ombudsman complaints. |
| [ombudsman-nz](skills/ombudsman-nz/SKILL.md) | `nz-public-data` | Office of the Ombudsman | Query Ombudsman NZ OIA/LGOIMA complaint statistics, case notes, and inspection publications from ombudsman.parliament.nz. |
| [osm-nz](skills/osm-nz/SKILL.md) | `nz-public-data` | OpenStreetMap contributors | Query OpenStreetMap Overpass API for nearby points of interest, attractions, amenities, shops, and services around any NZ location. Use when the task involves finding what's nearby — restaurants, cafes, parks, shops, transport stops, museums, beaches — given coordinates or an address. No login or API key required. Read-only. |
| [paknsave-nz](skills/paknsave-nz/SKILL.md) | `nz-commercial-web` | Foodstuffs New Zealand | Query PAK'nSAVE NZ stores, product categories, product search results, specials, and store-specific grocery prices using the public website's guest-token APIs. Use when the task involves PAK'nSAVE NZ product lookup, Papakura or other store prices, specials, category browsing, or product ID decoration. No account login required. |
| [pbtech-nz](skills/pbtech-nz/SKILL.md) | `nz-commercial-web` | PB Tech | Query PB Tech NZ public product search, category/product pages, prices, stock summary, and store-location pages through a lightweight no-login CLI. Use when the task involves PB Tech product lookup, electronics/computer prices, part codes, availability, store pickup counts, store addresses, opening hours, or machine-readable PB Tech retail data. Read-only; no login, cart, checkout, wishlist, or account actions. |
| [petcentral-nz](skills/petcentral-nz/SKILL.md) | `nz-commercial-web` | Pet Central | Query Pet Central NZ public Shopify product, collection, price, and availability snapshots through a no-login read-only CLI. Use when a task needs current Pet Central catalogue lookup or structured product detail; never for cart, checkout, account, payment, prescription, or veterinary advice. |
| [petdirect-nz](skills/petdirect-nz/SKILL.md) | `nz-commercial-web` | Petdirect | Use when searching Petdirect NZ products, comparing current public variant prices, checking availability, or reading product details. Parses bounded public search-page state and product JSON-LD through a read-only Python CLI; no cart, checkout, account, payment, subscription, prescription, or other mutations. |
| [petrolmate-nz-au](skills/petrolmate-nz-au/SKILL.md) | `nz-commercial-web` | PetrolMate | Query live AU & NZ fuel prices from petrolmate.com.au's public API. Search stations near any AU or NZ location, filter by supported fuel type, sort by price or distance. Covers AU state FuelCheck data and NZ Gaspy data. No API key or authentication required. |
| [petstock-nz](skills/petstock-nz/SKILL.md) | `nz-commercial-web` | Petstock | Query Petstock NZ's public Algolia catalogue and product JSON-LD for bounded product search, current standard and Autoship prices, public offers, rewards signals, and online availability. Use when comparing Petstock NZ products or checking a known product handle, URL, or SKU. Read-only; no account, cart, checkout, payment, vet, booking, or other mutations. |
| [pharmac-schedule-nz](skills/pharmac-schedule-nz/SKILL.md) | `nz-public-data` | Pharmac | Query official Pharmac Schedule funding, subsidy, restriction and Special Authority resources. Use for source-backed medicine/device funding research; not clinical advice. |
| [pptx](skills/pptx/SKILL.md) | `artifact-tools` | Anthropic | Use this skill any time a .pptx file is involved in any way — creating, reading, editing, combining, splitting, or updating decks, slides, presentations, templates, layouts, speaker notes, or comments. |
| [property-rates-nz](skills/property-rates-nz/SKILL.md) | `nz-public-data` | Auckland Council | Query Auckland Council public property rates, capital value (CV), land value, improvement value, and annual rates through the council's no-login rate-assessment API. Use when the task involves Auckland property CV, council valuation, land value, improvement value, annual rates total, floor area, land area, or legal description. Read-only; requires an Auckland Council property ID (ACRateAccountKey). |
| [public-housing-nz](skills/public-housing-nz/SKILL.md) | `nz-public-data` | Ministry of Housing and Urban Development and Stats NZ | Query New Zealand public and social housing open data from the Ministry of Housing and Urban Development (HUD) on data.govt.nz — public housing stock (Kainga Ora and community housing providers), social housing IRRS and market-rent tenancies, accommodation supplement recipients and weekly spend, and the Local Housing Statistics dashboard (housing affordability, rent burden, bonds, building consents, MSD benefit numbers, and the year-on-year change in the public/social housing register). Use when the task involves NZ public housing, the social housing register or wait-list, Kainga Ora, housing deprivation, accommodation supplement, housing affordability, or HUD housing statistics. No API key, login, or browser session required. |
| [public-trust-grants](skills/public-trust-grants/SKILL.md) | `nz-public-data` | Public Trust | Query Public Trust New Zealand public grants and scholarships through the unauthenticated grants search index and public detail pages. Use when the task involves finding Public Trust-managed NZ grant or scholarship opportunities by keyword, organisation/individual type, region, sector, or application-open status, or checking public grant criteria text. Read-only; no login, application submission, SmartyGrants form access, or paywalled/commercial grant database scraping. |
| [raw-essentials-nz](skills/raw-essentials-nz/SKILL.md) | `nz-commercial-web` | Raw Essentials | Query Raw Essentials NZ public catalogue, product-page, and store-page HTML through a no-login read-only CLI. Use when a task needs current Raw Essentials product discovery or source-page detail; never for cart, checkout, account, payment, booking, or veterinary advice. |
| [rbnz-data](skills/rbnz-data/SKILL.md) | `nz-public-data` | Reserve Bank of New Zealand | Discover and fetch Reserve Bank of New Zealand public statistics datasets through data.govt.nz CKAN and browser-compatible rbnz.govt.nz public file/chart endpoints. Use when the task involves RBNZ exchange rates, wholesale interest rates, OCR/key graphs, retail mortgage/deposit rate charts, dataset metadata, resource URLs, downloadable XLSX series, or JSON chart-cache previews. Read-only; no authentication required. |
| [rental-bond-nz](skills/rental-bond-nz/SKILL.md) | `nz-public-data` | Ministry of Business, Innovation and Employment | Query MBIE/Tenancy Services NZ rental bond and market-rent statistics, including quarterly/monthly bonded-tenancy counts, median and quartile rent values, and market-rent snapshots by suburb, property type, and bedroom size. Use for rent affordability analysis, tenure trending, and housing policy workflows. Data is keyless and sourced from tenancy.govt.nz first-party endpoints with data.govt.nz CKAN metadata fallback where relevant. |
| [safeswim-nz](skills/safeswim-nz/SKILL.md) | `nz-public-data` | Safeswim | Query SafeSwim NZ public swimming-location water quality, swimming conditions, wastewater overflow alerts, and hour-by-hour forecast data through a no-login REST API. Use when the task involves SafeSwim-supported NZ beach/lake swimming safety, water quality (GREEN/AMBER/RED/RED+/BLACK), lifeguard/patrol status, safety hazards, facilities, or per-location forecasts. Read-only. |
| [seek-co-nz](skills/seek-co-nz/SKILL.md) | `nz-commercial-web` | SEEK | Search and inspect public SEEK.co.nz job listings through a lightweight no-login CLI. Use when the task involves New Zealand job search, SEEK listing IDs, role/company/location snapshots, salary snippets, classifications, or machine-readable public job data. Read-only; no login, saved searches, applications, account, recruiter, or job-posting actions. |
| [stats-nz](skills/stats-nz/SKILL.md) | `nz-public-data` | Stats NZ | Query official Stats NZ data: CPI, GDP, population estimates/projections, migration, and CSV catalogue. No API key or browser session required. |
| [statsnz-building-consents](skills/statsnz-building-consents/SKILL.md) | `nz-public-data` | Stats NZ | Query official Stats NZ building-consent counts, values and floor area by region, building type and period with revision context. |
| [statsnz-classifications-nz](skills/statsnz-classifications-nz/SKILL.md) | `nz-public-data` | Stats NZ | Query Stats NZ DataInfo+ / Aria classifications, concepts, concordances, and quality standards with lookup IDs, code lists, version history, and category metadata. |
| [the-warehouse-nz](skills/the-warehouse-nz/SKILL.md) | `nz-commercial-web` | The Warehouse Group | Query The Warehouse NZ product search, specials, product detail, and store finder. Use for The Warehouse NZ product lookup, prices, specials, SKUs, store locations, or opening hours. Optional --browser mode uses CloakBrowser for public read-only page/API fetches when installed. No cart or account. |
| [thecolab-brand](skills/thecolab-brand/SKILL.md) | `thecolab-internal` | TheColabAI | Use when creating TheColab.ai branded outputs: decks, proposals, one-pagers, event collateral, social images, reports, or WhatsApp bot responses that need The Colab's voice, positioning, colours, and visual style. |
| [trademe-nz](skills/trademe-nz/SKILL.md) | `nz-commercial-web` | Trade Me | Query Trade Me NZ public listings: marketplace, property sale/rental, motors, jobs, flatmates, rural, retirement, regions, categories, and listing details. No login or credentials required. |
| [treasury-fiscal-data-nz](skills/treasury-fiscal-data-nz/SKILL.md) | `nz-public-data` | New Zealand Treasury | Query official New Zealand Treasury fiscal forecast, appropriation, Crown revenue, expenditure and debt resources with publication provenance. |
| [wellington-bin-schedule](skills/wellington-bin-schedule/SKILL.md) | `nz-public-data` | Wellington City Council | Query Wellington City Council rubbish and recycling collection days using a WCC street ID. Use when the task involves Wellington bin day, rubbish/recycling schedules, or kerbside collection for a Wellington address. Requires a WCC street ID (found by searching your address on the WCC collection-day page). No account login required. |
| [winz-rates-nz](skills/winz-rates-nz/SKILL.md) | `nz-public-data` | Work and Income | Query current and historical public Work and Income New Zealand benefit/payment rate tables and A-Z benefit entitlement pages. Use when the task involves WINZ benefit rates, NZ Super rates, Jobseeker/Sole Parent/Supported Living payment amounts, Accommodation Supplement thresholds, or official Work and Income eligibility/criteria page summaries. |
| [woolworths-nz](skills/woolworths-nz/SKILL.md) | `nz-commercial-web` | Woolworths New Zealand | Query Woolworths NZ product search, specials, category browse, and SKU detail. Use for Woolworths NZ grocery prices, specials, and product lookup. Read-only; no trolley or checkout actions. |
<!-- END GENERATED SKILLS TABLE -->

Machine-readable filters, health, authentication, access mode, maintenance ownership, and outbound domains are in [`skills.json`](skills.json).

## Skill sets

- [./skills](./skills) - Real skills contributed to this repo
- [./spec](./spec/agent-skills-spec.md) - Agent Skills spec and repo-specific stance
- [./templates](./templates) - Source/workflow scaffold variants
- [./packs](./packs) - Generated trust-based installation manifests
- [./skills.json](./skills.json) - Generated machine-readable catalogue

## Skill Development Guidelines

All skills in this repository use **Python** as the canonical entrypoint.

- **Entrypoint:** Every skill must have `scripts/cli.py` with `#!/usr/bin/env python3` as its first line.
- **Python stdlib preferred.** Use `urllib.request`, `json`, `re`, `xml.etree.ElementTree`, `html.parser`, `argparse`, and the standard library where possible. If a third-party dependency is truly necessary, declare it in a `requirements.txt` in the skill directory or via inline `# /// script` PEP 723 metadata.
- **TypeScript/Node helpers are not accepted.** `jetstar-flights` has a declared legacy exception behind a canonical Python wrapper; do not copy it.
- **Every skill has:** `SKILL.md`, `scripts/cli.py`, `scripts/test_contract.py`, `scripts/smoke_test.py`, and deterministic fixtures.
- **Every data command exposes `--json`.** Use `scripts/run_skill.py` when the versioned common result envelope is required.
- **Stable failures:** use the exit codes in [docs/contracts.md](docs/contracts.md) and return blocked/schema states explicitly.

## Contributing

We’ve made this repo opinionated on purpose.

Don’t freestyle the structure. Generate a scaffold, fill it in properly, then validate it before you open a PR.

### Quick start

```bash
git clone https://github.com/thecolab-ai/.skills
cd .skills

python3 scripts/new_skill.py my-nz-skill \
  --variant public-api \
  --description "Query the official example API. Use for example records and status checks." \
  --source-owner "Example Agency" \
  --source-url "https://example.govt.nz/api"
python3 scripts/validate_skill.py skills/my-nz-skill
python3 skills/my-nz-skill/scripts/test_contract.py
python3 scripts/run_smoke_tests.py my-nz-skill
python3 scripts/generate_catalogue.py
```

### Available scaffold variants

- `public-api`
- `public-download`
- `html-readonly`
- `authenticated-personal`
- `documentation-workflow`

### Canonical skill folder structure

```text
skills/
  my-nz-skill/
    SKILL.md
    references/source-notes.md
    scripts/
      cli.py
      test_contract.py
      smoke_test.py
    tests/fixtures/
```

See [docs/contracts.md](docs/contracts.md), [docs/packs.md](docs/packs.md), and [docs/migration.md](docs/migration.md).

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
