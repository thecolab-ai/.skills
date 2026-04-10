"""
fuelclock-nz skill

Fetches New Zealand fuel supply and price data from fuelclock.nz's public API.
No authentication required. All endpoints return JSON.

Data sources behind the API:
  - Prices: Gaspy (updated every 15 minutes)
  - Supply/MSO: MBIE + FuelClock adjustments (near real-time)
  - MBIE stocks: Official government figures (weekly)
  - Vessels: nzoilwatch (updated every 4 minutes)
  - Geopolitical risk: Polymarket prediction markets
  - News: AI-summarised digest (cached 60 minutes)
"""

import json
import urllib.request
from typing import Any

BASE_URL = "https://fuelclock.nz"
DEFAULT_TIMEOUT = 10


def _get(path: str) -> Any:
    """Make a GET request to the fuelclock.nz API and return parsed JSON."""
    url = f"{BASE_URL}{path}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT) as response:
        return json.loads(response.read().decode("utf-8"))


def get_fuel_prices() -> dict:
    """
    Return current national average retail pump prices (NZD/litre) for NZ.

    Data sourced from Gaspy, updated every 15 minutes.

    Returns a dict with:
      prices: list of price objects, one per fuel type (91 Unleaded, Diesel,
              95 Premium, 98 Premium). Each has:
                type, price, change7d, change28d, direction7d, direction28d,
                changePercent28d, min, max, stationCount
      source: "Gaspy"
      fetchedAt: ISO 8601 timestamp
      isFallback: bool — True if live data was unavailable and cached data returned

    Example:
      >>> data = get_fuel_prices()
      >>> for p in data["prices"]:
      ...     print(f"{p['type']}: ${p['price']:.3f}/L")
    """
    return _get("/api/fuel-prices")


def get_supply_status() -> dict:
    """
    Return NZ fuel supply security status: days of supply remaining, MSO status,
    and overall risk level for petrol, diesel, and jet fuel.

    MSO (Minimum Stock Obligation) is the government-mandated minimum reserve.
    belowMSO=True means the fuel type is below its legal minimum threshold.

    Returns a dict with:
      timestamp: ISO 8601 timestamp
      fuelStates: list of objects, one per fuel type. Each has:
                    fuelType, currentDays, msoThreshold, belowMSO,
                    calendarDaysToDepletion, overallRisk
      overallRisk: "normal" | "elevated" | "critical" — worst-case across all types
      countdownHours: float — hours until the most constrained fuel hits zero

    Example:
      >>> data = get_supply_status()
      >>> print(f"Overall risk: {data['overallRisk']}")
      >>> for fs in data["fuelStates"]:
      ...     print(f"{fs['fuelType']}: {fs['currentDays']:.1f} days, belowMSO={fs['belowMSO']}")
    """
    return _get("/api/fuel-data")


def get_mbie_stocks() -> dict:
    """
    Return official New Zealand government MBIE petroleum stock figures.

    These are the raw MBIE numbers, not FuelClock-adjusted. Updated weekly.
    Figures are in days of supply (at average consumption rates).

    Returns a dict with:
      asAtDate: human-readable date string for the data snapshot
      inCountryDays: {petrol, diesel, jet} — stock physically in NZ
      onWaterDays: {petrol, diesel, jet} — stock on vessels en route
      totalDays: {petrol, diesel, jet} — in-country + on-water combined
      nextUpdate: human-readable string for the next expected update time

    Example:
      >>> data = get_mbie_stocks()
      >>> print(f"As at: {data['asAtDate']}")
      >>> print(f"Petrol total: {data['totalDays']['petrol']} days")
    """
    return _get("/api/mbie-stocks")


