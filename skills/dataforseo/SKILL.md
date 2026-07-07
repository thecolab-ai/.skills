---
name: dataforseo
description: Query DataForSEO for SEO + market-validation data — Google SERP rank checks, keyword search volume, keyword discovery (semantic ideas, related-search expansion, search-intent classification), domain/competitor analytics, backlinks, and App Store / Play data (which apps rank + review mining). Use when checking where a site ranks, finding or discovering what people search for, validating demand and competition for an app/business idea, analysing a domain or its competitors, auditing backlinks, or mining competitor app reviews for pain points. Requires DATAFORSEO_USERNAME (or DATAFORSEO_LOGIN) and DATAFORSEO_PASSWORD. Every call spends DataForSEO credits.
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
2. Export them in `~/.zshenv` (not `.zshrc`, not a repo `.env`): `.zshenv` is
   read by every zsh — interactive and not — so the skill and the DataForSEO
   MCP subprocess both inherit them, and the secret never lands in a git repo.
   ```bash
   export DATAFORSEO_USERNAME="your_api_login"   # the email login
   export DATAFORSEO_PASSWORD="your_api_password" # plaintext — NOT the base64 token
   ```
   Then `chmod 600 ~/.zshenv` and open a fresh shell (or `source ~/.zshenv`).
3. **Use the plaintext password**, not the pre-encoded "token" the dashboard
   shows — the CLI does its own base64 encoding, so a token gives auth failures.

The CLI accepts `DATAFORSEO_USERNAME` (the DataForSEO MCP's variable name) or
`DATAFORSEO_LOGIN` for the login, so one pair of env vars powers both. It does
not read the credentials until a command actually calls the API, so `--help`
works without them.

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

## Discovery commands (counter confirmation bias)

These surface demand you did **not** seed — the antidote to "I searched my own
idea and found some volume, so it's validated." Run these before deciding what a
market wants.

### `ideas <seed...>`

Semantically *related* keywords that need not contain the seed (category match,
not text match). The workhorse for finding demand you'd never have typed. Review
the output — semantic matching also surfaces adjacent meanings (a "grow a garden"
seed can pull in a Roblox game).

```bash
python3 skills/dataforseo/scripts/cli.py ideas "companion planting" --location us --limit 25
```

### `related <seed>`

Google's "searches related to" expansion, walked to `--depth` (0-4; default 2 —
higher is wider and pricier). Lateral exploration of a topic.

```bash
python3 skills/dataforseo/scripts/cli.py related "raised garden bed" --location us --depth 2
```

### `intent <keyword...>`

Classifies each keyword as informational / navigational / commercial /
transactional (with confidence). Tells "wants a free answer" from "wants to buy"
— use it to separate real commercial demand from idle curiosity. (No location.)

```bash
python3 skills/dataforseo/scripts/cli.py intent "buy raised garden bed" "how to build raised bed" --language en
```

## App Store / Play commands (async)

⚠️ **DataForSEO does NOT provide in-store search volume** (App Store / Play ASO
keyword demand) — nobody does; Apple/Google don't publish it. For apps you get
**which apps rank, their ratings/review counts, and review text**, so you *infer*
demand and read competition + pain points directly. Web search `volume` stays
your quantified demand signal.

These are async (submit + poll), so they take a few seconds and print after
polling — unlike the instant `live` commands. Raise `--timeout` if one is slow.

### `appsearch <keyword> [--store apple|google]`

Which apps rank in the store for a query, with ratings and review counts (your
incumbent-strength read). Default store `apple`.

```bash
python3 skills/dataforseo/scripts/cli.py appsearch "plant identifier" --store apple --location us
```

### `appreviews <app_id> [--store apple|google] [--worst]`

Mine an app's reviews for pain points (`app_id` comes from `appsearch`). `--worst`
floats the lowest-rated reviews to the top — the store-agnostic way to find what
users hate about the incumbent, in their own words. This is the highest-signal,
lowest-bias input for spotting a gap. Pull a larger `--limit` to reach more
critical reviews (Apple has no "most critical" API sort).

```bash
python3 skills/dataforseo/scripts/cli.py appreviews 1252497129 --store apple --worst --limit 30
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
