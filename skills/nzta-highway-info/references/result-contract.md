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
  "error": {"code": 5, "message": "upstream unavailable or timed out: ..."},
  "data": null,
  "warnings": [],
  "blocked": false
}
```

Exit codes follow `docs/contracts.md`: 2 invalid input, 4 blocked/rate-limited,
5 upstream unavailable, and 6 source schema/parser failure.
