---
name: akahu-personal
description: Query personal transactional bank-account data — account lists, balances, settled/pending transactions, payment history, parties, refreshes, webhooks, and arbitrary authenticated API endpoints — from Akahu, a New Zealand open-banking provider. Use when the task involves personal bank data exports, NZ account balances, transaction analysis, cashflow/spending categorisation, or calling a specific authenticated banking-data endpoint. Requires user-provided AKAHU_APP_TOKEN and AKAHU_USER_TOKEN; never smoke-test against real personal data in CI.
---

# Akahu Personal App

## Goal

Fetch a user's own Akahu Personal App data through a small deterministic CLI, without committing tokens or financial exports.

## Use this when

- The user has created an Akahu Personal App and supplied tokens out-of-band
- A task needs Akahu `/me`, account balances, account metadata, or recent transactions
- A workflow needs a local JSON/CSV export of personal NZ banking data for analysis

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
python3 skills/akahu-personal/scripts/cli.py endpoint /payments --param start=2026-01-01 --param end=2026-02-01 --json
python3 skills/akahu-personal/scripts/cli.py export --out-dir /private/akahu-export
```

Commands:

- `me [--json]` - call `/v1/me`
- `accounts [--json] [--raw-account-numbers]` - list accounts and balances
- `transactions [--limit N] [--start ISO] [--end ISO] [--json] [--raw-account-numbers]` - recent settled transactions
- `endpoint PATH [--method METHOD] [--param key=value] [--data-json JSON] [--data-file FILE]` - call any Akahu API path with Personal App auth; non-GET methods require `--i-understand-this-can-mutate`
- `export --out-dir DIR [--limit N] [--raw-account-numbers]` - write private JSON exports with `0600` file permissions

## Resources

- CLI: `scripts/cli.py`
- Smoke test: `scripts/smoke_test.py` (intentional skip)
- API notes: `references/api-notes.md`
