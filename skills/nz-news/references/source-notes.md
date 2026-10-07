# Source notes

- Primary owner: Participating New Zealand news publishers
- Primary source: https://rss.nzherald.co.nz/rss/xml/nzhrsscid_000000001.xml
- Declared outbound hosts: rss.nzherald.co.nz,thespinoff.co.nz,www.interest.co.nz,www.newsroom.co.nz,www.rnz.co.nz,www.stuff.co.nz,www.omnycontent.com,omny.fm,podcastindex.org
- Access mode: html-readonly
- Authentication: none
- Last verified: 2026-10-07

The skill is read-only unless its SKILL.md metadata explicitly declares mutations. Live results must retain source and retrieval-time context. A blocked, unavailable, or changed source is an explicit failure state, never an empty successful dataset.

The 2026-09-12 verification covers the new bounded interview command: Omny
episode metadata works; RNZ robots rules block ChatGPT-User, so declared health
is degraded. Older multi-source headline surfaces were not re-verified by this
probe. The smoke suite uses fixtures for legacy aggregation and narrow live
interview requests; it does not probe all news publishers by default.
See [interview API notes](api-notes.md) for per-source coverage and rights.

The 2026-10-07 verification ran `sources`: all 12 news feeds returned items.
The Spinoff old WordPress feed (`/feed`) now returns HTTP 404 after a site
rebuild. Its homepage has no `rel="alternate"` feed link. The working Atom feed
is `https://thespinoff.co.nz/api/rss` (20 entries; each entry has the full
article HTML in `<content>` and no `<summary>`). The CLI keeps only a short
plain-text excerpt (first paragraph, max 280 chars) as the summary, so output
and search cover the standfirst like other feeds, not the full article.
The `rnz-morning-report` interview selector is still blocked by RNZ robots
rules, so declared health stays degraded.
