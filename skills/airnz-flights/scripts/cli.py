#!/usr/bin/env python3
"""Search public Air New Zealand flight fares.

Read-only browser-sniffed wrapper around Air NZ's public booking search flow. It
creates the same anonymous search session as the web UI, reads the public fare
selection page, and stops before selecting/holding/bookings seats.
"""
from __future__ import annotations

import argparse
import asyncio
import html
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from http.cookiejar import CookieJar
from typing import Any

BOOKING_HOST = "flightbookings.airnewzealand.co.nz"
BASE = f"https://{BOOKING_HOST}"
EXT_SEARCH_PATH = "/vbook/actions/ext-search"
SEARCH_API_PATH = "/vbook/ajax/bui/flights/search"
SELECT_ITINERARY_PATH = "/vbook/actions/selectitinerary"
SCHEDULE_PAGE = "https://www.airnewzealand.co.nz/flight-schedules"
TIMETABLE_FEED_PATH = "/feeds/flight-timetables"
IATA_RE = re.compile(r"^[A-Z]{3}$")
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/146 Safari/537.36"
)
FARE_LABELS = {
    "ds": "Seat",
    "db": "Seat + Bag",
    "dc": "Flexi change",
    "df": "Flexi refund",
}


class BrowserUnavailableError(RuntimeError):
    """Raised when --browser is requested but CloakBrowser is not installed."""


