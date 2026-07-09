# NZ Electricity API Notes

This skill is a read-only wrapper around public New Zealand electricity data sources. It does not use authenticated API products, private credentials, cookies, browser sessions, or paid feeds.

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

- `https://www.emi.ea.govt.nz/Retail/Reports/guehmt`
  - Commands: `dg-trends`, `dg-latest`, `dg-summary`
  - Official report: Installed distributed generation trends
  - Download endpoint: `https://www.emi.ea.govt.nz/Retail/Download/DataReport/CSV/GUEHMT`
  - Parameters used: `DateFrom`, `DateTo`, `RegionType`, `MarketSegment`, `Capacity`, `FuelType`, `Show=Capacity`
  - Default filters: `FuelType=solar_all`, `MarketSegment=All`, `Capacity=All_Total`, `RegionType=NZ`
  - Data freshness: monthly retail report data; the CSV includes a `Run at` metadata timestamp
  - Units: ICP count, uptake percentage, total installed capacity in MW, average installed capacity in kW, new installation count, and average new-installation capacity in kW
  - Parser note: the CSV starts with report metadata and parameters; the CLI skips rows until the `Month end` header, then parses with `csv.DictReader`
  - Caveats: market segments are not mutually exclusive; Solar+Batteries and Wind+Batteries registry categories were added in November 2023, so Solar and Other series can show category-change spikes around that period
  - Source note: values are derived from registry Fuel Type and Generation Capacity fields populated by distributors

### Electricity Authority gentailer energy margin source status

- Provider: Electricity Authority / Tableau Public
- Authority dashboard: `https://www.ea.govt.nz/data-and-insights/charts-and-dashboards/energy-margin/`
- Authority article: `https://www.ea.govt.nz/news/eye-on-electricity/gentailer-energy-margins-in-2024/`
- Linked Tableau workbook: `https://public.tableau.com/app/profile/electricity.authority/viz/Energymargin/Energymargin`
- Command: `energy-margin`
- Auth model: none
- Current behaviour: probes the official Authority pages and linked Tableau surfaces, then reports whether machine-readable per-company margin rows are available.
- Live status observed on 8 July 2026: the Tableau profile API for `Energymargin` returned `404`, the VizQL session endpoint for `/vizql/w/Energymargin/v/Energymargin/startSession/viewing` returned `404`, and the direct `/views/Energymargin/Energymargin` render path displayed Tableau's removed-or-renamed message. The command therefore returns `status: source_unavailable` and an empty `energy_margins` array rather than fabricating rows.
- Scope rule: do not reconstruct gentailer margins from spot prices, generation output, retail purchases, hedge positions, or company reports in this command unless the output is explicitly separated as a derived estimate. Issue #172 requested official pre-computed figures only.
- Future wiring: when the Authority publishes a public CSV/API feed or restores a machine-readable Tableau workbook, update `energy-margin` to parse that feed and preserve the current `source_checks` diagnostics for failure modes.

### NZ lines-company public outage feeds

- Command: `outages`
- Auth model for implemented feeds: no login, cookies, browser session, or private credentials
- Default behavior: fetch current/active outage records from every supported company
- `--all`: include planned, scheduled, or recent records where the company feed exposes them
- `--region`: case-insensitive text filter over company, location, cause, outage id, and raw record text

Implemented feeds:

- Vector
  - Current endpoint: `GET https://outagereporter.api.vector.co.nz/outagereporter/outages/shapes`
  - Planned endpoint used with `--all`: `GET https://outage-centre.api.vector.co.nz/v1/outages/planned-outages/shapes`
  - Required header: public browser `apikey` value read from `https://help.vector.co.nz/address/config.js`
  - Response shape: GeoJSON `FeatureCollection`; features include geometry and `properties.outageType`
  - CLI mapping: location is an approximate geometry centroid; cause/status use `outageType`
  - Quirks: public shape feed does not expose suburb, customer count, start time, restoration time, or a stable outage id. The more detailed `/outagereporter/outages` endpoint returned `403`, and subscription endpoints returned `401`.
  - Refresh rate: not documented in the public config; the map fetches the feed on load.

- Wellington Electricity
  - Endpoint: `GET https://www.welectricity.co.nz/outages/getalloutages`
  - Response shape: object with `plannedOutages` and `unplannedOutages` arrays
  - Useful fields: `suburbsText`, `lastUpdatedCustomersAffected`, `lastUpdatedComments`, `lastUpdatedEta`, `timeOfFault`, `timeBasedStatus`, `customersAffected`, `reasonForOutage`, `outageStartDateTime`, `outageEndDateTime`
  - CLI mapping: default includes unplanned rows with `timeBasedStatus=current` plus planned rows whose start/end window is active; `--all` includes all non-cancelled planned rows and current/recent unplanned rows
  - Quirks: the page states there may be a short delay and that outages affecting fewer than 10 properties may not appear.
  - Refresh rate: not documented; the endpoint is called directly by the outage page.

