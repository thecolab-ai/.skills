# Source notes — WREMO news

- Primary owner: Wellington Region Emergency Management Office
- Primary source: https://www.wremo.nz/news-and-events/wremo-news
- Declared outbound hosts: www.wremo.nz
- Access mode: html-readonly
- Authentication: none
- Last verified: 2026-07-22

## Why HTML

wremo.nz is a custom CMS with no RSS/Atom feed or JSON API (checked `/feed/`,
common feed paths, and page source on 2026-07-22). The news listing is the only
structured surface. WREMO's real-time channels are Emergency Mobile Alerts (via
`nz-emergency-alerts`) and social media; this skill covers the durable editorial
channel used for severe-weather updates, campaigns, and recovery information.

## Markup assumptions (verified 2026-07-22)

Listing page `/news-and-events/wremo-news` renders one
`div.card.card-article` per item containing:

- `h2.card-title > a` — href `/news-and-events/wremo-news/<slug>` + title
- `div.card-text` — snippet (may contain `<br/>` and inline tags)
- `div.article-date` — NZ-style date, e.g. `6 Sept 2024` (note `Sept`)

Article pages have a generic `News` H1; the real title comes from `<title>`
(suffix after `|`/`»` stripped). Body paragraphs are plain `<p>` elements mixed
with site chrome; the parser drops fragments under 40 characters and any
paragraph containing known chrome markers (`Toggle child menu`,
`Toggle site navigation`, `Visit our Facebook page`,
`WREMO > News and Events`). Zero parsed cards on the listing page is a schema
failure (exit 6), never an empty success.

## Stability and reuse

- Bare `curl` works; no bot wall observed. Volume is one page per command.
- Crown/CDEM public information; retain source URLs and attribution, summarise
  rather than republish whole articles.
- If WREMO redesigns the site, fixtures pin today's markup so the failure is a
  clear parser error; re-derive the selectors from a fresh listing page.
