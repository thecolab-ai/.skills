# Hazard Data CLI Capability Expansion Implementation Plan

> **For Codex:** Execute the four skill tasks with isolated file ownership. Subagents must not commit, push, or regenerate repository-wide catalogue files; the root agent performs integration and verification.

**Goal:** Expand four New Zealand hazard-data skills with source-native discovery, metadata, paging, spatial-query, and efficient multi-site data access.

**Architecture:** Each skill remains a standalone standard-library CLI using the repository fetch foundation and exact source allowlists. ArcGIS operations share consistent argument and output semantics but remain implemented within their owning skill; GeoNet ShakingLayers and Zenodo operations are source-specific. All behavior is covered first with fixture-backed tests, followed by bounded live smokes and repository-wide validation.

**Tech Stack:** Python 3 standard library, `argparse`, ArcGIS REST, GeoNet ShakingLayers API, Zenodo REST, repository `lib.nzfetch`, `unittest`.

---

### Task 1: Expand `gns-hazards-nz`

**Files:**
- Modify: `skills/gns-hazards-nz/scripts/cli.py`
- Modify: `skills/gns-hazards-nz/scripts/test_contract.py`
- Modify: `skills/gns-hazards-nz/scripts/smoke_test.py`
- Modify: `skills/gns-hazards-nz/SKILL.md`
- Modify: `skills/gns-hazards-nz/references/source-notes.md`
- Add fixtures under: `skills/gns-hazards-nz/tests/fixtures/`

**Step 1: Write failing tests**

Cover:

- Negative-leading coordinate/bbox normalization and finite/range validation.
- `events`, `versions`, `event-files`, and `event-data`.
- `latest` version resolution.
- Available-measure discovery, unit/provenance metadata, and unavailable-measure errors.
- Event ID/path validation and strict ShakingLayers host enforcement.
- `describe` normalized metadata.
- ArcGIS `--count`, `--ids-only`, `--no-geometry`, `--offset`, `--order-by`, `--geometry-precision`, and `--max-allowable-offset`.
- Mutual exclusion of count/IDs modes.

Run:

`python3 skills/gns-hazards-nz/scripts/test_contract.py`

Expected: the new tests fail before implementation.

**Step 2: Implement the GeoNet archive commands**

Use `https://shakinglayers.geonet.org.nz/api/v1` through `lib.nzfetch`. Validate event/version/file path segments before URL construction. Normalize event/version/file responses without discarding upstream IDs, issue times, statuses, types, URLs, or file names. Select measures from published contour files and attach explicit known units.

**Step 3: Implement ArcGIS metadata and query controls**

Add a normalized `describe` operation for the faults and shaking layers. Map each CLI option exactly to its ArcGIS REST parameter and retain bounded defaults.

**Step 4: Update docs and live smoke**

Document all commands, units, provenance, and examples. Add bounded live smoke coverage for event discovery/version/file metadata and ArcGIS describe/count.

**Step 5: Verify**

Run:

- `python3 skills/gns-hazards-nz/scripts/test_contract.py`
- `python3 skills/gns-hazards-nz/scripts/smoke_test.py`
- `python3 -m py_compile skills/gns-hazards-nz/scripts/*.py`

### Task 2: Expand `niwa-coastal-nz`

**Files:**
- Modify: `skills/niwa-coastal-nz/scripts/cli.py`
- Modify: `skills/niwa-coastal-nz/scripts/test_contract.py`
- Modify: `skills/niwa-coastal-nz/scripts/smoke_test.py`
- Modify: `skills/niwa-coastal-nz/SKILL.md`
- Modify: `skills/niwa-coastal-nz/references/source-notes.md`
- Add fixtures under: `skills/niwa-coastal-nz/tests/fixtures/`

**Step 1: Write failing tests**

Cover:

- `search --start` request mapping and normalized `next_start`.
- `item ITEM_ID` metadata normalization and ID/organisation/host rejection.
- `describe SERVICE --layer-id`.
- All shared ArcGIS query controls and mutually exclusive modes.
- `identify SERVICE --point` request construction, layer selection, tolerance, and geometry suppression.
- Both negative-leading `--point` forms, non-finite values, and longitude/latitude ranges.
- MapServer/FeatureServer path and redirect validation.

Run:

`python3 skills/niwa-coastal-nz/scripts/test_contract.py`

Expected: the new tests fail before implementation.

**Step 2: Implement catalogue metadata and pagination**

Preserve the existing NIWA organisation restriction. Normalize useful item metadata without stripping raw identifiers, ownership, licence, timestamps, tags, or service URL.

**Step 3: Implement describe, advanced query, and identify**

Use ArcGIS REST parameters directly. Construct identify requests with explicit WGS84 point geometry, map extent, image display, tolerance, selected layers, and return-geometry setting.

**Step 4: Update docs and live smoke**

Add source-native examples and bounded live calls for paging/item metadata, describe/count, and identify where the live service supports it.

**Step 5: Verify**

Run:

- `python3 skills/niwa-coastal-nz/scripts/test_contract.py`
- `python3 skills/niwa-coastal-nz/scripts/smoke_test.py`
- `python3 -m py_compile skills/niwa-coastal-nz/scripts/*.py`

### Task 3: Expand `searise-nz`

