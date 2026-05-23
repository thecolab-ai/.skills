#!/usr/bin/env python3
"""FuelClock NZ CLI.

Read-only stdlib wrapper around fuelclock.nz public API endpoints.
Provides fuel prices, supply status, inbound vessels, geopolitical risk markets,
and recent NZ fuel headlines.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
import urllib.error
import urllib.request
from typing import Any

BASE_URL = "https://fuelclock.nz"
UA = "fuelclock-nz-skill/1.0 (+https://github.com/thecolab-ai/.skills)"
DEFAULT_TIMEOUT = 10

PRICE_FUEL_ORDER = ["91", "95", "98", "diesel"]
SUPPLY_FUEL_ORDER = ["petrol", "diesel", "jet"]

try:
    from zoneinfo import ZoneInfo
    NZ_TZ: dt.tzinfo = ZoneInfo("Pacific/Auckland")
except Exception:
    NZ_TZ = dt.timezone(dt.timedelta(hours=12), name="Pacific/Auckland")


def die(message: str, code: int = 1) -> None:
    print(f"fuelclock-nz: {message}", file=sys.stderr)
    raise SystemExit(code)


def request_json(path: str, timeout: int = DEFAULT_TIMEOUT) -> Any:
    url = f"{BASE_URL}{path}"
    headers = {"Accept": "application/json", "User-Agent": UA}
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        die(f"HTTP {e.code} from {url}: {raw[:300]}")
    except urllib.error.URLError as e:
        die(f"network error calling {url}: {e.reason}")
    except json.JSONDecodeError as e:
        die(f"invalid JSON from {url}: {e}")


def positive_int(raw: str) -> int:
    try:
        v = int(raw)
    except ValueError:
        raise argparse.ArgumentTypeError(f"Expected positive integer, got: {raw}")
    if v <= 0:
        raise argparse.ArgumentTypeError(f"Expected positive integer, got: {raw}")
    return v


def format_nz_datetime(value: str | None) -> str:
    if not value:
        return "unknown"
    try:
        d = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(NZ_TZ)
        return d.strftime("%-d %b %Y, %-I:%M %p NZST")
    except Exception:
        return str(value)


def format_price(value: float) -> str:
    return f"${value:.3f}/L"


def format_cents(value: float) -> str:
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.2f} c/L"


def format_days(value: float) -> str:
    return f"{value:.1f}d"


def format_direction(direction: str) -> str:
    return {"up": "^", "down": "v", "flat": "->"}.get(direction, direction)


def format_gap_to_mso(value: float) -> str:
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.1f}d"


def format_percent(value: float) -> str:
    return f"{value * 100:.1f}%"


# --- Data fetchers ---

def get_fuel_prices() -> dict:
    return request_json("/api/fuel-prices") or {}


def get_supply_status() -> dict:
    return request_json("/api/fuel-data") or {}


def get_vessels() -> dict:
    return request_json("/api/vessels") or {}


def get_geopolitical_risk() -> dict:
    markets = request_json("/api/polymarket") or []
    fetched_at = None
    for m in markets:
        lu = m.get("lastUpdated")
        if lu and (fetched_at is None or lu > fetched_at):
            fetched_at = lu
    return {"markets": markets, "fetchedAt": fetched_at}


def get_news() -> dict:
    return request_json("/api/news") or {}


# --- View helpers ---

def price_row_fuel(row: dict) -> str:
    lower = row.get("type", "").lower()
    if "diesel" in lower:
        return "diesel"
    if lower.startswith("98"):
        return "98"
    if lower.startswith("95"):
        return "95"
    return "91"


def price_label(fuel: str) -> str:
    return "Diesel" if fuel == "diesel" else f"{fuel} Unleaded"


def select_price_rows(rows: list[dict], fuel: str | None = None) -> list[dict]:
    filtered = [r for r in rows if not fuel or price_row_fuel(r) == fuel]
    filtered.sort(key=lambda r: PRICE_FUEL_ORDER.index(price_row_fuel(r)) if price_row_fuel(r) in PRICE_FUEL_ORDER else 99)
    return [
        {
            "fuel": price_row_fuel(r),
            "label": r.get("type", ""),
            "price": r.get("price", 0),
            "change7d": r.get("change7d", 0),
            "change28d": r.get("change28d", 0),
            "changePercent28d": r.get("changePercent28d", 0),
            "direction7d": r.get("direction7d", "flat"),
            "direction28d": r.get("direction28d", "flat"),
            "min": r.get("min", 0),
            "max": r.get("max", 0),
            "stationCount": r.get("stationCount", 0),
        }
        for r in filtered
    ]


def to_supply_view(fuel: dict) -> dict:
    current_days = fuel.get("currentDays", 0)
    mso = fuel.get("msoThreshold", 0)
    return {
        "fuel": fuel.get("fuelType", ""),
        "label": fuel.get("label", ""),
        "currentDays": current_days,
        "totalDays": fuel.get("totalDays", 0),
        "onLandDays": fuel.get("onLandDays", 0),
        "onWaterDays": fuel.get("onWaterDays", 0),
        "msoThreshold": mso,
        "gapToMSODays": current_days - mso,
        "belowMSO": fuel.get("belowMSO", False),
        "calendarDaysToDepletion": fuel.get("calendarDaysToDepletion", 0),
        "dailyConsumptionML": fuel.get("dailyConsumptionML", 0) / 1_000_000,
        "currentStockML": fuel.get("currentStockML", 0) / 1_000_000,
        "remainingOnWaterDays": fuel.get("remainingOnWaterDays", 0),
        "remainingOnWaterML": fuel.get("remainingOnWaterML", 0) / 1_000_000,
        "mbieInCountryDays": fuel.get("mbieInCountryDays", 0),
    }


def select_fuel_states(fuels: list[dict], fuel: str | None = None, below_mso: bool = False) -> list[dict]:
    filtered = [f for f in fuels if not fuel or f.get("fuelType") == fuel]
    if below_mso:
        filtered = [f for f in filtered if f.get("belowMSO")]
    filtered.sort(key=lambda f: f.get("currentDays", 0))
    return [to_supply_view(f) for f in filtered]


def to_vessel_view(vessel: dict) -> dict:
    return {
        "name": vessel.get("name", ""),
        "fuel": vessel.get("fuelType", ""),
        "status": vessel.get("status", ""),
        "eta": vessel.get("eta"),
        "arrived": vessel.get("arrived", False),
        "cargoML": vessel.get("cargoML", 0) / 1_000_000,
        "cargoDays": vessel.get("cargoDays", 0),
        "origin": vessel.get("origin", ""),
        "progressPct": vessel.get("progressPct"),
        "flagRisk": vessel.get("flagRisk", False),
        "flagReason": vessel.get("flagReason"),
        "hormuzTransit": bool(vessel.get("hormuzTransit")),
    }


def eta_sort_value(vessel: dict) -> float:
    eta = vessel.get("eta")
    if not eta:
        return float("inf")
    try:
        return dt.datetime.fromisoformat(str(eta).replace("Z", "+00:00")).timestamp()
    except Exception:
        return float("inf")


def select_vessel_rows(vessels: list[dict], fuel: str | None = None, flagged_only: bool = False, limit: int | None = None) -> list[dict]:
    filtered = [v for v in vessels if not fuel or v.get("fuelType") == fuel]
    if flagged_only:
        filtered = [v for v in filtered if v.get("flagRisk")]
    filtered.sort(key=eta_sort_value)
    if limit is not None:
        filtered = filtered[:limit]
    return [to_vessel_view(v) for v in filtered]


def select_risk_rows(markets: list[dict], limit: int | None = None) -> list[dict]:
    sorted_markets = sorted(markets, key=lambda m: (-m.get("volume", 0), -m.get("probability", 0)))
    if limit is not None:
        sorted_markets = sorted_markets[:limit]
    return [
        {
            "title": m.get("title", ""),
            "shortTitle": m.get("shortTitle"),
            "probability": m.get("probability", 0),
            "volume": m.get("volume", 0),
            "liquidity": m.get("liquidity"),
            "lastUpdated": m.get("lastUpdated"),
            "isFallback": m.get("isFallback"),
            "subMarkets": m.get("subMarkets") or [],
        }
        for m in sorted_markets
    ]


def select_news_rows(articles: list[dict], limit: int | None = None) -> list[dict]:
    try:
        sorted_articles = sorted(
            articles,
            key=lambda a: dt.datetime.fromisoformat(str(a.get("date", "")).replace("Z", "+00:00")).timestamp()
            if a.get("date") else 0,
            reverse=True,
        )
    except Exception:
        sorted_articles = list(articles)
    if limit is not None:
        sorted_articles = sorted_articles[:limit]
    return [
        {
            "title": a.get("title", ""),
            "source": a.get("source", ""),
            "date": a.get("date", ""),
            "url": a.get("url", ""),
        }
        for a in sorted_articles
    ]


# --- Renderers ---

def render_prices(rows: list[dict], fetched_at: str, source: str, is_fallback: bool) -> str:
    lines = [f"NZ pump prices, {source}, updated {format_nz_datetime(fetched_at)}"]
    for r in rows:
        lines.append(
            f"- {r['label']}: {format_price(r['price'])}, "
            f"7d {format_direction(r['direction7d'])} {format_cents(r['change7d'])}, "
            f"28d {format_direction(r['direction28d'])} {format_cents(r['change28d'])} ({r['changePercent28d']:.1f}%), "
            f"range {format_price(r['min'])} to {format_price(r['max'])} across {r['stationCount']:,} stations"
        )
    if is_fallback:
        lines.append("")
        lines.append("Note: FuelClock reports this price snapshot came from fallback or cache data.")
    return "\n".join(lines)


def render_supply(rows: list[dict], meta: dict) -> str:
    lines = [f"NZ fuel supply, updated {format_nz_datetime(meta.get('timestamp'))}"]
    lines.append(f"Overall risk: {str(meta.get('overallRisk', 'unknown')).upper()}")
    lowest = meta.get("lowestFuel")
    if lowest:
        lines.append(
            f"Tightest fuel: {lowest['label']}, {format_days(lowest['currentDays'])} remaining, "
            f"gap to MSO {format_gap_to_mso(lowest['gapToMSODays'])}, depletion in {format_days(lowest['calendarDaysToDepletion'])}"
        )
    lines.append(f"Countdown: {meta.get('countdownHours', 0):.1f} hours ({format_days((meta.get('countdownHours', 0)) / 24)})")
    lines.append("")
    if not rows:
        lines.append("No fuels matched the selected filters.")
        return "\n".join(lines)
    for r in rows:
        mso_note = "below MSO" if r["belowMSO"] else "meets MSO"
        lines.append(
            f"- {r['label']}: {format_days(r['currentDays'])} current, "
            f"MSO {format_days(r['msoThreshold'])} ({format_gap_to_mso(r['gapToMSODays'])}, {mso_note}), "
            f"on-land {format_days(r['onLandDays'])}, on-water {format_days(r['onWaterDays'])}, "
            f"depletion {format_days(r['calendarDaysToDepletion'])}"
        )
        lines.append(
            f"  Stock {r['currentStockML']:.1f} ML, demand {r['dailyConsumptionML']:.1f} ML/day, "
            f"remaining on-water {r['remainingOnWaterML']:.1f} ML ({format_days(r['remainingOnWaterDays'])}), "
            f"MBIE in-country {format_days(r['mbieInCountryDays'])}"
        )
    return "\n".join(lines)


def render_vessels(rows: list[dict], meta: dict) -> str:
    lines = [f"Inbound fuel vessels, {meta.get('source', '')}, updated {format_nz_datetime(meta.get('fetchedAt'))}"]
    lines.append(f"Showing {len(rows)} of {meta.get('totalMatching', 0)} matching vessels.")
    gov = meta.get("govOnWaterByFuel")
    if gov:
        summary = ", ".join(
            f"{fuel} {gov[fuel]:.1f}"
            for fuel in SUPPLY_FUEL_ORDER
            if isinstance(gov.get(fuel), (int, float))
        )
        if summary:
            lines.append(f"Gov on-water snapshot: {summary}")
    lines.append("")
    if not rows:
        lines.append("No vessels matched the selected filters.")
        return "\n".join(lines)
    for i, r in enumerate(rows, 1):
        progress = f", progress {r['progressPct']:.1f}%" if isinstance(r.get("progressPct"), (int, float)) else ""
        lines.append(
            f"{i}. {r['name']}, {r['fuel']}, {r['status']}, "
            f"ETA {format_nz_datetime(r['eta'])}, "
            f"cargo {r['cargoML']:.1f} ML ({format_days(r['cargoDays'])}), "
            f"origin {r['origin']}{progress}"
        )
        if r.get("flagRisk"):
            lines.append(f"   Flagged: {r.get('flagReason') or 'risk flagged by source'}")
        if r.get("hormuzTransit"):
            lines.append("   Hormuz transit flagged.")
    return "\n".join(lines)


def render_risk(rows: list[dict], fetched_at: str | None) -> str:
    lines = ["Tracked geopolitical fuel-shipping markets"]
    lines.append(f"Latest market update: {format_nz_datetime(fetched_at)}")
    lines.append("Sorted by trading volume. The probability shown is the market yes-price, not a direct NZ fuel risk score.")
    lines.append("")
    if not rows:
        lines.append("No markets returned.")
        return "\n".join(lines)
    for r in rows:
        liq = f", ${r['liquidity']:,.0f} liquidity" if isinstance(r.get("liquidity"), (int, float)) else ""
        title = r.get("shortTitle") or r.get("title", "")
        lines.append(
            f"- {title}: {format_percent(r['probability'])} yes, "
            f"${r.get('volume', 0):,.0f} volume{liq}, updated {format_nz_datetime(r.get('lastUpdated'))}"
        )
        sub = r.get("subMarkets") or []
        if sub:
            sub_str = ", ".join(f"{s.get('label')} {format_percent(s.get('probability', 0))}" for s in sub)
            lines.append(f"  Sub-markets: {sub_str}")
    return "\n".join(lines)


def render_news(rows: list[dict], fetched_at: str) -> str:
    lines = [f"Recent NZ fuel headlines, updated {format_nz_datetime(fetched_at)}"]
    lines.append("")
    if not rows:
        lines.append("No articles returned.")
        return "\n".join(lines)
    for i, r in enumerate(rows, 1):
        lines.append(f"{i}. {r['title']}")
        lines.append(f"   {r['source']}, {format_nz_datetime(r['date'])}")
        lines.append(f"   {r['url']}")
    return "\n".join(lines)


# --- Commands ---

def emit(data: Any, as_json: bool, render_fn) -> None:
    if as_json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(render_fn())


def cmd_summary(args: argparse.Namespace) -> None:
    prices_data = get_fuel_prices()
    supply_data = get_supply_status()
    vessels_data = get_vessels()

    prices = select_price_rows(prices_data.get("prices", []))
    fuels = select_fuel_states(supply_data.get("fuelStates", []))
    vessels = select_vessel_rows(vessels_data.get("vessels", []), limit=3)
    lowest_raw = supply_data.get("lowestFuel")
    lowest = to_supply_view(lowest_raw) if lowest_raw else None
    below_mso = [f["label"] for f in fuels if f.get("belowMSO")]

    summary = {
        "prices": {
            "fetchedAt": prices_data.get("fetchedAt"),
            "source": prices_data.get("source"),
            "isFallback": prices_data.get("isFallback"),
            "prices": prices,
        },
        "supply": {
            "timestamp": supply_data.get("timestamp"),
            "overallRisk": supply_data.get("overallRisk"),
            "countdownHours": supply_data.get("countdownHours"),
            "lowestFuel": lowest,
            "belowMSO": below_mso,
            "fuels": fuels,
        },
        "vessels": {
            "fetchedAt": vessels_data.get("fetchedAt"),
            "source": vessels_data.get("source"),
            "totalVessels": len(vessels_data.get("vessels", [])),
            "flaggedCount": sum(1 for v in vessels_data.get("vessels", []) if v.get("flagRisk")),
            "vessels": vessels,
        },
    }

    def render() -> str:
        lines = ["NZ fuel summary"]
        lines.append(f"Updated: {format_nz_datetime(prices_data.get('fetchedAt'))}")
        lines.append("")
        lines.append("Prices:")
        for r in prices:
            lines.append(f"- {price_label(r['fuel'])} {format_price(r['price'])} ({format_direction(r['direction28d'])} {format_cents(r['change28d'])} over 28d)")
        lines.append("")
        lines.append(
            f"Supply: {str(supply_data.get('overallRisk', 'unknown')).upper()} risk, "
            f"tightest fuel {lowest['label'] if lowest else 'unknown'} at "
            f"{format_days(lowest['currentDays']) if lowest else 'unknown'}, "
            f"MSO flags: {', '.join(below_mso) if below_mso else 'none'}"
        )
        first_vessel = vessels[0] if vessels else None
        lines.append(
            f"Vessels: {len(vessels_data.get('vessels', []))} inbound, "
            f"{summary['vessels']['flaggedCount']} flagged, "
            f"next ETA {format_nz_datetime(first_vessel['eta']) if first_vessel else 'unknown'}"
        )
        return "\n".join(lines)

    emit(summary, args.json, render)


def cmd_prices(args: argparse.Namespace) -> None:
    data = get_fuel_prices()
    prices = select_price_rows(data.get("prices", []), args.fuel or None)
    output = {
        "fetchedAt": data.get("fetchedAt"),
        "source": data.get("source"),
        "isFallback": data.get("isFallback"),
        "filters": {"fuel": args.fuel or None},
        "count": len(prices),
        "prices": prices,
    }
    emit(output, args.json, lambda: render_prices(prices, data.get("fetchedAt", ""), data.get("source", ""), bool(data.get("isFallback"))))


def cmd_supply(args: argparse.Namespace) -> None:
    data = get_supply_status()
    fuels = select_fuel_states(data.get("fuelStates", []), args.fuel or None, bool(getattr(args, "below_mso", False)))
    lowest_raw = data.get("lowestFuel")
    lowest = to_supply_view(lowest_raw) if lowest_raw else None
    output = {
        "timestamp": data.get("timestamp"),
        "anchorDate": data.get("anchorDate"),
        "mbieAsAtDate": data.get("mbieAsAtDate"),
        "overallRisk": data.get("overallRisk"),
        "countdownHours": data.get("countdownHours"),
        "lowestFuel": lowest,
        "filters": {
            "fuel": args.fuel or None,
            "belowMSO": bool(getattr(args, "below_mso", False)),
        },
        "count": len(fuels),
        "fuels": fuels,
    }
    meta = {
        "timestamp": data.get("timestamp"),
        "overallRisk": data.get("overallRisk"),
        "countdownHours": data.get("countdownHours"),
        "lowestFuel": lowest,
    }
    emit(output, args.json, lambda: render_supply(fuels, meta))


def cmd_vessels(args: argparse.Namespace) -> None:
    data = get_vessels()
    all_vessels = data.get("vessels", [])
    fuel_filter = args.fuel or None
    flagged_only = bool(getattr(args, "flagged_only", False))
    matching = [v for v in all_vessels if not fuel_filter or v.get("fuelType") == fuel_filter]
    if flagged_only:
        matching = [v for v in matching if v.get("flagRisk")]
    vessels = select_vessel_rows(all_vessels, fuel=fuel_filter, flagged_only=flagged_only, limit=args.limit)
    output = {
        "fetchedAt": data.get("fetchedAt"),
        "source": data.get("source"),
        "govOnWaterByFuel": data.get("govOnWaterByFuel"),
        "filters": {
            "fuel": fuel_filter,
            "flaggedOnly": flagged_only,
            "limit": args.limit or None,
        },
        "totalMatching": len(matching),
        "returnedCount": len(vessels),
        "vessels": vessels,
    }
    meta = {
        "fetchedAt": data.get("fetchedAt"),
        "source": data.get("source"),
        "totalMatching": len(matching),
        "govOnWaterByFuel": data.get("govOnWaterByFuel"),
    }
    emit(output, args.json, lambda: render_vessels(vessels, meta))


def cmd_watch(args: argparse.Namespace) -> None:
    risk_data = get_geopolitical_risk()
    news_data = get_news()
    markets = select_risk_rows(risk_data.get("markets", []), 3)
    articles = select_news_rows(news_data.get("articles", []), 3)

    output = {
        "risk": {
            "fetchedAt": risk_data.get("fetchedAt"),
            "totalMarkets": len(risk_data.get("markets", [])),
            "markets": markets,
        },
        "news": {
            "fetchedAt": news_data.get("fetchedAt"),
            "totalArticles": len(news_data.get("articles", [])),
            "articles": articles,
        },
    }

    def render() -> str:
        lines = ["NZ fuel watch briefing"]
        lines.append(f"Market update: {format_nz_datetime(risk_data.get('fetchedAt'))}")
        lines.append(f"Headline update: {format_nz_datetime(news_data.get('fetchedAt'))}")
        lines.append("")
        if markets:
            m0 = markets[0]
            title = m0.get("shortTitle") or m0.get("title", "")
            lines.append(f"Top market: {title} at {format_percent(m0['probability'])} yes on ${m0.get('volume', 0):,.0f} volume")
        if articles:
            lines.append(f"Latest headline: {articles[0]['title']} ({articles[0]['source']})")
        if not markets and not articles:
            lines.append("No watch items returned.")
        return "\n".join(lines)

    emit(output, args.json, render)


def cmd_risk(args: argparse.Namespace) -> None:
    data = get_geopolitical_risk()
    markets = select_risk_rows(data.get("markets", []), args.limit)
    output = {
        "fetchedAt": data.get("fetchedAt"),
        "sort": "volume-desc",
        "filters": {"limit": args.limit or None},
        "totalMarkets": len(data.get("markets", [])),
        "returnedCount": len(markets),
        "markets": markets,
    }
    emit(output, args.json, lambda: render_risk(markets, data.get("fetchedAt")))


def cmd_news(args: argparse.Namespace) -> None:
    data = get_news()
    articles = select_news_rows(data.get("articles", []), args.limit)
    output = {
        "fetchedAt": data.get("fetchedAt"),
        "filters": {"limit": args.limit or None},
        "totalArticles": len(data.get("articles", [])),
        "returnedCount": len(articles),
        "articles": articles,
    }
    emit(output, args.json, lambda: render_news(articles, data.get("fetchedAt", "")))


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Query live NZ fuel prices, supply status, inbound vessels, geopolitical risk markets, and recent fuel headlines from fuelclock.nz."
    )
    sub = ap.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("summary", help="show a compact NZ fuel briefing across pump prices, supply, and inbound vessels")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_summary)

    sp = sub.add_parser("prices", help="show national average NZ pump prices")
    sp.add_argument("--fuel", choices=PRICE_FUEL_ORDER, help="restrict to one fuel")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_prices)

    sp = sub.add_parser("supply", help="show NZ fuel supply days remaining")
    sp.add_argument("--fuel", choices=SUPPLY_FUEL_ORDER, help="restrict to one fuel")
    sp.add_argument("--below-mso", action="store_true", help="only show fuels currently below MSO threshold")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_supply)

    sp = sub.add_parser("vessels", help="show inbound fuel vessels")
    sp.add_argument("--fuel", choices=SUPPLY_FUEL_ORDER, help="restrict to one fuel")
    sp.add_argument("--flagged-only", action="store_true", help="only show vessels flagged as higher-risk")
    sp.add_argument("--limit", type=positive_int, help="limit the number of vessels returned")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_vessels)

    sp = sub.add_parser("watch", help="show a compact fuel watch briefing: top geopolitical markets and recent headlines")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_watch)

    sp = sub.add_parser("risk", help="show tracked geopolitical markets relevant to fuel shipping")
    sp.add_argument("--limit", type=positive_int, help="limit the number of markets returned")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_risk)

    sp = sub.add_parser("news", help="show recent NZ fuel headlines, newest first")
    sp.add_argument("--limit", type=positive_int, help="limit the number of articles returned")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_news)

    return ap


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
