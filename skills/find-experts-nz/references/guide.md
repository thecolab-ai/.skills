# find-experts-nz — guide

## The consent boundary (read this first)

This skill does **discovery**, not **contact**. Those are different acts with
different rules:

- **Discovery** is lawful and public: OpenAlex and ORCID are open scholarly data,
  and finding who published on a topic is like reading a library catalogue.
- **Contact** requires consent: approaching a person about their expertise is a
  Privacy Act 2020 collection event and (if by email) sits under the Unsolicited
  Electronic Messages Act 2007.

So the output of this skill is an **ephemeral candidate shortlist** for a human
steward. It is deliberately *not* a stored `candidate` registry: warehousing names
and affiliations you have not contacted is the creepiest, lowest-value part of an
expertise network, and it is the part that reads as "we scraped you" if it leaks.
Run discovery **on demand** when a gap fires; let the private, consented store begin
only at the point a human decides to invite someone.

For the For Good repo specifically: never write a discovered person's name into the
public repo. Findings attribute expert input by **role only** ("reviewed by an
aged-care finance SME"), per ADR-0010 and Constitution Article III.

## Where different experts actually live (tier model)

This skill scripts **Tier A** (via OpenAlex + Crossref + ORCID). Crossref widens
Tier A past universities into CRIs and government science. Tiers B–C are reached by
composing other skills or by human review — see below.

| Tier | Who | This skill? | Where to look instead |
|------|-----|-------------|-----------------------|
| A — Researchers / academics / CRI + govt scientists | Published authors | ✅ OpenAlex + Crossref + ORCID | also: NZ university "Find an Expert" portals, Royal Society Te Apārangi, Science Media Centre NZ expert database (all HTML — human review) |
| B — Practitioners | Beekeepers, nurses, tradespeople | ❌ mostly unpublished | professional registers + industry associations (see "human-review directories") |
| C — Organisations | Industry-classified entities, NGOs | ✅ via companion skills | `nzbn-register`, `companies-office-nz`, `charities-services-nz` |
| D — Commercial expert networks | GLG, Guidepoint, etc. | ❌ | paid, out of scope |

**The Science Media Centre NZ expert database is the model to emulate** — a
*consented* list of experts who opted in to being contacted. Worth approaching as a
partner rather than rebuilding.

## The organisation axis (composable, scripted today)

To reach practitioners, discover the org and let a human invite it. These skills
return clean JSON now:

```
# Businesses by name (leads to industry associations, e.g. the beekeeping example)
python3 skills/nzbn-register/scripts/cli.py search "apiculture" --json
python3 skills/companies-office-nz/scripts/cli.py search "beekeeping" --json

# NGOs / charities by sector + grant-making signal (great for #442 aged care)
python3 skills/charities-services-nz/scripts/cli.py activities --json      # sector taxonomy
python3 skills/charities-services-nz/scripts/cli.py search "aged care" --registered-only --json
python3 skills/charities-services-nz/scripts/cli.py officers <OrganisationId> --json
```

`charities-services-nz` strips email-like officer fields — keep that boundary: an
officer *role* at an org is org-level data; a person's contact detail is not.

## Human-review directories (no clean keyless API — do not script)

Real and valuable, but each is an HTML search form behind bot protection or terms
that forbid automated harvesting. Surface these to a human steward as *where to look
next*, don't scrape them:

- **Practitioner registers** — Engineering NZ (Chartered), CA ANZ, NZ Law Society
  "Find a Lawyer", Medical Council vocational register, Registered Architects Board,
  Teaching Council.
- **Industry associations** — Apiculture NZ, DairyNZ, Federated Farmers, NZ Aged
  Care Association. Often the fastest route to "the cracked one," and they can
  broadcast an open invite to their members (inbound signup beats cold outreach).
- **University "Find an Expert" portals** (Elsevier Pure) — Auckland, Otago, VUW,
  Massey, Canterbury, AUT. Public per-person profiles with curated expertise,
  teaching, and "available for media comment" flags — richer than publication data,
  and it includes staff who don't publish much. No keyless JSON API: JS-rendered and
  bot-walled to bare HTTP (`profiles.auckland.ac.nz` returns only a ~2 KB JS shell).
  **Reachable with a real browser** — see "Browser-assisted route" below.
- **Royal Society Te Apārangi fellows**, **Science Media Centre expert database** —
  HTML directories; SMC is a *consented* expert list and is better approached as a
  partner than scraped.

Probed as script sources and set aside: Semantic Scholar (429s without an API key);
the Pure portals, Royal Society, and SMC (JS/bot-walled, no keyless JSON). Revisit
if any publishes a keyless JSON API.

## Browser-assisted route (CloakBrowser) — proven, not yet built

The Pure portals are not CAPTCHA — they're JS-rendered pages behind IP/fingerprint
walls, exactly what CloakBrowser (stealth Chromium) is for. Verified working: a
CloakBrowser fetch of an Auckland profile returned full rendered expertise text where
bare HTTP got only a JS shell. So a **browser-assisted `--browser` mode** is viable
and would add genuinely new data (curated expertise + non-publishing staff).

Deliberately not built into this skill, because:

- It's a heavyweight optional dependency (Chromium) and `.skills` keeps browser mode
  optional and off by default; this skill's core stays keyless/stdlib/fast.
- Each Pure portal is bespoke HTML — 6+ NZ universities means 6+ parsers, brittle to
  redesigns. That deserves its own skill boundary, not a bolt-on.
- Terms: browser mode is for public, read-only pages only — never login, CAPTCHA
  bypass, or auth flows (`.skills` `docs/browser-assisted-skills.md`).

Recommended shape when built: a separate `nz-university-experts` skill with a
`--browser` flag, one adapter per portal, returning `{name, title, department,
expertise[], profile_url}` — still discovery-only, still handed to a human steward,
never a stored contact list.

## Query recipes

Resolve a fuzzy topic first — a topic id filters far more precisely than free text:

```
cli.py topics "freshwater nitrate dairy"
cli.py search "nitrate leaching" --topic-id T10662 --since 2018 --limit 8
```

Broaden when a niche leaf is empty — drop `--topic-id`, widen `--since`, raise
`--sample` (max 200 works per query):

```
cli.py search "rest home funding residential aged care" --sample 200 --since 2015
```

Widen past universities — `--source crossref` reaches CRI/government authors that
OpenAlex's institution filter misses; `--source both` (default) merges and ranks
cross-source matches highest:

```
cli.py search "varroa colony loss beekeeping" --source crossref   # CRI + MPI authors
cli.py search "varroa colony loss beekeeping" --source both       # merged shortlist
```

Target a specific university, CRI, or company (OpenAlex classifies every institution
by type — education / company / government / facility / nonprofit / healthcare):

```
cli.py institutions "otago"            # -> I80281795 University of Otago [education]
cli.py institutions "healthcare" --type company   # -> Fisher & Paykel Healthcare [company]
cli.py search "residential aged care" --institution I80281795     # experts at Otago
cli.py search "medical device respiratory" --org-type company     # company scientists
```

`--org-type company` is the keyless route to "leading companies with smart people" —
it surfaces authors affiliated to R&D-active NZ companies (e.g. a Fisher & Paykel
Healthcare respiratory scientist). It only catches companies that *publish*; for
company discovery by industry/region generally, use the org-axis skills above.

Profile + cross-check a candidate before handing them to a steward:

```
cli.py author 0000-0002-1801-5687 --works 5      # ORCID or OpenAlex A-id both work
cli.py orcid  0000-0002-1801-5687                # self-declared employment + keywords
```

Non-NZ affiliation: `--country AU`, `--country GB`, etc. (ISO-2 codes).

## Ranking & limitations

- Candidates are ranked by **count of topic-matching works in the sample**, then by
  **recency**. This is a coarse "who works on this a lot, lately" signal — not an
  authority score. `author` gives citation count / h-index if you want depth.
- The sample is the first `--sample` works OpenAlex returns for the query (relevance
  sort when a free-text topic is given). A prolific author on an adjacent topic can
  out-rank a specialist; always eyeball the sample works.
- OpenAlex topic tags are automated and imperfect. Free-text `search` without
  `--topic-id` casts wider but noisier.
- ORCID records are self-maintained: employment/keywords may be sparse or stale.
- **Codes and publications find the field, not the "cracked one."** Treat every
  shortlist as a starting point for a human, and remember snowball referral
  ("who should I actually ask?") usually beats any automated list for the truly niche.

## Exit codes

- `0` success · `1` usage/validation error · `2` `network error` (transient bot-wall
  or upstream outage — smoke tests SKIP rather than FAIL on this).

## University directories (`directory` command)

`directory` searches a university "Find an Expert" portal's public JSON API and
returns named academics with **curated** expertise tags (what they chose to be found
by), title, department, and profile URL — complementing the publication-based
`search`. Wired up: **Auckland** (`POST /api/users`) and **Massey** (Solr expert
search). Others (`unis` shows them as `todo`) each need their portal's public JSON
search endpoint identified.

**Adding a university:** open the portal's expert search in a browser, watch the
Network tab (XHR/fetch) as you search, find the request returning JSON, add an
adapter in `scripts/cli.py` that calls it via the shared `fetch_json` (POST bodies
supported) and maps records to `{name, title, positions[], expertise[], profile_url,
university}`, then register it in `DIRECTORIES` with `"method": "api"`. Public,
read-only search endpoints only.

**Never collect contact details.** Massey's API returns email/phone; the adapter
drops them and emits expertise only. Keep that rule in any new adapter — this skill
surfaces expertise for a human steward, not a contact list.

## Professional registers (`register` command)

`register` searches an official practitioner register — reaching the **practitioner
tier** (tradespeople, advisers, clinicians) that publication and directory sources
miss. Each returns `{name, role, organisation, expertise[], status, location,
profile_url, register}`.

Wired up:

- **pgdb** — Plumbers, Gasfitters & Drainlayers Board public register (`pgdb-api.pgdb.co.nz`), by name. Registration types (Certifying Plumber…) become the expertise tags.
- **legalaid** — MoJ Legal Aid Lawyer Finder: one JSON roster of ~3,000 lawyers, filtered here by name / firm / practice area (matter-type hashes resolved to readable names).
- **irpnz** — Institute of Rural Professionals "find a member": ~650 farm-systems advisers, nutrient specialists, rural consultants; paginated, filtered by name/role/firm.
- **mcnz** — Medical Council register of doctors (~25k): keyless, HTML-in-JSON, by name, with scope of practice and status.

**Never collect contact details.** PGDB, IRPNZ, and legal-aid records carry
email/phone/address; every adapter drops them and emits only expertise + a public
profile link. A smoke test asserts no contact detail reaches output. Keep that rule
in any new register adapter.

**Confirm terms before bulk use.** These are public lookups; the skill does per-query,
capped fetches (no full-register mirroring). MoJ Legal Aid data licensing and CAB-style
acceptable-use should be checked before any redistribution beyond an ephemeral steward
shortlist. See the source build queue for per-source notes.

**Adding a register:** identify its public JSON (or HTML-in-JSON) search endpoint,
write an adapter returning the record shape above via `fetch_json`, drop all contact
fields, and register it in `REGISTERS`.
