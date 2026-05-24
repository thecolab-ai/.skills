#!/usr/bin/env python3
"""CarJam NZ public read-only vehicle information lookup CLI.

Fetches the public CarJam vehicle page and extracts the free/basic fields that are
already rendered in the HTML. No login, paid report purchase, owner lookup, or
write actions.
"""
from __future__ import annotations

import argparse
import html
from html.parser import HTMLParser
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

BASE_URL = "https://www.carjam.co.nz"
USER_AGENT = "Mozilla/5.0 (compatible; thecolab-carjam-nz-skill/1.0)"
LOCKED_MARKERS = ("Get Report", "May be in Report", "Subscribe")

LABELS = {
    "year_of_manufacture": "Year",
    "make": "Make",
    "model": "Model",
    "submodel": "Submodel",
    "main_colour": "Colour",
    "second_colour": "Second colour",
    "body_style": "Body style",
    "plate": "Plate",
    "vin": "VIN",
    "chassis": "Chassis",
    "engine_number": "Engine number",
    "cc_rating": "Engine size",
    "fuel_type": "Fuel",
    "latest_odometer_reading": "Latest odometer",
    "registration_status": "Registration status",
    "licence_expiry": "Licence expiry",
    "expiry_date_of_last_successful_wof": "WOF expiry",
    "date_of_latest_wof_inspection": "Latest WOF inspection",
    "result_of_latest_wof_inspection": "Latest WOF result",
    "police_reported_stolen": "Police stolen list",
    "reported_stolen": "Reported stolen",
    "ruc": "RUC",
    "cof": "COF",
    "country_of_origin": "Country of origin",
    "vehicle_type": "Vehicle type",
    "no_of_seats": "Seats",
    "date_of_first_registration_in_nz": "First NZ registration",
    "date_of_last_registration": "Last registration",
    "cancellation_date_of_registration": "Registration cancellation date",
    "cancellation_reason_code": "Registration cancellation reason",
    "previous_country_of_registration": "Previous country",
    "odometer_inconsistent": "Odometer inconsistent",
    "usage_level": "Usage level",
    "imported_damaged": "Imported damaged",
    "write_off": "Write-off",
    "flood_description": "Flood records",
}

SUMMARY_KEYS = [
    "year_of_manufacture", "make", "model", "submodel", "main_colour", "second_colour",
    "body_style", "plate", "vin", "chassis", "fuel_type", "cc_rating", "latest_odometer_reading",
    "registration_status", "expiry_date_of_last_successful_wof", "licence_expiry",
    "police_reported_stolen", "ruc", "cof",
]


def die(message: str, code: int = 1) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(code)


def normalise_identifier(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9-]", "", value or "").upper()
    if not cleaned:
        die("identifier cannot be empty")
    if len(cleaned) > 40:
        die("identifier is too long for a plate/VIN/chassis lookup")
    return cleaned


_RETRY_STATUSES = {429, 502, 503, 504}
_RETRY_DELAYS = (2, 5, 10)  # seconds between attempts 1→2, 2→3, 3→fail


def fetch(url: str) -> str:
    """Fetch *url* with up to 3 attempts and exponential backoff.

    Retries on HTTP 429/502/503/504, connection/timeout errors, and Cloudflare
    challenge responses ("Just a moment" body or ``cf-mitigated`` header).
    Other 4xx errors (bad plate etc.) fail immediately.
    """
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    last_error: str = "unknown error"
    for attempt, delay in enumerate((*_RETRY_DELAYS, None), start=1):
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                body = response.read().decode("utf-8", "replace")
                # Cloudflare challenge — treat as transient
                cf_mitigated = response.headers.get("cf-mitigated", "")
                if cf_mitigated or "Just a moment" in body:
                    last_error = f"Cloudflare challenge on attempt {attempt}"
                    should_retry = True
                else:
                    return body
        except urllib.error.HTTPError as exc:
            if exc.code not in _RETRY_STATUSES:
                # Non-retryable HTTP error (e.g. 404 for bad plate) — fail fast
                detail = exc.read().decode("utf-8", "replace")[:300]
                die(f"HTTP {exc.code} for {url}: {detail}")
            last_error = f"HTTP {exc.code} for {url}"
            should_retry = True
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = f"network error for {url}: {exc}"
            should_retry = True

        if should_retry:
            if delay is None:
                # All retries exhausted
                die(f"all {attempt} attempts failed — last error: {last_error}")
            time.sleep(delay)

    raise AssertionError("unreachable")


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self.skip_depth += 1
        elif tag in {"br", "p", "div", "tr", "td", "li", "h1", "h2", "h3"}:
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self.skip_depth:
            self.skip_depth -= 1
        elif tag in {"p", "div", "tr", "td", "li", "h1", "h2", "h3"}:
            self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        if not self.skip_depth:
            self.parts.append(data)

    def text(self) -> str:
        return re.sub(r"\s+", " ", " ".join(self.parts)).strip()


def strip_tags(fragment: str) -> str:
    parser = TextExtractor()
    parser.feed(fragment)
    value = html.unescape(parser.text())
    value = re.sub(r"\s+", " ", value).strip(" :\t\n\r")
    return value


def extract_title(page: str) -> str | None:
    match = re.search(r"<title>(.*?)</title>", page, re.S | re.I)
    if not match:
        return None
    return strip_tags(match.group(1))


