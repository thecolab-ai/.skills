# Source notes

- Primary owner: Toitū Te Whenua LINZ and SwellMap
- Primary source: https://www.linz.govt.nz
- Declared outbound hosts: developer.metservice.com,niwa.co.nz,static.charts.linz.govt.nz,www.linz.govt.nz,www.surfline.com,www.swellmap.com
- Access mode: public-api
- Authentication: none
- Last verified: 2026-10-12

The skill is read-only unless its SKILL.md metadata explicitly declares mutations. Live results must retain source and retrieval-time context. A blocked, unavailable, or changed source is an explicit failure state, never an empty successful dataset.

## Standard-port tidal levels

Verified on 2026-10-12 from the official page `https://www.linz.govt.nz/guidance/marine-information/tide-prediction-guidance/standard-port-tidal-levels` (HTTP 200, HTML, one table). The page states that the levels are in metres and are referred to Chart Datum, which is the same as the zero of the tidal predictions.

`https://www.linz.govt.nz/copyright`, fetched the same day, states that LINZ website content is licensed under Creative Commons Attribution 4.0 International unless otherwise specified. Attribute Toitū Te Whenua Land Information New Zealand in writing. Do not reproduce emblems. Data provided through the LINZ Data Service carries its own terms. This table is website content, not a LINZ Data Service dataset and not an observed gauge archive.

`levels` fetches that one page only, with a 10-second timeout, a 256 KiB cap, and `www.linz.govt.nz` as the only allowed host. A successful table may be reused for 24 hours. The command does not open the standard-port periods-of-observation page, tide-prediction CSVs, or sea-level gauge files. Surf-beach aliases are not standard ports. Daily high and low predictions stay on `tides` and `next-tide`.
