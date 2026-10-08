# Additional NZ ArcGIS sources

`layers --curated nz` combines the unchanged Auckland selection with these additional records. Use `--publisher ccc|dcc|hcc|flooded|akl` and optionally `--problem F1|T1|T2|T3|W1|W2|W3` to narrow it. Source catalogue: `skills/nz-data-catalogue/data/catalogue.json.gz`. Every included source passed live metadata checks; feature layers also passed a count query. Counts below are verification snapshots, not current live counts.

`layers-nz.json` retains per-record source URL, publisher, licence or unknown-licence note, probe timestamp and catalogue caveat. `latest_data` is an upstream editing timestamp only when published; `catalogue_latest_data` retains the catalogue freshness label. No observation dates are inferred.

PC120 services expose cached map metadata only: use `describe SERVICE_URL` or `layers akl SERVICE_URL`; they have no queryable features. Their extents use NZTM2000 (EPSG:2193) and remain in that CRS in metadata. Proposed plan maps may have changed since publication. No tiles or image data are downloaded.

For Flooded NZ, queries default to the enforced allowlist `objectid,obs_date,impact,impact_items,obs_depth,obs_depth_v2,historic,status`. Explicit `*` or other fields are refused with exit 2; `describe` exposes only allowlisted fields. The service also exposes contact fields, which the CLI excludes from output. Council ownership is supported by its [launch announcement](https://ourauckland.aucklandcouncil.govt.nz/news/2023/03/aucklanders-asked-to-provide-their-flood-images-to-support-future-storm-responses/). This does not establish reuse permission for submissions. The registry permits only the named Council service in its contractor tenant.

| Catalogue ID / grade | Source | Organisation | Verified count / access | Problem tags |
|---|---|---|---|---|
| S0618 / B | [Footpath](https://apps.dunedin.govt.nz/arcgis/rest/services/Public/RAMM/MapServer/11) | dcc | 9724 | T2 |
| S0625 / B | [Street Lights](https://apps.dunedin.govt.nz/arcgis/rest/services/Public/RAMM/MapServer/0) | dcc | 15693 | T2 |
| S0789 / A | [PC120Revised_PROD_ProposedAmendmentsPC120Zones](https://tiles.arcgis.com/tiles/n4yPwebTjJCmXB6W/arcgis/rest/services/PC120Revised_PROD_ProposedAmendmentsPC120Zones/MapServer) | akl | metadata only | W1 |
| S0790 / A | [PC120Revised_PROD_Precincts](https://tiles.arcgis.com/tiles/n4yPwebTjJCmXB6W/arcgis/rest/services/PC120Revised_PROD_Precincts/MapServer) | akl | metadata only | W1 |
| S0792 / A | [PC120Revised_PROD_Policy3D_UpzoningAroundCentreZones](https://tiles.arcgis.com/tiles/n4yPwebTjJCmXB6W/arcgis/rest/services/PC120Revised_PROD_Policy3D_UpzoningAroundCentreZones/MapServer) | akl | metadata only | W1 |
| S0943 / B | [RecyclingCollection](https://gis.ccc.govt.nz/server/rest/services/OpenData/SiteUtility/FeatureServer/12) | ccc | 165 | W2 |
| S0945 / B | [Refuse collection (all areas)](https://apps.dunedin.govt.nz/arcgis/rest/services/Public/Refuse_Collection_Property/MapServer/1) | dcc | 66307 | W2 |
| S1098 / A | [Hamilton_City_Traffic_Counts](https://services1.arcgis.com/R6s0QqCMQdwKY6yp/arcgis/rest/services/Hamilton%20City%20Traffic%20Counts/FeatureServer/0) | hcc | 765 | T1, T2 |
| S1099 / B | [Stormwater Catchpit Hamilton City Council](https://services1.arcgis.com/R6s0QqCMQdwKY6yp/arcgis/rest/services/Stormwater%20Dataset%20-%20Hamilton%20City%20Council/FeatureServer/0) | hcc | 13629 | F1 |
| S1100 / A | [Cycleway](https://gis.ccc.govt.nz/server/rest/services/OpenData/Cycle/FeatureServer/1) | ccc | 4920 | T1, T2 |
| S1101 / A | [CoastalInundationHazard](https://gis.ccc.govt.nz/server/rest/services/OpenData/WaterCharacteristic/FeatureServer/47) | ccc | 105134 | F1 |
| S1102 / A | [Fence](https://gis.ccc.govt.nz/server/rest/services/OpenData/Structure/FeatureServer/2) | ccc | 14067 | F1 |
| S1103 / A | [Building](https://gis.ccc.govt.nz/server/rest/services/OpenData/Property/FeatureServer/12) | ccc | 237094 | W1 |
| S1104 / B | [CollectionDepot](https://gis.ccc.govt.nz/server/rest/services/OpenData/SiteUtility/FeatureServer/9) | ccc | 16 | W2 |
| S2095 / B | [StreetCentreLine](https://gis.ccc.govt.nz/server/rest/services/OpenData/Road/MapServer/7) | ccc | 12440 | T1 |
| S2162 / B | [RoadIntersection](https://gis.ccc.govt.nz/server/rest/services/OpenData/Road/FeatureServer/6) | ccc | 7265 | T2 |
| S2516 / B | [Daily special clean areas](https://apps.dunedin.govt.nz/arcgis/rest/services/Public/Roading_contract/FeatureServer/2) | dcc | 3 | W3 |
| S2516 / B | [Routine street cleaning - daily](https://apps.dunedin.govt.nz/arcgis/rest/services/Public/Roading_contract/FeatureServer/3) | dcc | 99 | W3 |
| S2516 / B | [Routine street cleaning - weekly](https://apps.dunedin.govt.nz/arcgis/rest/services/Public/Roading_contract/FeatureServer/4) | dcc | 195 | W3 |
| S2516 / B | [Routine street cleaning - fortnightly](https://apps.dunedin.govt.nz/arcgis/rest/services/Public/Roading_contract/FeatureServer/5) | dcc | 7 | W3 |
| S2516 / B | [Green Island tunnels - monthly](https://apps.dunedin.govt.nz/arcgis/rest/services/Public/Roading_contract/FeatureServer/6) | dcc | 2 | W3 |
| S2516 / B | [Street cleaning - Stadium](https://apps.dunedin.govt.nz/arcgis/rest/services/Public/Roading_contract/FeatureServer/7) | dcc | 115 | W3 |
| S2516 / B | [Leaf clearing](https://apps.dunedin.govt.nz/arcgis/rest/services/Public/Roading_contract/FeatureServer/8) | dcc | 317 | W3 |
| S2516 / B | [Street cleaning zones](https://apps.dunedin.govt.nz/arcgis/rest/services/Public/Roading_contract/FeatureServer/12) | dcc | 17 | W3 |
| S2686 / A | [survey](https://services-ap1.arcgis.com/eqbFSejuTufXDr0E/arcgis/rest/services/flooded_nz_gdb_v2_202603181308/FeatureServer/0) | flooded | 742 | F1 |
| S2927 / B | [Formed Roads](https://apps.dunedin.govt.nz/arcgis/rest/services/Public/Search/FeatureServer/0) | dcc | 2259 | T3 |
| S2932 / A | [Road_PairwiseDissolve](https://services1.arcgis.com/R6s0QqCMQdwKY6yp/arcgis/rest/services/RoadHierarchy20260623/FeatureServer/0) | hcc | 2416 | T3 |
| S2933 / A | [Road Surface Renewals](https://services1.arcgis.com/R6s0QqCMQdwKY6yp/arcgis/rest/services/Transport_Renewals/FeatureServer/2) | hcc | 1429 | T3 |

Reverify with `python3 skills/nz-arcgis/scripts/curate_more_layers.py skills/nz-data-catalogue/data/catalogue.json.gz`. This updates only the additional selection and its failure/deferred list, leaving the original Auckland curated files unchanged. Fixtures for these additions contain synthetic values in the verified response shapes.

Deferred: Dunedin/Hamilton roadworks and closure catalogue sources are HTML notices (S2925, S2926, S2929, S2930). Neither formed roads nor transport renewals establishes closure status. Auckland tiled DEM/DSM metadata and identify probes (C0070, C0071) are deferred because `https://tiledimageservices1.arcgis.com/robots.txt` returned `User-agent: *` and `Disallow: /` on 8 October 2026. Do not crawl those routes; existing allowlist entries are retained for compatibility.