def extract_fields(page: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for match in re.finditer(r'<span\s+class="key"\s+data-key="([^"]+)"[^>]*>', page, re.I):
        key = match.group(1)
        if key in fields:
            continue
        row_end = page.find("</td>", match.end())
        if row_end == -1:
            row_end = min(len(page), match.end() + 2500)
        row = page[match.end():row_end]
        value_match = re.search(r'<span\s+class="value"[^>]*>(.*)', row, re.S | re.I)
        if not value_match:
            continue
        value = strip_tags(value_match.group(1))
        value = value.replace("ⓘ", "")
        value = re.sub(r"\s+", " ", value).strip()
        if value:
            fields[key] = value
    return fields


def is_locked(value: str | None) -> bool:
    return bool(value and any(marker.lower() in value.lower() for marker in LOCKED_MARKERS))


def parse_vehicle(page: str, *, source_url: str, identifier: str, lookup_type: str) -> dict[str, Any]:
    title = extract_title(page) or ""
    fields = extract_fields(page)
    if not any(fields.get(k) for k in ("year_of_manufacture", "make", "model", "plate", "vin", "chassis")):
        die(f"no public vehicle fields found for {lookup_type} {identifier!r}")

    summary = {key: fields.get(key) for key in SUMMARY_KEYS if key in fields}
    locked = sorted(key for key, value in fields.items() if is_locked(value))
    vehicle_name = " ".join(
        part for part in [fields.get("year_of_manufacture"), fields.get("make"), fields.get("model"), fields.get("submodel")] if part
    )
    alerts = []
    for pattern in [
        r"WOF expired[^.]+\.",
        r"Licence expired[^.]+\.",
        r"Registration has been cancelled[^.]+\.",
        r"Registration cancellation reason:[^.]+\.",
        r"Vehicle failed WOF on:[^.]+\.",
    ]:
        found = re.search(pattern, strip_tags(page), re.I)
        if found:
            alerts.append(found.group(0).strip())

    return {
        "source": "CarJam NZ public vehicle page",
        "source_url": source_url,
        "lookup_type": lookup_type,
        "query": identifier,
        "title": title,
        "vehicle": vehicle_name or None,
        "plate": fields.get("plate"),
        "summary": summary,
        "locked_fields": locked,
        "alerts": alerts,
        "fields": fields,
        "read_only_notice": "Public/basic HTML fields only; paid report, owner, purchase, account, and write actions are not used.",
    }


def lookup(identifier: str, lookup_type: str) -> dict[str, Any]:
    ident = normalise_identifier(identifier)
    query = urllib.parse.urlencode({lookup_type: ident})
    url = f"{BASE_URL}/car/?{query}"
    page = fetch(url)
    return parse_vehicle(page, source_url=url, identifier=ident, lookup_type=lookup_type)


def print_vehicle(result: dict[str, Any], *, all_fields: bool = False) -> None:
    print(f"{result.get('vehicle') or result.get('title')}")
    print(f"Source: {result['source_url']}")
    fields = result["fields"] if all_fields else result["summary"]
    for key, value in fields.items():
        label = LABELS.get(key, key.replace("_", " ").title())
        locked = " [paid/report-gated]" if is_locked(value) else ""
        print(f"{label}: {value}{locked}")
    if result.get("alerts"):
        print("Alerts:")
        for alert in result["alerts"]:
            print(f"- {alert}")
    if result.get("locked_fields"):
        print(f"Report-gated fields: {', '.join(result['locked_fields'][:12])}")


def cmd_lookup(args: argparse.Namespace) -> None:
    result = lookup(args.identifier, args.type)
    if args.json:
        if not args.raw:
            result = {k: v for k, v in result.items() if k != "fields"}
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print_vehicle(result, all_fields=args.raw)


def cmd_batch(args: argparse.Namespace) -> None:
    rows = []
    for index, identifier in enumerate(args.identifiers):
        if index and args.sleep:
            time.sleep(args.sleep)
        try:
            result = lookup(identifier, args.type)
            rows.append({
                "query": result["query"],
                "vehicle": result.get("vehicle"),
                "plate": result.get("plate"),
                "make": result["summary"].get("make"),
                "model": result["summary"].get("model"),
                "year": result["summary"].get("year_of_manufacture"),
                "colour": result["summary"].get("main_colour"),
                "registration_status": result["summary"].get("registration_status"),
                "wof_expiry": result["summary"].get("expiry_date_of_last_successful_wof"),
                "source_url": result["source_url"],
            })
        except SystemExit as exc:
            if args.fail_fast:
                raise
            rows.append({"query": identifier, "error": str(exc)})
    if args.json:
        print(json.dumps({"vehicles": rows}, indent=2, ensure_ascii=False))
    else:
        for row in rows:
            if row.get("error"):
                print(f"{row['query']}: ERROR {row['error']}")
            else:
                bits = [str(row.get("query")), str(row.get("vehicle") or "unknown vehicle")]
                for key in ["colour", "registration_status", "wof_expiry"]:
                    if row.get(key):
                        bits.append(f"{key.replace('_', ' ')}: {row[key]}")
                print(" | ".join(bits))


def main() -> int:
    parser = argparse.ArgumentParser(description="CarJam NZ public read-only vehicle lookup.")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("lookup", help="Lookup one vehicle by plate, VIN, or chassis")
    p.add_argument("identifier", help="Plate, VIN, or chassis")
    p.add_argument("--type", choices=["plate", "vin", "chassis"], default="plate")
    p.add_argument("--json", action="store_true")
    p.add_argument("--raw", action="store_true", help="Include/print all parsed public fields")
    p.set_defaults(func=cmd_lookup)

    p = sub.add_parser("batch", help="Lookup multiple identifiers and print a compact summary")
    p.add_argument("identifiers", nargs="+")
    p.add_argument("--type", choices=["plate", "vin", "chassis"], default="plate")
    p.add_argument("--sleep", type=float, default=0.5, help="Seconds to sleep between live requests")
    p.add_argument("--fail-fast", action="store_true")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_batch)

    args = parser.parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
