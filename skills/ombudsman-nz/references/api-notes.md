# Ombudsman NZ API notes

## Source site

- Public directory: `https://www.ombudsman.parliament.nz`
- Listing endpoint used by the CLI: `https://www.ombudsman.parliament.nz/resources`
- Detail pages use the path pattern: `https://www.ombudsman.parliament.nz/resources/{slug}`
- File assets are exposed under: `https://www.ombudsman.parliament.nz/sites/default/files/...`

## Known discovery controls

The listing page is a Drupal view with query params:

- `f[0]=category:{taxonomy-id}` (e.g. `f%5B0%5D=category%3A1993`)
- `query=<text>` (server-side filtering can be inconsistent, so CLI filters client-side too)
- `page=<n>` for pagination

Category IDs observed during implementation:

- `74` — case notes
- `1993` — OPCAT
- `1989` — official information complaints data
- `2148` — reports

The CLI discovers category IDs from the first resources page at runtime as a fallback.

## Complaint data extraction

Complaint statistics are not exposed through a dedicated API; they are discovered from resource
cards and then parsed from attachment files on matching resource pages.

Files are parsed when extensions match:

- `*.xlsx`
- `*.xls` (treated as XLSX-style worksheet parsing when possible)
- `*.csv`

Field extraction details:

- Resource card parsing (`/resources`):
  - `title`, `slug`, `source_url`, `category`, `published_at`, `snippet`
- Resource detail parsing:
  - `title`, `published_at`, `category` (taxonomy terms), `snippet`, `attachments`
- Complaint attachment parsing:
  - `source_url`, `title`, `format`, inferred `act` (`OIA`/`LGOIMA`), inferred `kind` (`received`/`completed`), inferred `period` (`YYYY-H1|H2`)
- XLSX parsing:
  - reads workbook XML directly (`xl/workbook.xml` and sheet XML)
  - parses shared strings and shared inline strings
  - returns a preview slice per worksheet with normalized headers + row dictionaries

## Source caveats and limitations

- The website may return bot-protection pages (403/429) for non-browser traffic in some environments.
- `query` filtering on `/resources` is not fully reliable, so the CLI always applies a client-side filter.
- Pagination is bounded by `--max-pages`; a larger value gives broader coverage but more HTTP calls.
- Large XLSX sheets are not fully downloaded into objects; results are capped by `--limit` rows per sheet for practical output size.
- If structured files are missing on a resource page, that resource is excluded from complaints table output.

## Freshness and reliability notes

- The CLI performs live discovery every run from `https://www.ombudsman.parliament.nz/resources`; published counts and the set of linked attachments are therefore point-in-time only.
- The Ombudsman site may change card markup and query parameter handling; if discovery starts returning fewer rows, verify with `--json` and reduce required parsing assumptions before adding new heuristics.
- Bot-protection or WAF enforcement can intermittently return HTTP 403/429; in that case the CLI returns `upstream_blocked` and smoke tests skip.

## Usage examples

- List/Filter complaints data:
  - `python3 scripts/cli.py complaints --period 2025-H2 --act OIA --json`
  - `python3 scripts/cli.py complaints --act LGOIMA --limit 5 --json`

- Search case notes:
  - `python3 scripts/cli.py case-notes search --query detention --limit 10 --json`

- List reports / OPCAT pages:
  - `python3 scripts/cli.py reports --category OPCAT --json`

- Fetch publication metadata and attachments:
  - `python3 scripts/cli.py resource /resources/oia-and-lgoima-complaints-received-between-1-january-and-30-june-2024 --json`
