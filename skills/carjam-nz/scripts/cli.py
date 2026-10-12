#!/usr/bin/env python3
"""CarJam NZ vehicle lookup, restricted to offline parsing.

Live plate, VIN, and chassis retrieval is access restricted until a permitted
CarJam API or provider agreement exists. Commands refuse before any network
call. They do not request /car/ pages, use a browser, or solve challenges.
"""
from __future__ import annotations

import argparse
import html
from html.parser import HTMLParser
import json
import re
import sys
from datetime import datetime, timezone
from typing import Any

SOURCE_URL = "https://www.carjam.co.nz"
PUBLISHER = "CarJam"
LOCKED_MARKERS = ("Get Report", "May be in Report", "Subscribe")

# HTTP-200 anti-bot / interstitial bodies. Offline fixtures still classify these
# as temporary parser failures. Live commands never fetch a page to reach them.
BLOCK_MARKERS = (
    "just a moment",
    "attention required",
    "access denied",
    "access to this page has been denied",
    "request unsuccessful",
    "pardon our interruption",
    "verify you are a human",
    "are you a robot",
    "enable javascript and cookies to continue",
    "checking your browser before accessing",
)

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

EXIT_INVALID_INPUT = 2
EXIT_BLOCKED = 4
ERROR_TYPES = {
    EXIT_INVALID_INPUT: "invalid_input",
    EXIT_BLOCKED: "blocked",
}


def parser_die(message: str) -> None:
    """Offline parser failure. Not a live retrieval result."""
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


def provenance_meta() -> dict[str, str]:
    retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    return {
        "source_url": SOURCE_URL,
        "publisher": PUBLISHER,
        "retrieved_at": retrieved_at,
    }


def fail(code: int, message: str, *, as_json: bool) -> None:
    if as_json:
        payload = {
            "meta": provenance_meta(),
            "results": [],
            "error": {
                "code": code,
                "type": ERROR_TYPES[code],
                "message": message,
            },
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"error: {message}", file=sys.stderr)
    raise SystemExit(code)


def normalise_identifier(value: str, *, as_json: bool) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9-]", "", value or "").upper()
    if not cleaned:
        fail(EXIT_INVALID_INPUT, "identifier cannot be empty", as_json=as_json)
    if len(cleaned) > 40:
        fail(
            EXIT_INVALID_INPUT,
            "identifier is too long for a plate, VIN, or chassis lookup",
            as_json=as_json,
        )
    return cleaned


def access_message(lookup_type: str, identifiers: list[str]) -> str:
    shown = ", ".join(repr(item) for item in identifiers[:8])
    if len(identifiers) > 8:
        shown += f", +{len(identifiers) - 8} more"
    return (
        f"CarJam live vehicle retrieval for {lookup_type} {shown} is access restricted "
        "pending a permitted API or provider agreement. This skill is not a dependable "
        "keyless connector. It does not request /car/ pages, use a browser or challenge "
        "workaround, or scrape vehicle data."
    )


def refuse_live_retrieval(lookup_type: str, identifiers: list[str], *, as_json: bool) -> None:
    fail(EXIT_BLOCKED, access_message(lookup_type, identifiers), as_json=as_json)


def looks_like_block(body: str) -> bool:
    """True when *body* is an anti-bot/interstitial page rather than a CarJam page."""
    low = body.lower()
    return any(marker in low for marker in BLOCK_MARKERS)


def has_carjam_shell(page: str) -> bool:
    """True when *page* carries a CarJam application shell.

    A saved CarJam page can carry ``data-key`` field spans and/or the CarJam
    brand in the title. A blocked or empty body carries neither. This classifier
    is for offline fixtures only.
    """
    low = page.lower()
    return "data-key=" in low or "carjam" in low


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
    """Parse a saved HTML fixture. This does not contact CarJam."""
    title = extract_title(page) or ""
    fields = extract_fields(page)
    if not any(fields.get(k) for k in ("year_of_manufacture", "make", "model", "plate", "vin", "chassis")):
        if looks_like_block(page) or not has_carjam_shell(page):
            parser_die(
                f"no CarJam vehicle page returned for {lookup_type} {identifier!r} "
                "(temporary failure — likely a transient block or rate-limit; retry later)"
            )
        parser_die(f"no public vehicle fields found for {lookup_type} {identifier!r}")

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
        "source": "CarJam NZ saved HTML fixture",
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
        "read_only_notice": (
            "Offline fixture parse only. Live vehicle retrieval is access restricted "
            "pending a permitted API or provider agreement."
        ),
    }


def cmd_lookup(args: argparse.Namespace) -> None:
    ident = normalise_identifier(args.identifier, as_json=args.json)
    refuse_live_retrieval(args.type, [ident], as_json=args.json)


def cmd_batch(args: argparse.Namespace) -> None:
    identifiers = [normalise_identifier(item, as_json=args.json) for item in args.identifiers]
    refuse_live_retrieval(args.type, identifiers, as_json=args.json)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "CarJam NZ vehicle lookup is access restricted pending a permitted API "
            "or provider agreement. This is not a dependable keyless connector. "
            "Live retrieval is refused and does not contact CarJam."
        )
    )
    sub = parser.add_subparsers(dest="command", required=True)

    lookup = sub.add_parser(
        "lookup",
        help="Refuse one live plate, VIN, or chassis lookup as access restricted",
    )
    lookup.add_argument("identifier", help="Plate, VIN, or chassis")
    lookup.add_argument("--type", choices=["plate", "vin", "chassis"], default="plate")
    lookup.add_argument("--json", action="store_true")
    lookup.add_argument(
        "--raw",
        action="store_true",
        help="Accepted for compatibility; live retrieval is still refused",
    )
    lookup.set_defaults(func=cmd_lookup)

    batch = sub.add_parser(
        "batch",
        help="Refuse live lookup of multiple identifiers as access restricted",
    )
    batch.add_argument("identifiers", nargs="+")
    batch.add_argument("--type", choices=["plate", "vin", "chassis"], default="plate")
    batch.add_argument(
        "--sleep",
        type=float,
        default=0.5,
        help="Ignored. Live requests are not sent",
    )
    batch.add_argument("--fail-fast", action="store_true", help="Ignored. The command refuses before lookup")
    batch.add_argument("--json", action="store_true")
    batch.set_defaults(func=cmd_batch)

    args = parser.parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