def get_vessels() -> dict:
    """
    Return incoming fuel tanker data for New Zealand, updated every 4 minutes.

    Includes vessels that are scheduled, en route, or recently arrived.
    flagRisk=True means the vessel's origin country has a geopolitical risk flag.

    Returns a dict with:
      vessels: list of vessel objects. Each has:
                 name, fuelType, cargoML (cargo in millilitres), cargoDays
                 (days of supply this cargo represents), origin, status,
                 eta (ISO 8601), arrived (bool), flagRisk (bool), flagReason

    Example:
      >>> data = get_vessels()
      >>> for v in data["vessels"]:
      ...     eta = v["eta"][:10] if v["eta"] else "unknown"
      ...     print(f"{v['name']} ({v['fuelType']}): {v['cargoDays']:.1f} days, ETA {eta}")
    """
    return _get("/api/vessels")


def get_geopolitical_risk() -> dict:
    """
    Return Polymarket prediction market probabilities for geopolitical events
    that could affect New Zealand's fuel supply chain.

    Probabilities are between 0 and 1 (e.g. 0.245 = 24.5% chance).
    Volume is in USD.

    Returns a dict with:
      markets: list of market objects. Each has:
                 title, probability (float 0–1), volume (float, USD)

    Example:
      >>> data = get_geopolitical_risk()
      >>> for m in data["markets"]:
      ...     print(f"{m['title']}: {m['probability']*100:.1f}%")
    """
    return _get("/api/polymarket")


def get_news() -> dict:
    """
    Return an AI-summarised digest of recent NZ fuel news. Cached for 60 minutes.

    Returns a dict with:
      summary: str — paragraph summary of current fuel situation
      key_topics: list of str — main themes in current coverage
      recent_developments: list of str — specific recent events
      notable_quotes: list of str — notable quotes from sources

    Example:
      >>> data = get_news()
      >>> print(data["summary"])
    """
    return _get("/api/news")


def get_summary() -> str:
    """
    Return a concise plain-text summary of NZ fuel prices and supply status.

    Calls get_fuel_prices() and get_supply_status() and formats the results
    into a short human-readable block suitable for an agent to read and relay.

    Returns a plain-text string. Returns an error message string if either
    API call fails.

    Example:
      >>> print(get_summary())
      NZ Fuel Summary (2026-04-10T04:22:56Z)
      ...
    """
    try:
        prices_data = get_fuel_prices()
    except Exception as exc:
        return f"Error fetching fuel prices: {exc}"

    try:
        supply_data = get_supply_status()
    except Exception as exc:
        return f"Error fetching supply status: {exc}"

    lines = []

    fetched_at = prices_data.get("fetchedAt", "unknown")
    lines.append(f"NZ Fuel Summary ({fetched_at})")
    lines.append("")

    lines.append("Retail pump prices (NZD/litre, national average):")
    for p in prices_data.get("prices", []):
        direction = p.get("direction7d", "")
        arrow = {"up": "↑", "down": "↓", "flat": "→"}.get(direction, "")
        lines.append(
            f"  {p['type']}: ${p['price']:.3f}/L {arrow}  "
            f"(7d: {p.get('change7d', 0):+.3f}, "
            f"28d: {p.get('change28d', 0):+.3f})"
        )

    lines.append("")
    overall_risk = supply_data.get("overallRisk", "unknown")
    countdown_hours = supply_data.get("countdownHours")
    lines.append(f"Supply security: overall risk = {overall_risk.upper()}")
    if countdown_hours is not None:
        lines.append(
            f"  Most constrained fuel depletes in {countdown_hours:.1f} hours "
            f"({countdown_hours / 24:.1f} days)"
        )

    lines.append("")
    lines.append("Days of supply remaining:")
    for fs in supply_data.get("fuelStates", []):
        mso_flag = " [BELOW MSO]" if fs.get("belowMSO") else ""
        lines.append(
            f"  {fs['fuelType'].capitalize()}: {fs['currentDays']:.1f} days "
            f"(MSO threshold: {fs['msoThreshold']} days){mso_flag}"
        )
        lines.append(
            f"    Risk: {fs.get('overallRisk', 'unknown')}, "
            f"depletion in {fs.get('calendarDaysToDepletion', '?'):.1f} days"
        )

    is_fallback = prices_data.get("isFallback", False)
    if is_fallback:
        lines.append("")
        lines.append("Note: price data is from cache (live data unavailable).")

    return "\n".join(lines)


if __name__ == "__main__":
    print(get_summary())
