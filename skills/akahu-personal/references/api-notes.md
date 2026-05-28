# Akahu Personal App API Notes

Source docs: https://developers.akahu.nz/docs/personal-apps

## Authentication

Akahu Personal Apps use two tokens supplied as request headers:

```text
Authorization: Bearer <User Access Token>
X-Akahu-Id: <App ID Token>
```

This skill reads those from environment variables by default:

```text
AKAHU_USER_TOKEN
AKAHU_APP_TOKEN
```

Do not commit tokens, screenshots containing tokens, API responses, CSV exports, or smoke-test fixtures generated from a real account.

## Base URL and endpoints

Default base URL:

```text
https://api.akahu.io/v1
```

Implemented endpoints:

- `GET /me` - identity/access-grant metadata for the authorised user
- `GET /accounts` - account names, masked/formatted account identifiers, status, type, attributes, balances, refresh timestamps
- `GET /transactions` - recent transactions; supports date range and limit query parameters in the CLI
- `endpoint PATH` - escape hatch for the full Akahu Personal App API surface, including account-specific transactions, pending transactions, parties, payments, webhooks, refresh, categories, connections, and other documented paths

The named commands cover common read-only analysis. Use `endpoint` when Akahu adds new endpoints or the task needs a path not represented by a first-class subcommand.

## Data boundaries

This is authenticated personal banking data, not public-data scraping. The first-class commands are read-only. The generic `endpoint` command supports non-GET methods only with the explicit `--i-understand-this-can-mutate` flag because those endpoints may refresh data, initiate payments, cancel payments, revoke access, update webhooks, or otherwise change Akahu/user state.

The smoke test must remain an explicit `[SKIP]` in CI. If local verification is needed, run the CLI manually with private environment variables and save outputs under a private directory such as `~/.hermes/tmp/akahu/`.

## Redaction

The CLI redacts account-like strings by default, preserving only the final segment/digits where practical. Use `--raw-account-numbers` only when the output remains local and private.
