---
name: woolworths-nz
description: "Query Woolworths NZ product search, specials, category browse, and SKU details, plus a user's own past orders, favourites, saved lists, and trolley when they explicitly provide account credentials. Manage the user's saved lists or trolley only when they explicitly request a specific change."
license: MIT
compatibility: "Requires Python 3.10+ and network access; first account login additionally requires the optional Camoufox browser package"
metadata:
  thecolab.category: "food-and-fuel"
  thecolab.source_owner: "Woolworths New Zealand"
  thecolab.source_type: "commercial"
  thecolab.auth: "mixed"
  thecolab.access_mode: "authenticated-personal"
  thecolab.data_class: "personal"
  thecolab.writes: "true"
  thecolab.browser: "true"
  thecolab.risk: "high"
  thecolab.cache_ttl: "30m"
  thecolab.schema_version: "1"
  thecolab.skill_type: "authenticated-personal"
  thecolab.pack: "nz-personal-data"
  thecolab.source_url: "https://www.woolworths.co.nz"
  thecolab.allowed_domains: "auth.woolworths.co.nz,iam.woolworths.co.nz,www.woolworths.co.nz"
  thecolab.last_verified: "2026-07-24"
  thecolab.health: "gated"
  thecolab.maintainer: "@adam91holt"
  thecolab.mutations: "authenticated-api-post,authenticated-api-delete"
---

# Woolworths NZ

## Goal

Query live Woolworths NZ product data, optionally retrieve the authenticated user's own account history, and perform explicit saved-list or trolley changes through one CLI.

## Use this when

- A user asks for Woolworths NZ product prices, specials, keyword search, or SKU details
- A user explicitly wants their own past Woolworths orders, favourites, or saved lists
- A user wants their own Woolworths tax-invoice PDF enriched with the matching past-order SKUs
- A user explicitly asks to create/delete a saved list or add, update, or remove a list product
- A user explicitly asks to inspect their trolley or add, update, remove, or clear its products

## Do not use this for

- Woolworths Australia or another retailer
- Checkout, ordering, payment, delivery-slot, fulfilment, account, or Everyday Rewards changes
- List or trolley mutation the user has not explicitly requested
- Reading another person's account or using credentials not supplied by the account holder
- Redistributing Woolworths product or account data as a dataset
- Historical pricing claims unless another source provides history

## Preferred workflow

1. Run `scripts/cli.py` with the narrowest command that answers the task
2. Use public `search`, `specials`, `browse`, and `product` commands without credentials
3. Use account commands only after the user supplies their own credentials as environment variables
4. Run saved-list or trolley mutations only for the exact change the user requested
5. Preserve every `--yes` deletion/removal guard
6. Use `--json` only for private structured workflows; treat account JSON as personal data
7. For invoice enrichment, use the local tax-invoice PDF and its matching order ID; inspect unmatched or ambiguous joins before relying on them
8. Never use this skill to place an order or perform checkout/payment actions

## Authentication and privacy

Public product commands need no account. Personal commands require:

```bash
export WOOLWORTHS_USERNAME='member@example.nz'
export WOOLWORTHS_PASSWORD='...'
woolworths auth login
```

- `WOOLWORTHS_EMAIL` is accepted as an alias for `WOOLWORTHS_USERNAME`.
- The CLI registers and displays account commands only when both a username/email and `WOOLWORTHS_PASSWORD` exist in its environment.
- The password is passed only to Woolworths' browser login and is never written to disk.
- Woolworths' login page uses a browser challenge. Install the optional helper with `python3 -m pip install camoufox`, then run `python3 -m camoufox fetch` once.
- A reusable cookie cache is written to `~/.local/state/woolworths-nz/cookies.json` with file mode `0600`.
- Override the cache location with `WOOLWORTHS_SESSION_FILE`.
- If a hidden browser login cannot complete a challenge, retry `auth login --headed`.
- `auth status` never emits cookies or account details. `auth logout` removes only the local cookie cache; it does not sign out other devices or mutate the account.
- Orders, list names, favourites, item history, addresses, and raw account JSON are personal data. Do not paste them into shared logs, issues, or pull requests.
- Tax invoices and enriched invoice output are personal financial/order data. Never add a user's PDF or parsed rows to fixtures or source control.

