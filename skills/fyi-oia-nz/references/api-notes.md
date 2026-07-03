# FYI.org.nz OIA/LGOIMA API notes

## Source

- Base site: `https://fyi.org.nz`
- Programme stack: Alaveteli (same family as WhatDoTheyKnow)
- Public read guidance and examples: `https://fyi.org.nz/help/api`

## Endpoints used

- `GET /body/all-authorities.csv`
  - Full authority directory from FYI.
  - Current observed fields: `Name`, `Short name`, `URL name`, `Tags`, `Home page`, `Publication scheme`, `Disclosure log`, `Notes`, `Created at`, `Updated at`, `Version`.
  - Source of discovery for `authorities` and `categories` commands.

- `GET /body/<url_name>.json`
  - Public authority metadata JSON.
  - Observed public fields: `id`, `url_name`, `name`, `short_name`, `home_page`, `publication_scheme`, `notes`, `tags`, `created_at`, `updated_at`.

- `GET /request/<id>.json`
  - Request metadata JSON.
  - Observed fields include `id`, `title`, `url_title`, `described_state`, `display_status`, `awaiting_description`, `law_used`, `created_at`, `updated_at`, `public_body`, `tags`, `info_request_events`.
  - `info_request_events` entries commonly include `id`, `event_type`, `created_at`, `described_state`, `calculated_state`, `display_status`, and message IDs.

- `GET /search/all?...`, `GET /search?...` and `.json` variants where available
  - Used only for `search` command discovery.
  - Search results parsing is best-effort, returning request url/title projections when list endpoints are not present.

## Behavior and caveats

- Robots guidance for FYI disallows crawling `/search/` and `/feed/` for generic bots; this skill uses bounded single-shot search queries and does not run background crawling.
- FYI lists bot-type user agents in `robots.txt`; this skill sends a non-bot/plain descriptive user agent string by default and does not attempt login.
- The upstream does not guarantee machine-readable search JSON for all query shapes; `search` may return request projections only when HTML search output is reachable.
- Data can be edited over time by the FYI platform. Request states/timelines and authority metadata should be treated as live public record snapshots.
- This skill is strict read-only: it never POSTs, never sends credentials, and does not fetch attachment binaries.

## Freshness and cadence

- `all-authorities.csv` appears to be maintained by FYI operators and includes live update timestamps (`Created at`, `Updated at`).
- Request JSON and authority JSON are live read endpoints and may change as agencies update disclosures.

## Personal-data handling

- Default request output strips user/requester identifying fields to avoid exposing personal information from request metadata.
- Use `--full` to include event timeline IDs/timestamps and request-state progression, not private message bodies.
