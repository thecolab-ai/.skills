# CKAN actions

Both actions are GET requests under `https://data.gov.au/data/api/3/action/`.

## package_show

Query: `id=559708e5-480e-4f94-8429-c49571e82761`.

A usable body has `success: true` and an object `result` whose `id` is that
package. The organisation title is `result.organization.title`. Licence fields
are `license_id`, `license_title` and `license_url`. The package timestamp is
`metadata_modified`. `resources` is a list. Each resource needs a lowercase
UUID `id`, a non-empty `name`, and boolean `datastore_active`. `format` and
`last_modified` are text or null. `size` is a non-negative integer or null.

## datastore_search

Query: `resource_id` of one active resource from this package, and `limit`
from 1 to 20. No `offset`, `q`, `filters` or SQL is sent.

A usable body has `success: true`, integer `total` of at least 0, and a
`records` list no longer than `limit`. Each record is an object and is emitted
unchanged. `total` 0 with an empty list is an empty preview. `total` greater
than 0 with an empty list, or a list longer than `limit`, is a schema failure.

HTTP 429 is exit 4. HTTP 503 and other HTTP 5xx responses, timeouts and
transport failures are exit 5. Other HTTP statuses, non-JSON bodies and bodies
over 524288 bytes are exit 6. A redirect whose host, scheme or port leaves
`https://data.gov.au` is exit 7 and is not followed.