## CLI

Run with:

```bash
python3 skills/woolworths-nz/scripts/cli.py <command> [flags]
```

Public commands are always available:

- `search <query> [--limit N] [--page N] [--size text] [--in-stock-only] [--json]`
- `specials [query] [--limit N] [--page N] [--in-stock-only] [--json]`
- `browse <category-id> [--limit N] [--page N] [--in-stock-only] [--json]`
- `product <sku...> [--json]`

The following appear only when the credential environment variables are set:

- `auth login [--headed]`
- `auth status [--json]`
- `auth logout`
- `orders [--page N] [--date-filter value] [--json]`
- `order <order-id> [--json]`
- `order-items <order-id|all> [--page N] [--limit N] [--sort value] [--json]`
- `invoice-items <order-id> <invoice.pdf> [--min-confidence 0..1] [--json]`
- `favourites [--page N] [--limit N] [--sort value] [--in-stock-only] [--json]`
- `lists [--json]`
- `list <list-id> [--page N] [--limit N] [--sort value] [--json]`
- `list-create <name> [--source empty|trolley|favourites|list|order|all-orders] [--source-id id] [--json]`
- `list-delete <list-id> --yes [--json]`
- `list-add <list-id> <sku> [--quantity N] [--json]`
- `list-update <list-id> <sku> --quantity N [--json]`
- `list-remove <list-id> <sku> --yes [--json]`
- `cart [--json]`
- `cart-add <sku> [--quantity N] [--unit Each|Kg] [--json]`
- `cart-update <sku> --quantity N [--unit Each|Kg] [--json]`
- `cart-remove <sku> --yes [--unit Each|Kg] [--json]`
- `cart-clear --yes [--json]`

Examples:

```bash
python3 skills/woolworths-nz/scripts/cli.py search milk --limit 10
python3 skills/woolworths-nz/scripts/cli.py product 705692 --json
woolworths auth login
woolworths orders --json
woolworths invoice-items <order-id> ~/Downloads/invoice.pdf --json
woolworths lists
woolworths list-create "Weekly shop"
woolworths list-add <list-id> 705692 --quantity 2
woolworths cart-add 705692 --quantity 2
```

## Resources

- CLI entrypoint: `scripts/cli.py`
- Browser login helper: `scripts/browser_auth.py`
- Invoice parser and SKU matcher: `scripts/invoice_parser.py`
- Live and deterministic smoke tests: `scripts/smoke_test.py`
- API and stability notes: `references/api-notes.md`

## Notes

- Public commands remain stdlib-only and do not launch a browser.
- Account reads/writes use the saved Woolworths session directly; a 401/403 triggers one browser refresh and retry.
- `invoice-items` parses supplied/paid invoice rows from a text-based Woolworths tax-invoice PDF, fetches the matching past-order product list, and performs a one-to-one confidence-scored name join to SKUs.
- Invoice parsing has one additional optional dependency: `python3 -m pip install pdfplumber`. It is imported only by `invoice-items`; public product commands remain standard-library-only.
- A match below `--min-confidence` is left unmatched. Close runner-up candidates are marked ambiguous rather than silently accepted.
- Saved-list item writes use Woolworths' current `{itemsToAdd: [{sku, quantity}]}` request.
- Trolley writes use target quantities. `cart-add` reads then increments; `cart-update` sets the target.
- `Each` quantities must be whole numbers. Use `--unit Kg` for explicit weights.
- List deletion, list item removal, trolley item removal, and trolley clearing require `--yes`.
- Endpoint shapes can change; retry with a fresh session before assuming account data is unavailable.
- This is an unofficial integration and deliberately excludes checkout/order placement.
