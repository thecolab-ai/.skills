---
name: newworld-nz
description: "Query New World NZ stores, product categories, product search results, specials, and store-specific grocery prices using guest APIs, plus a user's own previous orders, purchases, shopping lists, and cart when they explicitly provide Club+ credentials. Manage the user's shopping lists or cart when they explicitly request a specific change."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "food-and-fuel"
  thecolab.source_owner: "Foodstuffs New Zealand"
  thecolab.source_type: "commercial"
  thecolab.auth: "mixed"
  thecolab.access_mode: "authenticated-personal"
  thecolab.data_class: "personal"
  thecolab.writes: "true"
  thecolab.browser: "false"
  thecolab.risk: "high"
  thecolab.cache_ttl: "30m"
  thecolab.schema_version: "1"
  thecolab.skill_type: "authenticated-personal"
  thecolab.pack: "nz-personal-data"
  thecolab.source_url: "https://www.newworld.co.nz"
  thecolab.allowed_domains: "api-prod.clubplus.co.nz,api-prod.newworld.co.nz,login.clubplus.co.nz,www.newworld.co.nz"
  thecolab.last_verified: "2026-07-24"
  thecolab.health: "gated"
  thecolab.maintainer: "@adam91holt"
  thecolab.mutations: "authenticated-api-put,authenticated-api-post,authenticated-api-delete"
---

# New World NZ

## Goal

Query live New World NZ store and grocery product data, optionally retrieve the authenticated user's own account history, and perform explicit shopping-list or cart changes through a small deterministic CLI.

## Use this when

- A user asks for New World NZ product prices or specials
- A user wants to search New World products by keyword
- A user needs store IDs, store lookup, or category browsing
- A user has New World product IDs and wants store-specific price/details
- A workflow needs machine-readable New World product data
- A user explicitly wants their own previous New World orders or purchases
- A user explicitly wants to retrieve their own saved New World shopping lists
- A user explicitly asks to create, rename, delete, or change products in one of their own shopping lists
- A user explicitly asks to inspect their cart or add, update, or remove one of its products

## Do not use this for

- PAK'nSAVE, Four Square, Woolworths, or non-New-World retailers
- Historical pricing or price-change claims unless another dataset provides history
- Checkout, ordering, payment, timeslot, fulfilment, or account/profile changes
- List or cart mutation that the user has not explicitly requested
- Reading another person's account or using credentials not supplied by the account holder

## Preferred workflow

1. Run `scripts/cli.py` with the narrowest subcommand that answers the task
2. Use `stores` first when the requested location is not the default store
3. Use `search` for keyword price/product lookup and `specials` for promotional products
4. Use `product` when exact product IDs are known
5. Use authenticated commands only after the user has supplied their own credentials through environment variables
6. Run list or cart mutation commands only when the user has explicitly requested that exact change
7. Preserve the `--yes` guard on list deletion and list/cart product removal; never infer confirmation from unrelated work
8. Use `--json` for agent chaining, comparisons, or structured reports
9. Treat authenticated JSON as personal data and mention that the integration is unofficial

## Authentication and privacy

Public catalogue commands need no account. Personal commands require the user's own Club+ credentials:

```bash
export NEWWORLD_USERNAME='member@example.nz'
export NEWWORLD_PASSWORD='...'
newworld auth login
```

- The CLI registers and displays account, order, list, and cart commands only when both `NEWWORLD_USERNAME` (or `NEWWORLD_EMAIL`) and `NEWWORLD_PASSWORD` are present in its environment.
- Without that credential pair, `--help` and command parsing expose only the guest catalogue commands.
- The password is read only from the environment and is never written to disk.
- Rotating access and refresh tokens are cached at `~/.cache/newworld-cli/auth.json` with file mode `0600`.
- Override the cache location with `NEWWORLD_AUTH_FILE`.
- If Club+ requires MFA, set `NEWWORLD_MFA_CODE` to the six-digit code and run `auth mfa`.
- `auth status` never prints token values. `auth logout` removes only the local token cache; it does not mutate the New World account.
- `NEWWORLD_ACCESS_TOKEN` and `NEWWORLD_REFRESH_TOKEN` may be used as runtime overrides.
- Orders, list names, item history, addresses, and raw JSON are personal data. Do not paste them into shared logs, issues, or pull requests.

## CLI

Run with:

```bash
python3 skills/newworld-nz/scripts/cli.py <command> [flags]
```

