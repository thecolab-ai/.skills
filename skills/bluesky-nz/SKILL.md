---
name: bluesky-nz
description: "Search public Bluesky posts and read public account feeds through the no-login Bluesky AppView API, tuned for New Zealand situational awareness: keyword and phrase search with recency sort, author feeds for official NZ accounts, and machine-readable post output. Use when the task involves scanning public social media for emerging NZ events, weather or hazard impacts, community reports, or monitoring a public Bluesky account. Read-only; no authentication required."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "emergency"
  thecolab.source_owner: "Bluesky Social (public AppView)"
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
  thecolab.source_url: "https://api.bsky.app/xrpc/app.bsky.feed.searchPosts"
  thecolab.allowed_domains: "api.bsky.app,bsky.app"
  thecolab.last_verified: "2026-07-22"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# Bluesky NZ

## Goal

Search public Bluesky posts and read public account feeds through the keyless
AppView API — a public social signal channel for detecting emerging NZ events
(weather impacts, outages, community reports) and monitoring official accounts.

## Use this when

- A task needs to scan public social media for emerging NZ incident reports
- A task needs recent public posts from a specific Bluesky account
- A workflow needs machine-readable public post data with engagement counts

## Do not use this for

- Posting, liking, following, DMs, or anything requiring a session
- Private/protected content (only public posts are visible)
- Treating crowd posts as verified fact — corroborate against official sources

## Commands

```bash
python3 skills/bluesky-nz/scripts/cli.py search "wellington south coast waves" --limit 20 --json
python3 skills/bluesky-nz/scripts/cli.py search "state of emergency" --since 2026-07-21 --lang en
python3 skills/bluesky-nz/scripts/cli.py feed wremo.bsky.social --limit 10
python3 skills/bluesky-nz/scripts/cli.py profile some-account.bsky.social
```

- `search QUERY [--sort latest|top] [--since ISO] [--lang CODE] [--limit N] [--json]` — public post search
- `feed HANDLE [--limit N] [--json]` — recent public posts from one account (replies excluded)
- `profile HANDLE [--json]` — public profile summary

## Notes

- **Craft NZ-specific queries.** Generic terms collide with overseas places —
  "wellington weather" surfaces Wellington, Ohio. Add NZ anchors: suburb names,
  "NZ", "Aotearoa", agency names.
- **Verify handles before trusting an account.** Handles are self-registered:
  `metservice.bsky.social` is a band, not the weather service. Run `profile`
  and check the description/domain handle (a `*.govt.nz`-style handle is
  domain-verified) before treating an account as official.
- Crowd posts are unverified by definition; the JSON output carries this warning.
- Timestamps are UTC as published. Post URLs link to the public web app.

## Resources

- CLI entrypoint: `scripts/cli.py`
- Contract test: `scripts/test_contract.py`; smoke test: `scripts/smoke_test.py`
- Endpoint behaviour and rate-limit notes: `references/source-notes.md`
