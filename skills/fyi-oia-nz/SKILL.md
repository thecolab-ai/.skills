---
name: fyi-oia-nz
description: "Query FYI.org.nz OIA/LGOIMA public authorities and request records through a read-only Alaveteli API surface, including request metadata, authority lookups, request timelines, and request search."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "government"
  thecolab.source_owner: "FYI and mySociety"
  thecolab.source_type: "community"
  thecolab.auth: "none"
  thecolab.access_mode: "public-api"
  thecolab.data_class: "public"
  thecolab.writes: "false"
  thecolab.browser: "false"
  thecolab.risk: "low"
  thecolab.cache_ttl: "24h"
  thecolab.schema_version: "1"
  thecolab.skill_type: "public-api"
  thecolab.pack: "nz-public-data"
  thecolab.source_url: "https://fyi.org.nz"
  thecolab.allowed_domains: "fyi.org.nz"
  thecolab.last_verified: "2026-07-19"
  thecolab.health: "gated"
  thecolab.maintainer: "@adam91holt"
---

# FYI.org.nz OIA/LGOIMA

## Scope

This skill wraps FYI.org.nz public authority/request read endpoints and the published all-authorities CSV. It is designed for public-corpus research and reproducible citations around OIA/LGOIMA requests.

## Use this when

- You need NZ public authority discovery from FYI’s authority list
- You need authority detail for a specific FYI body URL slug
- You need request metadata for an ID or `request/<id>-<slug>`
- You need request event timelines (calculated_state/state transitions)
- You need simple request-text search across FYI pages as a discovery aid

## Do not use this for

- Request drafting or posting
- Requester personal data extraction
- Bulk crawling of the search surface

## Commands

- `authorities [--tag <tag>] [--query <text>] [--limit N] [--json]`
  - List public authorities from `/body/all-authorities.csv`, with optional tag/text filtering.

- `categories [--limit N] [--json]`
  - List body tags/categories discovered in `all-authorities.csv`.

- `body <url_name_or_url> [--json]`
  - Fetch authority metadata from `/body/<url_name>.json`.

- `search <query> [--limit N] [--json]`
  - Search FYI request pages for matching titles; uses `/search/*` endpoints where available and falls back to parsed request result HTML.

- `request <id_or_slug> [--full] [--json]`
  - Fetch request metadata from `/request/<id>.json`.
  - Metadata-only mode strips requester-identifying fields.
  - `--full` includes the full timeline with event/type fields and message IDs.

- `events <id_or_slug> [--json]`
  - Fetch and flatten request event timeline only.

## Read-only contract

- No logins, tokens, keys, browser automation, or write operations.
- Defaults are metadata-first and remove requester personal text/name fields from command output.
- Uses only HTTPS GETs with conservative timeouts.

## Resources

- `scripts/cli.py`
- `scripts/smoke_test.py`
- `references/api-notes.md`
