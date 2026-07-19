---
name: find-experts-nz
description: "Discover New Zealand experts by topic across public sources — the OpenAlex and Crossref scholarly graphs, Wikidata, ORCID, and university \"Find an Expert\" directories (University of Auckland, Massey). Use when you need a citable candidate shortlist of who could speak to a research question — expert matching, \"find an expert\", verifying a finding, or building an SME/advisory candidate list. Returns ephemeral shortlists from public data only — discovery is not consent and output is never a contact list."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "education"
  thecolab.source_owner: "OpenAlex and contributing directories"
  thecolab.source_type: "mixed"
  thecolab.auth: "none"
  thecolab.access_mode: "public-api"
  thecolab.data_class: "public"
  thecolab.writes: "false"
  thecolab.browser: "false"
  thecolab.risk: "low"
  thecolab.cache_ttl: "24h"
  thecolab.schema_version: "1"
  thecolab.skill_type: "public-api"
  thecolab.pack: "nz-public-data"
  thecolab.source_url: "https://api.openalex.org"
  thecolab.allowed_domains: "academics.aut.ac.nz,api.crossref.org,api.openalex.org,en.wikipedia.org,people.wgtn.ac.nz,pgdb-api.pgdb.co.nz,profiles.auckland.ac.nz,pub.orcid.org,query.wikidata.org,researchers.lincoln.ac.nz,researchprofiles.canterbury.ac.nz,www.irpnz.co.nz,www.justice.govt.nz,www.massey.ac.nz,www.mcnz.org.nz,www.otago.ac.nz,www.waikato.ac.nz,www2.pgdb.co.nz"
  thecolab.last_verified: "2026-07-19"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# Find Experts (NZ)

## Goal

Turn a research topic into a ranked, citable shortlist of NZ-affiliated experts —
who has published on this, where they're based, with links to public profiles.
Keyless, read-only queries across **two** scholarly graphs (OpenAlex + Crossref)
plus ORCID. Searching both broadens the range beyond universities into Crown
Research Institutes (NIWA, Manaaki Whenua, ESR…) and government science (e.g. MPI),
whose authors OpenAlex's institution filter often misses. Python stdlib only.

## Use this when

- A stream/finding flags an expertise gap and you need candidate people who could verify it.
- You're building a candidate list for a consented SME / advisory network.
- You want to corroborate a surprising claim by finding who researches it in NZ.
- You need a public, machine-readable link (OpenAlex id / ORCID iD) for reproducible provenance.

## Do not use this for

- Building or storing a contact list. **Discovery is not consent.** Output is an
  *ephemeral* shortlist for a human steward to review — never a mailing list, never
  auto-contacted, never persisted as a `candidate` registry.
- Finding practitioners *via `search`* — OpenAlex/Crossref index *authors*, so they
  find academics, not the tradesperson or adviser. Use the `register` command for
  practitioners in a professional register, or the org axis (see references) for those
  in none.
- Any personal-data workflow. Emails and addresses are out of scope by design; this
  skill returns names, affiliations, and public profile links only.

## Workflow

1. **Resolve the topic** (optional but sharper): `topics "<fuzzy topic>"` returns
   OpenAlex topic ids. Pick the closest and pass it as `--topic-id T#####` to `search`.
2. **Search** for NZ-affiliated authors: `search "<topic>" [--topic-id T#####]`.
   Ranked by number of matching works then recency. `--country`, `--since`, `--limit`.
3. **Profile** a promising candidate: `author <OpenAlex-id|ORCID> --works 5` for
   citation counts, h-index, affiliation history, topics, recent papers.
4. **Cross-check** via ORCID: `orcid <iD>` for self-declared employment and keywords.
5. **Hand the shortlist to a human steward.** A human decides who (if anyone) to
   approach; a human always presses send. This skill stops at discovery.

## Commands

Run via `python3 scripts/cli.py <command>`:

