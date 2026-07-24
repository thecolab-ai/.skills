---
name: trademe-nz
description: "Search public Trade Me NZ listings and help a normal signed-in user view and manage their own seller account through the ordinary Trade Me website. Use for public marketplace/property/motors/jobs discovery, Selling/Sold/Unsold inventory, seller listing details, and user-approved create/edit/withdraw/relist workflows. Seller work is browser-backed: use the user's existing website session or let them complete sign-in and email/2FA in the browser. Never request a password, developer/OAuth credentials, cookies, browser storage, or session tokens."
license: MIT
compatibility: "Requires Python 3.10+ and network access; seller workflows require the supported Codex browser control surface and a user-completed Trade Me website sign-in"
metadata:
  thecolab.category: "public-data"
  thecolab.source_owner: "Trade Me"
  thecolab.source_type: "commercial"
  thecolab.auth: "mixed"
  thecolab.access_mode: "public-api-and-browser-authenticated-personal"
  thecolab.data_class: "personal"
  thecolab.writes: "true"
  thecolab.browser: "true"
  thecolab.risk: "high"
  thecolab.cache_ttl: "none"
  thecolab.schema_version: "1"
  thecolab.skill_type: "authenticated-personal"
  thecolab.pack: "nz-personal-data"
  thecolab.source_url: "https://www.trademe.co.nz"
  thecolab.allowed_domains: "api.trademe.co.nz,www.trademe.co.nz"
  thecolab.last_verified: "2026-07-24"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
  thecolab.mutations: "create-own-listing,edit-own-listing,withdraw-own-listing,relist-own-listing"
  thecolab.local_output: "optional-user-supplied-listing-json"
---

# Trade Me NZ

## Goal

Use the Python CLI for public search and deterministic seller-task planning.
Perform seller reads and actions through the ordinary Trade Me website in a
supported browser. Do not call member APIs or handle authentication material.

## Public workflow

1. Run `scripts/cli.py search` with the narrowest `--type`.
2. Apply region, price, bedroom, and category filters.
3. Run `listing ID` for public detail.
4. Use `--json` for structured output.

## Seller workflow

Read `references/browser-workflow.md` completely before seller work.

1. Run the relevant seller command with `--json` to validate the target and get
   the starting website URL.
2. Use the Browser skill and the browser selected for the Trade Me URL.
3. Reuse the normal website session without inspecting cookies, storage,
   request headers, tokens, profiles, or passwords.
4. If Trade Me shows sign-in, email confirmation, CAPTCHA, or 2FA, keep the same
   browser open and let the user complete the step. Resume only when they say it
   is ready.
5. Read Selling, Sold, Unsold, and listing details from visible page state.
6. For a seller action, fill only the user-requested values and continue to
   Trade Me's review or confirmation screen.
7. Stop before the final submit. Report the exact listing, changes, disposition,
   and any fee shown. Obtain a separate action-time confirmation.
8. After confirmation, re-check the page and click the exact final control once.
9. Verify the visible success state and re-read the affected seller page.

Never ask the user to paste a password, email code, OTP, cookie, token, or
browser-storage value into chat or the CLI. Never copy or persist browser
authentication data. Never bid, buy, pay, or manage another member's listings.

## CLI

Run:

```bash
python3 skills/trademe-nz/scripts/cli.py <command> [flags]
```

Public commands:

- `search [query] --type TYPE [filters] [--json]`
- `listing ID [--raw] [--json]`
- `regions [--json]`
- `categories [--query TEXT] [--depth N] [--limit N] [--json]`

Browser-backed seller task commands:

- `seller-summary [--json]`
- `my-selling [--json]`
- `my-sold [--json]`
- `my-unsold [--json]`
- `seller-listing ID [--json]`
- `prepare-edit ID [--json]`
- `validate-listing --data-file FILE [--json]`
- `create-listing --data-file FILE [--json]`
- `edit-listing --data-file FILE [--json]`
- `withdraw-listing ID [--sold --sale-price NZD] [--reason TEXT] [--json]`
- `relist-listing ID [--json]`

Seller commands do not drive a browser by themselves and do not imply approval
to submit a change. They produce a deterministic browser task for the agent to
complete under this skill's authentication and confirmation rules.

Examples:

```bash
python3 skills/trademe-nz/scripts/cli.py search iphone --limit 5
python3 skills/trademe-nz/scripts/cli.py my-selling --json
python3 skills/trademe-nz/scripts/cli.py my-sold --json
python3 skills/trademe-nz/scripts/cli.py seller-listing 1234567890 --json
python3 skills/trademe-nz/scripts/cli.py edit-listing --data-file /private/listing.json --json
```

## Resources

- CLI: `scripts/cli.py`
- Smoke test: `scripts/smoke_test.py`
- Browser authentication, page-reading, and action workflow:
  `references/browser-workflow.md`
- Public endpoint notes: `references/api-notes.md`
- Source declaration: `references/source-notes.md`

## Notes

- Public commands require no credentials.
- Seller work uses only visible, ordinary website UI in the selected browser.
- The browser owns its session; the skill never exports or persists it.
- Website labels and layout can change. Take a fresh DOM snapshot before
  constructing a locator, and use only locators grounded in that snapshot.
- Treat all inventory as a live snapshot.
