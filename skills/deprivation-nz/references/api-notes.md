# NZDep2023 feature service notes

## Source

- Dataset: New Zealand Index of Deprivation 2023 (NZDep2023)
- Publisher: University of Auckland / Stats NZ
- ArcGIS item: `d0caefba5f8f42d6918fc52faacec00b`
  - <https://www.arcgis.com/home/item.html?id=d0caefba5f8f42d6918fc52faacec00b>
- Access: public, no login, no API key
- Verified live: 31 May 2026 via curl + Python stdlib `json`

## Feature service

Base:

```
https://services6.arcgis.com/ZVM1rEuVZjtC1Wwk/arcgis/rest/services/New_Zealand_Index_of_Deprivation_2023_WFL1/FeatureServer
```

Two layers (standard ArcGIS REST FeatureServer query API):

| Layer | Path | Geometry | Rows | Content |
|-------|------|----------|------|---------|
| 0 | `/0/query` | esriGeometryPolygon | 32,746 SA1 areas | per-area decile + raw score + population |
| 1 | `/1/query` | esriGeometryPolygon | SA2 areas | area-averaged decile/score + parent SA3 |

`maxRecordCount` = 2000 on both layers.

## Query parameters used

The CLI always sends `f=json` and `returnGeometry=false` (keeps payloads small and stdlib-parseable). It additionally uses:

- `where=` - attribute filter, e.g. `SA12023_code='7000000'`, `NZDep2023=10`, or a `UPPER(name) LIKE UPPER('%text%')` clause
- `outFields=` - comma list of attribute fields to return
- `resultRecordCount=` - caps returned rows (mapped from `--limit`)
- `orderByFields=` - stable ordering for list commands
- `returnCountOnly=true` - used by `stats` to count without pulling rows

## Layer 0 (SA1) fields

| Field | Type | Notes |
|-------|------|-------|
| `SA12023_code` | string | 7-digit SA1 code, e.g. `7000000` |
| `NZDep2023` | double | decile 1 (least deprived) to 10 (most deprived) |
| `NZDep2023_Score` | double | raw deprivation score, roughly 1000-1357 |
| `URPopnSA1_2023` | double | usually resident population (2023) |
| `SA22023_name` | string | parent SA2 name, e.g. `North Cape` |

Sample: SA1 `7000000` = decile 10, score 1357, population 222, SA2 `North Cape`.

## Layer 1 (SA2) fields

| Field | Type | Notes |
|-------|------|-------|
| `SA22023_code` | string | 6-digit SA2 code, e.g. `127100` |
| `SA22023_name` | string | e.g. `Northcote Central (Auckland)` |
| `SA2_average_NZDep2023` | double | area-averaged decile 1-10 |
| `SA2_average_NZDep2023_score` | double | area-averaged raw score |
| `SA32023_code` | string | parent SA3 code |
| `SA32023_name` | string | parent SA3 region name, e.g. `Northcote (Auckland)` |

Sample: SA2 `127100` `Northcote Central (Auckland)` = avg decile 7, score 1021, SA3 `Northcote (Auckland)` (`51040`).

## Safety / conventions

- Read-only: no writes, no edits, no auth tokens.
- Name inputs for `LIKE` queries are validated against a safe character allowlist before being interpolated, to avoid SQL injection into the `where` clause.
- Errors returned by ArcGIS in a `{ "error": {...} }` body are surfaced via `die()` with a non-zero exit.
- NZDep is an area-level relative index; it is not an individual or household measure.
