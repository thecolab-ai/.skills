# Hazard Data CLI Capability Expansion Design

**Date:** 2026-07-26
**Status:** Approved
**Scope:** `gns-hazards-nz`, `niwa-coastal-nz`, `searise-nz`, and `wcc-arcgis-nz`

## Goal

Give an AI agent broad, composable access to each upstream hazard-data source through source-native CLI primitives. The skills should expose metadata, discovery, filtering, pagination, and raw spatial queries while leaving interpretation and cross-source composition to the calling agent.

## Design Principles

- Preserve upstream meaning, units, provenance, identifiers, and version information.
- Prefer small source-native operations over a combined “hazards at this location” answer.
- Keep current commands and single-site SeaRise output backward compatible.
- Return structured JSON by default and GeoJSON when the upstream operation naturally returns features.
- Validate user-controlled URLs, identifiers, coordinates, and numeric controls before network access.
- Reject non-finite coordinates and values outside longitude/latitude bounds.
- Keep the CLIs Python-standard-library-only and use the repository fetch foundation.
- Do not add persistent caches, write downloaded datasets to the repository, or invent data when a source is unavailable.

## Shared ArcGIS Query Surface

The ArcGIS-backed skills will expose the upstream query controls that an agent needs to build precise requests:

- `--count`
- `--ids-only`
- `--no-geometry`
- `--offset`
- `--order-by`
- `--geometry-precision`
- `--max-allowable-offset`

`--count` and `--ids-only` are mutually exclusive. Count and ID responses use normalized JSON envelopes; ordinary feature queries continue to return GeoJSON. Existing filters and record limits remain available.

Each ArcGIS-backed skill will add `describe`, returning normalized layer metadata including fields, aliases, types, units or descriptions when supplied, extent, spatial reference, capabilities, geometry type, object ID field, and record limits.

Coordinate-like CLI values that begin with a negative number will be normalized at the parser boundary so both `--point -41.29,174.78` and `--point=-41.29,174.78` work. The same treatment applies to existing bounding-box arguments.

## `gns-hazards-nz`

### GeoNet ShakingLayers archive

Add `shakinglayers.geonet.org.nz` to the strict source allowlist and expose:

- `events [--year YYYY]` — list available event IDs.
- `versions EVENT_ID` — list the event’s issued versions, statuses, types, issue times, and version paths.
- `event-files EVENT_ID [--version latest]` — list files for an event version with file names and source URLs.
- `event-data EVENT_ID --measure MEASURE [--version latest]` — return the selected contour GeoJSON.

Supported measures will be derived from the files actually published for the selected event. Known measures such as MMI, PGA, PGV, and PSA will include their published units in the normalized metadata. A requested measure that is unavailable for the event returns an explicit error containing the available measures/files.

The existing ArcGIS `shaking` command remains the convenient latest-layer query and is not redefined as measured-only data. Output and documentation will describe it as modelled shaking information with recorded observations used by the upstream system where applicable.

### ArcGIS metadata and queries

Add `describe` for the existing faults and shaking services and add the shared ArcGIS query controls to their feature-query commands.

## `niwa-coastal-nz`

- Add `search --start N` and preserve the upstream paging cursor.
- Add `item ITEM_ID` returning normalized catalogue metadata: title, type, owner, organisation, access, licence, description, tags, timestamps, size, and service URL when supplied.
- Add `describe SERVICE [--layer-id N]`.
- Add the shared ArcGIS query controls to feature queries.
- Add `identify SERVICE --point LON,LAT` with optional layer selection, tolerance, and geometry suppression. This is a raw MapServer identify primitive, not a hazard assessment.

Organisation and host validation remains strict for both search results and direct service access.

## `wcc-arcgis-nz`

- Add `search --start N` and preserve the upstream paging cursor.
- Add `item ITEM_ID` with the same normalized catalogue metadata contract as NIWA.
- Add `describe SERVICE [--layer-id N]`.
- Add the shared ArcGIS query controls to feature queries.
- Add `identify SERVICE --point LON,LAT` with optional layer selection, tolerance, and geometry suppression.

The existing Wellington City, Greater Wellington, and Wellington Water service hosts remain supported through exact allowlists.

## `searise-nz`

- Add `record` to expose the Zenodo record’s DOI, version, publication date, title, creators, licence, and file inventory including sizes, checksums, and download links.
- Allow one or more site IDs in a single `projections` invocation.
- Download and parse the selected projection file once for all requested sites.
- Iterate CSV rows rather than materializing every row as a dictionary list.
- Preserve all existing scenario, confidence, year, and VLM filters.

For one site ID, the existing output shape remains unchanged. For multiple IDs, return ordered per-site results and a clear list of requested IDs; unknown IDs produce explicit per-site empty/not-found results rather than silently disappearing.

No persistent cache is added. The CLI continues to stream source data through the repository fetch layer and keeps all work ephemeral.

## Errors and Source Honesty

Commands distinguish invalid input, blocked host or organisation, upstream HTTP failure, malformed response, missing event/file/site, and legitimate empty results. Errors are emitted as structured JSON on stderr with a non-zero exit status. No command substitutes stale fixtures or hardcoded public-data rows for a failed live source.

## Verification

Each skill gets fixture-backed unit and contract tests for new arguments, validation, normalized response shapes, pagination, and failure cases. Live smoke tests cover safe, bounded metadata or small-query paths. SeaRise is additionally exercised manually against both large projection files, including a multi-site request, while retaining fixture tests for fast CI.

After implementation:

1. Run all four changed-skill tests and smoke tests.
2. Regenerate and check `README.md` and `skills.json`.
3. Run foundation tests, strict agent/repository validation, all contract tests, security checks, Python compilation, and diff checks.
4. Have an independent subagent adversarially inspect the diff and exercise malformed, boundary, paging, empty, and live-source cases.

## Non-Goals

- No combined location-risk score or cross-source “what hazards are here?” command.
- No geocoding or inference of a user’s location.
- No scientific interpretation, safety recommendation, or policy conclusion.
- No persistent database, cache, background synchronization, or bulk mirror.
- No relaxation of URL, host, organisation, or redirect security controls.