- Orion
  - Endpoint: `GET https://www.oriongroup.co.nz/outages-and-support/outages/refresh-outages`
  - Response shape: object with `CurrentOutages`, `PlannedOutages`, `RecentOutages`, and `TimeStamp`
  - Useful fields: `Areas`, `Streets`, `TotalNumberOff`, `MaxNumberOff`, `OutageCause`, `PublicComments`, `TimeDown`, `EstTimeUp`, `PlannedStart`, `PlannedEnd`, `IncidentRef`, `Latitude`, `Longitude`
  - CLI mapping: default includes `CurrentOutages`; `--all` also includes non-cancelled `PlannedOutages`
  - Quirks: the older APIM URL referenced by page JavaScript (`https://apim.oriongroup.co.nz/ws/rest/api/v1/outages`) returned `401`; the same page exposes the clean refresh endpoint above.
  - Refresh rate: not documented; response includes its own `TimeStamp`.

- Powerco
  - Endpoint: `GET https://outages.powerco.co.nz/server/rest/services/Hosted/Outages/FeatureServer/1/query`
  - Query parameters: `f=json`, `where=1=1`, `outFields=*`, `returnGeometry=true`, `orderByFields=interruption_start_date DESC`
  - Response shape: ArcGIS FeatureServer `features[].attributes`
  - Useful fields: `suburb`, `town`, `feeder`, `number_of_detail_records`, `interruption_reason`, `interruption_start_date`, `interruption_restore_date`, `distributor_event_number`, `planned_outage`
  - CLI mapping: ArcGIS epoch millisecond timestamps are converted to ISO UTC; `planned_outage` controls the status label
  - Quirks: the outage page redirects to an ArcGIS ExperienceBuilder app; the FeatureServer layer URL is in the app config.
  - Refresh rate: not documented; treated as a live hosted ArcGIS layer.

- Aurora Energy
  - Current endpoint: `GET https://www.auroraenergy.co.nz/Umbraco/Api/Outage/currentCenterPoints`
  - Planned endpoint used with `--all`: `GET https://www.auroraenergy.co.nz/Umbraco/Api/Outage/plannedCenterPoints`
  - Related endpoints observed but not used: `currentPolygons`, `plannedPolygons`, `restoredCenterPoints`, `currentCounts`, `plannedCounts`
  - Response shape: GeoJSON `FeatureCollection`; useful values live in `features[].properties`
  - Useful fields: `eventNumber`, `eventStatus`, `suburbsAffected`, `town`, `streetsAffected`, `currentAffectedCustomers`, `plannedAffectedCustomers`, `totalFaultAffectedCustomers`, `groupOutages`, `eventCause`, `startDateTime`, `endDateTime`
  - CLI mapping: current endpoint is used by default; `--all` also adds planned center points; grouped customer counts are used when the summary count is zero or missing.
  - Refresh rate: not documented in the public JavaScript.

- WEL Networks
  - Endpoint: `POST https://server.ourpower.co.nz/api/?FETCH_GROUPED_FAULTS`
  - Request body: `{"application":"outages","emit":true,"type":"FETCH_GROUPED_FAULTS"}`
  - Response shape: object with `payload.groupedFaults[].incidents[]`
  - Useful fields: group `lat`, group `lng`, incident `faultType`, `suburb`, `street`, `propertiesAffected`, `reason`, `start`, `end`, `incidentReference`
  - CLI mapping: `faultType == 1` is planned; default includes unplanned incidents and planned incidents only when their start/end window is active; `--all` includes all planned rows.
  - Quirks: `https://wel.co.nz/outages/` embeds `https://outages.wel.co.nz/?embed=true`; the embedded app calls this OurPower endpoint.
  - Refresh rate: public app JavaScript polls every 60 seconds.

- Unison
  - Endpoint: `GET https://www.unison.co.nz/api/outages`
  - Response shape: JSON array of outage objects
  - Useful fields: `outageID`, `outageState`, `outageStatus`, `outageType`, `networkRegion`, `areaAffected`, `customersOff`, `interruptionReason`, `startTime`, `finishTime`
  - CLI mapping: default includes states such as `current` and `ongoing`; `--all` also includes other non-cancelled, non-completed, non-recent states.
  - Quirks: detailed time windows can appear under `outageWindows`; the CLI keeps the top-level fields in normal output and full raw record in JSON.
  - Refresh rate: public React widget polls every 300,000 ms (5 minutes).

