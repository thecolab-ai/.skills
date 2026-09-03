---
name: heritage-list-nz
description: "Search and inspect the official New Zealand Heritage List/Rārangi Kōrero CSV export by list number, name, address, council, entry type, and status. Use for heritage research, planning context, or an initial property due-diligence check. Keyless and read-only; not legal advice, a title search, a council plan check, or an archaeological authority check."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "property"
  thecolab.source_owner: "Heritage New Zealand Pouhere Taonga"
  thecolab.source_type: "official"
  thecolab.auth: "none"
  thecolab.access_mode: "public-download"
  thecolab.data_class: "public"
  thecolab.writes: "false"
  thecolab.browser: "false"
  thecolab.risk: "low"
  thecolab.cache_ttl: "none"
  thecolab.schema_version: "1"
  thecolab.skill_type: "public-download"
  thecolab.pack: "nz-public-data"
  thecolab.source_url: "https://www.heritage.org.nz/list-details"
  thecolab.allowed_domains: "www.heritage.org.nz,hnzpt-prod-web.azurewebsites.net"
  thecolab.last_verified: "2026-09-03"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# Heritage List NZ

Read the official New Zealand Heritage List/Rārangi Kōrero export without authentication or browser automation.

## Use it for

- Finding entries by name, address, list number, district council, List type, or status.
- Looking up the current CSV fields for one exact List number.
- Initial heritage research or property/planning due diligence before checking primary records.

Do not use a negative result as proof that no heritage or archaeological obligations apply.

## Commands

Run from the repository root:

```bash
python3 skills/heritage-list-nz/scripts/cli.py search "railway station" --json
python3 skills/heritage-list-nz/scripts/cli.py search --council "Auckland" --type "Category 1" --limit 10 --json
python3 skills/heritage-list-nz/scripts/cli.py get 9997 --json
python3 skills/heritage-list-nz/scripts/cli.py status --json
```

### `search [QUERY]`

Case-insensitive substring search across name, address, List number, council, type, and status.

Options:

- `--council TEXT` — district-council filter.
- `--type TEXT` — List-entry-type filter.
- `--status TEXT` — List-entry-status filter.
- `--limit N` — return 1–100 matches; default 20.
- `--json` — machine-readable output.

The query is optional so filters can be used alone. Search results deliberately omit the source's legal-description and long-form extent fields.

### `get LIST_NUMBER`

Exact lookup by the export's `ListNumber`. The result includes dates and NZAA identifiers but deliberately omits legal-description and long-form extent text. Follow the landing-page link and contact the relevant authority for primary-detail review.

### `status`

Fetch the export once and report its current schema, row count, content type, final URL, and retrieval time. The request timeout is 10 seconds and the response safety cap is 10 MB.

## Output and failure contract

Every successful command exposes the official source URL and UTC `retrieved_at`. JSON failures use the repository exit-code contract:

- `2` invalid input or exact List number not found
- `4` source blocked or rate-limited
- `5` upstream/network failure
- `6` CSV content or schema failure

## Caveats

- This is discovery evidence, not legal advice or a title, LIM, or district-plan search.
- Listing does not establish ownership, access rights, or every applicable protection.
- Archaeological-site obligations may apply whether or not a place appears in the export.
- Confirm current details with Heritage New Zealand Pouhere Taonga, the relevant council, and property/title records.
- Respect the source website's terms; do not republish the full export or protected long-form content.

Read `references/source-notes.md` for endpoint/schema provenance and `references/terms-and-safety.md` before reuse or due-diligence conclusions. Implementation and verification live in `scripts/`; the deterministic synthetic CSV lives in `tests/fixtures/`.