- `search TOPIC [--source openalex|crossref|wikidata|both|all] [--topic-id ID] [--institution IDS] [--org-type TYPE] [--country NZ] [--since YEAR] [--sample N] [--limit N] [--json]`
  — ranked NZ-affiliated experts on the topic. `both` = OpenAlex+Crossref (default);
  `all` = also Wikidata. Experts found in more sources rank highest. `--topic-id`,
  `--institution`, `--org-type` are OpenAlex-only. `wikidata` finds *notable* NZ
  experts (people with a Wikidata item) across **any** institution — including
  portals with no API — matched by field of work; NZ-only, soft-fails if WDQS is
  rate-limiting.
- `directory QUERY [--uni SLUG] [--limit N] [--json]` — search a university
  "Find an Expert" directory (default `--uni auckland`; also `massey`) for named
  academics with curated expertise tags, title, department, and profile URL.
  Directory data includes staff who don't publish much and the expertise *they*
  chose to be found by. Contact details are deliberately never collected.
- `unis [--json]` — list supported university directories (`api`) and roadmap ones.
- `register QUERY [--which pgdb|legalaid|irpnz|mcnz] [--limit N] [--json]` — search a
  professional register for named **practitioners** — the tier scholarly sources miss.
  `pgdb` (plumbers/gasfitters/drainlayers, by name), `legalaid` (MoJ legal-aid lawyers,
  by name or practice area), `irpnz` (rural professionals / farm advisers, by name/role/
  firm), `mcnz` (register of doctors, by name). Contact details are never collected.
- `registers [--json]` — list supported professional registers.
- `institutions QUERY [--type TYPE] [--country NZ] [--limit N] [--json]` — resolve
  NZ universities, CRIs, companies, and government bodies to OpenAlex institution
  ids. `--type company` lists R&D-active NZ companies; feed an id to
  `search --institution`. Types: education, company, government, facility,
  nonprofit, healthcare, other.
- `topics QUERY [--limit N] [--json]` — resolve a fuzzy topic to OpenAlex topic ids.
- `author ID [--works N] [--json]` — author profile by OpenAlex id (`A…`) or ORCID iD.
- `orcid ID [--json]` — public ORCID record: name, bio, keywords, employment history.

`--json` is supported on every command.

## Sources

- OpenAlex: `https://api.openalex.org` (works, authors, topics). Keyless. Setting
  `OPENALEX_MAILTO=you@example.org` joins the faster "polite pool" (also used as
  Crossref's `mailto`, optional).
- Crossref: `https://api.crossref.org/works` (works + author affiliations). Keyless.
- Wikidata Query Service: `https://query.wikidata.org/sparql` (NZ academics by field
  of work). Keyless, CC0. Notable-only; rate-limited (soft-fails when throttled).
- University directories (`directory`): University of Auckland (`/api/users`) and
  Massey (Solr expert search). Keyless. Massey returns email/phone; the skill
  **drops** them and emits expertise only.
- Professional registers (`register`): PGDB plumbers/gasfitters/drainlayers, MoJ
  Legal Aid lawyers, IRPNZ rural professionals, MCNZ register of doctors. Keyless.
  PGDB/IRPNZ/legal-aid expose contact details; the skill **drops** them.
- ORCID public API: `https://pub.orcid.org/v3.0` (record). Keyless.

## Reaching beyond academics

`search`/`directory` find *published or directory-listed* people. For practitioners
and organisations — the beekeeper, the aged-care provider — discover the
**organisation** first, then a human invites it. Compose these existing skills
(see `references/guide.md`):

- `nzbn-register` / `companies-office-nz` — find businesses by name; directors,
  industry classification.
- `charities-services-nz` — NGOs by sector/activity taxonomy, public officer roles,
  grant-making signals.

To target a specific university or company, use `institutions` then
`search --institution <id>` (or `--org-type company`) — all keyless via OpenAlex.
More university directories can be added under `directory` as each portal's public
JSON search endpoint is identified — see `references/guide.md`.

## Notes

- Stdlib-only, read-only. Uses the shared `nzfetch` helper, so a transient bot-wall
  is reported as `network error` (exit 2), not a crash.
- Never fabricate: every field is returned verbatim from a public API payload.
- NZ affiliation is filtered on `authorships.institutions.country_code` — an author
  with only a historical NZ affiliation may still surface; check `author` output.
- See [`references/guide.md`](references/guide.md) for the consent/ethics boundary,
  the tier model (where different kinds of experts actually live), and query recipes.
