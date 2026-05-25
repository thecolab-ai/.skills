#!/usr/bin/env python3
"""NZ Post Tracking CLI -- track NZ Post parcels via the public tools.nzpost.co.nz API.

Self-contained stdlib wrapper. No authentication required.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

API_BASE = "https://tools.nzpost.co.nz/tracking/api"
API_PARCELS = "/parceltrack/parcels"

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:151.0) Gecko/20100101 Firefox/151.0"
REFERER = "https://www.nzpost.co.nz/tools/tracking"

# Simplified regex covering common NZ Post domestic and international formats.
# Full pattern is available from the tracking-masks endpoint; this covers typical use.
TRACKING_RE = re.compile(
    r"^("
    r"\d{5,6}"                       # 5-6 digit domestic short codes
    r"|\d{8}"                        # 8 digit
    r"|[A-Z0-9]{10}"                 # 10-char alphanumeric
    r"|[A-Z]{2}\d{9}[A-Z]{2}"       # UPU international (e.g. EA123456789NZ)
    r"|[A-Z0-9]{20}"                 # 20-char alphanumeric
    r"|[A-Z0-9]{3}\d{7}"            # 3-letter prefix + 7 digits
    r"|[A-Z0-9]{5}\d{7}"            # 5-char prefix + 7 digits
    r"|[A-Z0-9]{24}"                 # 24-char
    r"|\d{10,14}"                    # 10-14 digits
    r"|\d{18}"                       # 18 digits
    r"|\d{20}"                       # 20 digits
    r"|\d{22}"                       # 22 digits
    r"|\d{30}"                       # 30 digits
    r"|[A-Z]{3}\d{8}"               # 3-letter + 8 digits
    r"|[A-Z]{2}\d{11}"              # 2-letter + 11 digits
    r"|TP[A-Z0-9]{16}"              # TP prefix 18-char
    r"|TPW\d{10}"                    # TPW + 10 digits
    r"|(RMA|RMC|RMP)\d{10}"         # RMA/RMC/RMP + 10 digits
    r"|CTC\d{8}"                     # CTC + 8 digits
    r"|SUN\d{10}"                    # SUN + 10 digits
    r"|MFB\d{17}[A-Z]{2}"           # MFB + 17 digits + 2 letters
    r")",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def die(message: str, code: int = 1) -> None:
    print(f"nzpost-tracking: {message}", file=sys.stderr)
    raise SystemExit(code)


def _safe_float(v: Any, default: float = 0.0) -> float:
    """Safely convert value to float, returning default if None or invalid."""
    if v is None:
        return default
    try:
        return float(v)
    except (ValueError, TypeError):
        return default


def _safe_str(v: Any, default: str = "") -> str:
    """Safely convert value to str, returning default if None."""
    if v is None:
        return default
    return str(v)


def strip_html(text: str) -> str:
    """Strip HTML tags from a string."""
    return re.sub(r"<[^>]+>", "", text)


def validate_tracking_number(tn: str) -> str:
    """Validate and normalise a tracking number. Returns cleaned string or exits."""
    cleaned = tn.strip().upper()
    if not cleaned:
        die("tracking number cannot be empty")
    if not TRACKING_RE.match(cleaned):
        die(
            f"unrecognised tracking number format: {tn!r}\n"
            "  NZ Post tracking numbers are typically 13 or 18-20 digits, or alphanumeric codes."
        )
    return cleaned


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

def fetch_tracking(tracking_reference: str, timeout: int = 15) -> dict[str, Any]:
    """Fetch tracking data for a tracking reference. Returns parsed JSON."""
    params = urllib.parse.urlencode({"tracking_reference": tracking_reference})
    url = f"{API_BASE}{API_PARCELS}?{params}"
    headers = {
        "User-Agent": UA,
        "Referer": REFERER,
        "Content-Type": "application/json",
    }
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            return json.loads(raw)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        die(f"HTTP {e.code} from tracking API: {raw[:300]}")
    except urllib.error.URLError as e:
        die(f"network error calling tracking API: {e.reason}")
    except json.JSONDecodeError as e:
        die(f"invalid JSON from tracking API: {e}")


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def print_banner() -> None:
    print("NZ Post Tracking")
    print("================")


def fmt_datetime(dt: str | None) -> str:
    """Format ISO datetime string to a human-readable local-style string."""
    if not dt:
        return "unknown"
    # dt is UTC e.g. "2026-03-12T20:34:07Z"
    # Show as-is but make it readable
    try:
        d, t = dt.rstrip("Z").split("T")
        year, mon, day = d.split("-")
        hour, minute, _ = t.split(":")
        months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        mon_name = months[int(mon) - 1]
        return f"{day} {mon_name} {year} {hour}:{minute} UTC"
    except Exception:
        return dt


def emit_human(tracking_reference: str, events: list[dict[str, Any]]) -> None:
    """Print human-readable tracking output."""
    print_banner()
    print(f"Tracking: {tracking_reference}")
    print()

    if not events:
        print("  No tracking events found.")
        return

    # Latest event = last in list
    latest = events[-1]
    latest_status = _safe_str(latest.get("status"), "Unknown").strip()
    latest_dt = fmt_datetime(latest.get("date_time"))
    latest_desc = strip_html(_safe_str(latest.get("description"), "")).strip()
    latest_depot = _safe_str(latest.get("depot_name"), "").strip()

    print(f"Status:   {latest_status}")
    print(f"Updated:  {latest_dt}")
    if latest_depot:
        print(f"Location: {latest_depot}")
    if latest_desc:
        print(f"Detail:   {latest_desc}")
    print()
    print(f"Events ({len(events)} total):")
    print()

    for ev in events:
        dt = fmt_datetime(ev.get("date_time"))
        status = _safe_str(ev.get("status"), "").strip()
        depot = _safe_str(ev.get("depot_name"), "").strip()
        run = _safe_str(ev.get("run_name"), "").strip()
        loc_parts = [p for p in [depot, run] if p]
        loc_str = f"  [{', '.join(loc_parts)}]" if loc_parts else ""
        print(f"  {dt}  {status}{loc_str}")


def emit_json_output(tracking_reference: str, events: list[dict[str, Any]]) -> None:
    """Print JSON-formatted tracking output."""
    latest = events[-1] if events else {}
    result = {
        "tracking_reference": tracking_reference,
        "status": _safe_str(latest.get("status"), "").strip(),
        "last_updated": _safe_str(latest.get("date_time"), ""),
        "last_depot": _safe_str(latest.get("depot_name"), "").strip() or None,
        "event_count": len(events),
        "events": [
            {
                "date_time": ev.get("date_time"),
                "status": _safe_str(ev.get("status"), "").strip(),
                "description": strip_html(_safe_str(ev.get("description"), "")).strip(),
                "depot_name": ev.get("depot_name"),
                "run_name": ev.get("run_name"),
                "edifact_code": ev.get("edifact_code"),
                "seqref": ev.get("seqref"),
            }
            for ev in events
        ],
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_track(args: argparse.Namespace) -> None:
    """Track a parcel by tracking number."""
    tn = validate_tracking_number(args.number)

    data = fetch_tracking(tn)

    if not data.get("success"):
        status_code = data.get("status_code")
        if not args.json:
            print_banner()
        die(f"tracking lookup failed (status_code={status_code})")

    results = data.get("results", [])
    if not results:
        if not args.json:
            print_banner()
        die(f"no tracking data found for: {tn}")

    parcel = results[0]
    events = parcel.get("tracking_events", [])
    ref = _safe_str(parcel.get("tracking_reference", tn))

    if args.json:
        emit_json_output(ref, events)
    else:
        emit_human(ref, events)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="NZ Post Tracking -- look up NZ Post parcel status via the public tracking API"
    )
    sub = ap.add_subparsers(dest="command")

    # track
    sp = sub.add_parser("track", help="track a parcel by tracking number")
    sp.add_argument("number", help="NZ Post tracking number (e.g. 00794210392715622565)")
    sp.add_argument("--json", action="store_true", help="machine-readable JSON output")
    sp.set_defaults(func=cmd_track)

    return ap


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 1
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
