# Open Food Facts source notes

- Publisher: Open Food Facts
- Primary source: https://world.openfoodfacts.org
- API introduction: https://openfoodfacts.github.io/openfoodfacts-server/api/
- Declared outbound host: world.openfoodfacts.org
- Authentication: none. Reads are keyless. Writes, accounts, and session cookies are out of scope.
- User-Agent: `TheColabSkills/1.0 (+https://github.com/thecolab-ai/.skills)`
- Last verified: 2026-10-11

The documentation asks for `AppName/Version (ContactEmail)`. This skill identifies
TheColabSkills and the public repository URL, and does not embed a private contact
address or secret.

## Verified reads

On 2026-10-11, `GET /api/v3/product/{barcode}.json` on `world.openfoodfacts.org`
returned HTTP 200 with a string `status` of `success`, `result.id` of
`product_found`, and a `product` object. That is the v3 envelope. API v2's integer
`status` of `1` is a different, deprecated shape and is rejected as a schema failure.

An unknown barcode returned HTTP 404 with `status` `failure` and `result.id`
`product_not_found`. HTTP success is not treated as a product, and HTTP 404 with
that result is an empty successful lookup. HTTP 429 is rate limiting. HTTP 503 and
timeouts are upstream unavailability. A redirect whose host is not `world.openfoodfacts.org` is refused before it is followed.
On 2026-10-11, barcode `8710447445990` did not redirect in the response body we could
read: HTTP 404, `status` `failure`, and `result.id`
`product_found_with_a_different_product_type`. That is exit 7. Open Products Facts,
Open Beauty Facts, and the other project hosts are separate APIs and are not requested.

`last_modified_t`, when the source sends a unix second timestamp, is copied to
`latest_data` as UTC. It is the product record's stated update time, not the
retrieval time. Retrieval time is `meta.retrieved_at`.

The v3 route used here is the documented product read. The introduction lists v3
(latest sub-version v3.6) as the version for new integrations. This skill does not
call a fictional v3 search API.

Live checks on 2026-10-11: barcode `3017624010701` returned `product_name` Nutella,
brand Ferrero, and no `nova_group` (`missing_fields`). Its `last_modified_t` was
`2026-10-02T17:52:32Z`. Barcode `1234567890128` returned HTTP 404 with
`product_not_found` and an empty result list. The New Zealand yogurts search above,
with `page_size=1`, returned one row and a source count. The 404 body is gzip
compressed; the client decompresses it before reading `status`.

Structured search was verified the same day:

`GET /api/v2/search?countries_tags=en:new-zealand&categories_tags=en:yogurts&page_size=2&fields=code,product_name,brands,countries_tags`

The body has `count`, `page`, `page_size`, and `products`. v3 does not offer this
search. Full-text search (`/cgi/search.pl` and Search-a-licious) is not implemented.

## Rate limits

The API introduction states:

- 15 requests per minute per IP for product reads (`GET /api/v*/product`)
- 10 requests per minute per IP for search (`GET /api/v*/search` or `GET /cgi/search.pl`)

Each command performs one request, with a 10 second timeout and a 256 KiB cap.
There is no crawl, no pagination loop, and no image download. A 429 keeps the
upstream `Retry-After` value in `error.retry_after` when the source sends one.

## Fields

Product reads request only: `code`, `product_name`, `brands`, `quantity`,
`categories_tags`, `countries_tags`, `ingredients_text`, `nutriscore_grade`,
`nova_group`, `allergens_tags`, `labels_tags`, and `last_modified_t`.
Tag lists are capped at 12 values. Ingredient text is capped at 400 characters.
Absent optional fields are named in `missing_fields`. Nutri-Score and NOVA are
published product attributes, not a personal health assessment. Nutrition tables
and knowledge panels are not requested.

Search requests `code`, `product_name`, `brands`, `categories_tags`, and
`countries_tags` for the first page only. `--limit` is the `page_size` (1 to 10).

Barcodes are sent as digit strings. Leading zeros are not converted with a
numeric cast. If the source normalises a code, the submitted digits stay in
`code` and `requested_code`, and the source value is `source_code`. A probe of
`0000000000000` produced `different_normalized_product_code` and a shortened code;
that response is a not-found result, not a rewritten barcode.

## Licence and share-alike

The database is under the Open Database License (ODbL). Individual contents are
under the Database Contents License (DbCL). Product images are under Creative
Commons Attribution-ShareAlike (CC BY-SA), and some pictures may also carry
separate pictorial rights. This skill does not download images.

The skill's MIT code licence is not the data licence. Publishing a substantial
extract or a derived database can trigger ODbL share-alike. Bounded lookups in
this tool are not a database mirror. Attribute Open Food Facts and
https://world.openfoodfacts.org when reusing records.

## Errors

| Condition | Exit | `error.type` |
|---|---:|---|
| Malformed barcode, bad limit, bad tag | 2 | `invalid_input` |
| HTTP 429 or a block | 4 | `blocked` |
| HTTP 503, timeout, other transport loss | 5 | `upstream_unavailable` |
| Malformed JSON, excessive nesting, unexpected envelope | 6 | `schema_failure` |
| Off-host redirect or non-allowlisted URL | 7 | `unsupported_operation` |

`--fixture` reads one named file in `tests/fixtures/` for contract tests. Those
results are marked as fixtures and are not live source data.
