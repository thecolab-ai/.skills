# SafeTravel NZ source notes

## Official source surfaces

| Surface | URL | Use in this skill |
|---|---|---|
| SafeTravel landing page | https://www.safetravel.govt.nz/ | Canonical MFAT/SafeTravel source landing page. |
| Official sitemap | https://www.safetravel.govt.nz/sitemap.xml | Read-only destination catalogue and allowlist. |
| Advice-level explainer | https://www.safetravel.govt.nz/destinations/about-our-travel-advice | Official definitions of the four travel-advice levels. |
| Destination page | `https://www.safetravel.govt.nz/destinations/<slug>` | Current country-level advice, regional cautions, page update date, and related news. |

Owner: Ministry of Foreign Affairs and Trade (MFAT). Authentication: none. Declared outbound host: `www.safetravel.govt.nz`. Last verified: 2026-09-03.

## Source observations and parser contract

The official sitemap is XML and currently exposes destination pages under `/destinations/<slug>`. The CLI accepts only those canonical pages after first resolving their slug in the sitemap; it does not follow arbitrary user-provided URLs.

A destination page currently exposes its advice entries in the `data-content` attribute of
`#js-advice-level-accordion`. The attribute must contain a standards-compliant JSON list:
non-standard constants, non-finite numbers, and unsupported nesting fail as source-schema
errors. Advice text/date fields retain their published JSON string types rather than being
coerced from booleans, numbers, objects, or nulls. Each item must carry an explicit JSON
boolean `regional` classification; missing, string, numeric, or null classifications are
rejected rather than coerced. The parser extracts a country-wide entry as `advice_level` and
entries with `regional: true` as `regional_cautions`.

Destination parsing also requires complete outer `html`/`head`/`body` structure and closed
parser-relevant elements. Materially truncated or unclosed markup fails closed instead of
yielding partial advice.

The visible page includes a `Page updated <date>` label. Related news cards link to `/news/...` pages and can display `Updated <date>`. Their text is returned only as a short source-page summary; this skill does not fetch or interpret the linked news article itself. Footer registration material is deliberately excluded from related-news output.

## Advice levels

SafeTravel's official explainer defines four levels:

1. Exercise normal safety and security precautions.
2. Exercise increased caution.
3. Avoid non-essential travel.
4. Do not travel.

The source's textual level and its stated `level N of 4` are both retained. Do not turn these labels into a booking, insurance, evacuation, medical, legal, or individual safety recommendation.

## Freshness, failure states, and caveats

- Each request uses a 10-second timeout and returns a retrieval timestamp in UTC.
- `page_updated` is absent when the official page does not display the expected label; a missing label is not fabricated.
- An unavailable upstream source returns exit code 5; a block or rate limit returns exit code 4; malformed source XML/HTML/JSON returns exit code 6.
- Source markup is an implementation detail and can change. Deterministic synthetic fixtures cover the sitemap and destination-page parser separately from live smoke checks.
- Advice can change. Users should consult the returned official SafeTravel page before travel and follow local emergency or government instructions.

## Deliberately excluded workflows

The public site promotes travel registration and login. This skill does not expose, automate, link into, or collect data for registration, login, contact details, profiles, bookings, emergency assistance, or any other mutation/personal-data workflow.
