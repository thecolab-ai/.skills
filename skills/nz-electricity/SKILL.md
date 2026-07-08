---
name: nz-electricity
description: Query NZ electricity market data: EM6 wholesale spot prices, grid demand, carbon intensity, historical nodal prices, monthly generation by fuel type, distributed-generation solar uptake, gentailer energy-margin source status, and NZ lines-company outage records. No login or API key.
---

# NZ Electricity

## Goal

Query New Zealand electricity-market and outage information through a small deterministic CLI with human-readable and JSON output, without browser automation, login, private API keys, or local cache state.

This skill ships support for:

- EM6 current regional wholesale spot prices
- EM6 current NZ carbon intensity and renewable percentage
- Electricity Authority EMI trading-period grid demand by New Zealand or zone region
- Electricity Authority EMI final/interim historical energy prices by point of connection
- Electricity Authority EMI monthly generation output by plant, aggregated by fuel type
- Electricity Authority EMI installed distributed-generation trends, including rooftop solar uptake
- Electricity Authority gentailer energy-margin official-source availability checks
- Public outage feeds for supported NZ lines companies

## Use this when

- A user asks for current wholesale electricity spot prices in New Zealand
- A user asks for NZ grid demand or demand by EMI zone
- A user asks for current NZ grid carbon intensity or renewable percentage
- A user wants historical wholesale spot prices for a node or point of connection
- A user wants monthly NZ generation output by fuel type or generation plant
- A user wants installed distributed-generation or rooftop-solar trends by market segment or capacity band
- A user asks for gentailer energy-margin data and needs to know whether the official Authority source currently exposes machine-readable rows
- A user asks for current or planned public outages from supported NZ lines companies
- A workflow needs public, no-login, machine-readable NZ electricity data

## Do not use this for

- Retail plan comparison, tariff advice, Powerswitch-style savings, or ICP-specific billing questions
- Authenticated EMI API products, EM6 paid feeds, private user data, or account actions
- Current real-time node load, current node generation, or current generation mix; the documented EM6 endpoints for those returned unauthorized in live testing
- Reconstructing gentailer energy margins from spot prices, generation volumes, hedge positions, or retail demand; the `energy-margin` command reports official source availability only until a public official dataset exists
- ICP-specific outage status, outage subscriptions, outage reporting, or fault logging
- Redistributing public-data extracts as a standalone dataset

## Preferred workflow

1. Run `scripts/cli.py` with the narrowest subcommand that answers the task
2. Use `spot --region` for live regional wholesale price snapshots
3. Use `demand --region` for national or EMI zone-level grid demand
4. Use `prices --node ... --from ... --to ...` for historical nodal prices
5. Use `generation --month ... --type ...` for generation by fuel type from EMI monthly data
6. Use `dg-trends`, `dg-latest`, or `dg-summary` for installed distributed-generation and rooftop-solar EMI retail report data
7. Use `energy-margin --json` when a task needs the current official status of the Authority gentailer energy-margin source
8. Use `outages --company ...` or `outages --region ...` for lines-company public outage records
9. Use `--json` when another tool or agent needs machine-readable output
10. Mention the upstream source and whether the value is current EM6 data, EMI report/dataset data, EMI retail report data, Authority dashboard status, or a distributor outage feed

## CLI

Run with:

```bash
python3 skills/nz-electricity/scripts/cli.py <command> [flags]
```

## Commands

- `spot [--region REGION] [--json]` — current EM6 regional wholesale spot prices in $/MWh
- `carbon [--json]` — current EM6 NZ carbon intensity and renewable percentage
- `demand [--region REGION] [--from DATE] [--to DATE] [--json]` — EMI trading-period grid demand for New Zealand or an EMI zone
- `prices --node NODE [--from DATE] [--to DATE] [--json]` — EMI historical final/interim energy prices for a point of connection
- `generation [--month YYYY-MM] [--type fuel] [--limit N] [--json]` — EMI monthly generation output by fuel type and plant
- `dg-trends [--fuel solar_all] [--market-segment All|Res|SME|Com|Ind] [--capacity All_Total|Small|Large] [--region-type NZ|ZONE|...] [--from DATE] [--to DATE] [--json]` — EMI GUEHMT installed distributed-generation trends
- `dg-latest [--fuel solar_all] [--market-segment All|Res|SME|Com|Ind] [--capacity All_Total|Small|Large] [--region-type NZ|ZONE|...] [--json]` — latest GUEHMT distributed-generation rows
- `dg-summary [--fuel solar_all] [--market-segment All|Res|SME|Com|Ind] [--capacity All_Total|Small|Large] [--region-type NZ|ZONE|...] [--from DATE] [--to DATE] [--yearly] [--json]` — summarise GUEHMT distributed-generation trends
- `energy-margin [--company COMPANY] [--from DATE] [--to DATE] [--json]` — probe the official EA gentailer energy-margin dashboard/article and report whether machine-readable rows are currently available
- `outages [--company COMPANY] [--region REGION] [--all] [--json]` — current public outage records from supported NZ lines companies; `--all` also includes planned, scheduled, or recent records where feeds expose them

