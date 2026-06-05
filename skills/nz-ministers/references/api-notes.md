# nz-ministers — API & source notes

All data comes from **beehive.govt.nz**, the official NZ Government website (Drupal).
Read-only; no login, account, or API key.

## Sources

| Data | URL | Access |
|------|-----|--------|
| Latest releases/speeches (site-wide) | `https://www.beehive.govt.nz/rss.xml` | **Keyless.** Allowlisted by Incapsula; returns the latest ~30 items as RSS 2.0. |
| Minister profile + their articles | `https://www.beehive.govt.nz/minister/<slug>` | Behind Incapsula bot protection — needs browser clearance (see below). |
| Article / release page | `https://www.beehive.govt.nz/release/<slug>` etc. | Behind Incapsula. |

`<slug>` for a minister is `hon-firstname-lastname`, e.g. `hon-simeon-brown`. The CLI
accepts either the slug or a plain name (`"Simeon Brown"`) and tries sensible
candidates (`simeon-brown`, `hon-simeon-brown`).

## Bot protection & the `--browser` clearance bootstrap

Every beehive page **except `rss.xml`** is gated by **Imperva/Incapsula**, which serves
a JavaScript challenge to bare HTTP clients (curl, urllib) and to the Drupal JSON:API
and per-minister feed endpoints. Better headers, a warmed `visid_incap` cookie, and
realistic UA strings do **not** pass it — the challenge requires executing JS to mint
the `incap_ses_*` / `reese84` clearance cookies.

So `minister` and `articles` use this hybrid:

1. **Bootstrap (once):** `--browser` launches [CloakBrowser](https://github.com/CloakHQ/CloakBrowser),
   loads the homepage, lets the Incapsula challenge resolve, and reads back the
   `User-Agent` + clearance cookies.
2. **Cache:** the UA + cookies are written to `<tempdir>/nz-ministers-incap.json`
   with a 10-minute TTL.
3. **Reuse (no browser):** subsequent `minister`/`articles` calls — even without
   `--browser` — fetch the protected pages with **plain stdlib HTTP** using the
   cached cookies. The browser is only re-launched when the cache is missing/stale.

This means after a single `--browser` call, the skill works as a fast keyless-style
HTTP client until the cookies expire.

### Blocked / fallback states

- No cache and no `--browser` → exits 2 with `{"error": "clearance_required", ...}`.
- Cache stale mid-flight and no `--browser` → `{"error": "clearance_expired", ...}`.
- CloakBrowser not installed → `{"error": "cloakbrowser_not_installed", ...}`.
- CloakBrowser can't clear the wall → `{"error": "browser_blocked", ...}`.

In every blocked case `latest` still works with no browser. CAPTCHA / bot challenges
are treated as blocked states, never bypass targets.

## HTML parsing

Minister pages list each article as `<article class="teaser ...">` containing:

- `<em class="meta meta__content-type">Release</em>` — content type
- `<div class="meta meta__date"><time datetime="…">5 June 2026</time></div>` — date
- `<div class="field field--name-node-title">…<a href="/release/…">Title</a>` — title + URL

Portfolios are `<a href="/portfolio/<government>/<area>">Area</a>` links (deduped by area).

Parsing is regex-based over deterministic Drupal class names; if beehive restructures
these blocks the parsers may need updating.

## CI / smoke tests

`latest` is exercised on every run (keyless). When CloakBrowser is available
(`HERMES_SMOKE_WITH_CLOAKBROWSER=1`) or `HERMES_SMOKE_USE_BROWSER=1` is set, the smoke
test clears the wall with `--browser` and asserts real minister/article data; otherwise
it asserts the clean `clearance_required` blocked state. Network errors and bot
challenges are treated as SKIP.
