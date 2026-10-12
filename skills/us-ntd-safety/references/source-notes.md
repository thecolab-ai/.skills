# Source notes

- Primary owner: Federal Transit Administration
- Primary source: https://data.transportation.gov/
- Geography: United States. This is not Auckland and not a New Zealand feed.
- Authentication: none
- Last verified: 2026-10-11
- Declared outbound host: data.transportation.gov
- Access mode: public SODA JSON reads plus the matching view metadata
- Timeout: 15 seconds per request. Responses over 1.5 MB fail as truncated JSON.

The events view metadata read on 2026-10-11 returned `licenseId` `USGOV_WORKS`,
licence name `Public Domain U.S. Government`, and attribution
`Federal Transit Administration`. The modes view returned `licenseId`
`PUBLIC_DOMAIN` and licence name `Public Domain`. It had no attribution
field. The modes description identifies the National Transit Database.
Each command refuses its resource when a fresh view read does not repeat
that resource's licence id. `USGOV_WORKS` does not authorise `modes`, and
`PUBLIC_DOMAIN` does not authorise `events`.

Observed publisher pages, not requested by the CLI:

- Events attribution link: https://www.transit.dot.gov/ntd/ntd-data
- Events terms link: https://www.usa.gov/government-works

## Resources

`events` is SODA `9ivb-8ae9`, Major Safety and Security Events. The view
description says the series starts in January 2014, that monthly data are
released within about three months of submission, and that there is generally
at least a 90-day lag before an event appears.

`modes` is SODA `5ti2-5uiv`, Monthly Modal Time Series. It covers full
reporters: agencies operating modes with more than 30 vehicles in maximum
service. The description says the dataset is updated monthly, ridership is
released one month after the service month, null monthly service values can
mean late reporting, and safety events from the past three months are excluded
from the matching ridership rows while they are validated. The series includes
major and non-major events where the source says so, and it is not adjusted
for historical continuity.

`meta.latest_data` is the view `rowsUpdatedAt` instant converted to UTC. It is
the Socrata update time, not the newest event or the newest complete month.

## Fields, units and withholding

Only allowlisted columns are selected. The CLI also drops anything outside
that list if a row contains it. Withheld names:

- `incident_description`
- `other_event_type_description`
- `person_list` (injury and fatality person-type, age-group and gender lists)
- `approximate_address`, `latitude`, `longitude`, `latlon`
- `multiple_locations_list`, `revenue_vehicle_identifier_list`
- `non_transit_vehicle_action_list`
- comment and other-description fields: `evacuation_comment`,
  `weather_comment`, `hazmat_type_description`, `other_fire_fuel_description`,
  `rail_grade_crossing_comment`, `action_type`, `manufacturer_description`
- Socrata computed-region columns

`assault_homicide_person_type_desc` is a transit-worker category code, not a
person record. `collisions_with_person` and `personal_security_events` are
counts.

Coded text longer than 160 characters fails closed so a narrative cannot hide
in a coded column. Calendar dates and clock times are copied unchanged.
`incident_time` has no source timezone. Do not relabel it as UTC or as
Auckland time.

Stated units:

- `property_damage`: US dollars (source: estimated dollar value)
- `vehicle_speed`: the column description does not state a unit, so none is attached
- `primary_uza_sq_miles`, `service_area_sq_miles`: square miles
- `primary_uza_population`, `service_area_population`: people
- `vehicles`: revenue vehicles (VOMS)
- `vehicle_revenue_miles`: miles
- `vehicle_revenue_hours`: hours
- `ridership`: boardings

Miles, hours and ridership are calendar-year figures and are year-to-date when
the year is incomplete. Absent measure keys are omitted. An explicit null stays
null. Neither means zero. A short non-numeric token in a number column is kept
as text and named in `unparsed_measures`.

## Errors

Invalid arguments, unknown fixture names and path-like fixture tokens return
exit 2 and do not open a socket. HTTP 429 is exit 4 with `retry_after` when
the source sends one. HTTP 503, timeouts and other upstream failures are exit
5. Non-JSON, truncated JSON, a changed column type and an unexpected row shape
are exit 6. A licence mismatch is exit 4 and does not return rows. Redirects
must stay on `https://data.transportation.gov`. Proxies are not used.

Live smoke requests `$limit=1` for events, and `$limit=1` with `--year 2024`
for modes. The newest modes month can omit ridership and event totals while
those months are still being validated, so the modes probe uses a completed
year. An outage, a licence mismatch, or zero rows is not a pass.
