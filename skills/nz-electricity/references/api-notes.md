# NZ Electricity API Notes

This skill is a read-only wrapper around public New Zealand electricity data sources. It does not use authenticated API products, cookies, browser sessions, or paid feeds.

## Sources shipped

### EM6 public JSON feeds

- Provider: Energy Market Services / EM6
- Website: `https://www.ems.co.nz/services/em6/em6-data-feeds/`
- Integration guide: `https://www.ems.co.nz/documents/374/Em6_API_Integration_Guide_1.12.pdf`
- API base used by the CLI: `https://api.em6.co.nz/ords/em6/data_api`
- Auth model for implemented commands: none

Implemented endpoints:

- `GET /region/price/`
  - Command: `spot`
  - Official EM6 description: current regional price API returning average dispatch prices at five-minute intervals for each region
  - Data freshness: current snapshot; observed timestamps update on a five-minute cadence
  - Units: dollars per megawatt-hour

- `GET /current_carbon_intensity/`
  - Command: `carbon`
  - Official EM6 description: recent NZ carbon intensity and renewable percentage for recent trading periods
  - Data freshness: recent trading periods
  - Units: grams CO2 per kWh, tonnes CO2, renewable percentage

### Electricity Authority EMI public CSV datasets

- Provider: Electricity Authority / EMI
- Dataset portal: `https://www.emi.ea.govt.nz`
- Auth model for implemented commands: none

Implemented datasets:

- `https://www.emi.ea.govt.nz/Wholesale/Reports/W_GD_C`
  - Command: `demand`
  - Official report: Demand trends
  - Download endpoint: `https://www.emi.ea.govt.nz/Wholesale/Download/DataReport/CSV/W_GD_C`
  - Parameters used: `DateFrom`, `DateTo`, `RegionType=NZ|ZONE`, `TimeScale=TP`, `Show=Gwh`
  - Data freshness: current-day report rows are available but can be partial; reconciled data lags by month and recent periods can use final-pricing proxy conventions described by EMI
  - Units: GWh per trading period; CLI also derives average MW for each half-hour period as `GWh * 2000`

- `https://www.emi.ea.govt.nz/Wholesale/Datasets/DispatchAndPricing/FinalEnergyPrices`
  - Command: `prices`
  - Official dataset: Final and interim energy prices
  - Daily files: `{YYYYMMDD}_FinalEnergyPrices.csv` and `{YYYYMMDD}_FinalEnergyPrices_I.csv`
  - Monthly files: `ByMonth/{YYYYMM}_FinalEnergyPrices.csv`
  - Data freshness: daily files for recent dates; older data accumulated into monthly files
  - Units: dollars per megawatt-hour
  - Notes: recent files may be interim until final prices are published

- `https://www.emi.ea.govt.nz/Wholesale/Datasets/Generation/Generation_MD`
  - Command: `generation`
  - Official dataset: Generation output by plant
  - Monthly files: `{YYYYMM}_Generation_MD.csv`
  - Data freshness: monthly, historical; latest observed file on 23 May 2026 was `202604_Generation_MD.csv`
  - Units: source columns are kWh by trading period; CLI aggregates to GWh

## Official vs derived values

- Official values:
  - EM6 regional spot `price`
  - EM6 carbon intensity and renewable fields
  - EMI report `Demand (GWh)` and `Demand ($)`
  - EMI point-of-connection `DollarsPerMegawattHour`
  - EMI generation plant trading-period kWh values

- Derived by this CLI:
  - `demand` total GWh, average GWh per period, peak period, and average MW conversion
  - `prices` min, max, and average
  - `generation` fuel totals, technology totals, plant totals, GWh conversion, and share percentages

## Sources checked but not shipped

- EM6 `price/24hrs/{node_id}`, `current_load/{node_id}`, `recent_load/{node_id}`, `current_generation/{node_id}`, `recent_generation/{node_id}`, `generation_type/24hrs/`, `nz/24hrs/`, and regional peak/load endpoints were documented in the EM6 guide but returned unauthorized or forbidden in live no-login testing from the public API base.
- EMI Azure API products for real-time prices and dispatch require subscription-key access, so they are out of scope for this no-login skill.
- Powerswitch plan comparison was skipped because it requires user-specific inputs and is not suitable for a stateless read-only market-data CLI.
- Lines-company outage feeds were not implemented because no single clean national public API surface was identified during this build.