Examples:

```bash
python3 skills/nz-electricity/scripts/cli.py spot --region auckland
python3 skills/nz-electricity/scripts/cli.py spot --json
python3 skills/nz-electricity/scripts/cli.py carbon --json
python3 skills/nz-electricity/scripts/cli.py demand --region UNI --from 2026-05-22 --to 2026-05-22 --json
python3 skills/nz-electricity/scripts/cli.py prices --node BEN2201 --from 2026-05-20 --to 2026-05-20 --json
python3 skills/nz-electricity/scripts/cli.py generation --month 2026-04 --type hydro --limit 5 --json
python3 skills/nz-electricity/scripts/cli.py dg-trends --fuel solar_all --market-segment Res --capacity All_Total --from 2025-01-01 --to 2025-12-31 --json
python3 skills/nz-electricity/scripts/cli.py dg-latest --fuel solar_all --market-segment All --json
python3 skills/nz-electricity/scripts/cli.py dg-summary --fuel solar_all --yearly --json
python3 skills/nz-electricity/scripts/cli.py energy-margin --company meridian --json
python3 skills/nz-electricity/scripts/cli.py outages --company vector
python3 skills/nz-electricity/scripts/cli.py outages --region tahawai --json
```

## Resources

- CLI entrypoint: `scripts/cli.py`
- API and dataset notes: `references/api-notes.md`

## Notes

- No private API key, username, password, cookie, or browser session is required for implemented commands
- `spot` and `carbon` use EM6 public free JSON feeds from `https://api.em6.co.nz/ords/em6/data_api`
- `demand` uses the public Electricity Authority EMI Demand trends CSV report from `https://www.emi.ea.govt.nz/Wholesale/Reports/W_GD_C`
- `prices` and `generation` use public Electricity Authority EMI CSV dataset files from `https://www.emi.ea.govt.nz`
- `dg-trends`, `dg-latest`, and `dg-summary` use the public Electricity Authority EMI GUEHMT retail CSV report from `https://www.emi.ea.govt.nz/Retail/Reports/guehmt`
- `energy-margin` probes the Electricity Authority energy-margin dashboard/article and linked Tableau public workbook; it returns explicit source-unavailable status while those public official surfaces do not expose machine-readable per-company rows
- `outages` uses clean public distributor feeds for Vector, Wellington Electricity, Orion, Powerco, Aurora Energy, WEL Networks, Unison, Counties Energy, and Top Energy
- Vector's public map exposes outage shapes only, so Vector records may only have an approximate centroid and outage type
- Northpower was checked but not shipped because its outage map uses Livewire snapshot/update state rather than a clean stable public JSON feed
- EM6 regional spot prices are current dispatch-price snapshots and may update every five minutes
- EMI demand is trading-period report data in GWh; current-day data may be partial and recent periods can use final-pricing proxy conventions described by EMI
- EMI final/interim energy prices are half-hourly by point of connection; recent files may be interim until finalized
- EMI generation output by plant is monthly and historical, not current real-time generation mix
- EMI distributed-generation trends are monthly retail report data derived from registry fields; market segments are not mutually exclusive, and Solar+Batteries category changes in November 2023 can create Solar/Other series breaks
- Gentailer energy-margin values are not reconstructed or copied into this skill; use the `energy-margin` status payload to show whether the official Authority surface is currently machine-readable
- Distributor outage feeds vary by company and may omit cause, customer count, or restoration time
- Default output is human-readable; every data command supports `--json` for chaining into other tools
- Avoid high-volume polling; use narrow regions, nodes, date ranges, and months
