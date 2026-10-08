# LINZ public STAC source notes

Authentication: none

Last verified: 2026-10-08

Primary catalogues:

- [Elevation catalogue](https://nz-elevation.s3.ap-southeast-2.amazonaws.com/catalog.json)
- [Imagery catalogue](https://nz-imagery.s3.ap-southeast-2.amazonaws.com/catalog.json)
- [LINZ imagery project](https://github.com/linz/imagery) documents the public archive.

These static STAC documents have relative links: catalogue `rel=child` points
to a collection; collection `rel=item` points to tile Features. Resolve every
link and asset against its containing document URL. There is no STAC API
`/search` endpoint here. No bucket listing, credentials or signed URLs are used.

## Search method

LINZ publishes the Topo50 sheet/subtile naming algorithm in
[tile_index.py](https://github.com/linz/topo-imagery/blob/master/packages/geoprocessor-gdal/src/geoprocessor_gdal/tile/tile_index.py).
The helper independently implements the grid constants: 24,000 × 36,000 m
sheets, column-zero west origin 988,000 m, northern row AS at 6,234,000 m,
and omitted rows BI, BO, CI. Subtile names contain scale then one-based row and
column, e.g. `BA31_10000_0505` and `BA31_1000_4344`. Scale 500 uses three digits
per row/column. This is a metadata prefilter, not a geodetic transformation API.

A GRS80 transverse Mercator series projects the requested WGS84 bbox edges
into NZTM2000, with 100 m padding. Item links are filtered locally by their
published tile names, avoiding thousands of HTTP calls. Retrieved STAC polygon
or multipolygon footprints are then intersected with the original bbox,
including polygon holes. No footprints or raster URLs are guessed.

Tile Features supply `id`, `bbox`, `geometry`, `properties.start_datetime` /
`end_datetime`, and `assets.visual.href`. A COG asset must explicitly declare
`profile=cloud-optimized` in its media type. Collection metadata supplies
`license`, `providers`, `gsd`, `extent`, `linz:region`, `created` and `updated`.
Some collections omit `gsd`; resolution then comes from the published path.
Use the capture interval for `latest_data`, not processing timestamps.
The required Auckland collections declare `CC-BY-4.0`. Attribution should also
retain the collection's producer/licensor providers when publishing derivatives.

## Auckland selectors

Prefix each path with `elevation:` or `imagery:` as appropriate.

| Bucket | Path | Product |
|---|---|---|
| elevation | `auckland/auckland-part-1_2024/dem_1m/2193` | 2024 1 m DEM |
| elevation | `auckland/auckland-part-1_2024/dsm_1m/2193` | 2024 1 m DSM |
| elevation | `auckland/auckland-part-2_2024/dem_1m/2193` | 2024 1 m DEM |
| elevation | `auckland/auckland-part-2_2024/dsm_1m/2193` | 2024 1 m DSM |
| elevation | `auckland/auckland-north_2016-2018/dem_1m/2193` | 2016–18 1 m DEM |
| imagery | `auckland/auckland_2024_0.075m/rgb/2193` | 2024–25 7.5 cm RGB |
| imagery | `auckland/auckland_2024_0.075m/rgbnir/2193` | 2024–25 7.5 cm infrared |

The imagery paths say 2024, while their titles and capture intervals cover
2024–2025. Preserve that distinction. Part 1 and Part 2 elevation cover
different acquisition areas; query the relevant collection rather than merging
them into an assumed single dataset. The example bbox surrounds Mt Albert:
`174.715,-36.905,174.725,-36.895`.

## Sampling and limits

`point` provides `gdallocationinfo -valonly -wgs84 /vsicurl/<COG URL> <lon> <lat>`.
GDAL must be installed separately. The skill does not invoke GDAL, install
packages, or decode TIFF compression, floating-point predictors, georeferencing
and nodata in stdlib. Its scalar `elevation` stays null; tile availability alone
cannot establish an elevation value. The GDAL command samples band 1. DSM is
surface height, so select DEM for terrain analysis. Verify the source's vertical
datum and units rather than assuming sea-level equivalence.

Each network request has a 10 s timeout and each JSON response a 16 MiB cap.
There is no persistent cache or raster download command. Unknown tile names,
non-NZTM collections, malformed STAC and oversized bboxes fail explicitly.
The search scope is mainland NZ (165–180° E, 48–33° S); it does not cover the
Chatham Islands, antimeridian-crossing requests, point clouds or other grids.
Footprints represent whole raster tiles; nodata may exist within a footprint.

`tests/fixtures/stac-samples.json` contains captured public responses. Catalogue
children and collection item links are trimmed to seven Auckland collections,
Mt Albert candidates and each collection's first tile. All remaining source
fields are unchanged. The fixture records its capture time and trim description.
Tests use the same parser/search path offline and reject malformed metadata.
