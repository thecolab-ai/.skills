---
name: nz-libraries
description: Query selected New Zealand public library catalogues, branch locations, hours, book details, and public availability through a lightweight read-only CLI. Use when the task involves finding books in major NZ public library networks or checking which branches currently show copies.
---

# NZ Libraries

## Goal

Query live public catalogue and branch data for major New Zealand public library networks through a small deterministic CLI with human-readable and JSON output, without browser automation, login, holds, or account actions.

Catalogue search is the primary feature. Branch locations and hours are wired where the public site exposes a stable no-login page.

## Use this when

- A user asks whether a book is held by Auckland, Wellington, Christchurch, Hamilton, Dunedin, or Tauranga public libraries
- A user wants public branch-level availability where the catalogue exposes it
- A user wants branch names, addresses, opening hours, contact details, or facilities for supported branch-hour pages
- A workflow needs machine-readable public catalogue results from NZ library networks
- A user needs a fast read-only alternative to manually opening several library catalogues

## Do not use this for

- Holds, reservations, renewals, checkouts, fines, borrower records, saved lists, login, or account actions
- Authenticated catalogue views or patron-specific availability
- High-volume harvesting, dataset redistribution, or bypassing rate limits
- Libraries outside the supported networks unless the CLI has been extended and verified

## Preferred workflow

1. Run `scripts/cli.py networks` to confirm the currently wired networks and limitations
2. Use `search <query> --network <key>` for the narrowest catalogue lookup
3. Use `book <id>` with an id returned by `search` for public bib/detail fields
4. Use `availability <id>` for branch/copy information where the backend exposes it
5. Use `branches`, `branch`, or `hours` for branch pages where public hours are wired
6. Use `--json` for agent chaining, comparisons, alerts, or structured reports

## CLI

Run with:

```bash
python3 skills/nz-libraries/scripts/cli.py <command> [flags]
```

## Commands

- `networks [--json]` - list supported networks, backends, and branch-hours support
- `branches [--network auckland|wellington|christchurch|hamilton|dunedin|tauranga] [--json]` - list wired branch locations and hours
- `branch <name> [--network key] [--json]` - show one branch by fuzzy name
- `search <query> [--network key] [--limit N] [--json]` - search one or all supported catalogues
- `book <id> [--network key] [--json]` - fetch public book/bib detail
- `availability <book-id> [--network key] [--json]` - show public availability/copy information
- `hours [--network key] [--json]` - list opening hours for wired branch-hour networks

## Examples

```bash
python3 skills/nz-libraries/scripts/cli.py networks
python3 skills/nz-libraries/scripts/cli.py search "Eleanor Catton" --network auckland --limit 5 --json
python3 skills/nz-libraries/scripts/cli.py search "Pip Adam" --network christchurch --limit 5
python3 skills/nz-libraries/scripts/cli.py branches --network wellington --json
python3 skills/nz-libraries/scripts/cli.py hours --network christchurch --json
python3 skills/nz-libraries/scripts/cli.py availability auckland:3b4b3224-44e2-5e5d-a627-823679741a24 --json
```

## Resources

- CLI entrypoint: `scripts/cli.py`
- API and stability notes: `references/api-notes.md`

## Notes

- Supported networks: Auckland Libraries (`aucklandlibraries.govt.nz`, `discover.aucklandlibraries.govt.nz`), Wellington City Libraries (`wcl.govt.nz`, `catalogue.wcl.govt.nz`), Christchurch City Libraries (`christchurchcitylibraries.com`, `christchurch.bibliocommons.com`), Hamilton City Libraries (`hamiltonlibraries.co.nz`, `ent.kotui.org.nz/client/en_AU/hamilton`), Dunedin Public Libraries (`dunedinlibraries.govt.nz`, `ent.kotui.org.nz/client/en_AU/dunedin`), and Tauranga City Libraries (`library.tauranga.govt.nz`, `ent.kotui.org.nz/client/en_AU/tauranga`)
- Auckland catalogue search, detail, and physical branch availability use public Vega endpoints; Auckland branch hours come from the public locations-and-services page
- Wellington catalogue search and availability use public Spydus HTML/XHLD pages; Wellington branch hours come from public WCL branch pages
- Christchurch catalogue search and detail use BiblioCommons server-rendered JSON; Christchurch branch hours come from the public BiblioCommons locations fragment
- Hamilton, Dunedin, and Tauranga catalogue search use public Kotui/SirsiDynix Enterprise search pages; branch-hours pages are not wired in this lightweight version
- No API key, username, password, account cookie, browser session, or write action is required
- Endpoint shapes can change without notice because these are unofficial public website surfaces
