# Property Rates NZ API notes

This skill is an unofficial lightweight wrapper around a public read-only Auckland Council rate-assessment endpoint.

## Source and auth

- Council rates page: `https://www.aucklandcouncil.govt.nz/en/property-rates-valuations/find-property-rates-valuation.html`
- Public API: `https://experience.aucklandcouncil.govt.nz/nextapi/property/{propertyId}/rate-assessment`
- Property page: `https://www.aucklandcouncil.govt.nz/en/property-rates-valuations/find-property-rates-valuation/{propertyId}.html`
- Auth model: public browser bearer token extracted from the council page; no user credentials, API key, cookie, or login required
- The endpoint requires standard browser-like `User-Agent`, `Accept`, `Authorization`, `Origin`, and `Referer` headers

## Endpoint

`GET /nextapi/property/{propertyId}/rate-assessment`

Returns JSON with Auckland Council valuation and rates data for a single property.

### Response shape

```json
{
  "capitalValue": "1250000.00",
  "landValue": "750000.00",
  "valueOfImprovements": "500000.00",
  "totalRates": "3450.00",
  "valuationNumber": "2024001234",
  "rateAccountKey": "12343300679",
  "area": "450",
  "areaUnits": "m²",
  "totalFloorArea": "180",
  "buildingSiteCoverage": "120",
  "landUseDescription": "Single Unit excluding bach",
  "localBoard": "Waitematā",
  "propertyCategory": "Residential",
  "legalDescription": "Lot 123 DP 45678"
}
```

All monetary values are strings with two decimal places. The CLI converts them to integers (rounded).

## Property ID

The property ID used by this API is the **ACRateAccountKey** — a numeric string assigned by Auckland Council. This is the same ID:

- Used on the Auckland Council rates search page
- Returned by the `auckland-bin-schedule` skill's address lookup
- Embedded in the council rates page URL: `.../find-property-rates-valuation/{propertyId}.html`

## Discovery notes

- The `experience.aucklandcouncil.govt.nz` domain hosts Auckland Council's "Experience" platform — the rate-assessment endpoint is part of the same API family used by the bin-collection and property-search widgets
- The endpoint name `rate-assessment` returns the current council valuation snapshot, not historical records
- Some properties may return partial data — rural properties may lack floor area; commercial properties may have different field sets
- The `valuationNumber` may change across revaluation cycles
- Valuation date is not directly exposed by this endpoint; Auckland Council revalues every three years (most recent: 2024)

## Stability and safety

- Treat council valuations as official snapshots, not market value — CVs can differ significantly from market prices
- Annual rates is the total assessment; actual payment may differ due to rebates, targeted rates, or arrears
- Endpoint shapes can change without notice as this is not a formally documented public API
- Do not use for financial, lending, or legal decisions without verified council documentation
- Avoid high-frequency polling; the data changes rarely (annual rates updates, triennial valuations)
- This endpoint covers Auckland Council only — Wellington, Christchurch, and other councils have separate systems
