# EECA Public EV Charger Sources

## Official Sources

- EECA Public EV Charger Dashboard:
  `https://www.eeca.govt.nz/insights/data-tools/public-ev-charger-dashboard/`
- data.govt.nz package:
  `https://catalogue.data.govt.nz/dataset/public-ev-chargers`
- CKAN package API:
  `https://catalogue.data.govt.nz/api/3/action/package_show?id=public-ev-chargers`

## CSV Resources

The CLI fetches these no-key CSV exports directly from EECA:

- Public EV chargers:
  `https://www.eeca.govt.nz/assets/EECA-Resources/Public-EV-Charger-Dashboard/Public-EV-chargers.csv`
- Co-funded EV chargers:
  `https://www.eeca.govt.nz/assets/EECA-Resources/Public-EV-Charger-Dashboard/Co-funded-EV-chargers.csv`
- EV metrics by region:
  `https://www.eeca.govt.nz/assets/EECA-Resources/Public-EV-Charger-Dashboard/EV-metrics-by-region.csv`
- EV metrics by district:
  `https://www.eeca.govt.nz/assets/EECA-Resources/Public-EV-Charger-Dashboard/EV-metrics-by-district.csv`

## Field Notes

`Public-EV-chargers.csv` contains one row per charger unit:

- `UnitId`, `SiteId`, `Owner`, `Operator`
- `Points`, `Current`, `KwRated`, `Connectors`
- `DateFirstOperational`
- `Address`, `Locality`, `Region`, `District`, `Latitude`, `Longitude`

`Co-funded-EV-chargers.csv` contains application/project rows:

- `ApplicationId`, `Applicant`, `Status`, `GoLiveDate`
- `Points`, `KwRated`
- `Address`, `Locality`, `Region`, `District`, `Latitude`, `Longitude`

The metrics CSVs contain already-aggregated dashboard measures:

- `Charge Points`, `Units`, `Sites`
- `Battery Electric Vehicles`, `Total Vehicles`, `Population Estimate`
- `Total KW Charging`
- `BEVs per Charge Point`, `KW Charging per BEV`
- `BEV Penetration`, `BEVs per Capita`
- District metrics also include `Region`

## Caveats

- The EECA dashboard is public dashboard data, not a live charger-status API.
  Do not infer current availability, faults, pricing, or access restrictions.
- EVRoam is the upstream charger-data ecosystem, but the public keyless path used
  by this skill is the EECA/data.govt.nz CSV export set. If an EVRoam download
  endpoint later becomes publicly accessible without credentials, add it as an
  optional command and label its source separately.
- `summary` uses current CSV rows and may not exactly match EECA metric totals
  where dashboard metric rows use a different refresh point or aggregation rule.
- Charger kW aggregation is an approximation: the CLI multiplies each unit's
  rated kW by its charge-point count so users can compare areas consistently.
- District and region filters are text matches from the CSV fields. They are not
  geospatial containment checks.
