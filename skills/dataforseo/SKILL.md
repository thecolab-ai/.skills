---
name: dataforseo
description: Query DataForSEO for SEO data — Google SERP rank checks, keyword search volume and suggestions, domain/competitor analytics, and backlinks. Use when the task involves checking where a site ranks for a keyword, finding keyword ideas and search volumes, analysing what a domain ranks for or who its competitors are, or auditing backlinks. Requires DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD. Every call spends DataForSEO credits.
---

# DataForSEO

## Goal

Query DataForSEO's v3 **live** (synchronous) endpoints through a CLI that is easy
for agents to script and easy for humans to scan — SERP rank checks, keyword
research, domain/competitor analytics, and backlinks.

## Use this when

- Checking where a site ranks for a keyword (`serp <keyword> --domain <site>`)
- Listing the top Google organic results for a query
- Finding search volume, CPC, and competition for keywords (`volume`)
- Getting long-tail keyword ideas from a seed term (`suggestions`)
- Seeing what keywords a domain already ranks for (`ranked`)
- Finding a domain's organic competitors (`competitors`)
- Getting a domain's organic/paid rank overview (`domain`)
- Auditing a domain's backlinks and referring domains (`backlinks`, `refdomains`)

## Do not use this for

- Idle exploration — **every command spends DataForSEO credits.** Run the
  narrowest command that answers the question, and use `--limit` to cap rows.
- Site audits / on-page crawling — not wrapped in v1 (uses async task endpoints).
- Bulk async jobs — this skill only calls synchronous `live` endpoints.
- Anything outside SEO data (no writes, no account/billing management).

## Setup

Requires DataForSEO **API credentials** (your API login + password from the
dashboard — these are *not* your website login/password).

1. Get them at https://app.dataforseo.com/api-access
2. Export them in your shell profile (`~/.zshrc`):
   ```bash
   export DATAFORSEO_LOGIN="your_api_login"
   export DATAFORSEO_PASSWORD="your_api_password"
   ```
3. Reload: `source ~/.zshrc`. The CLI reads these from the environment; it does
   not check them until a command actually calls the API, so `--help` works
   without them.

## Preferred workflow

1. Run `scripts/cli.py` with the narrowest subcommand that answers the task.
2. Default location is New Zealand (`nz`). For keyword *volume*, a larger market
   (`--location us`) is usually more meaningful than tiny NZ numbers.
3. Use default human output for direct answers; `--json` when piping to another
   tool or agent.
4. Keep `--limit` low to control cost, especially on `ranked` and `refdomains`.

## CLI

Run with:

```bash
python3 skills/dataforseo/scripts/cli.py <command> [flags]
```

Common flags: `--location` (alias like `nz`/`us`/`uk`/`au` or a numeric
`location_code`), `--language` (default `en`), `--limit`, `--json`.

### `serp <keyword> [--domain <site>]`

Top Google organic results for a keyword. With `--domain`, reports that site's
rank position instead of listing results.

```bash
python3 skills/dataforseo/scripts/cli.py serp "vegetable garden planner"
python3 skills/dataforseo/scripts/cli.py serp "garden planner app" --domain grovekeeper.app
python3 skills/dataforseo/scripts/cli.py serp "garden planner" --location us --limit 20
```

### `volume <keyword...>`

Search volume, CPC, and competition for one or more keywords (Google Ads data).

```bash
python3 skills/dataforseo/scripts/cli.py volume "garden planner" "vegetable planner" --location us
```

### `suggestions <seed>`

Long-tail keyword ideas containing the seed term, with volumes.

```bash
python3 skills/dataforseo/scripts/cli.py suggestions "companion planting" --location us --limit 25
```

### `ranked <domain>`

Keywords a domain already ranks for.

```bash
python3 skills/dataforseo/scripts/cli.py ranked grovekeeper.app --location us --limit 25
```

### `competitors <domain>`

Domains competing for the same keywords.

```bash
python3 skills/dataforseo/scripts/cli.py competitors grovekeeper.app --location us
```

### `domain <domain>`

Organic/paid rank overview: keyword count, estimated traffic, position buckets.

```bash
python3 skills/dataforseo/scripts/cli.py domain grovekeeper.app --location us
```

### `backlinks <domain>`

Backlink summary: total backlinks, referring domains, domain rank. (No location.)

```bash
python3 skills/dataforseo/scripts/cli.py backlinks grovekeeper.app
```

### `refdomains <domain>`

Referring domains, ranked by domain rank. (No location.)

```bash
python3 skills/dataforseo/scripts/cli.py refdomains grovekeeper.app --limit 25
```

## Notes

- Location aliases: `nz us uk/gb au ca ie za in`. For anything else, pass a
  numeric `location_code` (see the DataForSEO locations endpoints).
- Errors surface DataForSEO's `status_message` and exit non-zero rather than
  dumping raw JSON. HTTP 401/403 means the credentials are wrong (or you used
  your website login instead of the API login).
- See `references/endpoints.md` for the endpoint each command hits and
  approximate per-call cost.

## Testing

```bash
python3 skills/dataforseo/scripts/smoke_test.py
```

Offline checks (`--help`, arg validation, missing-credential handling) always
run. Live API checks run only when `DATAFORSEO_LOGIN`/`DATAFORSEO_PASSWORD` are
set, and each one spends a small amount of credit.
