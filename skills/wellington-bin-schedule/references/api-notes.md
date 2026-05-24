# Wellington Bin Schedule API notes

This skill is an unofficial wrapper around the public Wellington City Council collection-day component used by the website.

## Source and auth

- Collection-day search page: `https://wellington.govt.nz/rubbish-recycling-and-waste/when-to-put-out-your-rubbish-and-recycling`
- Collection results component: `https://wellington.govt.nz/rubbish-recycling-and-waste/when-to-put-out-your-rubbish-and-recycling/components/collection-search-results`
- Street autocomplete endpoint: `https://wellington.govt.nz/layouts/wcc/GeneralLayout.aspx/GetRubbishCollectionStreets`
- Auth model: **no credentials required** for the collection results endpoint

## Endpoint details

### Collection results (`components/collection-search-results`)

- **Method:** POST
- **Content-Type:** `application/x-www-form-urlencoded`
- **Body:** `streetId=<id>&streetName=<name>`
- **Response:** HTML fragment with collection schedule
- **Required headers:**
  - `Origin: https://wellington.govt.nz`
  - `Referer: https://wellington.govt.nz/rubbish-recycling-and-waste/when-to-put-out-your-rubbish-and-recycling`

The response HTML contains:
- Street name in an `<h3>` heading
- Collection date in `<p class="collection-date h2 mt-2">` — format: "Friday, 29 May"
- Put-out time in `<span class="nowrap">` — preceded by "out before"
- Collected items as `<li>` elements with CSS classes `recycling-icon-rubbish` and `recycling-icon-glass`

### Street autocomplete (`GetRubbishCollectionStreets`)

This ASP.NET ASMX endpoint requires server-side authentication (returns HTTP 401 for all programmatic requests) and **cannot be used**. Users must obtain their street ID from the WCC website directly.

## Wellington collection model

Unlike Auckland, Wellington collects **rubbish and recycling on the same day**:
- Rubbish (red-lid wheelie bin or official bags)
- Recycling (glass crate only — no mixed recycling bin)

There is **no kerbside food scraps / organics collection** in Wellington.

## Stability and safety

- Treat dates as live current snapshots from WCC, not historical or guaranteed data
- Public holidays can shift collection dates
- The component endpoint is a Sitecore rendering — its path and response shape could change
- Avoid high-volume scraping; rate-limit requests
- Do not use this skill for account changes or service requests
