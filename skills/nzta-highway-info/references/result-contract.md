# Normalised result contract

Every successful `--json` command returns:

```json
{
  "schema_version": "1",
  "ok": true,
  "kind": "events",
  "source": {
    "name": "NZ Transport Agency Waka Kotahi Traffic and Travel API",
    "url": "https://trafficnz.info/service/traffic/rest/4/events/all/10",
    "catalogue_url": "https://catalogue.data.govt.nz/dataset/nzta-highway-information1",
    "contract_url": "https://trafficnz.info/service/traffic/rest/4?_wadl",
    "retrieved_at": "2026-09-03T08:50:54Z",
    "latest_item_update_at": "2026-09-03T20:19:34.857+12:00"
  },
  "query": {},
  "data": [],
  "returned": 0,
  "source_count": 0,
  "truncated": false,
  "complete": false,
  "warnings": [],
  "blocked": false
}
```

`source_count` is the collection size returned by the single upstream call.
`returned` is the locally filtered/capped size. `truncated` means the returned
list is smaller than the upstream collection; filters and limits can both cause
it. `complete` is deliberately always false because the source does not warrant
complete operational or safety coverage.

## Event items

- `id`
- `type`, `description`, `comments`, `location`, `impact`, `status`
- `planned`
- `start_at`, `end_at`, `expected_resolution`, `last_updated_at`
- `alternative_route`
- `region`, `highway`
- `geometry_wkt`

Dates are preserved as source strings. The client does not guess a timezone or
rewrite fuzzy expected-resolution text.

The source `planned` field is required and accepts the same strict boolean forms
as camera state. Missing, null, or malformed values fail closed.

Event, camera, VMS, and travel-time sign `id` values must be non-empty strings or
integers. Missing, boolean, fractional, object, list, or blank identifiers are
source-schema failures rather than normalised nulls.

When an event, camera, VMS, or travel-time sign includes a region object, its
`id` follows the same identifier rules. Region-list item IDs do too.

## Camera items

- `id`, `name`, `description`, `direction`, `region`, `highway`
- `latitude`, `longitude`
- `status`: `online`, `maintenance`, or `offline`
- `offline`, `under_maintenance`
- `image_url`, `thumbnail_url`, `view_url`
- `last_updated_at`: always null unless the upstream contract adds a supported
  timestamp

Relative image paths are resolved only against `trafficnz.info`. An unexpected
host is a schema failure rather than an open redirect. `online` means the source
flags neither offline nor under maintenance; it does not prove the image is
recent, visible, or accurate.

Both `offline` and `under_maintenance` are required source states. Their accepted
source representations are booleans, integer `0`/`1`, or strings `false`/`true`
and `0`/`1`. Missing, null, or malformed states fail closed; they never default
to `online`.

## VMS items

- `id`, `name`, `description`, `direction`, `region`, `highway`
- `latitude`, `longitude`
- `message`: newline-joined display text
- `message_lines`: `[nl]` and `[np]` source markers split into ordered lines/pages
- `last_message_update`, `last_updated_at`

An empty message is preserved as an empty list/null, not interpreted as a safe or
clear route.

## Travel-time sign items

- `id`, `name`, `region`, `highway`, coordinates
- `enabled`, `mode`, `virtual`
- `pages`: source sign lines with scalar values only
- `destinations`: lines with a text `left` label and numeric `right` value,
  normalised to `{name, minutes}`
- `last_updated_at`: the source `timeStamp` when present
- `congestion_status`: always null
- `source_provides_baseline`: always false

A numeric right-hand sign value is treated as displayed minutes. No comparison to
normal/free-flow time is made.

The source `enabled` and `virtual` fields are required and accept the same strict
boolean forms as camera state. Missing, null, or malformed values fail closed
rather than defaulting to `false`.

## Region items

- `id`
- `name`

Large region geometry is intentionally omitted.

## Failure envelope

Expected failures return one stable exit code and no Python traceback:

```json
{
  "schema_version": "1",
  "ok": false,
  "kind": "events",
  "source": {
    "name": "NZ Transport Agency Waka Kotahi Traffic and Travel API",
    "url": "https://trafficnz.info/service/traffic/rest/4/events/all/10",
    "catalogue_url": "https://catalogue.data.govt.nz/dataset/nzta-highway-information1",
    "contract_url": "https://trafficnz.info/service/traffic/rest/4?_wadl",
    "retrieved_at": "2026-09-03T10:00:00Z",
    "latest_item_update_at": null
  },
  "query": {
    "region": null,
    "text": null,
    "event_type": null,
    "active_only": false,
    "limit": 20
  },
  "error": {
    "code": 5,
    "category": "upstream_unavailable",
    "message": "upstream response interrupted: ..."
  },
  "data": null,
  "warnings": [],
  "blocked": false
}
```

Argument parse failures requested with `--json` use the same envelope; typed
query fields that were not successfully parsed are null.

`error.category` is `invalid_input`, `blocked`, `upstream_unavailable`, or
`source_schema`, matching exit codes 2, 4, 5, and 6 respectively.

Exit codes follow `docs/contracts.md`: 2 invalid input, 4 blocked/rate-limited,
5 upstream unavailable, and 6 source schema/parser failure.

Source JSON is decoded strictly: `NaN`, `Infinity`, `-Infinity`, and non-finite
numbers at any nested depth are exit-6 schema failures. Successful and failure
envelopes are serialised with `allow_nan=false`, so emitted JSON is RFC-compatible.
