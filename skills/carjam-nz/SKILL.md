---
name: carjam-nz
description: "Report CarJam NZ vehicle lookup as access restricted. Use when a task asks for a New Zealand plate, VIN, or chassis, make, model, year, or a CarJam source URL. This is not a dependable keyless connector: live vehicle retrieval requires a permitted CarJam API or provider agreement and is refused with a blocked result. Offline HTML fixtures remain for parser coverage only. Read-only; no scraping, challenge bypass, paid report purchase, owner lookup, login, or write actions."
license: MIT
compatibility: "Requires Python 3.10+. Live vehicle retrieval is access restricted and does not use the network."
metadata:
  thecolab.category: "public-data"
  thecolab.source_owner: "CarJam"
  thecolab.source_type: "commercial"
  thecolab.auth: "none"
  thecolab.access_mode: "access-restricted"
  thecolab.data_class: "public"
  thecolab.writes: "false"
  thecolab.browser: "false"
  thecolab.risk: "low"
  thecolab.cache_ttl: "none"
  thecolab.schema_version: "1"
  thecolab.skill_type: "html-readonly"
  thecolab.pack: "nz-commercial-web"
  thecolab.source_url: "https://www.carjam.co.nz"
  thecolab.allowed_domains: "www.carjam.co.nz"
  thecolab.last_verified: "2026-10-12"
  thecolab.health: "gated"
  thecolab.maintainer: "@adam91holt"
---

# CarJam NZ

## Goal

Tell the caller that CarJam live vehicle retrieval is access restricted. This skill is not a dependable keyless connector. `lookup` and `batch` return the repository blocked result and do not contact CarJam.

A permitted CarJam API or provider agreement is required before any live vehicle retrieval can be added. This copy does not implement that API and does not hold an agreement.

## Use this when

- A user asks for CarJam details for a New Zealand plate, VIN, or chassis
- A workflow needs an honest machine-readable refusal instead of a guessed vehicle
- Someone needs to confirm that keyless HTML retrieval is not the supported path

## Do not use this for

- Live plate, VIN, or chassis retrieval, including retries against `/car/`
- Browser automation, cookies, or challenge solving
- Paid report purchase, checkout, subscription, login, or account actions
- Owner name or address lookup, or any write action
- Treating a previous public snippet, or an offline fixture, as a current vehicle record

## Preferred workflow

1. Run `lookup` or `batch`. Expect exit code 4 and error type `blocked`.
2. Tell the user that live retrieval needs a permitted CarJam API or provider agreement.
3. Do not work around the refusal with another host, a browser, or a cached vehicle.
4. Use the offline parser only on the synthetic fixtures in this skill.

## CLI

Run with:

```bash
python3 skills/carjam-nz/scripts/cli.py <command> [flags]
```

### Commands

- `lookup <identifier> [--type plate|vin|chassis] [--json] [--raw]` — refuse one live lookup
- `batch <identifier...> [--type plate|vin|chassis] [--json]` — refuse a live batch

Both commands validate the identifier locally, then refuse. `--json` prints `meta`, an empty `results` array, and `error`. Human output prints the same refusal on stderr. Invalid identifiers exit 2 with type `invalid_input`. Neither command exits 0 for a vehicle query.

Examples:

```bash
python3 skills/carjam-nz/scripts/cli.py lookup ABC123 --json
python3 skills/carjam-nz/scripts/cli.py batch ABC123 KMM42 --json
```

## Resources

- CLI entrypoint: `scripts/cli.py`
- Smoke test: `scripts/smoke_test.py`
- Source notes: `references/source-notes.md`
- Restriction notes: `references/api-notes.md`

## Notes

- Declared health is `gated`. Smoke records the restriction as a skip plus fixture and contract checks, not as a live vehicle pass.
- The 12 October 2026 live failure `no public vehicle fields found for plate 'PSP532'` stays a recorded failure. It is not reclassified as a successful lookup or as a temporary outage.
- Offline parsing of synthetic HTML remains covered. A saved CarJam shell with no public fields is still a hard parser failure.
- Authentication stays `none` because this skill does not collect or send a credential. Lack of a credential is not success.
