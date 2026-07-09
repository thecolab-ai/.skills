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
   (file mode `0600`) with a 5-minute TTL.
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

All parsing is regex-based over deterministic Drupal view/field class names. If
beehive restructures these blocks the parsers may need updating.

**Articles** (`articles`, and `recent_articles` in `minister`) — each is an
`<article class="teaser ...">` block containing:

- `<em class="meta meta__content-type">Release</em>` — content type
- `<div class="meta meta__date"><time datetime="…">5 June 2026</time></div>` — date
- `<div class="field field--name-node-title">…<a href="/release/…">Title</a>` — title + URL

**Roles & responsibilities** (`roles`, and `roles` in `minister`) — the
`view-appointments` block, one row per portfolio:

```html
<span class="views-field views-field-field-portfolio"><a href="/portfolio/<gov>/<area>">Health</a></span>
 - <span class="views-field views-field-field-position">Minister</span>
<span class="views-field views-field-field-archived"><span class="field-content"></span></span>
```

Rows with a non-empty `field-archived` are treated as past roles and excluded.

**Biography** — a `<a href="/minister/biography/<name>">` link → `biography_url`.

**Diary / calendar** (`diary`, and `latest_diary` in `minister`) — the
`view-ministerial-diaries` block holds the latest published diary: `views-field-title`
(e.g. *Hon Simeon Brown - March 2026*), a `<time datetime>` issue date, and a `.pdf`
attachment URL. The full diary archive is a JavaScript-rendered Solr search
(`/search?f[0]=content_type_facet:ministerial_diary&f[1]=ministers:<id>…`); its result
list is **not** in the static HTML, so the CLI returns the latest diary plus
`archive_url` rather than scraping the JS list. The numeric minister id in that URL is
read from the minister page (`ministers:<id>`).

**Slugs** — ministers carry honorifics: most are `hon-<first>-<last>`; the Prime
Minister and some senior ministers are `rt-hon-<first>-<last>`; ministers styled "Dr"
include a `dr-` element (e.g. `hon-dr-shane-reti`). From a plain name the CLI strips any
supplied honorific and tries the bare slug plus the `hon-`, `rt-hon-`, `hon-dr-`,
`rt-hon-dr-`, and `dr-` forms.

## CI / smoke tests

`latest` is exercised on every run (keyless). When CloakBrowser is available
(`COLAB_SMOKE_WITH_CLOAKBROWSER=1`) or `COLAB_SMOKE_USE_BROWSER=1` is set, the smoke
test clears the wall with `--browser` and asserts real minister/article data; otherwise
it asserts the clean `clearance_required` blocked state. Network errors and bot
challenges are treated as SKIP.
