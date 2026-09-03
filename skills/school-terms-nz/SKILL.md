---
name: school-terms-nz
description: "Look up official New Zealand school term and holiday dates, identify the term or break covering a date, find the next school break, and summarise published school years with Ministry of Education caveats."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "education"
  thecolab.source_owner: "Ministry of Education"
  thecolab.source_type: "official"
  thecolab.auth: "none"
  thecolab.access_mode: "html-readonly"
  thecolab.data_class: "public"
  thecolab.writes: "false"
  thecolab.browser: "false"
  thecolab.risk: "low"
  thecolab.cache_ttl: "24h"
  thecolab.schema_version: "1"
  thecolab.skill_type: "html-readonly"
  thecolab.pack: "nz-public-data"
  thecolab.source_url: "https://www.education.govt.nz/school/school-terms-and-holidays"
  thecolab.allowed_domains: "www.education.govt.nz"
  thecolab.last_verified: "2026-09-03"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# School Terms NZ

## Goal

Query the Ministry of Education's current public school terms and holidays page with a bounded, read-only, standard-library Python CLI.

## Use This When

- A user asks for official New Zealand school term or school holiday dates.
- A workflow needs to identify the published term or break covering a date.
- A user wants the current or next published school break from a date.
- A user needs the current or past years published by the Ministry, with source provenance.

## Do Not Use This For

- An individual school's exact opening, closing, teacher-only or local-event dates.
- Early childhood service or private-school calendars, which may set their own dates.
- Public-holiday entitlement advice or local anniversary dates.
- Historical dates outside the past-year sections currently published on the source page.

## Preferred Workflow

1. List the Ministry's complete current and past published years:

   ```bash
   python3 skills/school-terms-nz/scripts/cli.py years --json
   ```

2. Inspect one complete published year:

   ```bash
   python3 skills/school-terms-nz/scripts/cli.py year 2026 --json
   ```

3. Classify an ISO date as a published term, break, school-dependent period or uncovered date:

   ```bash
   python3 skills/school-terms-nz/scripts/cli.py date 2026-04-10 --json
   ```

4. Find the current or next published break from an ISO date:

   ```bash
   python3 skills/school-terms-nz/scripts/cli.py next-break 2026-06-01 --json
   ```

5. Preserve `source_url` and `fetched_at` in any answer. Report `certainty` and `caveat` whenever school dates vary.

All data commands accept `--timeout SECONDS` (default 10) and `--json`.

## Interpretation Rules

- Terms 2 and 3 use the fixed dates published by the Ministry.
- Schools have flexibility over Term 1 opening and Term 4 closing dates. During either variable window, `date` returns `school_term_or_break` with `certainty: "school_dependent"` rather than claiming a definite term or break.
- Published inter-term breaks are returned as fixed ranges. Summer holidays begin on each school's closing date, no later than the published boundary; duration details remain source-derived in the returned description.
- Weekends, teacher-only days, public holidays, local anniversary days and emergency closures can close a school during a term; this CLI does not infer those local closures.
- `next-break` returns the current break when the query date is already inside one; otherwise it returns the next break represented by the published years.
- Inside the inclusive Term 1 opening window, `next-break` cannot know whether an individual school is still on summer holiday or has opened. The usual top-level envelope remains unchanged, but `break` has `certainty: "school_dependent"`, `days_until: null`, an individual-school-calendar `caveat`, and `next_fixed_break` with `name`, `start`, `end` and `days_until` for the next universally published break. Dates before the earliest opening remain current summer holiday results; dates after the latest opening use the usual certain next-break shape.
- During Term 4, the Ministry publishes only a no-later-than closing boundary. `next-break` therefore returns summer holidays with `certainty: "school_dependent"` and `days_until: null` until the latest possible closing day has passed; use the individual school's calendar for an exact countdown.

## Errors

- Exit 2: invalid ISO date, timeout or unpublished year.
- Exit 4: source access blocked or rate-limited.
- Exit 5: upstream source unavailable.
- Exit 6: Ministry page schema changed or published sections are incomplete.

Errors are concise and emit structured JSON when `--json` is supplied. Date inputs are validated before any network request. The CLI never writes to the source or local user files.

## Resources

- CLI: `scripts/cli.py`
- Deterministic contract check: `scripts/test_contract.py`
- Fixture and bounded live smoke: `scripts/smoke_test.py`
- Source and parser details: `references/source-notes.md`
