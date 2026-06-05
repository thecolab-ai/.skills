# SEEK.co.nz source notes

Last verified: 2026-05-29 from an unauthenticated NZ SEEK search/detail workflow.

## Public source boundary

Supported commands use public pages on:

- `https://nz.seek.com/<keywords>-jobs/in-<location>`
- `https://nz.seek.com/job/<job-id>`

No login, account cookie, OAuth token, application action, saved search, recruiter surface, cart-like mutation, or job-posting workflow is used.

## Browser/network sweep

A representative browser visit to `https://www.seek.co.nz/python-developer-jobs/in-Auckland` redirects to:

```text
https://nz.seek.com/python-developer-jobs/in-All-Auckland
```

The page server-renders the job cards in HTML. A sampled result page contained 32 `data-testid="job-card"` articles and displayed 246 total Python developer jobs in Auckland at verification time.

Same-site/API traffic observed during the public search page load:

- `POST https://nz.seek.com/graphql` with `operationName: JobCountsV6` — returns facet counts for classification, location, and work type.
- `POST https://nz.seek.com/graphql` with `operationName: getKeywordSuggestions` — returns keyword suggestions.
- `POST https://nz.seek.com/graphql` with `operationName: GetBanner` — returns footer/advice banner data.
- The result list itself was available in the server-rendered HTML, so the CLI does not need to reproduce GraphQL queries for core search results.
- Other sampled requests were static assets, image/logo CDN URLs, analytics, telemetry, or ad pixels.

A public detail page such as `https://nz.seek.com/job/92100951` exposes:

- `window.SK_DL` with public job metadata: job id, title, advertiser name, posted age, area/location, classification, and status.
- visible `data-automation="jobAdDetails"` HTML with the public job-ad body.

## Fetching notes

A bare default Python `urllib` request can receive `403 Forbidden` from the edge, while the same public pages work with ordinary browser-compatible headers:

- `User-Agent`
- `Accept`
- `Accept-Language`
- `Referer: https://www.seek.co.nz/`
- `Upgrade-Insecure-Requests: 1`

The CLI uses those headers and does not store or require cookies.

## Stability notes

- Search URL slugs are public route conventions rather than a documented API contract.
- CSS class names are hashed and volatile; parsing should key off semantic `data-testid`, `data-automation`, `data-job-id`, and `window.SK_DL` markers.
- Job ids, counts, titles, salary snippets, and listed dates are live and will change.
- Keep smoke tests source-backed but flexible: assert non-empty search results and shape, not specific listing ids.

## Out-of-scope

- Applying, saving, sign-in, candidate profile, recruiter, employer, and posting flows.
- Private job recommendations or personalised account surfaces.
- Bulk collection or redistribution.
