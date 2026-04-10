---
name: fuelclock-nz
description: Fetch New Zealand fuel supply and price data from fuelclock.nz. Use when the task involves NZ pump prices, fuel supply security, days of supply remaining, MSO (Minimum Stock Obligation) status, incoming tanker vessels, geopolitical risk to NZ fuel supply, or NZ fuel news. No authentication required.
---

# FuelClock NZ

## Goal

Query live NZ fuel supply security data and retail pump prices from fuelclock.nz, which aggregates Gaspy, MBIE, nzoilwatch, and Polymarket into a single public API.

## Use this when

- A user asks about current NZ petrol, diesel, or 95/98 premium prices
- A user wants to know if NZ has enough fuel (days of supply, MSO status)
- A user asks about the NZ fuel supply risk level
- A user wants to know what fuel tankers are en route to New Zealand
- A user asks about geopolitical risks to NZ's fuel supply (Hormuz Strait, etc.)
- A user wants a fuel news digest or summary of the current NZ fuel situation

## Do not use this for

- Fuel prices outside New Zealand
- Electricity, gas, or LPG pricing
- Vehicle fuel efficiency or consumption calculations
- Predicting future fuel prices (this skill returns current observed data only)

## Data freshness

| Endpoint | Source | Update frequency |
|----------|--------|-----------------|
| Prices | Gaspy | Every 15 minutes |
| Supply / MSO | MBIE + FuelClock | Near real-time |
| MBIE stocks | MBIE (government) | Weekly |
| Vessels | nzoilwatch | Every 4 minutes |
| Geopolitical risk | Polymarket | Market-driven |
| News | AI digest | Every 60 minutes |

## Workflow

1. Import `skill.py` or run it directly
2. Call the relevant function for the task
3. Format the returned data into a clear response
4. For a general overview, call `get_summary()` — it combines prices and supply status into a ready-to-read plain-text block

## Functions

### `get_summary() -> str`

Calls `get_fuel_prices()` and `get_supply_status()` and returns a concise plain-text summary. Best default choice for general fuel situation questions.

```python
from skill import get_summary
print(get_summary())
```

Example output:

```
NZ Fuel Summary (2026-04-10T04:22:56Z)

Retail pump prices (NZD/litre, national average):
  91 Unleaded: $3.491/L ->  (7d: +0.000, 28d: +53.710)
  Diesel: $2.104/L v  (7d: -0.010, 28d: +12.300)
  95 Premium: $3.811/L ->  (7d: +0.000, 28d: +47.200)
  98 Premium: $4.021/L ->  (7d: +0.000, 28d: +41.100)

Supply security: overall risk = ELEVATED
  Most constrained fuel depletes in 452.6 hours (18.9 days)

Days of supply remaining:
  Petrol: 24.7 days (MSO threshold: 28 days) [BELOW MSO]
    Risk: elevated, depletion in 23.6 days
  Diesel: 31.2 days (MSO threshold: 25 days)
    Risk: normal, depletion in 30.1 days
  Jet: 18.4 days (MSO threshold: 14 days)
    Risk: normal, depletion in 17.8 days
```

---

### `get_fuel_prices() -> dict`

Current national average retail pump prices (NZD/litre). Includes 7-day and 28-day change, direction, min/max across stations, and station count.

Fuel types: `91 Unleaded`, `Diesel`, `95 Premium`, `98 Premium`

```python
from skill import get_fuel_prices
data = get_fuel_prices()
for p in data["prices"]:
    print(f"{p['type']}: ${p['price']:.3f}/L")
```

---

### `get_supply_status() -> dict`

Days of supply remaining per fuel type, MSO threshold, whether the fuel is currently below MSO, and the overall risk level. Includes a `countdownHours` field for the most constrained fuel type.

Risk levels: `normal`, `elevated`, `critical`

```python
from skill import get_supply_status
data = get_supply_status()
print(f"Overall risk: {data['overallRisk']}")
for fs in data["fuelStates"]:
    print(f"{fs['fuelType']}: {fs['currentDays']:.1f} days, belowMSO={fs['belowMSO']}")
```

---

### `get_mbie_stocks() -> dict`

Official MBIE government petroleum stock figures (not FuelClock-adjusted). Reports in-country days, on-water days, and total days for petrol, diesel, and jet. Updated weekly.

```python
from skill import get_mbie_stocks
data = get_mbie_stocks()
print(f"As at: {data['asAtDate']}")
print(f"Petrol in-country: {data['inCountryDays']['petrol']} days")
print(f"Petrol total (incl. on water): {data['totalDays']['petrol']} days")
```

---

### `get_vessels() -> dict`

Incoming fuel tanker data: vessel name, fuel type, cargo size in millilitres and days of supply equivalent, origin country, ETA, arrival status, and geopolitical risk flag with reason.

```python
from skill import get_vessels
data = get_vessels()
for v in data["vessels"]:
    eta = v["eta"][:10] if v["eta"] else "unknown"
    risk = " [FLAGGED]" if v["flagRisk"] else ""
    print(f"{v['name']} ({v['fuelType']}): {v['cargoDays']:.1f} days, ETA {eta}{risk}")
```

---

### `get_geopolitical_risk() -> dict`

Polymarket prediction market probabilities for events that affect NZ fuel supply (e.g. Hormuz Strait disruptions). Probabilities are `0.0`-`1.0`. Volume is in USD.

```python
from skill import get_geopolitical_risk
data = get_geopolitical_risk()
for m in data["markets"]:
    print(f"{m['title']}: {m['probability']*100:.1f}%  (vol ${m['volume']:,.0f})")
```

---

### `get_news() -> dict`

AI-summarised digest of recent NZ fuel news. Returns a paragraph summary, key topics, recent developments, and notable quotes. Cached for 60 minutes.

```python
from skill import get_news
data = get_news()
print(data["summary"])
print("Key topics:", ", ".join(data["key_topics"]))
```

## Running directly

Run the skill as a quick check:

```bash
python skill.py
```

This calls `get_summary()` and prints the result to stdout. Useful for verifying the API is reachable and returning current data.

## Notes

- No API key or authentication required
- All requests use a 10-second timeout
- `isFallback: true` in price data means the API returned cached data because the live source was unavailable
- `flagRisk: true` on a vessel means the origin country has an active geopolitical risk flag -- see `flagReason` for detail
- MBIE stock figures and FuelClock supply figures differ: MBIE is official government data, FuelClock applies its own adjustments to account for consumption rates and pipeline timing
