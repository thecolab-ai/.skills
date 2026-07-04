# Stats NZ DataInfo+ API notes

Source: `https://datainfoplus.stats.govt.nz`
Checked: 2026-07-03

## Public surface used by this skill

- Search pages:
  - `https://datainfoplus.stats.govt.nz/search/{scope}?Query=<term>&IncludeDeprecated=false`
  - `scope` values tested by this skill: `codelists`, `concepts`, `qualitystandards`, `concept-sets`.
- Item metadata JSON:
  - `https://datainfoplus.stats.govt.nz/item/{agency}/{identifier}/json`
- Version history:
  - `https://datainfoplus.stats.govt.nz/item/{agency}/{identifier}/_history`
- Item detail URLs used for user-facing references:
  - `https://datainfoplus.stats.govt.nz/item/{agency}/{identifier}`

## Field conventions observed

- IDs are usually UUID-like values paired with agency identifiers in the `/item/{agency}/{id}` path.
- Many item payloads are locale maps (`{"en-NZ": "text"}`); extraction prefers `en-NZ` with graceful fallback.
- Classifications commonly expose `Codes` with nested `Category` references and optional `ChildCodes` for hierarchy.
- Version history is HTML with a tabular `<table>` layout; rows are parsed from `<tr>` / `<td>` entries.

## Caveats and freshness

- The search interface is server-rendered HTML and can vary by scope.
- Some query terms return no rows on `qualitystandards`; empty results are handled as `not_found`/`unsupported` at command level.
- Concordance/crosswalk discovery is implemented via public search discovery and explicit heuristics.
  - If no reliable concordance mapping is found for a `from`/`to` pair, the command returns `unsupported` instead of guessing.
- Bot/protection handling is conservative: network/HTTP failures and 403-like blocks are returned in JSON as outage/blocked statuses.

## Example queries

- `/search/codelists?Query=region&IncludeDeprecated=false`
- `/item/nz.govt.stats/ca9760fe-c843-40b4-98c9-11d2f4ea597e/json`
- `/item/nz.govt.stats/ca9760fe-c843-40b4-98c9-11d2f4ea597e/_history`

## Caching and rate behavior

No caching in this skill. Use a small `--limit`, category resolution caps, and short timeouts for safe repeated use.
