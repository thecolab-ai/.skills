# NZBN Register API notes

This skill is an unofficial lightweight wrapper around public NZBN Register website read-only endpoints. It does not use authenticated MyNZBN functionality.

## Source and auth

- Website: `https://www.nzbn.govt.nz`
- Public register UI route: `https://www.nzbn.govt.nz/mynzbn/search/`
- Website proxy used by this skill: `https://www.nzbn.govt.nz/api/business/nzbn?u={encoded-uri}`
- Upstream official gateway surfaced by payload links: `https://api.business.govt.nz/gateway/nzbn/v5`
- Auth model for this skill: none for the implemented read-only website-proxy requests

No username, password, account cookie, private token, browser session, or API subscription key is required for the implemented commands.

## Endpoint families used

The website React bundle calls a local proxy endpoint and passes the upstream NZBN API URI in the `u` query parameter. The CLI mirrors only these read-only GET calls:

- Search entities:
  - Proxy call: `GET /api/business/nzbn?u=entities%3Fsearch-term%3D{query}%26page-size%3D{limit}%26page%3D{page}`
  - Upstream shape: `entities?search-term={query}&page-size={limit}&page={page}`
- Exact NZBN lookup:
  - Proxy call: `GET /api/business/nzbn?u=entities%2F{nzbn}`
  - Upstream shape: `entities/{nzbn}`

The direct official gateway was tested and returned `401` without a subscription key, for example:

```text
GET https://api.business.govt.nz/gateway/nzbn/v5/entities?search-term=the%20warehouse&page-size=5&page=0
=> 401 Access denied due to missing subscription key
```

The website proxy returned live public data for the same entity search and exact lookup without credentials. Some upstream filter parameters shown in older/UI code paths can be rejected by the proxy (`400 One or more values not recognized`), so this skill intentionally keeps the supported search surface to query, page, and page size.

## Response notes

Search responses include:

- `pageSize`, `page`, `totalItems`
- `items[]` with `entityName`, `nzbn`, entity status/type fields, trading names, previous names, registration date, and source-register id

Lookup responses include public details such as:

- entity status/type, registration and last-updated dates
- source register and source-register identifier
- public addresses and websites
- public email/phone/GST/classification fields when the register exposes them

The CLI simplifies common fields by default and can include the raw exact-lookup payload with `lookup <nzbn> --raw --json`.

## Stability and safety

- The website proxy is public and read-only for these calls, but it is not a formal stable API contract for third-party clients.
- The official documented API may be preferable for production/high-volume use, but direct gateway calls require an API subscription key.
- Avoid high-volume scraping or full-register replication. Use narrow queries and small limits.
- Do not use authenticated MyNZBN endpoints, account actions, watchlists, authority requests, update flows, cookies, or private data.
- Public register fields can change or be suppressed; treat output as a live snapshot and cite the NZBN/source where relevant.
