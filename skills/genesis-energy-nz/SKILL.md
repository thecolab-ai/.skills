---
name: genesis-energy-nz
description: "Get electricity use and usage costs from your Genesis Energy NZ account. Use for hourly readings, daily totals, or a summary of up to 31 days."
license: MIT
metadata:
  thecolab.category: "energy"
  thecolab.source_owner: "Genesis Energy"
  thecolab.source_type: "commercial"
  thecolab.auth: "mixed"
  thecolab.access_mode: "authenticated-personal"
  thecolab.data_class: "personal"
  thecolab.writes: "false"
  thecolab.browser: "false"
  thecolab.risk: "high"
  thecolab.cache_ttl: "none"
  thecolab.schema_version: "1"
  thecolab.skill_type: "authenticated-personal"
  thecolab.pack: "nz-personal-data"
  thecolab.source_url: "https://myaccount.genesisenergy.co.nz"
  thecolab.allowed_domains: "auth.genesisenergy.co.nz,web-api.genesisenergy.co.nz,myaccount.genesisenergy.co.nz"
  thecolab.last_verified: "2026-10-31"
  thecolab.health: "gated"
  thecolab.maintainer: "@jameshulse"
---

# Genesis Energy NZ

See how much electricity you have used and the usage costs Genesis reports for
your account. Get hourly readings, daily totals or a summary for a chosen period.

## What it retrieves

| Data | What you get |
| --- | --- |
| Electricity use | kWh for each completed hour |
| Usage costs | The NZD cost Genesis reports for those hours |
| Summaries | Daily totals or a total for a chosen period of up to 31 days |
| Latest reading | When the newest supplied hour started |
| Completeness | How many requested hours were supplied or are still missing |

## Example

Made-up data from the synthetic test fixture; no real account information:

| Hour starting (NZ time) | Electricity use | Usage cost |
| --- | ---: | ---: |
| 1 Jan 2024, 00:00 | 0.10 kWh | NZ$0.03 |
| 1 Jan 2024, 01:00 | 0.20 kWh | NZ$0.06 |

**Summary:** 0.30 kWh and NZ$0.09 across 2 of the day's 24 hours. The latest
reading starts at 01:00 NZDT. **22 hours are missing, so this is a partial total.**

<details>
<summary>Example JSON summary record</summary>

The same example as one record in the JSON `results` array:

```json
{
  "start_date": "2024-01-01",
  "end_date": "2024-01-01",
  "timezone": "Pacific/Auckland",
  "expected_intervals": 24,
  "received_intervals": 2,
  "missing_intervals": 22,
  "coverage": "incomplete",
  "latest_interval_start": "2024-01-01T01:00:00+13:00",
  "observed_usage_kwh": "0.30",
  "observed_usage_cost_nzd": "0.09"
}
```

</details>

Usage costs cover the readings Genesis supplies. They are not a tariff quote or
a complete bill; tax, fixed charges and discount coverage still need confirmation.

## Setup

Requires a Genesis account, Python 3.10+ and IANA timezone data.
Uses only the Python standard library.
This community skill connects to the Genesis My Account website endpoints.

## Access and privacy

- Use only when the user authorises reading their own Genesis account.
- The user supplies `GENESIS_EMAIL` and `GENESIS_PASSWORD` out of band through
  the environment. Do not ask them to paste credentials into chat or put them
  in command arguments, source files, logs, fixtures, or commits.
- Both credentials are required. There is no separate developer API key or paid
  API subscription in this implementation; an accessible Genesis account is needed.
  Example variable names for a private environment file are `GENESIS_EMAIL` and
  `GENESIS_PASSWORD`; provision their values privately and never commit that file.
  The CLI does not automatically load environment files or existing application credentials.
- Authentication goes directly to Genesis. Cookies and tokens are kept only
  in memory. No external proxy service, telemetry, disk cache or credential store.
- Treat returned usage and costs as private household data. Avoid shared logs,
  issues and PRs; if saving output, use an owner-only path.
- A challenge, rejected login, rate limit, changed schema or failed chunk stops
  the invocation. Do not automate CAPTCHA/MFA, repeatedly retry, or bypass controls.

## Commands

After the user has privately populated the two environment variables:

```bash
python3 skills/genesis-energy-nz/scripts/cli.py usage --start 2024-01-01 --end 2024-01-02 --json
python3 skills/genesis-energy-nz/scripts/cli.py summary --start 2024-01-01 --end 2024-01-31 --group day --json
python3 skills/genesis-energy-nz/scripts/cli.py summary --start 2024-01-01 --end 2024-01-31 --group range --json
```

Substitute the requested dates. Dates are inclusive in `Pacific/Auckland`,
limited to 31 days per invocation, and cannot extend beyond today. Reads use
inclusive two-date chunks, one second apart. Query on demand; do not poll more
than hourly. Older date availability is controlled by Genesis and not guaranteed.

`usage` returns completed hourly intervals. `summary` returns one record per NZ
calendar day, or one for the whole range. Both accept `--json`; without it they
print a coverage header and readable records. The common repo runner also works.

## Interpretation

- `usage_cost_nzd` is the provider's `costNZD` for that interval. These are
  observed usage costs, not tariff quotes, invoices, balances or a complete bill.
  GST, fixed charges, discounts and fee inclusion have not been established.
- The provider field `kw` is interpreted as interval kWh, following the upstream
  integration. Confirm against My Account before relying on totals.
- `observed_*` sums include only supplied completed intervals. Missing intervals
  never become zero. An empty period has null totals and `no_readings`.
- Coverage compares received hours with the **entire requested date range**;
  provider lag and the unfinished part of today therefore remain missing. Report
  `coverage`, `missing_intervals` and `latest_interval_start` with any total.
- The upstream endpoint implicitly selects a site. This version cannot list or
  select sites; use only where that default is the intended site.
- Only electricity is implemented. There are no gas, invoice, payment, profile,
  tariff-change or generic endpoint commands.

## Verification and resources

- `scripts/cli.py`: canonical entrypoint; JSON uses the provenance helpers in
  `scripts/provenance.py` with static error messages and stable exit codes.
- `scripts/genesis.py`: fixed-destination authentication and electricity reads.
- `scripts/usage.py`: strict field selection, intervals and NZ coverage handling.
- `scripts/test_contract.py` and `scripts/smoke_test.py`: offline synthetic checks;
  neither authenticates or reads personal data, even when credentials are set.
- `tests/fixtures/`: hand-authored synthetic data, never captured account responses.
- [Source notes](references/source-notes.md): protocol, units, error and provenance
  details, licence attribution, and the current live-verification limitation.
