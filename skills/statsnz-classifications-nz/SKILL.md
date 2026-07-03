---
name: statsnz-classifications-nz
description: Query Stats NZ DataInfo+ / Aria classifications, concepts, concordances, and quality standards with lookup IDs, code lists, version history, and category metadata.
---

# Stats NZ DataInfo+ / Aria

## Goal

Read-only access to Stats NZ DataInfo+ / Aria metadata for NZ statistical classifications and their lineage.

This skill lives in `scripts/cli.py` and documents upstream behavior in `references/api-notes.md`.

## Use this when

- You need definitions, labels, and stable IDs for classifications, concept variables, and related metadata.
- You need to inspect code lists or resolve category labels used by official NZ classifications.
- You need concordance or version metadata where the source exposes it.
- You need a machine-readable source link for reproducible metadata workflows.

## Do not use this for

- Time series data or non-DataInfo+ statistics values.
- High-volume mirroring or full catalog scraping.
- Any source with explicit rate limits or restrictions.

## Commands

- `search TERM [--scope {all,codelists,concepts,qualitystandards,concept-sets}] [--limit N] [--json]` - search DataInfo+ items
- `classification get ID [--agency AGENCY] [--code-limit N] [--code-depth D] [--category-limit N] [--json]` - inspect one item, returning metadata and code/category references when present
- `classification versions ID [--agency AGENCY] [--json]` - fetch public version history
- `classification categories ID [--agency AGENCY] [--limit N] [--json]` - resolve category metadata referenced by a classification
- `concordance FROM TO [--query-queries Q1,Q2] [--limit N] [--json]` - return concept-set/registry entries that match a concordance/crosswalk pair when available
- `standards [QUERY] [--limit N] [--json]` - list currently discoverable quality standards metadata records

## Sources

- Search pages: `https://datainfoplus.stats.govt.nz/search/{scope}`
- Item JSON: `https://datainfoplus.stats.govt.nz/item/{agency}/{identifier}/json`
- Version history: `https://datainfoplus.stats.govt.nz/item/{agency}/{identifier}/_history`

## Notes

- Stdlib-only, read-only HTTP calls.
- Upstream outages and blocked responses are returned as `upstream_unavailable`/`upstream_blocked` status payloads in JSON mode.
- Never fabricate metadata: payloads are returned only from public upstream pages.
- `--json` is supported on all data commands.
