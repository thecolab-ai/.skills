# Source notes

- Owner: New Zealand Ministry of Education
- Primary source: https://www.educationcounts.govt.nz/directories/list-of-nz-schools
- Documentation: https://www.educationcounts.govt.nz/directories/school-directory-api
- DataStore resource ID: `4b292323-9fcc-41f8-814b-3c7b19cf14b3`
- API host: `catalogue.data.govt.nz`
- Authentication: none
- Update cadence: nightly
- Last verified: 2026-07-19

The Education Counts API documentation identifies the exact data.govt.nz DataStore resource and
states that it is updated nightly. The CLI reads the resource metadata first, then the current
DataStore rows, so every result carries the published CSV URL and resource modification time.

The output includes official school identity, status, type, authority, location, region,
coordinates, enrolment-scheme indicator, Equity Index, roll date and indicative total roll. The
Ministry states that the indicative roll is an ENROL estimate and that the Equity Index is not a
quality measure; both caveats are emitted on every result. Ethnic sub-counts, principal names and
email addresses are intentionally not emitted by this initial connector.

Year-level bounds prefer the directory's literal `Lowest_Class` and `Highest_Class` fields, then
an explicit `Year N-M` range in `Org_Type`. When neither is published, the connector applies only
these canonical Ministry type definitions: `Contributing` = Years 1-6, `Full Primary` = Years 1-8,
and `Intermediate` = Years 7-8. Ambiguous types remain null rather than being guessed. Every record
includes `year_levels_provenance` naming the source field and whether a type mapping was applied.

`near` calculates great-circle distance only between user-supplied coordinates and the official
school coordinates. `zone --address` returns an unsupported-operation state because the directory
does not itself provide address geocoding or zone polygons. `changes` is deliberately limited to
opening dates represented in the current directory and does not claim to enumerate closures,
mergers or renames.
