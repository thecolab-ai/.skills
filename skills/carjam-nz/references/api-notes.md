# CarJam NZ access restriction

## Current behaviour

`lookup` and `batch` do not retrieve vehicles. After local identifier checks they exit:

| Case | Exit | `error.type` |
|---|---:|---|
| Empty or overlong identifier | 2 | `invalid_input` |
| Any otherwise valid live lookup or batch | 4 | `blocked` |

The blocked message says live retrieval is access restricted pending a permitted API or provider agreement, and that this skill is not a dependable keyless connector.

`--json` prints one object:

```json
{
  "meta": {
    "source_url": "https://www.carjam.co.nz",
    "publisher": "CarJam",
    "retrieved_at": "2026-10-12T00:00:00Z"
  },
  "results": [],
  "error": {
    "code": 4,
    "type": "blocked",
    "message": "CarJam live vehicle retrieval is access restricted pending a permitted API or provider agreement."
  }
}
```

`retrieved_at` is the refusal time, not a retrieval time. `results` stays empty. Human output uses the same message on stderr and does not print a vehicle summary.

The common runner wraps that payload as `ok: false`, `blocked: true`, and `error.code: 4`.

## Why live HTML retrieval stopped

- Robots rules for `www.carjam.co.nz` disallow `/car/`.
- The site terms restrict screen scraping and automated reuse, and the API terms require a provider agreement.
- Smoke run 38192832106 failed `lookup` and `batch` for plate `PSP532` with `no public vehicle fields found for plate 'PSP532'`. The skill diff between the last pass and that failure was empty.
- A later direct `/car/` response from the repair lane was HTTP 403 challenge HTML. This skill does not request that path again and does not treat either body as a vehicle.

Reclassifying every CarJam-branded page with no free fields as a temporary outage would hide that hard parser failure. The offline parser still keeps it.

## Offline parser

Saved HTML can still be parsed by `parse_vehicle` in tests. It reads `data-key` rows and report-gate markers such as `Get Report`, `May be in Report`, and `Subscribe`. That function is not a command and does not fetch.

Synthetic fixture files live in `tests/fixtures/`. They are not live CarJam responses and must not be presented as current vehicle records.

## Out of scope until an agreement exists

- Developer Connection API calls
- Credential prompts or stored tokens
- Browser, cookie, or challenge workarounds
- Owner and personal-information fields
- Report purchase, accounts, and write actions
