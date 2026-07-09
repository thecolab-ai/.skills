---
name: find-experts-nz
description: Discover New Zealand-affiliated researchers and subject experts by topic, using the public OpenAlex scholarly graph and ORCID registry. Use when you need a citable candidate shortlist of who could speak to a research question — expert matching, "find an expert", verifying a finding with a practitioner, or building an SME/advisory candidate list. Returns ephemeral shortlists from public data only — discovery is not consent and output is never a contact list.
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
- Finding non-published practitioners (beekeepers, tradespeople, front-line staff).
  OpenAlex indexes *authors* — it finds academics, not the practitioner in no register.
  Use industry associations / registers for those (see references).
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

- `search TOPIC [--source openalex|crossref|both] [--topic-id ID] [--institution IDS] [--org-type TYPE] [--country NZ] [--since YEAR] [--sample N] [--limit N] [--json]`
  — ranked NZ-affiliated authors who published on the topic. Defaults to `both`;
  authors found in both sources rank highest (corroboration). `--topic-id`,
  `--institution`, `--org-type` are OpenAlex-only; Crossref matches NZ affiliation
  by free-text string.
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
- ORCID public API: `https://pub.orcid.org/v3.0` (record). Keyless.

## Reaching beyond academics (companion skills)

OpenAlex/Crossref only find *published* people. For practitioners and organisations
— the beekeeper, the aged-care provider — discover the **organisation** first, then
a human invites it. Compose these existing skills (see `references/guide.md`):

- `nzbn-register` / `companies-office-nz` — find businesses by name; directors,
  industry classification.
- `charities-services-nz` — NGOs by sector/activity taxonomy, public officer roles,
  grant-making signals.

To target a specific university or company, use `institutions` then
`search --institution <id>` (or `--org-type company`) — all keyless via OpenAlex.

University "Find an Expert" portals (Elsevier Pure) and professional registers
(Engineering NZ, NZ Law Society, Medical Council) have no keyless JSON API and are
JS-rendered / bot-walled to bare HTTP. They *are* reachable with a real browser
(CloakBrowser) — a proven but heavier, per-portal route documented as a future
optional `--browser` companion in `references/guide.md`, not scripted here.

## Notes

- Stdlib-only, read-only. Uses the shared `nzfetch` helper, so a transient bot-wall
  is reported as `network error` (exit 2), not a crash.
- Never fabricate: every field is returned verbatim from a public API payload.
- NZ affiliation is filtered on `authorships.institutions.country_code` — an author
  with only a historical NZ affiliation may still surface; check `author` output.
- See [`references/guide.md`](references/guide.md) for the consent/ethics boundary,
  the tier model (where different kinds of experts actually live), and query recipes.
