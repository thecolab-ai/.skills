# Ministry Fleet Statistics Source Notes

The primary source is the Ministry of Transport annual fleet statistics page:

- `https://www.transport.govt.nz/statistics-and-insights/fleet-statistics/sheet/annual-fleet-statistics`
- `https://www.mot-dev.link/fleet/annual-motor-vehicle-fleet-statistics/`

The Ministry page says the annual fleet statistics use the Motor Vehicle Register as a key source and that the 2024 open data tool provides downloadable machine-readable CSV extracts plus a complete open data spreadsheet. The tool page identifies the 2024 release as covering 2000-2024 and lists release notes including Version 4.0, released in October/November 2025.

## Workbook Handling

The skill does not vendor the live workbook or hardcode result rows. It discovers workbook links from the official HTML when reachable, then parses `.xlsx` files directly with Python standard-library ZIP/XML tooling:

- `xl/workbook.xml` and `xl/_rels/workbook.xml.rels` for sheet names and file targets
- `xl/sharedStrings.xml` for shared string cells
- worksheet XML for cached cell values and inline strings

If the official site is blocked by Incapsula, Cloudflare, CAPTCHA, or a similar edge system, commands return `status: "blocked"` with the relevant source URL. Use `--url file:///.../NZVehicleFleet_2024.xlsx` after manually downloading the public workbook when direct HTTP is blocked.

## Table Mappings

The issue request names the immediate 2024 targets as:

- `8.2a,b` - annual travel by fuel and vehicle type, including petrol, diesel, and pure-electric VKT tables
- `8.4` and `8.5` - light-fleet fuel or powertrain counts
- `1.4` to `1.7` - total light travel context

The CLI searches sheet names and nearby headings for those table-code patterns. If a future workbook renames sheets, use `tables --json` or `workbook --sheet NAME --json` to inspect the current workbook before trusting a focused command.

## Caveats

- VKT means vehicle kilometres travelled.
- The workbook may publish some VKT tables by broad fuel category only. Hybrid and plug-in hybrid VKT splits should be treated as unavailable unless the source workbook publishes those categories explicitly.
- Figures are annual aggregate statistics. They are not individual vehicle records.
- Attribute the Ministry of Transport as the source and keep the workbook URL or official page URL with any reported values.
