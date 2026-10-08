# LINZ Data Service API notes

Public Koordinates services API base:

```text
https://data.linz.govt.nz/services/api/v1/
```

Verified endpoints:

- `layers/?q=<query>` returns public layer search results.
- `layers/<id>/` returns full layer metadata, description, licence, categories, tags, permissions, and HTML/canonical URLs.
- `layers/<id>/services/` returns advertised service endpoints such as CS-W, WFS, WMTS, ArcGIS/XYZ links, plus whether each uses no auth or API key auth.

Live probe: `layers/?q=address` returned `NZ Addresses` with id `123113`, public_access `download`, and user_permissions including `find`, `view`, `download`.

Catalogue service templates may require an API key. Feature queries use only the separate keyless public mirror below.

## Keyless public ArcGIS mirror (verified 8 October 2026)

- Primary parcels: `https://services.arcgis.com/xdsHIIxuCWByZiCB/arcgis/rest/services/LINZ_NZ_Primary_Parcels/FeatureServer/0`
- Building outlines: `https://services.arcgis.com/xdsHIIxuCWByZiCB/arcgis/rest/services/LINZ_NZ_Building_Outlines/FeatureServer/0`
- Directory: `https://services.arcgis.com/xdsHIIxuCWByZiCB/arcgis/rest/services/?f=json`

Both layers support GeoJSON, an OBJECTID field, and a 2000-record server page cap.
Queries send a WGS84 envelope (`geometryType=esriGeometryEnvelope`, `inSR=4326`,
`spatialRel=esriSpatialRelIntersects`), count-only first, then GeoJSON pages with
`outSR=4326`, `outFields=*`, offsets and OBJECTID order. The CLI returns at most
2000 features, in pages of at most 1000, and accepts bboxes up to 1 degree
wide/high. Features are intersected, not clipped. Each call times out at 10 s;
ArcGIS responses have an 8 MiB byte cap. Large rural/coastal polygons can exceed
that cap; split the bbox or reduce the limit. Paging is not a transactional snapshot.

The public directory lists primary parcels but no NZ Parcels service. A live
probe of `LINZ_NZ_Parcels/FeatureServer/0` returned ArcGIS error 400, Invalid URL.
This skill therefore marks `parcels` unsupported and exits 7 if requested.
Primary parcels are a different dataset (current primary polygons); they exclude
non-primary, historic and pending parcels. LDS NZ Parcels is catalogue layer 51571.
Do not silently substitute title/property boundaries or a third-party mirror.

ArcGIS items `7442ad2e98534d67a3c45df9b7fbcf5e` (primary parcels) and
`ef40ae8beaff4b6eb43f3c6971b34d1b` (building outlines) identify LINZ and CC BY 4.0.
`latest_data` uses the layer `editingInfo.dataLastEditDate`. Building properties
include `capture_source_from`/`capture_source_to` (epoch milliseconds) and
`last_modified`, which describe feature-specific source imagery and edits.
Parcel boundaries need not match fences or ownership; building coverage and
capture dates vary by area.

`tests/fixtures/spatial.json` contains three real features per supported layer,
counts, selected layer metadata, and the directory's parcel service names.
`scripts/spatial_contract.py` verifies paging, provenance, GeoJSON, bbox validation,
upstream errors and the unsupported NZ Parcels boundary. It runs from
`scripts/test_contract.py` and `scripts/smoke_test.py`.
