# nz-university-experts — guide

## The consent boundary (read this first)

This skill does **discovery**, not **contact**. University "Find an Expert" pages are
public, and searching them is like reading a directory. But approaching a person is a
Privacy Act 2020 collection event, so the output here is an **ephemeral candidate
shortlist** for a human steward — never a stored list, never auto-contacted.

Each academic's public profile page carries their contact details; this skill does
**not** collect or emit them. It returns only what identifies expertise: name, title,
department, self-declared expertise tags, and the public profile URL. A human visits
the profile and decides whether to reach out.

For the For Good repo: never write a discovered person's name into the public repo.
Findings attribute expert input by **role only** ("reviewed by a University of
Auckland gerontology academic"), per ADR-0010 and Constitution Article III.

## Why this complements find-experts-nz

`find-experts-nz` ranks people by what they've *published* (OpenAlex + Crossref).
This skill reads what universities *curate*: the expertise tags an academic chose to
be found by, their current role and department, and staff who are directory-listed
but not prolific publishers. Use both — publications show output, directories show
self-declared focus and current position.

## How to add a university

Every wired-up portal is just its public JSON search endpoint. To add one:

1. Open the university's "Find an Expert" / staff-profile search in a browser.
2. Watch the Network tab (XHR/fetch) as you search — find the request that returns
   JSON results (for Auckland it's `POST /api/users` with a JSON body of
   `params` + `filters`).
3. Add an adapter function in `scripts/cli.py` that calls it via `nzfetch` and maps
   its records to `{name, title, positions[], expertise[], profile_url, university}`.
4. Register it in `ADAPTERS` with `"method": "api"`. Until then leave it `"todo"`.

Keep it to **public, read-only search endpoints** only — no login, token, or
account-scoped API. If a portal has no public JSON search, leave it `todo` rather
than scraping rendered HTML.

## Supported / roadmap

- **auckland** — `api`, live. `POST /api/users` (JSON body).
- **massey** — `api`, live. Solr expert search (`.../profiles_solr_native.cfc`,
  form-encoded, `method=getExpertsFromSolr`). Its docs carry email/phone — the adapter
  drops them; keep it that way in any new adapter.
- **otago, vuw, canterbury, aut, waikato, lincoln** — `todo`: each needs its portal's
  public JSON search endpoint identified (step 2 above). Run `unis` for the current list.

**When a portal returns contact details** (Massey returns email/phone), map only
name / title / department / expertise / profile_url. Never emit email, phone, or
image fields — this skill surfaces expertise for a human steward, not a contact list.

## Reaching non-academics

University directories only hold academics. For practitioners and organisations,
discover the **organisation** and let a human invite it — compose:

- `nzbn-register` / `companies-office-nz` — businesses by name; industry, directors.
- `charities-services-nz` — NGOs by sector/activity; officer roles; grant signals.

## Exit codes

- `0` success · `1` usage/validation error · `2` `network error` (transient block or
  upstream outage — smoke tests SKIP rather than FAIL on this).