**Files:**
- Modify: `skills/searise-nz/scripts/cli.py`
- Modify: `skills/searise-nz/scripts/test_contract.py`
- Modify: `skills/searise-nz/scripts/smoke_test.py`
- Modify: `skills/searise-nz/SKILL.md`
- Modify: `skills/searise-nz/references/source-notes.md`
- Add fixtures under: `skills/searise-nz/tests/fixtures/`

**Step 1: Write failing tests**

Cover:

- `record` normalized Zenodo metadata and file inventory.
- Single-site `projections` output backward compatibility.
- Multiple site IDs, input-order preservation, duplicates, and missing sites.
- One fetch/parse pass for multiple sites.
- Iterator-based parsing without a materialized all-rows list.
- Existing scenario, confidence, year, and VLM filters in multi-site mode.
- Invalid IDs and structured upstream/malformed-response errors.

Run:

`python3 skills/searise-nz/scripts/test_contract.py`

Expected: the new tests fail before implementation.

**Step 2: Implement `record`**

Fetch the existing Zenodo record API and normalize DOI, version, publication date, title, creators, licence, and files with key, size, checksum, and download URL.

**Step 3: Implement iterator parsing and multi-site projections**

Accept `site_ids` with `nargs="+"`. Stream `csv.DictReader` iteration over the fetched text, selecting all requested IDs in one pass. Preserve the existing top-level response for exactly one requested site. For multiple IDs return ordered per-site results, including explicit empty/not-found results. Define deterministic duplicate handling and test it.

**Step 4: Update docs and live smoke**

Document record metadata, multi-site output, filter interactions, download size, ephemeral behavior, and examples. Keep the routine smoke bounded; the root integration pass performs the full large-file exercises.

**Step 5: Verify**

Run:

- `python3 skills/searise-nz/scripts/test_contract.py`
- `python3 skills/searise-nz/scripts/smoke_test.py`
- `python3 -m py_compile skills/searise-nz/scripts/*.py`

### Task 4: Expand `wcc-arcgis-nz`

**Files:**
- Modify: `skills/wcc-arcgis-nz/scripts/cli.py`
- Modify: `skills/wcc-arcgis-nz/scripts/test_contract.py`
- Modify: `skills/wcc-arcgis-nz/scripts/smoke_test.py`
- Modify: `skills/wcc-arcgis-nz/SKILL.md`
- Modify: `skills/wcc-arcgis-nz/references/source-notes.md`
- Add fixtures under: `skills/wcc-arcgis-nz/tests/fixtures/`

**Step 1: Write failing tests**

Cover:

- `search --start` and `item ITEM_ID`.
- Item host and Wellington organisation/owner validation.
- `describe SERVICE --layer-id`.
- All shared ArcGIS query controls and mutual exclusion.
- `identify SERVICE --point`, including negative-leading values and numeric bounds.
- Service path validation across the existing Wellington City, Greater Wellington, and Wellington Water hosts.
- Structured empty and malformed upstream responses.

Run:

`python3 skills/wcc-arcgis-nz/scripts/test_contract.py`

Expected: the new tests fail before implementation.

**Step 2: Implement pagination and item metadata**

Preserve current Wellington catalogue restrictions and expose normalized ownership, licence, timestamps, tags, access, size, and service URL metadata.

**Step 3: Implement describe, advanced query, and identify**

Map the shared controls to ArcGIS REST. Ensure identify works with multi-layer MapServers and exposes raw result attributes and geometry without deriving hazard conclusions.

**Step 4: Update docs and live smoke**

Add examples for all three allowed service hosts and bounded live metadata/count/identify checks.

**Step 5: Verify**

Run:

- `python3 skills/wcc-arcgis-nz/scripts/test_contract.py`
- `python3 skills/wcc-arcgis-nz/scripts/smoke_test.py`
- `python3 -m py_compile skills/wcc-arcgis-nz/scripts/*.py`

### Task 5: Integrate, adversarially review, and publish

**Files:**
- Regenerate: `README.md`
- Regenerate: `skills.json`
- Review all files changed by Tasks 1–4.

**Step 1: Inspect and normalize the combined diff**

Check file ownership, CLI consistency, output compatibility, source allowlists, help text, and that no subagent committed or changed repository-wide generated files.

**Step 2: Run changed-skill verification**

Run all four contract tests, live smoke tests, and Python compilation.

**Step 3: Run full SeaRise live exercises**

Exercise both projection datasets (with and without VLM), including a multi-site request, and verify the response is source-derived and internally consistent.

**Step 4: Run independent adversarial review**

Assign a fresh read-only subagent to inspect the complete diff and test malformed identifiers, hostile URLs, negative/non-finite/out-of-range coordinates, pagination edges, count/ID mode conflicts, missing events/files/sites, empty results, output compatibility, and bounded live calls. Address every material finding and rerun affected tests.

**Step 5: Regenerate catalogue**

Run:

- `python3 scripts/generate_catalogue.py`
- `python3 scripts/generate_catalogue.py --check`

**Step 6: Run exact repository validation**

Run:

- `python3 -m unittest discover -s tests -p 'test_*.py'`
- `python3 scripts/validate_agent_spec.py --strict`
- `python3 scripts/validate_repo_policy.py --strict`
- `python3 scripts/run_contract_tests.py`
- `python3 scripts/security_check.py`
- `python3 -m compileall -q skills lib scripts tests`
- the repository diff/packaging check required by CI

**Step 7: Commit, push, and verify**

Stage only intended files, inspect the staged diff, commit to the PR branch, push, and wait for all PR checks. Do not merge the PR unless the user explicitly asks.
