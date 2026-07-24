# Source notes — NIWA ArcGIS open data

- Primary owner: NIWA (National Institute of Water and Atmospheric Research /
  Earth Sciences New Zealand)
- Primary source: https://data-niwa.opendata.arcgis.com/
- Declared outbound hosts: data-niwa.opendata.arcgis.com, www.arcgis.com,
  services.arcgis.com, services3.arcgis.com, gis.niwa.co.nz
- Access mode: public-api
- Authentication: none
- Last verified: 2026-07-24

## Search: org-scoped sharing search

Same rationale as `wcc-arcgis-nz`: the Hub portal fronts a standard ArcGIS
Online organisation, and hub-wide search APIs return the global catalogue.
The CLI uses `https://www.arcgis.com/sharing/rest/search?q=<kw> orgid:<orgId>`.

Org id resolved via `https://hub.arcgis.com/api/v3/domains/data-niwa.opendata.arcgis.com`
on 2026-07-24: `fp1tibNcN9mbExhG` (~1,373 public items at verification).

## Layer query hosts

A 40-item survey of public item service URLs found these hosts:
`services3.arcgis.com` (main Esri-hosted tenant, path prefix
`/fp1tibNcN9mbExhG/`), `gis.niwa.co.nz` (NIWA's own ArcGIS Server 11.1 — the
`COAST` folder carries the coastal classification MapServers referenced by
MBIE's Coastal Explorer), plus tile/stream variants
(`tiles.arcgis.com`, `dservices3.arcgis.com`, `tiledimageservices3.arcgis.com`)
that do not answer feature queries and are not allowed, and a few third-party
hosts (NOAA, GNS) that belong to other owners' skills. The CLI accepts
`services.arcgis.com`/`services3.arcgis.com` only with the NIWA tenant as the
first path segment, and `gis.niwa.co.nz` exactly; everything else exits 7.

## Verified key datasets (WCC-EM GIS overview, 2026-07-24)

- NZ Coastal Sensitivity Index CSI erosion — item
  `c894b53b102f4f9db55278f7572ca4f6` →
  `services3.arcgis.com/fp1tibNcN9mbExhG/arcgis/rest/services/NZ_Coastal_Sensitivity_Index_CSI_erosion/FeatureServer`
- Coastal Sensitivity Index CSI inundation — item
  `35f79b410def4148908dda7452b30d6f` (Map Service)
- NZ Coastal classification Beach exposure — item
  `2e2f8ea5ea31453e808b36b2a1ca43a0` (Map Service)
- NZ Coastal classification — Hinterland characteristics / Landform type —
  `gis.niwa.co.nz/server/rest/services/COAST/...` MapServers

## Reuse and licence

Items carry CC BY 4.0 licence blocks in their `licenseInfo` (verified on the
CSI erosion item). Attribute NIWA. The CSI layers are snapshots of *potential*
sensitivity to future climate-driven coastal change — not engineering-grade
hazard maps; keep NIWA's caveats attached when summarising.

## Failure modes

- ArcGIS answers HTTP 200 with a JSON `error` body on bad queries — converted
  to exit 5 with the upstream message.
- Map Services (as opposed to Feature Services) may not support `f=geojson`
  on all layers; the schema-failure guard (exit 6) reports the raw payload
  head when that happens.