Default store is New World Papakura: `ef977d89-f3d8-4e8b-8a48-b895ded38646`.
Override with `--store-id <id>` or `NEWWORLD_STORE_ID`.

### Commands

The first six guest commands are always available. The remaining account commands appear only when the Club+ username/email and password environment variables are set.

- `stores [--query text] [--limit N] [--json]` — list or filter New World stores
- `categories [--store-id id] [--depth N] [--json]` — browse a store category tree
- `search <query> [--store-id id] [--limit N] [--page N] [--promo] [--json]` — product search with prices
- `specials [query] [--store-id id] [--limit N] [--page N] [--json]` — promotional products
- `product <product-id...> [--store-id id] [--json]` — decorate exact product IDs with details
- `token [--refresh] [--json]` — fetch/cache a short-lived guest token without emitting its value
- `auth login [--json]` — log in with environment-provided Club+ credentials
- `auth mfa [--json]` — finish an MFA login using `NEWWORLD_MFA_CODE`
- `auth refresh [--json]` — rotate the cached New World access token
- `auth status [--json]` — report token availability without revealing tokens
- `auth logout [--json]` — remove only the local authenticated-token cache
- `store-select [--store-id id] [--json]` — select the store used for authenticated list and cart writes
- `orders [--page N] [--limit N] [--source ALL|ONLINE|IN_STORE] [--json]` — retrieve previous orders
- `order <order-id> [--source ONLINE|IN_STORE]` — retrieve one previous order
- `previous-purchases [--limit N] [--include-cart] [--json]` — retrieve previously purchased products
- `lists [--json]` — retrieve saved shopping lists
- `list <list-id>` — retrieve one saved shopping list
- `list-create <name> [--json]` — create an empty shopping list
- `list-rename <list-id> <name> [--json]` — rename a shopping list
- `list-delete <list-id> --yes [--json]` — permanently delete a shopping list
- `list-add <list-id> <product-id> [--quantity N] [--sale-type UNITS|WEIGHT] [--json]` — add a product
- `list-update <list-id> <product-id> --quantity N [--sale-type UNITS|WEIGHT] [--json]` — change quantity
- `list-remove <list-id> <product-id> --yes [--sale-type UNITS|WEIGHT] [--json]` — remove a product
- `cart [--json]` — retrieve the current cart
- `cart-add <product-id> [--quantity N] [--sale-type UNITS|WEIGHT] [--json]` — increment a cart product quantity
- `cart-update <product-id> --quantity N [--sale-type UNITS|WEIGHT] [--json]` — set a cart product quantity
- `cart-remove <product-id> --yes [--sale-type UNITS|WEIGHT] [--json]` — remove a cart product

Examples:

```bash
python3 skills/newworld-nz/scripts/cli.py stores --query auckland --limit 5
python3 skills/newworld-nz/scripts/cli.py search milk --limit 10
python3 skills/newworld-nz/scripts/cli.py specials cheese --limit 10 --json
python3 skills/newworld-nz/scripts/cli.py product 5201479 --json
newworld auth status
newworld store-select
newworld orders --limit 20 --json
newworld lists --json
newworld list-create "Weekly shop"
newworld list-add <list-id> 5201479 --quantity 2
newworld cart
newworld cart-add 5201479 --quantity 2
```

## Resources

- CLI entrypoint: `scripts/cli.py`
- Live smoke test: `scripts/smoke_test.py`
- API and stability notes: `references/api-notes.md`

## Notes

- Public commands use the guest-token flow and cache tokens under `~/.cache/newworld-cli/guest-token.json`
- Personal commands mirror the Club+ login, secure-code exchange, and rotating New World refresh flow used by the website
- If a fresh authenticated session has no store, the CLI selects `NEWWORLD_STORE_ID` (or the Papakura default) once and retries the request; `store-select` can change it explicitly
- Store changes can be rejected when current cart products are unavailable at the target store; the CLI reports the service reason without clearing the cart
- List writes use the same endpoints as the website and are intentionally exposed only as explicit subcommands
- `list-delete` and `list-remove` require `--yes`; they cannot be invoked accidentally through a zero quantity
- Cart writes use target quantities internally: `cart-add` reads and increments, while `cart-update` sets the target directly
- `cart-remove` requires `--yes`; use grams for `WEIGHT` quantities and units for `UNITS`
- Email verification must be completed in the normal New World login page before CLI login
- Endpoint shapes can change; retry with a fresh token before assuming data is unavailable
- `--json` output is intended for exact matching and private agent workflows
