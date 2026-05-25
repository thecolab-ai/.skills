---
name: petrolmate-nz-au
description: Query live AU & NZ fuel prices from petrolmate.com.au's public API. Search stations near any AU or NZ location, filter by 9 fuel types, sort by price or distance. Covers AU state FuelCheck data and NZ Gaspy data. No API key or authentication required.
---

# PetrolMate (AU + NZ)

## Goal

Query live AU and NZ fuel prices from petrolmate.com.au's public API through a lightweight CLI. Covers Australian state fuel data (NSW/QLD/VIC/SA/TAS FuelCheck) and NZ crowd-sourced data (Gaspy). No authentication required.

## Use this when

- A user asks for current fuel prices at a specific AU or NZ location
- A user wants the cheapest fuel type near them ("cheapest 95 near St Heliers")
- A user wants to compare fuel prices across stations in an area
- A user asks "where's the cheapest diesel near me?"
- A user wants to filter by brand (Shell, BP, Z, NPD, etc.)
- The Gaspy authenticated API or PetrolSpy is unavailable, or the user wants official FuelCheck data for AU

## Do not use this for

- National average prices (use `gaspy-nz summary` for NZ, no AU equivalent via PetrolMate)
- Fuel supply, vessel tracking, or geopolitical risk (use `fuelclock-nz`)
- Historical price trends or charts
- User-reported Gaspy station search (use `gaspy-nz` stations or `petrolspy-nz`)

## Preferred workflow

1. Run `search --location "st heliers" --fuel PULP95` for a location-based price comparison
2. Use `--radius 10` to widen the search, `--radius 3` to tighten
3. Use `--brand Shell` to filter to a specific brand
4. Use `--sort distance` when you care about proximity over price
5. Use `--json` for machine-readable output or piping to jq
6. Note that not all fuel types are available in all regions — NSW FuelCheck only reports ULP, E10, LPG, E85

## CLI

Run with:

```bash
python3 skills/petrolmate-nz-au/scripts/cli.py <command> [flags]
```

### `search`

Search for stations near a location.

```bash
# By named location (from built-in lookup or PetrolMate geocoding)
python3 skills/petrolmate-nz-au/scripts/cli.py search --location "st heliers"

# Filter by fuel type, sorted cheapest first
python3 skills/petrolmate-nz-au/scripts/cli.py search --location "st heliers" --fuel PULP95

# Wider radius, filter by brand
python3 skills/petrolmate-nz-au/scripts/cli.py search --location "auckland" --fuel DIESEL --radius 10 --brand Z

# Custom coordinates
python3 skills/petrolmate-nz-au/scripts/cli.py search --lat -33.86 --lon 151.20 --fuel PULP98 --json

# IP-based location
python3 skills/petrolmate-nz-au/scripts/cli.py search --geoip --fuel ULP --radius 3

# Australian address (PetrolMate geocodes it)
python3 skills/petrolmate-nz-au/scripts/cli.py search --location "Brisbane QLD" --fuel DIESEL
```

### `locations`

List built-in location names:

```bash
python3 skills/petrolmate-nz-au/scripts/cli.py locations
```

### `fuel-types`

List available fuel types:

```bash
python3 skills/petrolmate-nz-au/scripts/cli.py fuel-types
```

## Fuel Type Codes

| Code | Description |
|------|-------------|
| ULP | Unleaded 91 |
| E10 | E10 (Ethanol 10%) |
| PULP95 | Premium 95 |
| PULP98 | Premium 98 |
| PREMIUM | Premium (95+98) |
| DIESEL | Diesel |
| PDIESEL | Premium Diesel |
| LPG | LPG/Autogas |
| E85 | E85 (Ethanol 85%) |

## Resources

- CLI entrypoint: `scripts/cli.py`
- API notes and data sources: `references/api-notes.md`

## Notes

- PetrolMate aggregates official (AU) and crowd-sourced (NZ) data — AU prices are typically more reliable
- `hours_old` shows data freshness; NZ Gaspy data can be 1–2 days old
- Prices are displayed in cents (divide by 100 for dollars)
- `--location` first checks the built-in lookup table, then falls back to PetrolMate geocoding
- No third-party dependencies — Python stdlib only (`urllib` + `json`)
- Not all fuel types available in all states: NSW reports ULP, E10, LPG, E85 only; VIC/QLD/NZ report all 9 types
