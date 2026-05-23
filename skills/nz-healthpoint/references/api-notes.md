# Healthpoint NZ API notes

This skill is an unofficial lightweight read-only wrapper around public Healthpoint NZ directory pages used by `healthpoint.co.nz`.

## Source and auth

- Website: `https://www.healthpoint.co.nz`
- Auth model for this skill: none for implemented read-only operations
- Backend shape observed during discovery: server-rendered Cactuslab/Healthpoint pages with webpack/static JS helpers, not a Next.js app
- `__NEXT_DATA__` was checked and was not present on the homepage, branch pages, search pages, or detail pages fetched during discovery

No username, password, provider login, account cookie, private token, browser profile, or session storage is required.

## Endpoint and page families used

### Branch/category result pages

Healthpoint branch pages return server-rendered result HTML. Implemented examples:

```text
GET /pharmacy/
GET /pharmacy/?region=central-auckland
GET /gps-accident-urgent-medical-care/?region=wellington&serviceType=accident-urgent-medical-care-ae
GET /dentistry/?region=wellington
GET /public/?region=central-auckland
```

Useful query parameters:

- `region={slug}` - region filter from Healthpoint's region select
- `serviceType={slug}` - provider-type filter, used for GP and urgent-care provider types
- `serviceArea={slug}` - service/treatment filter where a branch exposes one
- `openNow=true` - Healthpoint's current-open filter
- `options=openLate` - Healthpoint's late-opening filter; on the site this means open after 5:30pm, so the CLI further checks detail hours for `--open-late`
- `options=openSundays`, `options=openWeekends`, `options=openBooks` - observed on some branch filter forms; Saturday lookup uses Healthpoint's weekend filter where a branch exposes it
- `services={offset}` - pagination offset for service results; observed page size is 40
- `locations={offset}` - pagination offset for public-hospital location results

Useful HTML sections:

- `section#paginator-services` - service/practice result cards
- `section#paginator-locations` - public hospital/facility location list
- `section#paginator-people` - people results; intentionally not the primary source for service lookup
- `<small class="count">` - result count
- `.openingstatus` - current-day opening summary such as `Open today 9:30 AM to 12:00 AM.`
- `href="tel:..."` - public phone link on many service cards

### Text search

```text
GET /search?q={query}
```

Search pages render `<ul class="search-results">` with `<li class="search-result ...">` cards. These cards can include services, people, and specialist pages. The CLI uses this for untyped name/keyword lookup, and uses branch pages for typed/region/open-now workflows because branch pages expose better filters.

Autocomplete used by the website:

```text
GET /autocomplete.do?{serialized search form}
```

This endpoint was sniffed from the static JS (`/static/js/chunk/9023...js`) but is not needed by the CLI because `/search?q=` is sufficient for deterministic lookup.

### Nearby/address lookup

Address autocomplete used by the website:

```text
GET /nearme.do?q={address text}
```

Response shape is a public JSON array. Useful keys:

- `value`
- `lat`
- `lon`
- `street`, `suburb`, `city`, `region`, `postcode`, `country`

Nearby result pages:

```text
GET /near/{lat},{lon}/?addr={address}
GET /pharmacy/near/{lat},{lon}/?addr={address}&openNow=true
GET /gps-accident-urgent-medical-care/near/{lat},{lon}/?serviceType=accident-urgent-medical-care-ae
```

The generic `/near/...` page lists branch counts. Branch-scoped `/pharmacy/near/...` style pages render normal `paginator-services` cards, apparently ordered by proximity. The CLI scores `/nearme.do` suggestions by query-token, city, and region matches instead of blindly taking the first row. It does not claim exact distances because the result cards do not expose a stable distance field.

### Map markers

The map bundle calls:

```text
GET /geo.do?zoom={z}&minLat={lat}&maxLat={lat}&minLng={lng}&maxLng={lng}&...filters
```

Response includes marker/cluster JSON under `results`. It is useful for map overlays but the CLI does not rely on it for service details because listing/detail pages expose richer public data.

### Detail pages

Detail pages are fetched by id/path/url from search results, for example:

```text
GET /pharmacy/pharmacy/medicines-to-midnight/
GET /gps-accident-urgent-medical-care/accident-urgent-medical-care-ae/wellington-accident-and-urgent-medical-centre/
GET /auckland-city-hospital/
```

Useful detail fields:

- `<h1>` - service/facility name
- `<p class="opening-hours">` - current-day opening summary
- `<table class="hours">` - listed opening rows
- `meta itemprop="latitude"` / `longitude` - coordinates
- `itemprop="address"` after `Street Address` - public street address
- `h4.label-text` contact rows such as Phone, Website, Healthlink EDI
- `section-serviceArea` collapsible service titles for pharmacies/primary care
- `section-services` / `span.practice-name` service links for hospitals
- Emergency Department indicator: detail page services/contacts containing `Emergency Department`

## Type and region mapping

Common CLI type aliases map to Healthpoint branches and provider-type filters:

- `pharmacy`, `chemist` -> `/pharmacy/`
- `gp`, `general-practice` -> `/gps-accident-urgent-medical-care/?serviceType=gp`
- `urgent-care`, `accident-medical`, `a-and-m` -> `/gps-accident-urgent-medical-care/?serviceType=accident-urgent-medical-care-ae`
- `hospital`, `ed` -> `/public/`
- `dentist`, `dental` -> `/dentistry/`
- `optometrist` -> `/eye-care/`
- `physio` -> `/allied-health/`

Healthpoint splits Auckland into five region slugs:

- `north-auckland`
- `east-auckland`
- `central-auckland`
- `west-auckland`
- `south-auckland`

The CLI treats `--region Auckland` as all five subregions and deduplicates result ids.

## Hours parsing notes

The CLI treats Healthpoint opening data as provider-supplied directory data, not a guarantee.

Implemented parsing:

- `--open-now` sends `openNow=true` where a branch page is used, then parses each returned `.openingstatus` against current `Pacific/Auckland` time
- `Open today 12:00 AM to 12:00 AM` is treated as 24-hour
- end times earlier than start times are treated as crossing midnight
- `pharmacies --open-late` sends `options=openLate`, fetches detail pages for returned pharmacies, and keeps pharmacies whose listed hours close at/after 9pm on at least one listed day

Known limitations:

- Some cards omit opening-status text even when detail pages have hours
- Some Healthpoint text uses `midnight` in the detail table and `12:00 AM` in the current-day status
- Public holiday hours may be present as free text and are not fully normalized
- Healthpoint's own `openLate` checkbox is documented in the page label as after 5:30pm, so CLI `--open-late` adds a stricter after-9pm detail-hours check
- ED wait times, live queues, appointment availability, and capacity are not reliably available from these pages

## Safety and stability

- Read-only only: no booking, payment, referral, enrolment, login, patient-account, prescription, or provider-admin actions
- This skill is for finding services, not medical advice or triage
- For emergencies call 111. For Healthline call 0800 611 116.
- Directory details are supplied by providers and can be incomplete, stale, or inconsistent between result cards and detail pages
- Endpoint names, filters, and HTML structures are not a formal public API contract and can change without notice
- Use narrow queries and small limits for routine workflows
- Do not commit HAR files, raw browser captures, downloaded JS bundles, HTML snapshots, cookies, browser profiles, screenshots with private data, or large scraped datasets
