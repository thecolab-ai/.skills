# Public Trust grants NZ API notes

This skill is an unofficial read-only wrapper around the public grants finder at `publictrust.co.nz`.

## Source and auth

- Website: `https://www.publictrust.co.nz/grants/?query=&type=organisation`
- Public Algolia app id observed: `00GCMOPT4B`
- Public grants index: `prod_publictrust_grants`
- Auth model for this skill: none for read-only search/detail requests

The CLI does not commit the public search-only key. It fetches the grants page, parses the current Nuxt public configuration (`algoliaAppId`, `algoliaApiKey`, and `algoliaGrantsIndex`), and then queries Algolia. If Public Trust removes or changes that config, the CLI returns a clear error rather than pretending results are complete.

No username, password, account cookie, private token, browser session, application submission, or form mutation is required for the implemented operations.

## Endpoint used

- `GET https://www.publictrust.co.nz/grants/?query=&type=organisation` to read current public configuration
- `POST https://{app_id}-dsn.algolia.net/1/indexes/*/queries` for search/list/facet-style discovery
- `GET https://{app_id}-dsn.algolia.net/1/indexes/{index}/{objectID}` for exact detail lookup

## Record fields observed

The grants index currently returns compact records with fields such as:

- `title`
- `uri`
- `keywords`
- `grants_regions`
- `sectors`
- `grant_type`
- `applications_open_now`
- `applications_open_date`
- `excerpt`
- `distinctObjectID`
- `objectID`

The CLI normalises those into `id`, `distinct_id`, `slug`, `title`, `url`, `grant_type`, `regions`, `sectors`, `applications_open_now`, `applications_open_date`, `excerpt`, and `keywords`.

## Commands and query shape

Search sends an Algolia multi-query request with URL-encoded parameters such as:

```json
{
  "requests": [
    {
      "indexName": "prod_publictrust_grants",
      "params": "query=youth&hitsPerPage=10&page=0&facetFilters=%5B%5C%22grant_type%3Aorganisation%5C%22%5D"
    }
  ]
}
```

Supported filters map to current Algolia attributes:

- `--region VALUE` -> `grants_regions:VALUE`
- `--sector VALUE` -> `sectors:VALUE`
- `--type VALUE` -> `grant_type:VALUE`
- `--open-only` / `list-open` -> `applications_open_now:true`

Use `sectors --json` and `regions --json` to inspect exact values observed in the current index before applying filters.

## Stability and safety

- The Algolia key is a public browser search-only key and may rotate.
- Index names and record fields can change because this is not an official API contract.
- Open/closed status and open-date text are current only at fetch time.
- The finder is Public Trust-specific; it is not exhaustive NZ grant coverage.
- Machine-readable access does not imply an open data licence or permission to redistribute a bulk dataset.
- Keep use read-only and respectful; do not submit enquiries/applications, bypass login, or scrape protected areas.
