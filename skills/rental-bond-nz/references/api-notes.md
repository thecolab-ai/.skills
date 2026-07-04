# rental-bond-nz API notes

Source of truth for this skill is Tenancy Services (formerly MBIE) public
rental-bond and market-rent pages on `tenancy.govt.nz`.

- Rental bond data page:
  - https://www.tenancy.govt.nz/about-tenancy-services/data-and-statistics/rental-bond-data/
  - The page links to first-party assets (CSV/ZIP), including:
    - `detailed-monthly-tla-tenancy-v2.csv`
    - `detailed-monthly-region-tenancy-v2.csv`
    - `detailed-quarterly-tenancy-2020-to-2026.csv`
- Market rent data tool:
  - `https://www.tenancy.govt.nz/rent-bond-and-bills/market-rent/`
  - Market-rent AJAX data endpoint:
    - `.../market-rent/updateMarketValueLocation/?ajax_city=<city>&ajax_suburb=<suburb>`
    - returns JSON containing `Finder` and `Table` HTML fragments
  - Market-rent autocomplete endpoint used for area discovery:
    - `.../market-rent/suggestLocations?query=<text>`
- CKAN discovery fallback:
  - `https://catalogue.data.govt.nz/api/3/action/package_search?q=...`
  - used to discover packages and resource metadata, not as the primary metric source

## Field mapping and semantics

- Bond rows use source columns:
  - `Time Frame` (YYYY-MM-01 in source CSVs)
  - `Location` (TA/region text)
  - `Lodged Bonds`, `Active Bonds`, `Closed Bonds`
  - `Median Rent`, `Geometric Mean Rent`, `Lower Quartile Rent`, `Upper Quartile Rent`
- Market-rent rows are parsed from returned HTML table sections:
  - property type sections (`Apartment`, `Flat`, `House`, `Room`)
  - row sizes such as `1 bedroom`, `2 bedroom`, `3+ bedroom`
  - `Active bonds`, `Lower Quartile`, `Median Rent`, `Upper Quartile`

## Freshness / quality notes

- Tenancy bond monthly CSVs are maintained by Tenancy Services and labelled by the
  source page as current as of the page update date.
- Market-rent endpoint content covers a rolling six-month period and is updated
  monthly.
- Source methods include rounding and suppression constraints for small-count cells.
- Network/caching behaviour can vary in blocked environments; command code treats
  HTTP errors, empty responses, and JSON parse failures as `upstream_unavailable`.
