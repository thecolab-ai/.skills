# NZ grant portal API recon

Issue #112 asked for public machine-readable data discovery across NZ grant-discovery portals, without login, paywall/CAPTCHA bypass, or application submission.

## Findings

| Source | Classification | Notes |
|---|---|---|
| Public Trust grants (`publictrust.co.nz/grants`) | Public machine-readable, no auth | Nuxt page publishes an Algolia search-only configuration (`algoliaAppId`, browser API key, grants index, alphabetical replica). Algolia records include title, URI, excerpt, type, region/sector facets, `applications_open_now`, and open-date fields. Public grant detail pages are HTML and can be fetched without login. This skill uses this source. |
| givUS / Generosity NZ | Council/library-sponsored or subscription access; no public grant data found | Public marketing page is Squarespace-style HTML. It points users to libraries/councils and sign-up/access flows. No grant-record JSON/search index was found in public page HTML. |
| Fundsorter | Commercial/subscription; no public grant data found | Home/pricing pages are marketing/pricing content with login/sign-up links. No public grant-record JSON/search endpoint found. |
| GEM Local marketing (`gemlocal.co.nz`) | Commercial/product marketing; no public grant data found | WordPress/Strategic Grants marketing site with pricing/login content. Public page does not expose a reusable grant-record API. |
| Ruapehu GEM Local instance | Public portal shell, but grant database access unclear/protected | The instance exposes a Laravel/Vue shell and static JS, but the public landing page primarily routes to login/subscribe flows. No safe unauthenticated grant-record search endpoint was confirmed. |
| GrantsGuru / Rangitīkei context | Council announcement/link-out only | Rangitīkei page announces GrantGuru access for residents. It is not itself a machine-readable grant dataset. |
| Strategic Grants / GEMS | Commercial/product marketing; no public grant data found | WordPress marketing page for GEMS with login/demo/subscription context. No unauthenticated public grant records found. |
| Funding HQ | Marketing/resource site; no public database API found | WordPress site with visible public content and login links; no grant discovery API suitable for a skill found in public HTML. |
| localcommunity.org.nz | Public community/category pages, not a grant database | Public pages are server-rendered and category/community oriented. No grant-record search API found; TLS chain required local verification bypass during recon only. |

## Implementation decision

A dedicated `public-trust-grants` skill was implemented because Public Trust is the only confirmed safe public machine-readable grant source in this recon set. The skill dynamically reads the browser-published Algolia configuration from the public grants page, avoids committing the search key, and only performs read-only search/detail fetches.

## Caveats

- Public Trust listings are not a comprehensive NZ grant database; they cover Public Trust-published grants and scholarships.
- A browser search-only API key being public does not imply an open licence. The skill returns source URLs and should be used with modest quotation/citation.
- Commercial/sponsored portals may have data available after authorised login; this recon intentionally did not inspect or bypass those areas.
