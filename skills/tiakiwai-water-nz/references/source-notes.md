# Source notes — Wellington Water (Tiaki Wai) job status

- Primary owner: Wellington Water (Tiaki Wai)
- Primary source: https://www.tiakiwai.co.nz/faults-and-outages/see-outages/network-status
- Declared outbound hosts: www.tiakiwai.co.nz, services7.arcgis.com
- Access mode: public-api
- Authentication: none
- Last verified: 2026-07-22

## Endpoint discovery

Tiaki Wai's network-status page embeds an ArcGIS Experience app
(`87b887b5023e45efbe59736e8b2e0f27`). Its data sources (via the arcgis.com sharing
API) include the public feature layer this skill queries:

`https://services7.arcgis.com/2ECs938g489DMWjt/arcgis/rest/services/Job_Status_Public_View/FeatureServer/5`

Standard ArcGIS REST `query` with `f=geojson`, no key. ~1,500 rows at verification;
supports `where`, `orderByFields`, `returnDistinctValues`, and `outStatistics`
(used for `summary`).

## Observed field semantics (2026-07-22)

- `councilid`: WCC, HCC, UHCC, PCC (no SWDC rows observed).
- `watertype`: Potable Water, Storm Water, Waste Water.
- `StatusDescription`: New, In Queue, Under Investigation, In Progress, Resolved,
  Do Not Display. "Do Not Display" is the source's own suppression flag — always
  excluded. `faults` and `summary` exclude Resolved by default
  (`--include-resolved` re-adds it); direct `fault` lookup may return a resolved
  record when its job number is known.
- `reportdate`/`actstart`/`compdate`: epoch milliseconds; converted to
  Pacific/Auckland ISO in output.
- `wonum` is the stable public job number; `externalrefid` is the council's
  service-request reference.
- Geometry is a point per job (WGS84 after `outSR=4326`).

## Stability and reuse

- The layer backs Tiaki Wai's own public map, so it moves only if their app is
  rebuilt; the ArcGIS item ids above are the re-discovery path.
- No published licence on the layer itself; treat as public operational data,
  retain source links, and do not present jobs as confirmed supply outages —
  they are maintenance workflow records.
- Bounded, read-only use only; no reporting, subscription, or account flows.
