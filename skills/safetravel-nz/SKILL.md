---
name: safetravel-nz
description: "Use when looking up New Zealand Government SafeTravel destination advice, advice levels, regional cautions, related alerts or news, or source timestamps. Read-only, official, keyless travel-advice lookup."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live MFAT SafeTravel pages"
metadata:
  thecolab.category: "travel-safety"
  thecolab.source_owner: "Ministry of Foreign Affairs and Trade (MFAT)"
  thecolab.source_type: "official"
  thecolab.auth: "none"
  thecolab.access_mode: "html-readonly"
  thecolab.data_class: "public"
  thecolab.writes: "false"
  thecolab.browser: "false"
  thecolab.risk: "medium"
  thecolab.cache_ttl: "none"
  thecolab.schema_version: "1"
  thecolab.skill_type: "html-readonly"
  thecolab.pack: "nz-public-data"
  thecolab.source_url: "https://www.safetravel.govt.nz/"
  thecolab.allowed_domains: "www.safetravel.govt.nz"
  thecolab.last_verified: "2026-09-03"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# SafeTravel NZ

## Goal

Look up current, official New Zealand Government travel advice from MFAT's SafeTravel website. The skill is read-only: it searches the official destination sitemap and retrieves a destination's advice level, regional cautions, related alerts/news, and source timestamps.

## Use this when

- A user asks for the NZ Government's travel advice for a country or destination.
- A workflow needs the SafeTravel advice level (1–4), regional exceptions, or the destination page's update date.
- A user wants related SafeTravel news/alerts associated with a destination page.
- An agent needs a source URL and retrieval timestamp for a travel-safety briefing.

## Do not use this for

- Travel registration, login, profile/account access, emergency assistance, or storing contact details.
- Booking, visas, insurance eligibility, or immigration advice.
- Replacing a traveller's judgement, local emergency instructions, or direct official advice.
- Circumventing blocks, CAPTCHA, or access controls.

## Preferred workflow

1. Run `search` for the destination name and use its returned slug if there is any ambiguity.
2. Run `advice <slug> --json` to retrieve the current official page.
3. Report the `advice_level`, any `regional_cautions`, `related_alerts_news`, and the `source.page_updated` / `source.retrieved_at` timestamps.
4. Always say that travel advice can change and link the user to the returned official source page.

## CLI

Run from the repository root:

```bash
python3 skills/safetravel-nz/scripts/cli.py <command> [flags]
```

### Commands

- `search QUERY [--limit N] [--json]` — search destination pages listed in SafeTravel's official sitemap.
- `advice DESTINATION [--json]` — fetch a destination's current advice. `DESTINATION` can be a name, slug, or canonical SafeTravel destination URL.

Examples:

```bash
python3 skills/safetravel-nz/scripts/cli.py search australia --json
python3 skills/safetravel-nz/scripts/cli.py advice australia
python3 skills/safetravel-nz/scripts/cli.py advice "https://www.safetravel.govt.nz/destinations/australia" --json
```

## JSON result

`--json` emits the repository result envelope (`schema_version: "1"`) with:

- `source.url` and `source.retrieved_at` for each live result.
- `source.page_updated` when SafeTravel displays an update date on a destination page.
- `data.advice_level` with title, textual and numeric level, update/currentness fields, and advice body.
- `data.regional_cautions` for any regional advice entries distinct from the country-wide level.
- `data.related_alerts_news` for destination-page related news cards, with official links and displayed dates where present.
- A warning that advice can change.

## Resources

- CLI entrypoint: `scripts/cli.py`
- Deterministic parser test: `tests/test_parser.py`
- Bounded outage-aware smoke test: `scripts/smoke_test.py`
- Source surfaces, parser assumptions, and caveats: `references/source-notes.md`

## Notes and safety

- The CLI makes only GET requests to `www.safetravel.govt.nz`, with a 10-second timeout per request. It has no credentials, browser automation, cache, registration, or mutation flow.
- The official sitemap is used as the destination allowlist before a destination page is retrieved.
- SafeTravel advice may change without notice. For safety-critical or imminent travel decisions, open the returned official URL directly and follow local authority or emergency instructions.
