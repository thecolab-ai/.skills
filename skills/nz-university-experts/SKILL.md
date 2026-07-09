---
name: nz-university-experts
description: Search New Zealand university "Find an Expert" directories for named academics with their title, department, curated expertise tags, and public profile URL. Use when you need to find a university expert on a topic, verify a finding with an academic, or build an SME/advisory candidate list beyond publication data. Keyless, read-only, via each portal's public JSON API. Returns ephemeral shortlists — discovery is not consent and output is never a contact list.
---

# NZ University Experts

## Goal

Search NZ universities' public expert directories by topic and get back named
academics with **curated expertise** (self-declared research tags), title,
department, and a public profile link. This complements `find-experts-nz`
(publication graphs): directory data includes staff who don't publish much and
the expertise *they* chose to be found by. Keyless, read-only, Python stdlib only.

## Use this when

- You need university experts on a topic and want their self-declared expertise, not
  just publication counts.
- You're building a candidate shortlist for a consented SME / advisory network.
- You want a public profile URL to hand a human steward alongside a finding.

## Do not use this for

- Building or storing a contact list. **Discovery is not consent.** Output is an
  *ephemeral* shortlist for a human steward — never a stored candidate list, never
  auto-contacted. Profile pages hold contact details; this skill does not collect them.
- Non-academic practitioners (tradespeople, front-line staff) — they aren't in
  university directories. Use industry associations / registers, or the org axis
  (`nzbn-register`, `charities-services-nz`).

## Workflow

1. `unis` — list supported universities and which are searchable now (`api`) vs
   roadmap (`todo`).
2. `search "<topic>" --uni <slug>` — ranked directory matches with expertise tags
   and profile URLs.
3. Hand the shortlist to a human steward. A human decides who (if anyone) to
   approach; a human always presses send. This skill stops at discovery.

## Commands

Run via `python3 scripts/cli.py <command>`:

- `search QUERY [--uni SLUG] [--limit N] [--json]` — search a university's expert
  directory (default `--uni auckland`).
- `unis [--json]` — list supported universities, their slug, and status.

`--json` is supported on both commands.

## Sources

- University of Auckland: `https://profiles.auckland.ac.nz/api/users` (public JSON
  search). Keyless, read-only.

## Notes

- Stdlib-only. All egress via the shared `nzfetch` helper, so a transient block is
  reported as `network error` (exit 2), not a crash.
- Never fabricate: every field is returned verbatim from the portal's public API.
- Only `api`-status universities are wired up today; the rest are a documented
  roadmap. See [`references/guide.md`](references/guide.md) for the consent boundary
  and **how to add a university** (identify its portal's public JSON search endpoint).
