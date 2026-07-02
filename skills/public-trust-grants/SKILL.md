---
name: public-trust-grants
description: Query Public Trust New Zealand public grants and scholarships through the unauthenticated grants search index and public detail pages. Use when the task involves finding Public Trust-managed NZ grant or scholarship opportunities by keyword, organisation/individual type, region, sector, or application-open status, or checking public grant criteria text. Read-only; no login, application submission, SmartyGrants form access, or paywalled/commercial grant database scraping.
---

# Public Trust Grants

## Goal

Find Public Trust NZ grant and scholarship listings from the public grants search page and fetch readable text from public grant detail pages.

## Use this when

- The user asks for Public Trust grants, NZ trusts administered by Public Trust, or scholarships listed at `publictrust.co.nz/grants`.
- You need to search by keyword, `individual` vs `organisation`, region facet, sector facet, or `applications_open_now`.
- You need a source URL and public summary/criteria text for a specific Public Trust grant.

## Do not use this for

- givUS, Fundsorter, GEM Local, GrantsGuru, Funding HQ, Strategic Grants GEMS, or other commercial/library-sponsored grant databases.
- Logging in, bypassing paywalls/CAPTCHAs, submitting applications, or interacting with SmartyGrants forms.
- Treating Public Trust listings as a complete national grants database; it only covers grants/scholarships Public Trust publishes.

## CLI workflow

The tool is in `scripts/cli.py` and uses Python standard library only.

```bash
python3 skills/public-trust-grants/scripts/cli.py search community --type organisation
python3 skills/public-trust-grants/scripts/cli.py search scholarship --type individual --json
python3 skills/public-trust-grants/scripts/cli.py facets --json
python3 skills/public-trust-grants/scripts/cli.py detail thomas-richard-moore-trust --json
```

Typical steps:

1. Run `facets` if you need available `grants_regions` or `sectors` slugs.
2. Run `search` with a keyword and optional filters. Use `--json` when you need machine-readable output.
3. Use `detail` with a result slug/URL for public page text and cite `source_url` in the answer.

## References

- See `references/recon.md` for the issue #112 portal-by-portal recon notes and source classification.

## Safety and caveats

- The CLI dynamically reads the browser-published Algolia search-only configuration from the Public Trust grants page; no API key is committed.
- Listings are public and unauthenticated, but licensing/terms are not asserted. Quote modestly and link back to Public Trust.
- `applications_open_now` is the upstream facet and may lag real application windows; verify the detail page before giving deadline advice.
