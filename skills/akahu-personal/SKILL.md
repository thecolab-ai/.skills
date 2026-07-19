---
name: akahu-personal
description: "Query personal transactional bank-account data — account lists, balances, settled/pending transactions, account-specific transaction history, and private JSON/CSV exports — from Akahu, a New Zealand open-banking provider. Use when the task involves personal bank data exports, NZ account balances, transaction analysis, cashflow/spending categorisation, or inspecting authenticated Personal App banking data. Requires user-provided AKAHU_APP_TOKEN and AKAHU_USER_TOKEN; never smoke-test against real personal data in CI."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "finance"
  thecolab.source_owner: "Akahu"
  thecolab.source_type: "official"
  thecolab.auth: "personal-token"
  thecolab.access_mode: "authenticated-personal"
  thecolab.data_class: "personal"
  thecolab.writes: "true"
  thecolab.browser: "false"
  thecolab.risk: "high"
  thecolab.cache_ttl: "none"
  thecolab.schema_version: "1"
  thecolab.skill_type: "authenticated-personal"
  thecolab.pack: "nz-personal-data"
  thecolab.source_url: "https://api.akahu.io/v1"
  thecolab.allowed_domains: "api.akahu.io"
  thecolab.last_verified: "2026-07-19"
  thecolab.health: "gated"
  thecolab.maintainer: "@adam91holt"
  thecolab.mutations: "authenticated-api-post,authenticated-api-put,authenticated-api-patch,authenticated-api-delete,local-private-export"
  thecolab.local_output: "private-json-csv-export"
---

# Akahu Personal App

## Goal

Fetch a user's own Akahu Personal App data through a small deterministic CLI, without committing tokens or financial exports.

## Use this when

- The user has created an Akahu Personal App and supplied tokens out-of-band
- A task needs Akahu `/me`, account balances, account metadata, or recent transactions
- A workflow needs settled or pending transaction samples for analysis
- A workflow needs a local JSON/CSV export of personal NZ banking data

## Privacy and safety

- Requires both `AKAHU_APP_TOKEN` and `AKAHU_USER_TOKEN` in the environment.
- Treat output as personal financial data. Save only to private paths and do not paste raw exports into issues, PRs, logs, or shared chats.
- Account numbers are redacted by default. Pass `--raw-account-numbers` only in a private environment.
- CI smoke tests intentionally skip live API calls because this skill requires personal credentials and personal banking data.

## CLI

```bash
export AKAHU_APP_TOKEN='app_token_...'
export AKAHU_USER_TOKEN='user_token_...'

python3 skills/akahu-personal/scripts/cli.py me --json
python3 skills/akahu-personal/scripts/cli.py accounts --json
python3 skills/akahu-personal/scripts/cli.py transactions --limit 20 --json
python3 skills/akahu-personal/scripts/cli.py endpoint /accounts/<account_id>/transactions/pending --json
python3 skills/akahu-personal/scripts/cli.py export --out-dir /private/akahu-export
```

Commands:

- `me [--json]` - call `/v1/me`
- `accounts [--json] [--raw-account-numbers]` - list accounts and balances
- `transactions [--limit N] [--start ISO] [--end ISO] [--json] [--raw-account-numbers]` - recent settled transactions
- `endpoint PATH [--method METHOD] [--param key=value] [--data-json JSON] [--data-file FILE]` - advanced escape hatch for documented Akahu paths if the Personal App token has permission; non-GET methods require `--i-understand-this-can-mutate`
- `export --out-dir DIR [--limit N] [--raw-account-numbers]` - write private JSON exports with `0600` file permissions

## Resources

- CLI: `scripts/cli.py`
- Smoke test: `scripts/smoke_test.py` (intentional skip)
- API notes: `references/api-notes.md`
