---
name: nz-ministers
description: "Query New Zealand government ministers, their portfolios, and their press releases from beehive.govt.nz. Use when the task involves NZ ministers, who holds a portfolio (health, finance, energy, etc.), a minister's bio, or all the releases/speeches by a given minister, plus the latest government announcements. The latest-releases feed is keyless; per-minister data uses an optional --browser (CloakBrowser) bootstrap to clear bot protection, then cached cookies for plain HTTP. Read-only; no login or account."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "government"
  thecolab.source_owner: "New Zealand Government"
  thecolab.source_type: "official"
  thecolab.auth: "none"
  thecolab.access_mode: "public-api"
  thecolab.data_class: "public"
  thecolab.writes: "false"
  thecolab.browser: "true"
  thecolab.risk: "medium"
  thecolab.cache_ttl: "24h"
  thecolab.schema_version: "1"
  thecolab.skill_type: "public-api"
  thecolab.pack: "nz-public-data"
  thecolab.source_url: "https://www.beehive.govt.nz"
  thecolab.allowed_domains: "www.beehive.govt.nz"
  thecolab.last_verified: "2026-07-19"
  thecolab.health: "gated"
  thecolab.maintainer: "@adam91holt"
---

# NZ Ministers

Query NZ government ministers, the portfolios they hold, and the press releases /
speeches attributed to them, from **beehive.govt.nz** (the official NZ Government
website). Read-only; no login, account, or API key.

## Use this when

- A user asks **who is the Minister of <X>**, or what portfolios a minister holds
- A user wants a **minister's profile** (roles, biography, latest diary, recent articles)
- A user wants a minister's **roles & responsibilities** (portfolios + position)
- A user wants **all articles by a minister** (releases, speeches, features)
- A user wants a minister's **diary / calendar** (latest published ministerial diary)
- A user wants the **latest government announcements** site-wide

## Do not use this for

- Drafting, editing, or sending anything (read-only)
- General NZ news — use the `nz-news` skill
- Parliamentary bills/Hansard, MP voting records, or electorate data
- Defeating CAPTCHAs or bot walls — challenges are treated as blocked states

## Commands

```bash
cli=skills/nz-ministers/scripts/cli.py

# Latest government releases/speeches — KEYLESS, no browser needed
python3 $cli latest --limit 10
python3 $cli latest --type speech --json

# A minister's full profile: roles, biography, latest diary, recent articles
python3 $cli minister hon-simeon-brown --browser --json
python3 $cli minister "Simeon Brown" --browser

# Roles & responsibilities (portfolios + position)
python3 $cli roles hon-simeon-brown --browser --json

# Latest published ministerial diary (calendar) + archive link
python3 $cli diary hon-simeon-brown --browser --json

# All releases/speeches by a minister
python3 $cli articles hon-simeon-brown --limit 20 --browser --json
```

### Arguments

- `latest` — `--limit N`, `--type {release,speech,feature}`, `--json`
- `minister <slug|name>` — `--browser`, `--json`
- `roles <slug|name>` — `--browser`, `--json`
- `diary <slug|name>` — `--browser`, `--json`
- `articles <slug|name>` — `--limit N`, `--type {release,speech,feature}`, `--browser`, `--json`

A minister is identified by slug (`hon-simeon-brown`, `rt-hon-christopher-luxon`,
`hon-dr-shane-reti`) or plain name (`"Simeon Brown"`, `"Shane Reti"`); the CLI tries the
`hon-` / `rt-hon-` / `hon-dr-` honorific forms.

## Bot protection & `--browser`

Only the latest-releases RSS feed is openly accessible. Minister pages are behind
**Incapsula** bot protection, so `minister`, `roles`, `diary`, and `articles` need a
browser to clear the challenge **once**:

- Pass `--browser` to launch [CloakBrowser](https://github.com/CloakHQ/CloakBrowser),
  clear the wall, and cache the clearance cookies (~5-minute TTL in a temp file).
- After that, those commands work over **plain HTTP from the cache** — no browser —
  until the cookies expire.
- Without clearance, those commands return a machine-readable blocked state
  (`clearance_required`, or `cloakbrowser_not_installed` if CloakBrowser is missing);
  `latest` always works regardless.

The **full ministerial-diary archive** is rendered by a JavaScript search on beehive;
`diary` returns the latest diary (title, date, PDF) directly plus the `archive_url`
for the complete history.

## Resources

- CLI entrypoint: `scripts/cli.py`
- Smoke test: `scripts/smoke_test.py`
- Source, bot-protection, parsing, and blocked-state details: `references/api-notes.md`

## Notes

- Data are live snapshots from beehive.govt.nz; releases reflect current site content.
- Use NZ English in any summaries you build from the output (organisation, colour).
- `--json` on every command gives machine-readable output for agent chaining.