- Counties Energy
  - Current endpoint: `GET https://api.integration.countiesenergy.co.nz/user/v1.0/outages`
  - Planned endpoint: `GET https://api.integration.countiesenergy.co.nz/user/v1.0/shutdowns`
  - Current response shape: object with `service_orders[]`
  - Planned response shape: object with `planned_outages[]`
  - Useful fields: current `address`, `customersAffected`, `description`, `crewStatus`, `etrDateTime`, `serviceOrderDateTime`, `no`, `lat`, `lng`; planned `address`, `affectedCustomers`, `projectType`, `latestInformation`, `shutdownPeriods`, `id`, `lat`, `lng`
  - CLI mapping: current service orders are always current records; planned rows are included by default only when their shutdown window is active, and all planned rows are included with `--all`.
  - Quirks: `https://countiesenergy.co.nz/outages/` links to `https://app.countiesenergy.co.nz/#/`; the app bundle uses the integration endpoints above.
  - Refresh rate: public app cache `staleTime` is 300,000 ms (5 minutes).

- Top Energy
  - Endpoint used by CLI: `GET https://outages.topenergy.co.nz/api/outages/regions`
  - Related endpoint observed but not used for detail: `GET https://outages.topenergy.co.nz/api/outages`
  - Response shape: object with `active[]` and `planned[]` arrays
  - Useful fields: `name`, `circuitName`, `customersCurrentlyOff`, `additionalInformation`, `startDateTime`, `endDateTime`, `isActive`
  - CLI mapping: active rows are current records; planned rows are included by default only when `isActive` is true, and all planned rows are included with `--all`.
  - Quirks: the `/api/outages` marker endpoint is useful for map coordinates, but `/api/outages/regions` carries better outage details.
  - Refresh rate: public app JavaScript checks poll state every 60 seconds.

## Official vs derived values

- Official values:
  - EM6 regional spot `price`
  - EM6 carbon intensity and renewable fields
  - EMI report `Demand (GWh)` and `Demand ($)`
  - EMI point-of-connection `DollarsPerMegawattHour`
  - EMI generation plant trading-period kWh values
  - EMI GUEHMT distributed-generation ICP, capacity, uptake, and new-installation fields
  - `energy-margin` source availability/status fields from the Authority dashboard/article/Tableau surfaces

- Derived by this CLI:
  - `demand` total GWh, average GWh per period, peak period, and average MW conversion
  - `prices` min, max, and average
  - `generation` fuel totals, technology totals, plant totals, GWh conversion, and share percentages
  - `dg-trends` filtered row counts and summary changes
  - `dg-latest` latest-month row selection
  - `dg-summary` overall and year-by-year changes
  - No gentailer energy-margin values are currently derived or copied by this CLI

## Sources checked but not shipped

- EM6 `price/24hrs/{node_id}`, `current_load/{node_id}`, `recent_load/{node_id}`, `current_generation/{node_id}`, `recent_generation/{node_id}`, `generation_type/24hrs/`, `nz/24hrs/`, and regional peak/load endpoints were documented in the EM6 guide but returned unauthorized or forbidden in live no-login testing from the public API base.
- EMI Azure API products for real-time prices and dispatch require subscription-key access, so they are out of scope for this no-login skill.
- Electricity Authority gentailer energy-margin dashboard/article surfaces were checked for official per-company machine-readable rows. The linked Tableau Public workbook currently appears removed or renamed through both the profile app and VizQL render path, so the `energy-margin` command reports an explicit unavailable state instead of returning a derived reconstruction.
- Powerswitch plan comparison was skipped because it requires user-specific inputs and is not suitable for a stateless read-only market-data CLI.
- Northpower outage data was checked at `https://northpower.com/electricity/current-outages` and `https://outages.northpower.nz`. The public app renders Livewire snapshots and uses Livewire websocket/update calls with snapshot and CSRF state. No clean stable unauthenticated JSON or ArcGIS FeatureServer feed was found, so `outages --company northpower` reports a warning instead of scraping the rendered app state. The page says the outage list refreshes at least every 15 minutes.
- Bonus distributors from the follow-up list (Mainpower, Marlborough Lines, Network Tasman, Electra, Westpower, Network Waitaki) were not investigated in this pass after nine of the top-ten target companies were wired.