def _request(
    opener: urllib.request.OpenerDirector,
    url: str,
    *,
    method: str = "GET",
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 45,
) -> tuple[int, str, str]:
    merged = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json, text/plain, */*",
        "Referer": f"{BASE}/fly/search",
    }
    if headers:
        merged.update(headers)
    req = urllib.request.Request(url, data=data, headers=merged, method=method)
    try:
        with opener.open(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return int(resp.status), resp.headers.get("content-type", ""), body
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Air NZ returned HTTP {exc.code} for {url}: {body[:300]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Air NZ request failed for {url}: {exc}") from exc


def booking_url(origin: str, destination: str, depart_date: str) -> str:
    dt = datetime.strptime(depart_date, "%Y-%m-%d").date()
    month = dt.strftime("%b").upper()
    params = {
        "searchLegs[0].originPoint": origin,
        "searchLegs[0].destinationPoint": destination,
        "searchLegs[0].tripStartMonth": month,
        "searchLegs[0].tripStartDate": str(dt.day),
        "tripType": "oneway",
        "searchType": "flexible",
        "adults": "1",
        "children": "0",
        "infants": "0",
        "displaySearchForFlight": "true",
    }
    return f"{BASE}{EXT_SEARCH_PATH}?{urllib.parse.urlencode(params)}"


def search_payload(origin: str, destination: str, depart_date: str, adults: int) -> dict[str, Any]:
    return {
        "journeyDetails": {
            "journeyLegs": [
                {
                    "originCityCode": origin,
                    "destinationCityCode": destination,
                    "departureDate": depart_date,
                }
            ],
            "passengerCounts": {"adultCount": adults, "childCount": 0, "infantCount": 0},
            "journeyType": "ONE_WAY",
        },
        "filterPreferences": {"serviceClass": "ECONOMY", "searchType": "FLEXIBLE"},
    }


def extract_json_array(text: str, marker: str) -> list[Any]:
    marker_index = text.find(marker)
    if marker_index == -1:
        # Air NZ sometimes HTML-escapes JSON in script payloads.
        unescaped = html.unescape(text)
        marker_index = unescaped.find(marker)
        if marker_index == -1:
            raise RuntimeError(f"Air NZ fare page did not contain {marker}")
        text = unescaped

    array_start = text.find("[", marker_index)
    if array_start == -1:
        raise RuntimeError(f"Air NZ fare page had {marker} but no JSON array")

    depth = 0
    in_string = False
    escaped = False
    for i in range(array_start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return json.loads(text[array_start : i + 1])
    raise RuntimeError(f"Air NZ fare page had unterminated {marker} JSON array")


def iso_from_airnz_parts(parts: list[Any] | None) -> str | None:
    if not parts or len(parts) < 5:
        return None
    year, month, day, hour, minute = [int(x) for x in parts[:5]]
    return f"{year:04d}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}"


def normalise_fare(raw: dict[str, Any]) -> dict[str, Any]:
    code = str(raw.get("code") or "").lower()
    label = FARE_LABELS.get(code)
    if not label:
        aria = str(raw.get("aria") or "")
        label = aria.split(",", 1)[0].strip() or code or None
    price = raw.get("s-price")
    if price is None:
        adult_price = str(raw.get("adultPrice") or "")
        digits = re.sub(r"[^0-9.]", "", adult_price)
        price = float(digits) if "." in digits else int(digits) if digits else None
    return {
        "code": code or None,
        "name": label,
        "adult_price": raw.get("adultPrice"),
        "price": price,
        "currency_symbol": raw.get("$"),
        "booking_class": raw.get("bookingClass"),
        "fare_band_code": raw.get("fareBandCode"),
        "selling_out": bool(raw.get("sellingOut")),
        "available": bool(raw.get("reveal", True)),
    }


def normalise_leg_option(row: dict[str, Any]) -> dict[str, Any]:
    fares: list[dict[str, Any]] = []
    for group in row.get("costs") or []:
        for fare in group.get("costs") or []:
            fares.append(normalise_fare(fare))
    fares.sort(key=lambda f: float(f["price"]) if isinstance(f.get("price"), (int, float)) else float("inf"))

    segments = []
    for seg in row.get("flights") or []:
        segments.append(
            {
                "flight_number": seg.get("flightNumber"),
                "origin": (seg.get("originAirport") or {}).get("airport", {}).get("code"),
                "destination": (seg.get("destinationAirport") or {}).get("airport", {}).get("code"),
                "departure": (seg.get("originAirport") or {}).get("dateTimeLocal"),
                "arrival": (seg.get("destinationAirport") or {}).get("dateTimeLocal"),
                "airline": (seg.get("operatingAirline") or {}).get("name"),
                "aircraft": (seg.get("equipment") or {}).get("shortDesc"),
            }
        )

    return {
        "id": row.get("id"),
        "currency": row.get("currency"),
        "origin": row.get("departureAirport"),
        "destination": row.get("arrivalAirport"),
        "departure": iso_from_airnz_parts(row.get("departureDateTime")),
        "arrival": iso_from_airnz_parts(row.get("arrivalDateTime")),
        "duration": row.get("duration"),
        "stops": max(int(row.get("noOfFlights") or 1) - 1, 0),
        "selling_out": bool(row.get("sellingOut")),
        "theme_code": row.get("themeCode"),
        "flights": segments,
        "fares": fares,
        "lowest_fare": fares[0] if fares else None,
    }


def normalise_timetable(data: dict[str, Any], origin: str, destination: str, depart_date: str, direct: bool) -> dict[str, Any]:
    flights = []
    for row in data.get("flights") or []:
        legs = []
        raw_legs = row.get("legs") or {}
        for key in sorted(raw_legs.keys(), key=lambda x: int(x) if str(x).isdigit() else str(x)):
            leg = raw_legs[key]
            legs.append(
                {
                    "flight_number": leg.get("flight"),
                    "origin": leg.get("origin"),
                    "destination": leg.get("destination"),
                    "departure": leg.get("std"),
                    "arrival": leg.get("sta"),
                }
            )
        flights.append(
            {
                "id": row.get("Flight"),
                "currency": None,
                "origin": origin,
                "destination": destination,
                "departure": legs[0].get("departure") if legs else None,
                "arrival": legs[-1].get("arrival") if legs else None,
                "duration": row.get("Duration"),
                "stops": max(len(legs) - 1, 0),
                "flights": legs,
                "fares": [],
                "lowest_fare": None,
                "booking_url": booking_url(origin, destination, depart_date),
            }
        )
    if direct:
        flights = [row for row in flights if row.get("stops") == 0]
    return {
        "source": "airnewzealand.co.nz",
        "method": "public timetable fallback; Air NZ fare search returned request-auth/CAPTCHA",
        "origin": origin,
        "destination": destination,
        "date": depart_date,
        "adults": 1,
        "direct_only": direct,
        "currency": None,
        "booking_search_url": booking_url(origin, destination, depart_date),
        "flights": flights,
        "fare_search_blocked": True,
        "notice": "Air NZ fare search hit request-auth/CAPTCHA from this environment; timetable rows only, no prices.",
    }


async def fetch_timetable(origin: str, destination: str, depart_date: str, direct: bool) -> dict[str, Any]:
    try:
        from playwright.async_api import async_playwright
    except Exception as exc:  # pragma: no cover - environment-specific
        raise RuntimeError("Air NZ fallback timetable search requires Python Playwright installed") from exc

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = await browser.new_page(user_agent=USER_AGENT)
        await page.goto(SCHEDULE_PAGE, wait_until="networkidle", timeout=60000)
        payload = await page.evaluate(
            """async ({path, origin, destination, date, direct}) => {
                const params = new URLSearchParams({
                    origin,
                    destination,
                    date,
                    direct: direct ? '1' : '0',
                    locale: 'en_NZ',
                });
                const res = await fetch(`${path}?${params}`, {
                    headers: { accept: 'application/json', 'x-requested-with': 'XMLHttpRequest' },
                });
                return { status: res.status, text: await res.text() };
            }""",
            {"path": TIMETABLE_FEED_PATH, "origin": origin, "destination": destination, "date": depart_date, "direct": direct},
        )
        await browser.close()
    if payload["status"] != 200:
        raise RuntimeError(f"Air NZ timetable feed returned HTTP {payload['status']}: {payload['text'][:200]}")
    return normalise_timetable(json.loads(payload["text"]), origin, destination, depart_date, direct)


def fetch_timetable_sync(origin: str, destination: str, depart_date: str, direct: bool) -> dict[str, Any]:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(fetch_timetable(origin, destination, depart_date, direct))

    # Some sync browser libraries run user code inside an event-loop-owning thread.
    # Run the Playwright fallback in a fresh thread so asyncio.run() remains valid.
    import threading

    result: dict[str, Any] | None = None
    error: BaseException | None = None

    def runner() -> None:
        nonlocal result, error
        try:
            result = asyncio.run(fetch_timetable(origin, destination, depart_date, direct))
        except BaseException as exc:  # pragma: no cover - defensive cross-thread path
            error = exc

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join()
    if error is not None:
        raise error
    if result is None:
        raise RuntimeError("Air NZ timetable fallback failed without returning a result")
    return result


def build_fare_result(
    leg_rows: list[Any],
    origin: str,
    destination: str,
    depart_date: str,
    adults: int,
    direct: bool,
    start_url: str,
    method: str,
) -> dict[str, Any]:
    leg_options = [normalise_leg_option(row) for row in leg_rows if isinstance(row, dict)]
    if direct:
        leg_options = [row for row in leg_options if row.get("stops") == 0]
    leg_options.sort(
        key=lambda row: (
            row.get("lowest_fare", {}).get("price")
            if isinstance(row.get("lowest_fare"), dict) and isinstance(row["lowest_fare"].get("price"), (int, float))
            else 10**9,
            row.get("departure") or "",
        )
    )
    return {
        "source": "airnewzealand.co.nz",
        "method": method,
        "origin": origin,
        "destination": destination,
        "date": depart_date,
        "adults": adults,
        "direct_only": direct,
        "currency": leg_options[0].get("currency") if leg_options else None,
        "booking_search_url": start_url,
        "flights": leg_options,
        "notice": "Fare snapshot only. This tool does not select flights, hold seats, log in, or proceed to checkout.",
    }


def fetch_fares_with_cloakbrowser(origin: str, destination: str, depart_date: str, adults: int, direct: bool) -> dict[str, Any]:
    try:
        from cloakbrowser import launch
    except Exception as exc:  # pragma: no cover - host-specific optional dependency
        raise BrowserUnavailableError(
            "cloakbrowser_not_installed: install CloakBrowser to use --browser. "
            "Recommended for headless/anti-bot-sensitive public web workflows."
        ) from exc

    start_url = booking_url(origin, destination, depart_date)
    browser = None
    try:
        browser = launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
            timezone="Pacific/Auckland",
            locale="en-NZ",
        )
        page = browser.new_page()
        page.goto(start_url, wait_until="networkidle", timeout=90000)
        payload = search_payload(origin, destination, depart_date, adults)
        search_result_raw = page.evaluate(
            """async ({url, payload}) => {
                const res = await fetch(url, {
                    method: 'POST',
                    headers: { accept: 'application/json', 'content-type': 'application/json' },
                    body: JSON.stringify(payload),
                });
                return { status: res.status, text: await res.text() };
            }""",
            {"url": SEARCH_API_PATH, "payload": payload},
        )
        if int(search_result_raw.get("status") or 0) != 200:
            raise RuntimeError(
                f"Air NZ browser fare search returned HTTP {search_result_raw.get('status')}: "
                f"{str(search_result_raw.get('text') or '')[:300]}"
            )
        search_result = json.loads(str(search_result_raw.get("text") or "{}"))
        redirect_url = str(search_result.get("redirectUrl") or SELECT_ITINERARY_PATH)
        if "captcha" in redirect_url.lower():
            return fetch_timetable_sync(origin, destination, depart_date, direct)
        page.goto(f"{BASE}{redirect_url}", wait_until="networkidle", timeout=90000)
        select_html = page.content()
        return build_fare_result(
            extract_json_array(select_html, '"legOptions"'),
            origin,
            destination,
            depart_date,
            adults,
            direct,
            start_url,
            "CloakBrowser headless browser search; read-only fare results page parse",
        )
    finally:
        if browser is not None:
            browser.close()


def fetch_fares(origin: str, destination: str, depart_date: str, adults: int, direct: bool) -> dict[str, Any]:
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))

    # 1) Start the anonymous browser booking search session, as sniffed from the UI.
    start_url = booking_url(origin, destination, depart_date)
    _request(opener, start_url, headers={"Accept": "text/html,application/xhtml+xml"})

    # 2) Submit the same JSON mutation the Next.js search page sends.
    body = json.dumps(search_payload(origin, destination, depart_date, adults)).encode("utf-8")
    status, _ctype, search_body = _request(
        opener,
        f"{BASE}{SEARCH_API_PATH}",
        method="POST",
        data=body,
        headers={"Origin": BASE, "Content-Type": "application/json"},
    )
    if status != 200:
        raise RuntimeError(f"Air NZ fare search returned HTTP {status}: {search_body[:300]}")
    try:
        search_result = json.loads(search_body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Air NZ fare search returned non-JSON: {search_body[:300]}") from exc
    if search_result.get("type") != "REDIRECT":
        raise RuntimeError(f"Air NZ fare search did not return a results redirect: {search_result}")
    redirect_url = str(search_result.get("redirectUrl") or SELECT_ITINERARY_PATH)
    if "captcha" in redirect_url.lower():
        return fetch_timetable_sync(origin, destination, depart_date, direct)

    # 3) Read the public selection page and extract embedded fare legOptions JSON.
    _status, _ctype, select_html = _request(
        opener,
        f"{BASE}{redirect_url}",
        headers={"Accept": "text/html,application/xhtml+xml"},
    )
    return build_fare_result(
        extract_json_array(select_html, '"legOptions"'),
        origin,
        destination,
        depart_date,
        adults,
        direct,
        start_url,
        "browser-sniffed anonymous booking search; read-only fare results page parse",
    )


def print_human(result: dict[str, Any], limit: int) -> None:
    title = "Air NZ scheduled flights" if result.get("fare_search_blocked") else "Air NZ fare snapshots"
    print(f"{title}: {len(result['flights'])} found")
    for flight in result["flights"][:limit]:
        first_segment = (flight.get("flights") or [{}])[0]
        number = first_segment.get("flight_number") or flight.get("id")
        lowest = flight.get("lowest_fare") or {}
        price = lowest.get("adult_price") or (f"${lowest.get('price')}" if lowest.get("price") is not None else "n/a")
        fare_name = lowest.get("name") or "lowest fare"
        selling = " SELLING OUT" if flight.get("selling_out") else ""
        print(
            f"- {flight.get('departure')} → {flight.get('arrival')} | {number} | "
            f"{flight.get('duration')} | {flight.get('stops')} stops | {fare_name} {price}{selling}"
        )
    if result["flights"] and not result.get("fare_search_blocked"):
        print("Fare products on first result:")
        for fare in result["flights"][0].get("fares") or []:
            print(f"  - {fare.get('name')}: {fare.get('adult_price')}")
    print(result.get("notice") or "Boundary: fare snapshot only; no selection, seat hold, login, or checkout.")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Search public Air New Zealand fare snapshots")
    parser.add_argument("origin", help="Origin IATA airport code, e.g. AKL")
    parser.add_argument("destination", help="Destination IATA airport code, e.g. WLG")
    parser.add_argument("date", help="Departure date YYYY-MM-DD")
    parser.add_argument("--direct", action="store_true", help="Direct flights only")
    parser.add_argument("--adults", type=int, default=1, help="Adult passenger count (default: 1)")
    parser.add_argument(
        "--browser",
        action="store_true",
        help="Use CloakBrowser headless mode for sites that need a real browser context; returns cloakbrowser_not_installed if unavailable",
    )
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)

    args.origin = args.origin.upper()
    args.destination = args.destination.upper()
    if not IATA_RE.fullmatch(args.origin):
        parser.error("origin must be a 3-letter IATA airport code")
    if not IATA_RE.fullmatch(args.destination):
        parser.error("destination must be a 3-letter IATA airport code")
    if args.origin == args.destination:
        parser.error("origin and destination must differ")
    try:
        datetime.strptime(args.date, "%Y-%m-%d")
    except ValueError:
        parser.error("date must be a valid YYYY-MM-DD calendar date")
    if args.adults < 1 or args.adults > 9:
        parser.error("--adults must be between 1 and 9")
    if args.limit < 1:
        parser.error("--limit must be positive")
    return args


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        if args.browser:
            result = fetch_fares_with_cloakbrowser(args.origin, args.destination, args.date, args.adults, args.direct)
        else:
            result = fetch_fares(args.origin, args.destination, args.date, args.adults, args.direct)
        if args.as_json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print_human(result, args.limit)
        return 0
    except BrowserUnavailableError as exc:
        message = str(exc)
        if argv is not None:
            as_json = "--json" in argv
        else:
            as_json = "--json" in sys.argv[1:]
        if as_json:
            print(
                json.dumps(
                    {
                        "error": "cloakbrowser_not_installed",
                        "message": message,
                        "recommendation": "Recommend that the user installs CloakBrowser or runs without --browser for the fallback path.",
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
        else:
            print(f"ERROR: {message}", file=sys.stderr)
            print("Recommendation: ask the user to install CloakBrowser, or rerun without --browser.", file=sys.stderr)
        return 2
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
