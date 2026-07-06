# DataForSEO endpoint reference

All commands hit **v3 `live`** (synchronous) endpoints — one HTTP round trip, no
task polling. Base URL: `https://api.dataforseo.com`. Auth: HTTP Basic with the
API login/password.

## Command → endpoint map

| Command | Endpoint | Key request fields |
|---|---|---|
| `serp` | `v3/serp/google/organic/live/advanced` | `keyword`, `location_code`, `language_code`, `depth` |
| `volume` | `v3/keywords_data/google_ads/search_volume/live` | `keywords[]`, `location_code`, `language_code` |
| `suggestions` | `v3/dataforseo_labs/google/keyword_suggestions/live` | `keyword`, `location_code`, `language_code`, `limit` |
| `ranked` | `v3/dataforseo_labs/google/ranked_keywords/live` | `target`, `location_code`, `language_code`, `limit` |
| `competitors` | `v3/dataforseo_labs/google/competitors_domain/live` | `target`, `location_code`, `language_code`, `limit` |
| `domain` | `v3/dataforseo_labs/google/domain_rank_overview/live` | `target`, `location_code`, `language_code` |
| `backlinks` | `v3/backlinks/summary/live` | `target` |
| `refdomains` | `v3/backlinks/referring_domains/live` | `target`, `limit`, `order_by` |

## Response envelope

Every response looks like:

```json
{
  "status_code": 20000,
  "status_message": "Ok.",
  "tasks": [
    {
      "status_code": 20000,
      "status_message": "Ok.",
      "result": [ ... ]
    }
  ]
}
```

`status_code` 20000 = success at both the top level and the task level. The CLI
validates both and dies with the `status_message` on anything else. Common
errors: `40501`/`40400` (bad params), `40200` (payment required / out of
credits), HTTP `401`/`403` (bad credentials).

## Approximate cost per call

DataForSEO prices per API call (and Labs/backlinks scale a little with rows).
Rough order, cheapest first — check your plan's pricing page for exact numbers:

- `serp` (organic advanced) — a few tenths of a cent per call.
- `volume` — cheap; billed per call, all keywords in one request.
- `suggestions`, `ranked`, `competitors`, `domain` (Labs) — a bit more; keep
  `--limit` modest.
- `backlinks`, `refdomains` — backlinks data is the priciest tier; `refdomains`
  scales with `--limit`.

`--limit` caps the rows requested where the endpoint supports it (`suggestions`,
`ranked`, `competitors`, `refdomains`) and the SERP `depth`, so it's the main
lever for controlling both noise and cost.

## Location codes

The CLI ships a small alias map (`nz us uk/gb au ca ie za in`). For any other
market, pass a numeric `location_code`. The full list is available (unauthed
GET, not wrapped here):

- SERP: `GET https://api.dataforseo.com/v3/serp/google/locations`
- Labs: `GET https://api.dataforseo.com/v3/dataforseo_labs/locations_and_languages`

## Not wrapped in v1 (intentional)

- **On-Page / site audit** — uses async `task_post` + `task_get` polling.
- **Task-based (queued) SERP/keyword jobs** — cheaper at volume but need polling.
- **Bing / YouTube / Amazon SERPs, Google Trends, historical data.**

These are easy to add later following the same client/command pattern in
`scripts/cli.py`.
