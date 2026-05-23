#!/usr/bin/env python3
"""NZX lightweight market-data CLI.

Read-only stdlib wrapper around public delayed NZX ticker and market-data
endpoints. No login, API key, portfolio access, browser automation, or cache.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

try:
    from zoneinfo import ZoneInfo

    NZ_TZ: dt.tzinfo = ZoneInfo("Pacific/Auckland")
except Exception:
    NZ_TZ = dt.timezone(dt.timedelta(hours=12), name="Pacific/Auckland")

TICKER_BASE = "https://api.nzx.com/ticker/1.0"
PUBLIC_BASE = "https://api.nzx.com/public"
NZX_WEB = "https://www.nzx.com"
UA = "nzx-skill/1.0 (+https://github.com/thecolab-ai/.skills)"
DELAY_NOTE = "NZX market data is delayed by 20 minutes and may be cached."

INDEX_ALIASES = {
    "nzx50": "NZ50",
    "nzx-50": "NZ50",
    "nz50": "NZ50",
    "50": "NZ50",
    "nzx20": "NZ20",
    "nzx-20": "NZ20",
    "nz20": "NZ20",
    "20": "NZ20",
    "nzx-all": "ALL",
    "nzxall": "ALL",
    "all": "ALL",
}


def die(message: str, code: int = 1) -> None:
    print(f"nzx: {message}", file=sys.stderr)
    raise SystemExit(code)


def request_json(url: str, timeout: int = 20) -> Any:
    headers = {
        "Accept": "application/json, text/plain, */*",
        "User-Agent": UA,
        "Referer": NZX_WEB + "/",
    }
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            payload = json.loads(raw)
            detail = payload.get("message") or payload.get("error") or raw[:240]
        except Exception:
            detail = raw[:240]
        die(f"HTTP {e.code} from {url}: {detail}")
    except urllib.error.URLError as e:
        die(f"network error calling {url}: {e.reason}")
    except TimeoutError:
        die(f"timeout calling {url}")
    except json.JSONDecodeError as e:
        die(f"invalid JSON from {url}: {e}")


def ticker(raw: str) -> str:
    cleaned = raw.strip().upper()
    if not cleaned:
        die("ticker cannot be empty")
    return cleaned


def parse_date(raw: str) -> dt.date:
    try:
        return dt.date.fromisoformat(raw)
    except ValueError:
        die(f"expected DATE as YYYY-MM-DD, received: {raw}")


def positive_int(raw: str) -> int:
    try:
        value = int(raw)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected positive integer, received: {raw}")
    if value <= 0:
        raise argparse.ArgumentTypeError(f"expected positive integer, received: {raw}")
    return value


def as_float(raw: Any) -> float | None:
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def as_int(raw: Any) -> int | None:
    if raw is None or raw == "":
        return None
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return None


def round4(value: float | None) -> float | None:
    return None if value is None else round(value, 4)


def pct_from_relative(raw: Any) -> float | None:
    value = as_float(raw)
    return None if value is None else round(value * 100, 2)


def money(value: Any) -> str:
    parsed = as_float(value)
    if parsed is None:
        return "-"
    return f"${parsed:,.4f}"


def money2(value: Any) -> str:
    parsed = as_float(value)
    if parsed is None:
        return "-"
    return f"${parsed:,.2f}"


def pct(value: Any) -> str:
    parsed = as_float(value)
    if parsed is None:
        return "-"
    return f"{parsed:.2f}%"


def number(value: Any, digits: int = 3) -> str:
    parsed = as_float(value)
    if parsed is None:
        return "-"
    return f"{parsed:,.{digits}f}"


def nz_date_from_epoch(raw: Any) -> str | None:
    value = as_float(raw)
    if value is None:
        return None
    return dt.datetime.fromtimestamp(value, tz=NZ_TZ).date().isoformat()


def nz_datetime_from_epoch(raw: Any) -> str | None:
    value = as_float(raw)
    if value is None:
        return None
    return dt.datetime.fromtimestamp(value, tz=NZ_TZ).isoformat()


def fetch_quote(code: str) -> dict[str, Any]:
    url = f"{TICKER_BASE}/instrument/{urllib.parse.quote(code)}/last"
    payload = request_json(url)
    if not isinstance(payload, dict) or not payload.get("code"):
        die(f"no NZX quote returned for {code}")
    return payload


def fetch_market_quotes(market: str = "nzsx") -> list[dict[str, Any]]:
    url = f"{TICKER_BASE}/{market.lower()}/instruments/last"
    payload = request_json(url, timeout=30)
    if not isinstance(payload, list):
        die(f"unexpected NZX market quote payload from {url}")
    return [item for item in payload if isinstance(item, dict)]


def fetch_active_instruments(market: str = "NZSX") -> list[dict[str, Any]]:
    url = f"{PUBLIC_BASE}/market/{market.upper()}/instruments/active.json"
    payload = request_json(url, timeout=30)
    if not isinstance(payload, list):
        die(f"unexpected NZX active instruments payload from {url}")
    return [item for item in payload if isinstance(item, dict)]


def fetch_instrument_metadata(code: str) -> dict[str, Any]:
    url = f"{PUBLIC_BASE}/instruments/by/code/{urllib.parse.quote(code)}/all.json"
    payload = request_json(url)
    items = payload if isinstance(payload, list) else []
    exact = [item for item in items if isinstance(item, dict) and str(item.get("code", "")).upper() == code]
    if not exact:
        die(f"no NZX instrument metadata returned for {code}")
    return exact[0]


def simplify_quote(item: dict[str, Any]) -> dict[str, Any]:
    rel = as_float(item.get("priceChangeRelative"))
    code = str(item.get("code") or item.get("ISIN") or "")
    return {
        "code": code,
        "name": item.get("description") or item.get("issuerName") or item.get("name"),
        "isin": item.get("ISIN") or item.get("isin"),
        "market": item.get("market"),
        "currency": item.get("currency"),
        "price": as_float(item.get("priceAmount")),
        "change": as_float(item.get("priceChangeAmount")),
        "change_relative": rel,
        "change_percent": pct_from_relative(rel),
        "open": as_float(item.get("firstPrice")),
        "high": as_float(item.get("highPrice")),
        "low": as_float(item.get("lowPrice")),
        "bid": as_float(item.get("bestBid")),
        "offer": as_float(item.get("bestOffer")),
        "volume": as_int(item.get("totalVolume")),
        "value": as_float(item.get("totalValue")),
        "trades": as_int(item.get("totalCount")),
        "market_cap": as_int(item.get("capitalisation")),
        "pe_ratio": as_float(item.get("peRatio")),
        "gross_dividend_yield_percent": as_float(item.get("gdyPerShare")),
        "last_price_at": item.get("priceAt") or item.get("lastPriceAt"),
        "last_updated_at": item.get("lastUpdatedAt"),
        "source_url": f"{NZX_WEB}/instruments/{urllib.parse.quote(code)}" if code else None,
    }


def simplify_index(item: dict[str, Any]) -> dict[str, Any]:
    rel = as_float(item.get("valueChangeRelative") if "valueChangeRelative" in item else item.get("priceChangeRelative"))
    value = item.get("value") if "value" in item else item.get("priceAmount")
    change = item.get("valueChange") if "valueChange" in item else item.get("priceChangeAmount")
    high = item.get("valueHigh") if "valueHigh" in item else item.get("highPrice")
    low = item.get("valueLow") if "valueLow" in item else item.get("lowPrice")
    open_value = item.get("valueOpen") if "valueOpen" in item else item.get("startingPriceAmount")
    return {
        "id": item.get("id") or item.get("ISIN"),
        "code": item.get("code"),
        "name": item.get("description"),
        "date": item.get("indexDate"),
        "value": as_float(value),
        "change": as_float(change),
        "change_relative": rel,
        "change_percent": pct_from_relative(rel),
        "open": as_float(open_value),
        "high": as_float(high),
        "low": as_float(low),
        "last_updated_at": item.get("lastUpdatedAt"),
    }


def simplify_instrument(item: dict[str, Any], quote: dict[str, Any] | None = None) -> dict[str, Any]:
    out = {
        "code": item.get("code"),
        "name": item.get("name") or item.get("description"),
        "isin": item.get("isin") or item.get("ISIN"),
        "market": item.get("marketType") or item.get("market"),
        "trading_board": item.get("tradingBoard"),
        "category": item.get("category"),
        "type": item.get("type"),
        "currency": item.get("currencyCode") or item.get("currency"),
        "shares_issued": as_int(item.get("sharesIssued")),
        "first_listed_date": item.get("firstListedDate") or item.get("issueDate"),
        "source_url": f"{NZX_WEB}/instruments/{urllib.parse.quote(str(item.get('code') or ''))}",
    }
    if quote:
        out.update(
            {
                "price": as_float(quote.get("priceAmount")),
                "change": as_float(quote.get("priceChangeAmount")),
                "change_percent": pct_from_relative(quote.get("priceChangeRelative")),
                "volume": as_int(quote.get("totalVolume")),
                "last_updated_at": quote.get("lastUpdatedAt"),
            }
        )
    return out


def cmd_quote(args: argparse.Namespace) -> None:
    started = time.perf_counter()
    codes = [ticker(code) for code in args.tickers]
    quotes = [simplify_quote(fetch_quote(code)) for code in codes]
    data = {
        "source": "NZX ticker snapshot API",
        "source_url": TICKER_BASE + "/instrument/{ticker}/last",
        "delay": DELAY_NOTE,
        "count": len(quotes),
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "quotes": quotes,
    }
    emit(data, args.json, render_quotes)


def resolve_index_name(raw: str) -> str:
    key = raw.strip().lower()
    if key in INDEX_ALIASES:
        return INDEX_ALIASES[key]
    valid = "nzx50, nzx20, nzx-all"
    die(f"unknown index '{raw}'. Valid names: {valid}")


def cmd_index(args: argparse.Namespace) -> None:
    wanted = resolve_index_name(args.name)
    started = time.perf_counter()
    url = TICKER_BASE + "/indices/all/last"
    items = request_json(url)
    if not isinstance(items, list):
        die(f"unexpected NZX index payload from {url}")
    selected = [item for item in items if isinstance(item, dict) and item.get("id") == wanted]
    if not selected:
        die(f"NZX index {wanted} was not returned by {url}")
    data = {
        "source": "NZX ticker indices snapshot API",
        "source_url": url,
        "delay": DELAY_NOTE,
        "count": len(selected),
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "indices": [simplify_index(item) for item in selected],
    }
    emit(data, args.json, render_indices)


def cmd_movers(args: argparse.Namespace) -> None:
    started = time.perf_counter()
    items = fetch_market_quotes("nzsx")
    movers = [
        item
        for item in items
        if as_float(item.get("priceChangeRelative")) is not None
        and as_float(item.get("priceAmount")) is not None
        and as_int(item.get("totalVolume")) is not None
    ]
    losers = bool(args.losers)
    movers.sort(key=lambda item: as_float(item.get("priceChangeRelative")) or 0.0, reverse=not losers)
    selected = movers[: args.limit]
    data = {
        "source": "NZX ticker NZSX market snapshot API",
        "source_url": TICKER_BASE + "/nzsx/instruments/last",
        "delay": DELAY_NOTE,
        "direction": "losers" if losers else "top",
        "limit": args.limit,
        "count": len(selected),
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "movers": [simplify_quote(item) for item in selected],
    }
    emit(data, args.json, render_movers)


def history_sources(code: str) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    meta = fetch_instrument_metadata(code)
    isin = str(meta.get("isin") or "")
    if not isin:
        die(f"no ISIN returned for {code}")
    perf_url = f"{PUBLIC_BASE}/instrument/{urllib.parse.quote(isin)}/metrics/performance/past/2Y.json"
    activity_url = f"{PUBLIC_BASE}/instrument/{urllib.parse.quote(isin)}/metrics/activity/past/2Y.json"
    perf = request_json(perf_url, timeout=30)
    activity = request_json(activity_url, timeout=30)
    perf_rows = [row for row in perf if isinstance(row, dict)] if isinstance(perf, list) else []
    activity_rows = [row for row in activity if isinstance(row, dict)] if isinstance(activity, list) else []
    return meta, perf_rows, activity_rows


def simplify_history_row(row: dict[str, Any], activity: dict[str, Any] | None = None) -> dict[str, Any]:
    date = nz_date_from_epoch(row.get("date"))
    activity = activity or {}
    return {
        "date": date,
        "open": as_float(row.get("firstPrice")),
        "high": as_float(row.get("highPrice")),
        "low": as_float(row.get("lowPrice")),
        "close": as_float(row.get("lastPrice")),
        "market_price": as_float(row.get("marketPrice")),
        "high_offer": as_float(row.get("highOffer")),
        "low_offer": as_float(row.get("lowOffer")),
        "index": as_float(row.get("index")),
        "volume": as_int(activity.get("volume")),
        "value": as_float(activity.get("value")),
        "on_market_volume": as_int(activity.get("onMarketVolume")),
        "off_market_volume": as_int(activity.get("offMarketVolume")),
        "trades": as_int(activity.get("tradeCount")),
        "market_cap": as_float(activity.get("capitalisation")),
    }


def cmd_history(args: argparse.Namespace) -> None:
    code = ticker(args.ticker)
    start = parse_date(args.from_date) if args.from_date else None
    end = parse_date(args.to_date) if args.to_date else None
    if start and end and end < start:
        die("--to must be on or after --from")

    started = time.perf_counter()
    meta, performance, activity = history_sources(code)
    activity_by_date = {nz_date_from_epoch(row.get("date")): row for row in activity}
    rows: list[dict[str, Any]] = []
    for row in performance:
        row_date_raw = nz_date_from_epoch(row.get("date"))
        if not row_date_raw:
            continue
        row_date = parse_date(row_date_raw)
        if start and row_date < start:
            continue
        if end and row_date > end:
            continue
        rows.append(simplify_history_row(row, activity_by_date.get(row_date_raw)))

    rows.sort(key=lambda item: item.get("date") or "", reverse=True)
    source_count = len(rows)
    if not start and not end and args.limit is None:
        rows = rows[:30]
    elif args.limit is not None:
        rows = rows[: args.limit]

    closes = [row["close"] for row in rows if row.get("close") is not None]
    data = {
        "source": "NZX public instrument performance and activity APIs",
        "source_url": f"{PUBLIC_BASE}/instrument/{meta.get('isin')}/metrics/performance/past/2Y.json",
        "activity_source_url": f"{PUBLIC_BASE}/instrument/{meta.get('isin')}/metrics/activity/past/2Y.json",
        "delay": DELAY_NOTE,
        "ticker": code,
        "isin": meta.get("isin"),
        "name": meta.get("name"),
        "from": start.isoformat() if start else None,
        "to": end.isoformat() if end else None,
        "returned_rows": len(rows),
        "matched_rows": source_count,
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "summary": {
            "min_close": round4(min(closes) if closes else None),
            "max_close": round4(max(closes) if closes else None),
            "average_close": round4(statistics.fmean(closes) if closes else None),
        },
        "history": rows,
    }
    emit(data, args.json, render_history)


def simplify_dividend(row: dict[str, Any]) -> dict[str, Any]:
    amount = as_float(row.get("amount"))
    base_quantity = as_float(row.get("baseQuantity"))
    per_security = amount / base_quantity if amount is not None and base_quantity not in (None, 0) else None
    return {
        "id": row.get("id"),
        "isin": row.get("isin"),
        "type": row.get("type"),
        "expected_date": nz_date_from_epoch(row.get("expectedDate")),
        "record_date": nz_date_from_epoch(row.get("recordDate")),
        "payable_date": nz_date_from_epoch(row.get("payableDate")),
        "amount": amount,
        "base_quantity": base_quantity,
        "amount_per_security": round4(per_security),
        "currency": row.get("currencyCode"),
        "imputation_credit_amount": as_float(row.get("imputationCreditAmount")),
        "supplementary_amount": as_float(row.get("supplementaryAmount")),
    }


def cmd_dividends(args: argparse.Namespace) -> None:
    code = ticker(args.ticker)
    started = time.perf_counter()
    meta = fetch_instrument_metadata(code)
    isin = str(meta.get("isin") or "")
    if not isin:
        die(f"no ISIN returned for {code}")

    upcoming_url = f"{PUBLIC_BASE}/instrument/{urllib.parse.quote(isin)}/dividends/upcoming.json"
    past_url = f"{PUBLIC_BASE}/instrument/{urllib.parse.quote(isin)}/dividends/past/3Y.json"
    upcoming_raw = request_json(upcoming_url)
    past_raw = request_json(past_url)
    upcoming = [simplify_dividend(row) for row in upcoming_raw] if isinstance(upcoming_raw, list) else []
    past = [simplify_dividend(row) for row in past_raw] if isinstance(past_raw, list) else []
    past.sort(key=lambda row: row.get("expected_date") or "", reverse=True)
    data = {
        "source": "NZX public instrument dividends APIs",
        "source_url": upcoming_url,
        "past_source_url": past_url,
        "delay": DELAY_NOTE,
        "ticker": code,
        "isin": isin,
        "name": meta.get("name"),
        "upcoming_count": len(upcoming),
        "past_count": len(past),
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "upcoming": upcoming,
        "past": past,
    }
    emit(data, args.json, render_dividends)


def cmd_search(args: argparse.Namespace) -> None:
    started = time.perf_counter()
    query = args.query.strip()
    if not query:
        die("query cannot be empty")
    needle = query.lower()
    active = fetch_active_instruments("NZSX")
    quote_by_code = {str(item.get("code", "")).upper(): item for item in fetch_market_quotes("nzsx")}
    matches = []
    for item in active:
        code = str(item.get("code") or "")
        name = str(item.get("name") or "")
        haystack = f"{code} {name}".lower()
        if needle in haystack:
            quote = quote_by_code.get(code.upper())
            matches.append((score_match(needle, code, name), simplify_instrument(item, quote)))
    matches.sort(key=lambda pair: pair[0])
    results = [item for _, item in matches[: args.limit]]
    data = {
        "source": "NZX public active instruments API plus ticker NZSX snapshot API",
        "source_url": PUBLIC_BASE + "/market/NZSX/instruments/active.json",
        "quote_source_url": TICKER_BASE + "/nzsx/instruments/last",
        "delay": DELAY_NOTE,
        "query": query,
        "limit": args.limit,
        "count": len(results),
        "total_matches": len(matches),
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "results": results,
    }
    emit(data, args.json, render_search)


def score_match(needle: str, code: str, name: str) -> tuple[int, str, str]:
    code_l = code.lower()
    name_l = name.lower()
    if code_l == needle:
        rank = 0
    elif code_l.startswith(needle):
        rank = 1
    elif name_l.startswith(needle):
        rank = 2
    elif needle in code_l:
        rank = 3
    else:
        rank = 4
    return (rank, code_l, name_l)


def render_quotes(data: dict[str, Any]) -> str:
    quotes = data.get("quotes") or []
    lines = [
        f"NZX quotes: {len(quotes)} instrument(s) ({data.get('elapsed_ms')} ms)",
        str(data.get("delay")),
        "",
    ]
    for item in quotes:
        change = item.get("change")
        sign = "+" if change is not None and change > 0 else ""
        lines.append(
            f"{item.get('code', '').ljust(6)} {money(item.get('price')).rjust(10)}  "
            f"{sign}{money(item.get('change'))} ({pct(item.get('change_percent'))})  "
            f"vol {item.get('volume') or 0:,}  {item.get('name')}"
        )
        lines.append(
            f"       open {money(item.get('open'))} high {money(item.get('high'))} low {money(item.get('low'))} "
            f"bid {money(item.get('bid'))} offer {money(item.get('offer'))}"
        )
        lines.append(f"       updated {item.get('last_updated_at')} price_at {item.get('last_price_at')}")
    return "\n".join(lines).rstrip()


def render_indices(data: dict[str, Any]) -> str:
    indices = data.get("indices") or []
    lines = [
        f"NZX indices: {len(indices)} index ({data.get('elapsed_ms')} ms)",
        str(data.get("delay")),
        "",
    ]
    for item in indices:
        change = item.get("change")
        sign = "+" if change is not None and change > 0 else ""
        lines.append(
            f"{item.get('id', '').ljust(6)} {item.get('name')}  "
            f"{number(item.get('value'))}  {sign}{number(item.get('change'))} ({pct(item.get('change_percent'))})"
        )
        lines.append(
            f"       date {item.get('date')} open {number(item.get('open'))} "
            f"high {number(item.get('high'))} low {number(item.get('low'))}"
        )
    return "\n".join(lines).rstrip()


def render_movers(data: dict[str, Any]) -> str:
    movers = data.get("movers") or []
    lines = [
        f"NZX {data.get('direction')} movers: {len(movers)} instrument(s) ({data.get('elapsed_ms')} ms)",
        str(data.get("delay")),
        "",
    ]
    for item in movers:
        change = item.get("change")
        sign = "+" if change is not None and change > 0 else ""
        lines.append(
            f"{item.get('code', '').ljust(7)} {pct(item.get('change_percent')).rjust(8)}  "
            f"{sign}{money(item.get('change'))}  {money(item.get('price')).rjust(10)}  "
            f"vol {item.get('volume') or 0:,}  {item.get('name')}"
        )
    return "\n".join(lines).rstrip()


def render_history(data: dict[str, Any]) -> str:
    rows = data.get("history") or []
    lines = [
        f"NZX history for {data.get('ticker')}: {data.get('returned_rows')} row(s) ({data.get('elapsed_ms')} ms)",
        f"{data.get('name')} | matched {data.get('matched_rows')} row(s) from 2Y source",
    ]
    summary = data.get("summary") or {}
    if rows:
        lines.append(
            f"Close range {money(summary.get('min_close'))} - {money(summary.get('max_close'))}; "
            f"average {money(summary.get('average_close'))}"
        )
    lines.append("")
    for row in rows[:30]:
        lines.append(
            f"{row.get('date')}  O {money(row.get('open'))} H {money(row.get('high'))} "
            f"L {money(row.get('low'))} C {money(row.get('close'))}  vol {row.get('volume') or 0:,}"
        )
    if len(rows) > 30:
        lines.append(f"... {len(rows) - 30} more rows; use --json for full output")
    return "\n".join(lines).rstrip()


def render_dividends(data: dict[str, Any]) -> str:
    lines = [
        f"NZX dividends for {data.get('ticker')} ({data.get('elapsed_ms')} ms)",
        str(data.get("name")),
        "",
    ]
    upcoming = data.get("upcoming") or []
    past = data.get("past") or []
    lines.append(f"Upcoming: {len(upcoming)}")
    for row in upcoming:
        lines.append(dividend_line(row))
    lines.append("")
    lines.append(f"Past 3Y: {len(past)}")
    for row in past[:10]:
        lines.append(dividend_line(row))
    if len(past) > 10:
        lines.append(f"... {len(past) - 10} more rows; use --json for full output")
    return "\n".join(lines).rstrip()


def dividend_line(row: dict[str, Any]) -> str:
    return (
        f"{row.get('expected_date')} {str(row.get('type') or '').ljust(3)} "
        f"{money(row.get('amount_per_security'))} per security "
        f"(raw {row.get('amount')} per {row.get('base_quantity')}) "
        f"record {row.get('record_date')} payable {row.get('payable_date')}"
    )


def render_search(data: dict[str, Any]) -> str:
    results = data.get("results") or []
    lines = [
        f"NZX search '{data.get('query')}': {len(results)} of {data.get('total_matches')} match(es) ({data.get('elapsed_ms')} ms)",
        str(data.get("delay")),
        "",
    ]
    for item in results:
        price = money(item.get("price")) if item.get("price") is not None else "-"
        change = pct(item.get("change_percent")) if item.get("change_percent") is not None else "-"
        lines.append(f"{item.get('code', '').ljust(7)} {price.rjust(10)} {change.rjust(8)}  {item.get('name')}")
        lines.append(f"       {item.get('market')} {item.get('type')} {item.get('isin')}")
    return "\n".join(lines).rstrip()


def emit(data: dict[str, Any], as_json: bool, render: Callable[[dict[str, Any]], str]) -> None:
    if as_json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(render(data))


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Read-only NZX delayed market-data CLI using public ticker and market-data endpoints."
    )
    sub = ap.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("quote", help="current delayed price snapshot for one or more tickers")
    sp.add_argument("tickers", nargs="+", help="NZX ticker code, e.g. AIR FPH MEL")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_quote)

    sp = sub.add_parser("index", help="current delayed index level and day change")
    sp.add_argument("--name", default="nzx50", help="nzx50, nzx20, or nzx-all; default nzx50")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_index)

    sp = sub.add_parser("movers", help="top gainers or losers on NZSX today")
    group = sp.add_mutually_exclusive_group()
    group.add_argument("--top", action="store_true", help="show top gainers; default")
    group.add_argument("--losers", action="store_true", help="show top losers")
    sp.add_argument("--limit", type=positive_int, default=10)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_movers)

    sp = sub.add_parser("history", help="daily OHLC-style historical performance for a ticker")
    sp.add_argument("ticker", help="NZX ticker code, e.g. AIR")
    sp.add_argument("--from", dest="from_date", help="start date YYYY-MM-DD")
    sp.add_argument("--to", dest="to_date", help="end date YYYY-MM-DD")
    sp.add_argument("--limit", type=positive_int, help="limit returned rows; default latest 30 if no date range")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_history)

    sp = sub.add_parser("dividends", help="upcoming and recent dividends for a ticker")
    sp.add_argument("ticker", help="NZX ticker code, e.g. AIR")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_dividends)

    sp = sub.add_parser("search", help="find NZSX tickers by code or company/instrument name")
    sp.add_argument("query")
    sp.add_argument("--limit", type=positive_int, default=10)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_search)

    return ap


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
