#!/usr/bin/env python3
"""NZ ferries lightweight read-only CLI.

Self-contained stdlib wrapper around public ferry schedule and alert surfaces.
No login, booking mutation, payment, browser automation, or third-party deps.
"""
from __future__ import annotations

import argparse
import csv
import http.cookiejar
import html
import io
import json
import os
import pathlib
import re
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import date, datetime, time as dtime, timedelta, timezone
from html.parser import HTMLParser
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "lib"))
import nzfetch  # noqa: E402

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover - Python <3.9 fallback
    ZoneInfo = None  # type: ignore[assignment]


UA = os.environ.get(
    "NZ_FERRIES_USER_AGENT",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
)

NZ_TZ = ZoneInfo("Pacific/Auckland") if ZoneInfo else timezone(timedelta(hours=12))

SEALINK_BASE = "https://www.sealink.co.nz"
SEALINK_SCHEDULES = SEALINK_BASE + "/ferry-schedules"
SEALINK_ALERTS = SEALINK_BASE + "/travel-alerts"
SEALINK_TERMINALS = SEALINK_BASE + "/api/system/terminalLocations"
SEALINK_CATEGORY_MATRIX = SEALINK_BASE + "/api/booking/GetProductCategoryMatrix"
SEALINK_TERMINAL_MATRIX = SEALINK_BASE + "/api/system/getTerminalProductMatrix"
SEALINK_SLOTS = SEALINK_BASE + "/api/booking/getAvailableBookingSlots"

INTERISLANDER_BASE = "https://www.interislander.co.nz"
INTERISLANDER_TIMETABLE = INTERISLANDER_BASE + "/plan/ferry-timetable"
INTERISLANDER_ALERTS = INTERISLANDER_BASE + "/plan/service-alerts"
INTERISLANDER_DISRUPTIONS = INTERISLANDER_BASE + "/api/v1/disruption"

BLUEBRIDGE_BASE = "https://www.bluebridge.co.nz"
BLUEBRIDGE_TIMETABLE = BLUEBRIDGE_BASE + "/timetable/"
BLUEBRIDGE_ALERTS = BLUEBRIDGE_BASE + "/service-alerts/"

FULLERS_TIMETABLE = "https://www.fullers.co.nz/timetables-and-fares/"
FULLERS_UPDATES = "https://www.fullers.co.nz/news-updates/customer-updates/"
FULLERS_APP_BASE = "https://pim-mobile.fullers.co.nz"
BROWSER_MODE = False

AT_API_BASE = "https://api.at.govt.nz"
AT_GTFS_ZIP = os.environ.get("NZ_FERRIES_AT_GTFS_ZIP", "https://gtfs.at.govt.nz/gtfs.zip")
AT_GTFS_CACHE = os.environ.get("NZ_FERRIES_AT_GTFS_CACHE", os.path.join(tempfile.gettempdir(), "nz-ferries-at-gtfs.zip"))
AT_GTFS_CACHE_TTL_SECONDS = int(os.environ.get("NZ_FERRIES_AT_GTFS_CACHE_TTL_SECONDS", str(6 * 60 * 60)))

AT_SKILL_HINT = (
    "Fullers360 Auckland metro ferry schedules are fetched here from AT public GTFS static data; "
    "service alerts are fetched from AT GTFS-RT."
)

FULLERS_SOURCE_NOTE = (
    "Fullers360 app/site endpoints were reverse-engineered but direct stdlib requests are Radware-gated; "
    "this CLI uses AT public GTFS/GTFS-RT for Fullers-operated metro ferry schedules and alerts."
)

FULLERS_ALERT_ROUTE_IDS = {
    "DEV-209",
    "MTIA-209",
    "GULF-209",
    "HCRU-209",
    "HMB-209",
    "HOBS-209",
    "RANG-209",
    "BAYS-240",
    "BIRK-240",
    "PINE-210",
    "WSTH-211",
}


def at_api_key() -> str:
    key = os.environ.get("AT_API_KEY")
    if not key:
        die("AT_API_KEY is required for AT Metro/Fullers data; export it before running this command", 3)
    return key


OPERATORS: dict[str, dict[str, Any]] = {
    "sealink": {
        "name": "SeaLink",
        "website": "https://www.sealink.co.nz",
        "coverage": "Auckland vehicle/passenger ferries: Waiheke Island and Great Barrier Island",
        "live": ["sailings", "fares", "availability", "alerts"],
        "source": "sealink.co.nz public schedule and alert pages",
    },
    "interislander": {
        "name": "Interislander",
        "website": "https://www.interislander.co.nz",
        "coverage": "Cook Strait passenger/vehicle ferries: Wellington <-> Picton",
        "live": ["published timetable", "service alerts"],
        "source": "interislander.co.nz public timetable and disruption API",
    },
    "bluebridge": {
        "name": "Bluebridge",
        "website": "https://www.bluebridge.co.nz",
        "coverage": "Cook Strait passenger/vehicle ferries: Wellington <-> Picton",
        "live": ["published timetable", "service alerts"],
        "source": "bluebridge.co.nz public timetable and service-alert pages",
    },
    "fullers360": {
        "name": "Fullers360",
        "website": "https://www.fullers.co.nz",
        "coverage": "Auckland Harbour and Hauraki Gulf passenger ferries",
        "live": ["scheduled sailings", "service alerts"],
        "source": "AT public GTFS static schedules and GTFS-RT service alerts for Fullers/metro ferry routes",
        "scope_note": FULLERS_SOURCE_NOTE,
    },
}

OPERATOR_ALIASES = {
    "fullers": "fullers360",
    "fullers360": "fullers360",
    "fullers-360": "fullers360",
    "sealink": "sealink",
    "sea-link": "sealink",
    "interislander": "interislander",
    "kiwirail": "interislander",
    "bluebridge": "bluebridge",
    "blue-bridge": "bluebridge",
}


ROUTES: dict[str, dict[str, Any]] = {
    "wellington-picton": {
        "name": "Wellington to Picton",
        "from": "Wellington",
        "to": "Picton",
        "operators": ["interislander", "bluebridge"],
        "aliases": ["wlg-pic", "wellington-to-picton", "cook-strait-north-south"],
    },
    "picton-wellington": {
        "name": "Picton to Wellington",
        "from": "Picton",
        "to": "Wellington",
        "operators": ["interislander", "bluebridge"],
        "aliases": ["pic-wlg", "picton-to-wellington", "cook-strait-south-north"],
    },
    "auckland-waiheke": {
        "name": "Auckland to Waiheke Island",
        "from": "Auckland",
        "to": "Waiheke Island",
        "operators": ["sealink", "fullers360"],
        "sealink_from_code": "AKL",
        "sealink_to_code": "WHK",
        "fullers_gtfs_route_ids": ["MTIA-209"],
        "fullers_from_stop_ids": ["9711-113c104a"],
        "fullers_to_stop_ids": ["9790-3b0a55c0"],
        "aliases": ["akl-waiheke", "auckland-to-waiheke", "waiheke"],
    },
    "waiheke-auckland": {
        "name": "Waiheke Island to Auckland",
        "from": "Waiheke Island",
        "to": "Auckland",
        "operators": ["sealink", "fullers360"],
        "sealink_from_code": "WHK",
        "sealink_to_code": "AKL",
        "fullers_gtfs_route_ids": ["MTIA-209"],
        "fullers_from_stop_ids": ["9790-3b0a55c0"],
        "fullers_to_stop_ids": ["9711-113c104a"],
        "aliases": ["waiheke-akl", "waiheke-to-auckland"],
    },
    "half-moon-bay-waiheke": {
        "name": "Half Moon Bay to Waiheke Island",
        "from": "Auckland East, Half Moon Bay",
        "to": "Waiheke Island, Kennedy Point",
        "operators": ["sealink"],
        "sealink_from_code": "AKL",
        "sealink_to_code": "WHK",
        "sealink_from_terminal": "Auckland East, Half Moon Bay",
        "sealink_to_terminal": "Waiheke Island, Kennedy Point",
        "aliases": ["hmb-waiheke", "half-moon-bay-to-waiheke"],
    },
    "auckland-city-waiheke": {
        "name": "Auckland City Hamer St to Waiheke Island",
        "from": "Auckland City, Hamer St",
        "to": "Waiheke Island, Kennedy Point",
        "operators": ["sealink"],
        "sealink_from_code": "AKL",
        "sealink_to_code": "WHK",
        "sealink_from_terminal": "Auckland City, Hamer St",
        "sealink_to_terminal": "Waiheke Island, Kennedy Point",
        "aliases": ["hamer-st-waiheke", "wynyard-waiheke", "city-waiheke"],
    },
    "auckland-great-barrier": {
        "name": "Auckland to Great Barrier Island",
        "from": "Auckland",
        "to": "Great Barrier Island",
        "operators": ["sealink"],
        "sealink_from_code": "AKL",
        "sealink_to_code": "GBI",
        "aliases": ["akl-great-barrier", "auckland-to-great-barrier", "great-barrier"],
    },
    "great-barrier-auckland": {
        "name": "Great Barrier Island to Auckland",
        "from": "Great Barrier Island",
        "to": "Auckland",
        "operators": ["sealink"],
        "sealink_from_code": "GBI",
        "sealink_to_code": "AKL",
        "aliases": ["great-barrier-akl", "great-barrier-to-auckland"],
    },
    "auckland-devonport": {
        "name": "Auckland to Devonport",
        "from": "Auckland Downtown",
        "to": "Devonport",
        "operators": ["fullers360"],
        "fullers_gtfs_route_ids": ["DEV-209"],
        "fullers_from_stop_ids": ["9702-e5f42777"],
        "fullers_to_stop_ids": ["9670-6a81c363"],
        "aliases": ["devonport", "auckland-to-devonport"],
    },
    "devonport-auckland": {
        "name": "Devonport to Auckland",
        "from": "Devonport",
        "to": "Auckland Downtown",
        "operators": ["fullers360"],
        "fullers_gtfs_route_ids": ["DEV-209"],
        "fullers_from_stop_ids": ["9670-6a81c363"],
        "fullers_to_stop_ids": ["9702-e5f42777"],
        "aliases": ["devonport-to-auckland"],
    },
    "auckland-rangitoto": {
        "name": "Auckland to Rangitoto Island",
        "from": "Auckland Downtown",
        "to": "Rangitoto Island",
        "operators": ["fullers360"],
        "fullers_gtfs_route_ids": ["RANG-209"],
        "fullers_from_stop_ids": ["9714-be8c2752"],
        "fullers_to_stop_ids": ["9760-bfdc6415"],
        "aliases": ["rangitoto", "auckland-to-rangitoto"],
    },
    "rangitoto-auckland": {
        "name": "Rangitoto Island to Auckland",
        "from": "Rangitoto Island",
        "to": "Auckland Downtown",
        "operators": ["fullers360"],
        "fullers_gtfs_route_ids": ["RANG-209"],
        "fullers_from_stop_ids": ["9760-bfdc6415"],
        "fullers_to_stop_ids": ["9714-be8c2752"],
        "aliases": ["rangitoto-to-auckland"],
    },
    "devonport-rangitoto": {
        "name": "Devonport to Rangitoto Island",
        "from": "Devonport",
        "to": "Rangitoto Island",
        "operators": ["fullers360"],
        "fullers_gtfs_route_ids": ["RANG-209"],
        "fullers_from_stop_ids": ["9672-722c912c"],
        "fullers_to_stop_ids": ["9760-bfdc6415"],
        "aliases": ["devonport-to-rangitoto"],
    },
    "rangitoto-devonport": {
        "name": "Rangitoto Island to Devonport",
        "from": "Rangitoto Island",
        "to": "Devonport",
        "operators": ["fullers360"],
        "fullers_gtfs_route_ids": ["RANG-209"],
        "fullers_from_stop_ids": ["9760-bfdc6415"],
        "fullers_to_stop_ids": ["9672-722c912c"],
        "aliases": ["rangitoto-to-devonport"],
    },
    "auckland-half-moon-bay": {
        "name": "Auckland to Half Moon Bay",
        "from": "Auckland Downtown",
        "to": "Half Moon Bay",
        "operators": ["fullers360"],
        "fullers_gtfs_route_ids": ["HMB-209"],
        "fullers_from_stop_ids": ["9705-54050269"],
        "fullers_to_stop_ids": ["9700-2589eeb8"],
        "aliases": ["auckland-to-half-moon-bay"],
    },
    "half-moon-bay-auckland": {
        "name": "Half Moon Bay to Auckland",
        "from": "Half Moon Bay",
        "to": "Auckland Downtown",
        "operators": ["fullers360"],
        "fullers_gtfs_route_ids": ["HMB-209"],
        "fullers_from_stop_ids": ["9700-2589eeb8"],
        "fullers_to_stop_ids": ["9705-54050269"],
        "aliases": ["hmb-auckland", "half-moon-bay-to-auckland"],
    },
    "auckland-bayswater": {
        "name": "Auckland to Bayswater",
        "from": "Auckland Downtown",
        "to": "Bayswater",
        "operators": ["fullers360"],
        "fullers_gtfs_route_ids": ["BAYS-240", "BIRK-240"],
        "fullers_from_stop_ids": ["9701-8d24d4bc"],
        "fullers_to_stop_ids": ["9640-24d53d9c"],
        "aliases": ["auckland-to-bayswater"],
    },
    "bayswater-auckland": {
        "name": "Bayswater to Auckland",
        "from": "Bayswater",
        "to": "Auckland Downtown",
        "operators": ["fullers360"],
        "fullers_gtfs_route_ids": ["BAYS-240", "BIRK-240"],
        "fullers_from_stop_ids": ["9640-24d53d9c"],
        "fullers_to_stop_ids": ["9701-8d24d4bc"],
        "aliases": ["bayswater", "bayswater-to-auckland"],
    },
    "auckland-hobsonville": {
        "name": "Auckland to Hobsonville Point",
        "from": "Auckland Downtown",
        "to": "Hobsonville Point",
        "operators": ["fullers360"],
        "fullers_gtfs_route_ids": ["HOBS-209"],
        "fullers_from_stop_ids": ["9707-62737f23"],
        "fullers_to_stop_ids": ["9720-9e1a95ac"],
        "aliases": ["auckland-to-hobsonville"],
    },
    "hobsonville-auckland": {
        "name": "Hobsonville Point to Auckland",
        "from": "Hobsonville Point",
        "to": "Auckland Downtown",
        "operators": ["fullers360"],
        "fullers_gtfs_route_ids": ["HOBS-209"],
        "fullers_from_stop_ids": ["9720-9e1a95ac"],
        "fullers_to_stop_ids": ["9707-62737f23"],
        "aliases": ["hobsonville", "hobsonville-to-auckland"],
    },
    "auckland-beach-haven": {
        "name": "Auckland to Beach Haven",
        "from": "Auckland Downtown",
        "to": "Beach Haven",
        "operators": ["fullers360"],
        "fullers_gtfs_route_ids": ["HOBS-209"],
        "fullers_from_stop_ids": ["9707-62737f23"],
        "fullers_to_stop_ids": ["9650-5adb86d3"],
        "aliases": ["auckland-to-beach-haven"],
    },
    "beach-haven-auckland": {
        "name": "Beach Haven to Auckland",
        "from": "Beach Haven",
        "to": "Auckland Downtown",
        "operators": ["fullers360"],
        "fullers_gtfs_route_ids": ["HOBS-209"],
        "fullers_from_stop_ids": ["9650-5adb86d3"],
        "fullers_to_stop_ids": ["9707-62737f23"],
        "aliases": ["beach-haven", "beach-haven-to-auckland"],
    },
    "auckland-birkenhead": {
        "name": "Auckland to Birkenhead",
        "from": "Auckland Downtown",
        "to": "Birkenhead",
        "operators": ["fullers360"],
        "fullers_gtfs_route_ids": ["BIRK-240"],
        "fullers_from_stop_ids": ["9701-8d24d4bc"],
        "fullers_to_stop_ids": ["9660-33a61833"],
        "aliases": ["auckland-to-birkenhead"],
    },
    "birkenhead-auckland": {
        "name": "Birkenhead to Auckland",
        "from": "Birkenhead",
        "to": "Auckland Downtown",
        "operators": ["fullers360"],
        "fullers_gtfs_route_ids": ["BIRK-240"],
        "fullers_from_stop_ids": ["9660-33a61833"],
        "fullers_to_stop_ids": ["9701-8d24d4bc"],
        "aliases": ["birkenhead", "birkenhead-to-auckland"],
    },
    "auckland-northcote": {
        "name": "Auckland to Northcote Point",
        "from": "Auckland Downtown",
        "to": "Northcote Point",
        "operators": ["fullers360"],
        "fullers_gtfs_route_ids": ["BIRK-240"],
        "fullers_from_stop_ids": ["9701-8d24d4bc"],
        "fullers_to_stop_ids": ["9730-4fb1fd18"],
        "aliases": ["auckland-to-northcote", "auckland-northcote-point"],
    },
    "northcote-auckland": {
        "name": "Northcote Point to Auckland",
        "from": "Northcote Point",
        "to": "Auckland Downtown",
        "operators": ["fullers360"],
        "fullers_gtfs_route_ids": ["BIRK-240"],
        "fullers_from_stop_ids": ["9730-4fb1fd18"],
        "fullers_to_stop_ids": ["9701-8d24d4bc"],
        "aliases": ["northcote", "northcote-to-auckland", "northcote-point-auckland"],
    },
    "auckland-pine-harbour": {
        "name": "Auckland to Pine Harbour",
        "from": "Auckland Downtown",
        "to": "Pine Harbour",
        "operators": ["fullers360"],
        "fullers_gtfs_route_ids": ["PINE-210"],
        "fullers_from_stop_ids": ["9703-949ea191"],
        "fullers_to_stop_ids": ["9740-da781e65"],
        "aliases": ["auckland-to-pine-harbour"],
    },
    "pine-harbour-auckland": {
        "name": "Pine Harbour to Auckland",
        "from": "Pine Harbour",
        "to": "Auckland Downtown",
        "operators": ["fullers360"],
        "fullers_gtfs_route_ids": ["PINE-210"],
        "fullers_from_stop_ids": ["9740-da781e65"],
        "fullers_to_stop_ids": ["9703-949ea191"],
        "aliases": ["pine-harbour", "pine-harbour-to-auckland"],
    },
    "auckland-west-harbour": {
        "name": "Auckland to West Harbour",
        "from": "Auckland Downtown",
        "to": "West Harbour",
        "operators": ["fullers360"],
        "fullers_gtfs_route_ids": ["WSTH-211"],
        "fullers_from_stop_ids": ["9706-b652da2b"],
        "fullers_to_stop_ids": ["9810-c3dbb67c"],
        "aliases": ["auckland-to-west-harbour"],
    },
    "west-harbour-auckland": {
        "name": "West Harbour to Auckland",
        "from": "West Harbour",
        "to": "Auckland Downtown",
        "operators": ["fullers360"],
        "fullers_gtfs_route_ids": ["WSTH-211"],
        "fullers_from_stop_ids": ["9810-c3dbb67c"],
        "fullers_to_stop_ids": ["9706-b652da2b"],
        "aliases": ["west-harbour", "west-harbour-to-auckland"],
    },
}


class BrowserUnavailableError(RuntimeError):
    """Raised when --browser is requested but CloakBrowser is unavailable."""


def die(message: str, code: int = 1) -> None:
    print(f"nz-ferries: {message}", file=sys.stderr)
    raise SystemExit(code)


def clean(value: Any) -> str:
    if value is None:
        return ""
    text = html.unescape(str(value)).replace("\xa0", " ")
    return " ".join(text.split())


def strip_html(raw: Any) -> str:
    parser = TextOnlyParser()
    parser.feed(str(raw or ""))
    return clean(" ".join(parser.parts))


class TextOnlyParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data)


class OrderedTextParser(HTMLParser):
    """Small stdlib HTML parser that records headings, paragraphs, and table rows."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.events: list[tuple[str, Any]] = []
        self.capture_tag: str | None = None
        self.capture_parts: list[str] = []
        self.in_row = False
        self.in_cell = False
        self.row: list[str] = []
        self.cell_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self.in_row = True
            self.row = []
        elif self.in_row and tag in {"td", "th"}:
            self.in_cell = True
            self.cell_parts = []
        elif tag in {"h1", "h2", "h3", "h4", "p"} and not self.in_cell:
            self.capture_tag = tag
            self.capture_parts = []

    def handle_data(self, data: str) -> None:
        if self.in_cell:
            self.cell_parts.append(data)
        elif self.capture_tag:
            self.capture_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self.in_cell and tag in {"td", "th"}:
            value = clean(" ".join(self.cell_parts))
            if value:
                self.row.append(value)
            self.in_cell = False
            self.cell_parts = []
        elif self.in_row and tag == "tr":
            if self.row:
                self.events.append(("row", self.row))
            self.in_row = False
            self.row = []
        elif self.capture_tag == tag:
            value = clean(" ".join(self.capture_parts))
            if value:
                self.events.append((tag, value))
            self.capture_tag = None
            self.capture_parts = []


def request_text(url: str, *, referer: str | None = None, timeout: int = 25, opener: urllib.request.OpenerDirector | None = None) -> str:
    # When an `opener` is supplied, SeaLink is priming / reusing a cookie-jar
    # session that request_json then reuses — nzfetch cannot carry a cookie
    # session, so THAT path MUST stay on urllib (kept below, unchanged).
    #
    # The plain HTML targets (Interislander/Bluebridge timetables + alerts,
    # SeaLink alerts — all called with no opener) are served REAL 200 content to a
    # minimal request but a bot-wall CHALLENGE to nzfetch's full Client-Hint /
    # Sec-Fetch-* header set. So for the opener-less case we now MIGRATE onto the
    # shared nzfetch helper in LEAN-headers mode (browser_headers=False): only the
    # lean UA + Accept + language + encoding set (equivalent to the bare urllib
    # request this replaced), while gaining nzfetch's rotating-proxy fallback. A
    # genuine block raises Blocked → surfaced as a network error via the skill's
    # existing die() contract (SKIP, not FAIL). (JSON/GTFS-zip fetches DO go
    # through nzfetch above; the SeaLink cookie-jar opener stays on urllib.)
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json;q=0.8,*/*;q=0.7",
        "User-Agent": UA,
    }
    if referer:
        headers["Referer"] = referer
    if opener is None:
        # Let nzfetch own the User-Agent (its own browser UA); the opener cookie-jar
        # path below keeps the skill UA it was primed with.
        nz_headers = {k: v for k, v in headers.items() if k.lower() != "user-agent"}
        try:
            return nzfetch.fetch_text(
                url,
                timeout=timeout,
                accept=headers["Accept"],
                headers=nz_headers,
                browser_headers=False,
            )
        except nzfetch.Blocked as e:
            die(f"network error calling {url}: {e}")
        except nzfetch.FetchError as e:
            die(str(e))
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with opener.open(req, timeout=timeout) as resp:  # type: ignore[misc]
            raw = resp.read()
            charset = resp.headers.get_content_charset() or "utf-8"
            return raw.decode(charset, "replace")
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        detail = clean(strip_html(raw) or raw[:300])
        die(f"HTTP {e.code} from {url}: {detail[:300]}")
    except urllib.error.URLError as e:
        die(f"network error calling {url}: {e.reason}")


def request_json(
    url: str,
    *,
    method: str = "GET",
    body: Any | None = None,
    referer: str | None = None,
    timeout: int = 25,
    opener: urllib.request.OpenerDirector | None = None,
) -> Any:
    headers = {
        "Accept": "application/json, text/plain, */*",
        "X-Requested-With": "XMLHttpRequest",
        "User-Agent": UA,
    }
    data = None
    if referer:
        headers["Referer"] = referer
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if opener is not None:
        # SeaLink relies on its primed cookie-jar session; keep this path on urllib.
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with opener.open(req, timeout=timeout) as resp:  # type: ignore[misc]
                raw = resp.read().decode("utf-8", "replace")
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", "replace")
            detail = raw[:300]
            try:
                payload = json.loads(raw)
                detail = payload.get("title") or payload.get("message") or payload.get("Message") or detail
            except Exception:
                detail = clean(strip_html(raw) or detail)
            die(f"HTTP {e.code} from {url}: {detail}")
        except urllib.error.URLError as e:
            die(f"network error calling {url}: {e.reason}")
        except json.JSONDecodeError as e:
            die(f"invalid JSON from {url}: {e}")
    # Drop Accept (passed via accept=) and User-Agent (nzfetch owns the UA); the
    # opener cookie-jar path above keeps the skill UA it was primed with.
    extra_headers = {k: v for k, v in headers.items() if k.lower() not in ("accept", "user-agent")}
    try:
        raw_bytes, _ct, _final = nzfetch.fetch_bytes(
            url,
            timeout=timeout,
            accept="application/json, text/plain, */*",
            headers=extra_headers,
            data=data,
            method=(method if method != "GET" else None),
        )
    except nzfetch.Blocked as e:
        die(f"network error calling {url}: {e}")
    except nzfetch.FetchError as e:
        die(str(e))
    raw = raw_bytes.decode("utf-8", "replace")
    try:
        return json.loads(raw) if raw else None
    except json.JSONDecodeError as e:
        die(f"invalid JSON from {url}: {e}")


def nz_now() -> datetime:
    return datetime.now(NZ_TZ)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_date(value: str | None) -> date:
    if not value:
        return nz_now().date()
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        die(f"invalid date {value!r}; expected YYYY-MM-DD")


def parse_time_text(value: str) -> dtime:
    match = re.search(r"(\d{1,2})(?::(\d{2}))?\s*([ap]m)", value.lower())
    if not match:
        die(f"cannot parse time {value!r}")
    hour = int(match.group(1))
    minute = int(match.group(2) or "0")
    suffix = match.group(3)
    if suffix == "pm" and hour != 12:
        hour += 12
    if suffix == "am" and hour == 12:
        hour = 0
    return dtime(hour, minute)


def local_dt(day: date, time_text: str) -> datetime:
    return datetime.combine(day, parse_time_text(time_text), tzinfo=NZ_TZ)


def gtfs_time_to_local(day: date, value: str | None) -> datetime | None:
    text = clean(value)
    if not text:
        return None
    parts = text.split(":")
    if len(parts) < 2:
        return None
    try:
        hour = int(parts[0])
        minute = int(parts[1])
        second = int(parts[2]) if len(parts) > 2 else 0
    except ValueError:
        return None
    return datetime.combine(day, dtime(0, 0), tzinfo=NZ_TZ) + timedelta(hours=hour, minutes=minute, seconds=second)


def format_local_time(value: datetime) -> str:
    hour = value.hour % 12 or 12
    suffix = "AM" if value.hour < 12 else "PM"
    return f"{hour}:{value.minute:02d} {suffix}"


def iso_local(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()


def route_alias_map() -> dict[str, str]:
    aliases: dict[str, str] = {}
    for route_id, route in ROUTES.items():
        aliases[route_id] = route_id
        aliases[route_id.replace("-", " ")] = route_id
        for alias in route.get("aliases", []):
            aliases[alias] = route_id
            aliases[alias.replace("-", " ")] = route_id
    return aliases


def normalize_key(value: str) -> str:
    value = value.lower().strip()
    value = value.replace("↔", "-").replace("->", "-").replace(" to ", "-")
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value


def resolve_route(raw: str) -> tuple[str, dict[str, Any]]:
    aliases = route_alias_map()
    keys = [normalize_key(raw), normalize_key(raw).replace("-", " ")]
    for key in keys:
        if key in aliases:
            route_id = aliases[key]
            return route_id, ROUTES[route_id]
    known = ", ".join(sorted(ROUTES.keys()))
    die(f"unknown route {raw!r}; known routes: {known}", 2)


def resolve_operator(raw: str | None) -> str | None:
    if not raw:
        return None
    key = normalize_key(raw)
    op = OPERATOR_ALIASES.get(key)
    if not op:
        die(f"unknown operator {raw!r}; use one of: {', '.join(sorted(OPERATORS))}", 2)
    return op



def looks_browser_blocked(markup: str) -> bool:
    lower = (markup or "").lower()
    return any(marker in lower for marker in ("hcaptcha", "perimeterx", "perfdrive", "radware", "captcha", "access denied", "checking your browser"))


def fullers_query_url(route: dict[str, Any], day: date) -> str:
    params = {
        "from": route.get("from", ""),
        "to": route.get("to", ""),
        "date": day.strftime("%m/%d/%Y"),
    }
    return FULLERS_TIMETABLE + "?" + urllib.parse.urlencode(params)


def fetch_fullers_public_page_with_browser(route: dict[str, Any], day: date) -> dict[str, Any]:
    try:
        from cloakbrowser import launch
    except Exception as exc:  # pragma: no cover - optional host dependency
        raise BrowserUnavailableError(
            "cloakbrowser_not_installed: install CloakBrowser to use --browser for Fullers public timetable pages."
        ) from exc

    url = fullers_query_url(route, day)
    browser = None
    try:
        browser = launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
            timezone="Pacific/Auckland",
            locale="en-NZ",
        )
        page = browser.new_page()
        try:
            page.goto(url, wait_until="networkidle", timeout=90000)
            html_text = page.content()
            error = None
        except Exception as exc:
            try:
                html_text = page.content() if page else ""
            except Exception:
                html_text = ""
            error = str(exc).splitlines()[0][:240]
        blocked = bool(error) or looks_browser_blocked(html_text)
        text = clean(strip_html(html_text))
        return {
            "source_url": url,
            "method": "CloakBrowser public Fullers timetable page",
            "status": "blocked" if blocked else "loaded",
            "blocked": blocked,
            "text_preview": text[:300],
            "html_bytes": len(html_text),
            "error": error,
            "note": "Browser probe only; AT GTFS remains the structured schedule source. CAPTCHA/PerfDrive/hCaptcha pages are reported as blocked, not bypassed.",
        }
    finally:
        if browser is not None:
            browser.close()


def emit(data: Any, as_json: bool, render) -> None:  # type: ignore[no-untyped-def]
    if as_json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(render(data))


def money(value: Any) -> str:
    if value is None or value == "":
        return "-"
    try:
        return f"${float(value):.2f}"
    except Exception:
        return str(value)


def route_handoff_payload(route_id: str, route: dict[str, Any], command: str) -> dict[str, Any]:
    reason = AT_SKILL_HINT
    if route.get("coverage") == "fullers-public-page-blocked":
        reason = (
            "Fullers360 timetable query pages currently require hCaptcha/PerfDrive validation "
            "from direct CLI fetches. Use Fullers360 web/app for this tourism route."
        )
    return {
        "route": route_id,
        "route_name": route["name"],
        "operator": "fullers360",
        "supported": False,
        "command": command,
        "sailings": [],
        "warnings": [reason],
        "handoff": {
            "skill": "at-transport" if route.get("coverage") == "at-transport" else None,
            "source_url": FULLERS_TIMETABLE,
        },
    }


def at_request_json(path: str, *, timeout: int = 25) -> Any:
    url = AT_API_BASE + path
    try:
        raw_bytes, _ct, _final = nzfetch.fetch_bytes(
            url,
            timeout=timeout,
            accept="application/json",
            headers={"Ocp-Apim-Subscription-Key": at_api_key()},
            allowed_hosts={"api.at.govt.nz"},
        )
    except nzfetch.Blocked as e:
        die(f"network error calling {url}: {e}")
    except nzfetch.FetchError as e:
        die(f"AT API error from {url}: {e}")
    raw = raw_bytes.decode("utf-8", "replace")
    try:
        return json.loads(raw) if raw else None
    except json.JSONDecodeError as e:
        die(f"invalid JSON from {url}: {e}")


def at_gtfs_zip_bytes() -> bytes:
    if AT_GTFS_CACHE:
        try:
            if os.path.exists(AT_GTFS_CACHE):
                age = time.time() - os.path.getmtime(AT_GTFS_CACHE)
                if age < AT_GTFS_CACHE_TTL_SECONDS and os.path.getsize(AT_GTFS_CACHE) > 0:
                    with open(AT_GTFS_CACHE, "rb") as fh:
                        return fh.read()
        except OSError:
            pass

    try:
        data, _ct, _final = nzfetch.fetch_bytes(
            AT_GTFS_ZIP,
            timeout=60,
            accept="application/zip,*/*",
        )
    except nzfetch.Blocked as e:
        die(f"network error fetching AT GTFS zip: {e}")
    except nzfetch.FetchError as e:
        die(f"error fetching AT GTFS zip from {AT_GTFS_ZIP}: {e}")

    if AT_GTFS_CACHE:
        try:
            os.makedirs(os.path.dirname(AT_GTFS_CACHE), exist_ok=True)
            with open(AT_GTFS_CACHE, "wb") as fh:
                fh.write(data)
        except OSError:
            pass
    return data


def gtfs_rows(zf: zipfile.ZipFile, name: str) -> list[dict[str, str]]:
    with zf.open(name) as fh:
        text = io.TextIOWrapper(fh, encoding="utf-8-sig", newline="")
        return list(csv.DictReader(text))


def active_gtfs_services(zf: zipfile.ZipFile, day: date) -> set[str]:
    ymd = day.strftime("%Y%m%d")
    weekday = day.strftime("%A").lower()
    active: set[str] = set()
    for row in gtfs_rows(zf, "calendar.txt"):
        if row.get("start_date", "") <= ymd <= row.get("end_date", "") and row.get(weekday) == "1":
            active.add(row["service_id"])
    for row in gtfs_rows(zf, "calendar_dates.txt"):
        if row.get("date") != ymd:
            continue
        if row.get("exception_type") == "1":
            active.add(row["service_id"])
        elif row.get("exception_type") == "2":
            active.discard(row["service_id"])
    return active


def stop_time_value(row: dict[str, str], key: str) -> str:
    return clean(row.get(key) or row.get("departure_time") or row.get("arrival_time"))


def fullers_leg_from_stop_times(
    rows: list[dict[str, str]],
    from_stop_ids: set[str],
    to_stop_ids: set[str],
) -> tuple[dict[str, str], dict[str, str]] | None:
    rows.sort(key=lambda item: int(item.get("stop_sequence") or "0"))
    for idx, row in enumerate(rows):
        if row.get("stop_id") not in from_stop_ids:
            continue
        for later in rows[idx + 1 :]:
            if later.get("stop_id") in to_stop_ids:
                return row, later
    return None


def fullers_sailings(route_id: str, route: dict[str, Any], day: date) -> dict[str, Any]:
    route_ids = route.get("fullers_gtfs_route_ids") or []
    from_stop_ids = set(route.get("fullers_from_stop_ids") or [])
    to_stop_ids = set(route.get("fullers_to_stop_ids") or [])
    if not route_ids or not from_stop_ids or not to_stop_ids:
        die(f"Fullers route {route_id} is missing AT GTFS mapping", 2)

    started = time.perf_counter()
    try:
        zf = zipfile.ZipFile(io.BytesIO(at_gtfs_zip_bytes()))
    except zipfile.BadZipFile:
        die("AT GTFS zip could not be read")

    with zf:
        agencies = {row["agency_id"]: row for row in gtfs_rows(zf, "agency.txt")}
        routes = {row["route_id"]: row for row in gtfs_rows(zf, "routes.txt")}
        stops = {row["stop_id"]: row for row in gtfs_rows(zf, "stops.txt")}
        active_services = active_gtfs_services(zf, day)

        selected_trips: dict[str, dict[str, str]] = {}
        for trip in gtfs_rows(zf, "trips.txt"):
            if trip.get("route_id") in route_ids and trip.get("service_id") in active_services:
                selected_trips[trip["trip_id"]] = trip

        stop_times_by_trip: dict[str, list[dict[str, str]]] = {trip_id: [] for trip_id in selected_trips}
        with zf.open("stop_times.txt") as fh:
            text = io.TextIOWrapper(fh, encoding="utf-8-sig", newline="")
            for row in csv.DictReader(text):
                trip_id = row.get("trip_id")
                if trip_id in stop_times_by_trip:
                    stop_times_by_trip[trip_id].append(row)

        sailings: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()
        for trip_id, trip in selected_trips.items():
            leg = fullers_leg_from_stop_times(stop_times_by_trip.get(trip_id, []), from_stop_ids, to_stop_ids)
            if not leg:
                continue
            dep_row, arr_row = leg
            dep = gtfs_time_to_local(day, stop_time_value(dep_row, "departure_time"))
            arr = gtfs_time_to_local(day, stop_time_value(arr_row, "arrival_time"))
            if not dep or not arr:
                continue
            dedupe = (trip_id, dep_row.get("stop_sequence", ""), arr_row.get("stop_sequence", ""))
            if dedupe in seen:
                continue
            seen.add(dedupe)
            route_info = routes.get(trip.get("route_id", ""), {})
            agency = agencies.get(route_info.get("agency_id", ""), {})
            from_stop = stops.get(dep_row.get("stop_id", ""), {})
            to_stop = stops.get(arr_row.get("stop_id", ""), {})
            sailings.append(
                {
                    "operator": "fullers360",
                    "operator_name": OPERATORS["fullers360"]["name"],
                    "route": route_id,
                    "route_name": route["name"],
                    "date": day.isoformat(),
                    "departure_location": clean(from_stop.get("stop_name") or route["from"]),
                    "arrival_location": clean(to_stop.get("stop_name") or route["to"]),
                    "departure_time": format_local_time(dep),
                    "arrival_time": format_local_time(arr),
                    "departure_datetime": iso_local(dep),
                    "arrival_datetime": iso_local(arr),
                    "vessel": "",
                    "status": "scheduled",
                    "trip_id": trip_id,
                    "gtfs_route_id": trip.get("route_id"),
                    "gtfs_route_short_name": route_info.get("route_short_name"),
                    "gtfs_agency_id": route_info.get("agency_id"),
                    "gtfs_agency_name": agency.get("agency_name"),
                    "headsign": clean(trip.get("trip_headsign")),
                    "source": "AT public GTFS static schedule",
                    "source_url": AT_GTFS_ZIP,
                }
            )

    sailings.sort(key=lambda item: item["departure_datetime"])
    warnings = []
    if not sailings:
        warnings.append("No active AT GTFS trips matched this Fullers route/date and stop pair.")
    result = {
        "operator": "fullers360",
        "route": route_id,
        "route_name": route["name"],
        "date": day.isoformat(),
        "source_url": AT_GTFS_ZIP,
        "source_fetched_at": now_iso(),
        "source_note": FULLERS_SOURCE_NOTE,
        "gtfs_route_ids": route_ids,
        "count": len(sailings),
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "warnings": warnings,
        "sailings": sailings,
    }
    if BROWSER_MODE:
        probe = fetch_fullers_public_page_with_browser(route, day)
        result["browser_probe"] = probe
        if probe.get("blocked"):
            result.setdefault("warnings", []).append("Fullers public timetable page browser probe was blocked by CAPTCHA/PerfDrive/hCaptcha; AT GTFS schedule fallback was used.")
    return result


def sealink_opener() -> urllib.request.OpenerDirector:
    cookie_jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))
    request_text(SEALINK_SCHEDULES, opener=opener, timeout=20)
    return opener


def sealink_bootstrap() -> dict[str, Any]:
    opener = sealink_opener()
    return {
        "opener": opener,
        "terminals": request_json(SEALINK_TERMINALS, referer=SEALINK_SCHEDULES, opener=opener),
        "category_matrix": request_json(SEALINK_CATEGORY_MATRIX, referer=SEALINK_SCHEDULES, opener=opener),
        "terminal_matrix": request_json(SEALINK_TERMINAL_MATRIX, referer=SEALINK_SCHEDULES, opener=opener),
    }


def sealink_terminal_by_name(terminals: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    needle = clean(name).lower()
    for terminal in terminals:
        if clean(terminal.get("terminalName")).lower() == needle:
            return terminal
    return None


def sealink_prefix(route: dict[str, Any], bootstrap: dict[str, Any]) -> str | None:
    from_name = route.get("sealink_from_terminal")
    to_name = route.get("sealink_to_terminal")
    if not from_name or not to_name:
        return None
    terminals = bootstrap["terminals"] or []
    from_terminal = sealink_terminal_by_name(terminals, from_name)
    to_terminal = sealink_terminal_by_name(terminals, to_name)
    if not from_terminal or not to_terminal:
        return None
    from_guid = from_terminal.get("nodeGUID")
    to_guid = to_terminal.get("nodeGUID")
    for row in bootstrap["terminal_matrix"] or []:
        if row.get("terminalFrom") == from_guid and row.get("terminalTo") == to_guid:
            return clean(row.get("productCode")) or None
    return None


def sealink_category_code(route: dict[str, Any], bootstrap: dict[str, Any]) -> str:
    from_code = route.get("sealink_from_code")
    to_code = route.get("sealink_to_code")
    for row in bootstrap["category_matrix"] or []:
        if row.get("departureLocationCode") == from_code and row.get("returnLocationCode") == to_code and not row.get("isReturn"):
            return clean(row.get("productCategoryCode"))
    die(f"SeaLink route matrix has no product category for {from_code}->{to_code}")


def fare_summary(fare_types: list[dict[str, Any]]) -> dict[str, Any]:
    wanted = {
        "ADULT": "adult",
        "CHILD": "child",
        "SENIOR": "senior",
        "STUDENT": "student",
        "INFANT": "infant",
        "RETCAR+DR": "vehicle_driver",
        "MB+R": "motorcycle_rider",
        "WRADULT": "waiheke_resident_adult",
        "WRCR+DRVR": "waiheke_resident_vehicle_driver",
    }
    out: dict[str, Any] = {}
    for item in fare_types:
        code = clean(item.get("code")).upper()
        label = wanted.get(code)
        if label and label not in out:
            out[label] = item.get("price")
    return out


def normalize_sealink_slot(route_id: str, route: dict[str, Any], day: date, slot: dict[str, Any]) -> dict[str, Any]:
    dep = local_dt(day, clean(slot.get("departureTime")))
    arr = local_dt(day, clean(slot.get("arrivalTime")))
    if arr <= dep:
        arr += timedelta(days=1)
    status = clean(slot.get("status")) or "available"
    fares = fare_summary(slot.get("fareTypes") or [])
    return {
        "operator": "sealink",
        "operator_name": OPERATORS["sealink"]["name"],
        "route": route_id,
        "route_name": route["name"],
        "date": day.isoformat(),
        "departure_location": clean(slot.get("departureLocation")),
        "arrival_location": clean(slot.get("arrivalLocation")),
        "departure_time": clean(slot.get("departureTime")),
        "arrival_time": clean(slot.get("arrivalTime")),
        "departure_datetime": iso_local(dep),
        "arrival_datetime": iso_local(arr),
        "vessel": clean(slot.get("ferryName")),
        "product_code": clean(slot.get("productCode")),
        "status": status,
        "availability": clean(slot.get("availabilityString")),
        "passenger_spaces": slot.get("pax"),
        "limited_vehicle_area": bool(slot.get("limitedVehicleArea")),
        "fare_price_for_query": slot.get("farePrice"),
        "fare_summary": fares,
        "source": "sealink.co.nz",
        "source_url": SEALINK_SCHEDULES,
    }


def sealink_sailings(route_id: str, route: dict[str, Any], day: date) -> dict[str, Any]:
    started = time.perf_counter()
    boot = sealink_bootstrap()
    category = sealink_category_code(route, boot)
    prefix = sealink_prefix(route, boot)
    payload = {
        "code": category,
        "date": day.isoformat(),
        "includeUnavailDates": False,
        "days": 1,
        "fareTypes": [
            {"code": "RETCAR+DR", "name": "Car + Driver", "quantity": 1, "type": "F"},
            {"code": "ADULT", "name": "Adult", "quantity": 1, "type": "F"},
        ],
        "promotion": "",
    }
    raw = request_json(SEALINK_SLOTS, method="POST", body=payload, referer=SEALINK_SCHEDULES, opener=boot["opener"])
    slots = raw.get("slots") if isinstance(raw, dict) else []
    if prefix:
        slots = [slot for slot in slots if clean(slot.get("productCode")).startswith(prefix)]
    sailings = [normalize_sealink_slot(route_id, route, day, slot) for slot in slots if isinstance(slot, dict)]
    sailings.sort(key=lambda item: item["departure_datetime"])
    return {
        "operator": "sealink",
        "route": route_id,
        "route_name": route["name"],
        "date": day.isoformat(),
        "source_url": SEALINK_SCHEDULES,
        "source_fetched_at": now_iso(),
        "query_product_category": category,
        "terminal_product_prefix": prefix,
        "count": len(sailings),
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "sailings": sailings,
    }


def parse_ordered_text(html_text: str) -> list[tuple[str, Any]]:
    parser = OrderedTextParser()
    parser.feed(html_text)
    return parser.events


def route_direction_from_text(value: str) -> str | None:
    text = clean(value).lower()
    text = text.replace("\u00a0", " ")
    if "wellington to picton" in text:
        return "wellington-picton"
    if "picton to wellington" in text:
        return "picton-wellington"
    return None


def normalize_cook_sailing(
    operator: str,
    route_id: str,
    day: date,
    depart_time: str,
    arrival_time: str | None,
    vessel: str,
    note: str = "",
    source_url: str = "",
) -> dict[str, Any]:
    route = ROUTES[route_id]
    dep = local_dt(day, depart_time)
    if arrival_time:
        arr = local_dt(day, arrival_time)
        if arr <= dep:
            arr += timedelta(days=1)
    else:
        arr = dep + timedelta(hours=3, minutes=30)
    return {
        "operator": operator,
        "operator_name": OPERATORS[operator]["name"],
        "route": route_id,
        "route_name": route["name"],
        "date": day.isoformat(),
        "departure_location": route["from"],
        "arrival_location": route["to"],
        "departure_time": depart_time,
        "arrival_time": arrival_time or arr.strftime("%-I:%M%p").lower(),
        "departure_datetime": iso_local(dep),
        "arrival_datetime": iso_local(arr),
        "vessel": clean_vessel(vessel),
        "note": clean(note),
        "source": OPERATORS[operator]["source"],
        "source_url": source_url,
    }


def clean_vessel(value: str) -> str:
    text = clean(re.sub(r"\*+", "", value))
    text = text.replace("Kai \u0101 rahi", "Kai\u0101rahi")
    text = text.replace("Kai \u0101rahi", "Kai\u0101rahi")
    return text


def interislander_sailings(route_id: str, day: date) -> dict[str, Any]:
    started = time.perf_counter()
    html_text = request_text(INTERISLANDER_TIMETABLE)
    current_direction: str | None = None
    sailings: list[dict[str, Any]] = []
    for kind, value in parse_ordered_text(html_text):
        if kind == "row":
            row = value
            if len(row) == 1:
                current_direction = route_direction_from_text(row[0]) or current_direction
                continue
            if current_direction == route_id and len(row) >= 2 and re.search(r"\d", row[0]):
                if "am" in row[0].lower() or "pm" in row[0].lower():
                    sailings.append(
                        normalize_cook_sailing(
                            "interislander",
                            route_id,
                            day,
                            clean(row[0]),
                            None,
                            clean(row[1]),
                            "Published timetable; Interislander states crossings take about 3.5 hours.",
                            INTERISLANDER_TIMETABLE,
                        )
                    )
    sailings.sort(key=lambda item: item["departure_datetime"])
    return {
        "operator": "interislander",
        "route": route_id,
        "route_name": ROUTES[route_id]["name"],
        "date": day.isoformat(),
        "source_url": INTERISLANDER_TIMETABLE,
        "source_fetched_at": now_iso(),
        "count": len(sailings),
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "sailings": sailings,
    }


MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


def parse_period_ranges(period: str) -> list[tuple[date, date]]:
    ranges: list[tuple[date, date]] = []
    pattern = re.compile(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})\s*-\s*(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})")
    for match in pattern.finditer(period):
        sm = MONTHS.get(match.group(2).lower())
        em = MONTHS.get(match.group(5).lower())
        if sm and em:
            ranges.append(
                (
                    date(int(match.group(3)), sm, int(match.group(1))),
                    date(int(match.group(6)), em, int(match.group(4))),
                )
            )
    return ranges


def period_matches(period: str, day: date) -> bool:
    ranges = parse_period_ranges(period)
    if not ranges:
        return True
    return any(start <= day <= end for start, end in ranges)


def note_allows_day(note: str, day: date) -> bool:
    lower = note.lower()
    weekday = day.weekday()
    if "not available on weekends" in lower and weekday in {5, 6}:
        return False
    if "not available on saturdays" in lower and weekday == 5:
        return False
    if "not available on sundays" in lower and weekday == 6:
        return False
    if "not available on saturday" in lower and weekday == 5:
        return False
    if "not available on sunday" in lower and weekday == 6:
        return False
    return True


def bluebridge_sailings(route_id: str, day: date) -> dict[str, Any]:
    started = time.perf_counter()
    html_text = request_text(BLUEBRIDGE_TIMETABLE)
    current_period = ""
    current_direction: str | None = None
    skipped = 0
    sailings: list[dict[str, Any]] = []
    for kind, value in parse_ordered_text(html_text):
        text = clean(value if isinstance(value, str) else "")
        if kind == "h2" and text.lower().startswith("valid from"):
            current_period = text
            continue
        direction = route_direction_from_text(text)
        if direction:
            current_direction = direction
            continue
        if kind != "row" or current_direction != route_id or not period_matches(current_period, day):
            continue
        row = value
        if len(row) < 3 or row[0].lower().startswith("departs"):
            continue
        depart_time = clean(row[0])
        if not re.search(r"\d", depart_time) or ("am" not in depart_time.lower() and "pm" not in depart_time.lower()):
            continue
        note = clean(row[3] if len(row) > 3 else "")
        if not note_allows_day(note, day):
            skipped += 1
            continue
        sailings.append(
            normalize_cook_sailing(
                "bluebridge",
                route_id,
                day,
                depart_time,
                clean(row[1]),
                clean(row[2]),
                note,
                BLUEBRIDGE_TIMETABLE,
            )
        )
    sailings.sort(key=lambda item: item["departure_datetime"])
    return {
        "operator": "bluebridge",
        "route": route_id,
        "route_name": ROUTES[route_id]["name"],
        "date": day.isoformat(),
        "source_url": BLUEBRIDGE_TIMETABLE,
        "source_fetched_at": now_iso(),
        "count": len(sailings),
        "skipped_by_day_restriction": skipped,
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "sailings": sailings,
    }


def fetch_sailings(route_id: str, route: dict[str, Any], day: date, operator: str | None) -> dict[str, Any]:
    if route.get("coverage"):
        return route_handoff_payload(route_id, route, "sailings")
    if operator and operator not in route["operators"]:
        die(f"operator {operator} does not serve route {route_id}", 2)
    if operator == "fullers360":
        return fullers_sailings(route_id, route, day)
    if "sealink" in route["operators"] and (operator is None or operator == "sealink"):
        if operator and operator != "sealink":
            die(f"operator {operator} does not serve route {route_id}", 2)
        return sealink_sailings(route_id, route, day)
    if "fullers360" in route["operators"]:
        return fullers_sailings(route_id, route, day)
    requested = [operator] if operator else [op for op in route["operators"] if op in {"interislander", "bluebridge"}]
    results = []
    for op in requested:
        if op == "interislander":
            results.append(interislander_sailings(route_id, day))
        elif op == "bluebridge":
            results.append(bluebridge_sailings(route_id, day))
    combined_sailings = [s for result in results for s in result.get("sailings", [])]
    combined_sailings.sort(key=lambda item: item["departure_datetime"])
    return {
        "operator": operator or "combined",
        "route": route_id,
        "route_name": route["name"],
        "date": day.isoformat(),
        "source_fetched_at": now_iso(),
        "count": len(combined_sailings),
        "operators_returned": [result["operator"] for result in results],
        "operator_results": results,
        "sailings": combined_sailings,
    }


def next_sailings(route_id: str, route: dict[str, Any], operator: str | None, limit: int) -> dict[str, Any]:
    global BROWSER_MODE
    if route.get("coverage"):
        payload = route_handoff_payload(route_id, route, "next")
        payload["limit"] = limit
        return payload
    now = nz_now()
    found: list[dict[str, Any]] = []
    checked_dates: list[str] = []
    warnings: list[str] = []
    browser_probe: dict[str, Any] | None = None
    for offset in range(0, 8):
        day = (now + timedelta(days=offset)).date()
        checked_dates.append(day.isoformat())
        original_browser_mode = BROWSER_MODE
        if original_browser_mode and browser_probe is not None:
            BROWSER_MODE = False
        try:
            result = fetch_sailings(route_id, route, day, operator)
        finally:
            BROWSER_MODE = original_browser_mode
        if browser_probe is None and isinstance(result.get("browser_probe"), dict):
            browser_probe = result["browser_probe"]
        for warning in result.get("warnings") or []:
            if warning not in warnings:
                warnings.append(warning)
        for sailing in result.get("sailings", []):
            status = clean(sailing.get("status")).lower()
            if status in {"cancelled", "departed"}:
                continue
            try:
                dep = datetime.fromisoformat(sailing["departure_datetime"])
            except Exception:
                continue
            if dep >= now:
                found.append(sailing)
        if len(found) >= limit:
            break
    found.sort(key=lambda item: item["departure_datetime"])
    data = {
        "route": route_id,
        "route_name": route["name"],
        "operator": operator or "combined",
        "generated_at": now_iso(),
        "checked_dates": checked_dates,
        "count": min(len(found), limit),
        "warnings": warnings,
        "sailings": found[:limit],
    }
    if browser_probe is not None:
        data["browser_probe"] = browser_probe
    return data


def alert_from(title: str, content: str, operator: str, source_url: str, *, updated: str = "", kind: str = "alert") -> dict[str, Any]:
    return {
        "operator": operator,
        "operator_name": OPERATORS[operator]["name"],
        "kind": clean(kind).lower() or "alert",
        "title": clean(title),
        "summary": clean(content)[:700],
        "updated": clean(updated),
        "source_url": source_url,
    }


def sealink_alerts() -> list[dict[str, Any]]:
    html_text = request_text(SEALINK_ALERTS)
    alerts: list[dict[str, Any]] = []
    chunks = re.split(r'<div class="alert-reminder\s+([^"]*)">', html_text)
    for idx in range(1, len(chunks), 2):
        classes = chunks[idx]
        block = chunks[idx + 1]
        title = re.search(r'<h4 class="alert-reminder__title">(.*?)</h4>', block, re.S)
        content = re.search(r'<div class="alert-reminder__content">(.*?)</div>', block, re.S)
        updated = re.search(r'<div class="alert-reminder__right">.*?<strong>(.*?)</strong>', block, re.S)
        kind = "reminder" if "reminder" in classes else "alert"
        if title:
            alerts.append(
                alert_from(
                    strip_html(title.group(1)),
                    strip_html(content.group(1) if content else ""),
                    "sealink",
                    SEALINK_ALERTS,
                    updated=strip_html(updated.group(1) if updated else ""),
                    kind=kind,
                )
            )
    return alerts


def interislander_alerts() -> list[dict[str, Any]]:
    payload = request_json(INTERISLANDER_DISRUPTIONS, referer=INTERISLANDER_ALERTS)
    alerts = []
    for item in payload or []:
        title = clean(item.get("title"))
        if not title:
            continue
        summary = strip_html(item.get("summary") or item.get("content") or "")
        alerts.append(
            alert_from(
                title,
                summary,
                "interislander",
                INTERISLANDER_ALERTS,
                updated=clean(item.get("last_edited")),
                kind="alert",
            )
        )
        alerts[-1]["id"] = item.get("id")
        alerts[-1]["start"] = item.get("start")
        alerts[-1]["end"] = item.get("end")
        alerts[-1]["no_banner"] = item.get("no_banner")
    return alerts


def bluebridge_alerts() -> list[dict[str, Any]]:
    html_text = request_text(BLUEBRIDGE_ALERTS)
    start = html_text.find("<h1>Service Alerts")
    end = html_text.find("<!-- Footer -->", start)
    if start >= 0 and end > start:
        html_text = html_text[start:end]
    events = parse_ordered_text(html_text)
    alerts: list[dict[str, Any]] = []
    current_title = ""
    parts: list[str] = []

    def flush() -> None:
        nonlocal current_title, parts
        title = clean(current_title)
        if title and "____" not in title and title.lower() != "service alerts":
            content = clean(" ".join(parts))
            if content:
                updated = ""
                match = re.search(
                    r"updated\s+((?:\d{1,2}:\d{2}\s*[ap]m\s+)?(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+\d{1,2}\s+\w+)",
                    content,
                    re.I,
                )
                if match:
                    updated = match.group(1)
                alerts.append(alert_from(title, content, "bluebridge", BLUEBRIDGE_ALERTS, updated=updated))
        current_title = ""
        parts = []

    for kind, value in events:
        text = clean(value if isinstance(value, str) else "")
        if kind in {"h2", "h3"}:
            flush()
            current_title = text
        elif kind == "p" and current_title:
            if text and "EndFragment" not in text:
                parts.append(text)
    flush()
    return alerts


def at_translation_text(field: Any) -> str:
    translations = (field or {}).get("translation") if isinstance(field, dict) else None
    if isinstance(translations, list) and translations:
        return clean(translations[0].get("text"))
    return ""


def at_alert_is_active_today(periods: list[dict[str, Any]]) -> bool:
    if not periods:
        return True
    now = datetime.now(timezone.utc)
    today_start = datetime.combine(nz_now().date(), dtime(0, 0), tzinfo=NZ_TZ).astimezone(timezone.utc)
    today_end = today_start + timedelta(days=1)
    for period in periods:
        start_raw = period.get("start")
        end_raw = period.get("end")
        start = datetime.fromtimestamp(int(start_raw), timezone.utc) if start_raw else datetime.min.replace(tzinfo=timezone.utc)
        end = datetime.fromtimestamp(int(end_raw), timezone.utc) if end_raw else datetime.max.replace(tzinfo=timezone.utc)
        if start <= now <= end:
            return True
        if start < today_end and end > today_start:
            return True
    return False


def fullers_alerts() -> list[dict[str, Any]]:
    payload = at_request_json("/realtime/legacy/servicealerts")
    entities = (((payload or {}).get("response") or {}).get("entity") or [])
    alerts: list[dict[str, Any]] = []
    for entity in entities:
        alert = entity.get("alert") or {}
        informed = alert.get("informed_entity") or []
        route_ids = sorted(
            {
                item.get("route_id")
                for item in informed
                if item.get("route_id") in FULLERS_ALERT_ROUTE_IDS
            }
        )
        if not route_ids:
            continue
        periods = alert.get("active_period") or []
        if not at_alert_is_active_today(periods):
            continue
        title = at_translation_text(alert.get("header_text")) or entity.get("id") or "AT ferry service alert"
        summary = at_translation_text(alert.get("description_text"))
        item = alert_from(title, summary, "fullers360", "https://at.govt.nz/bus-train-ferry/service-announcements/", kind="alert")
        item["id"] = entity.get("id")
        item["route_ids"] = route_ids
        item["cause"] = alert.get("cause")
        item["effect"] = alert.get("effect")
        item["severity_level"] = alert.get("severity_level")
        item["active_period"] = periods
        item["source"] = "AT GTFS-RT servicealerts"
        alerts.append(item)
    alerts.sort(key=lambda item: (item.get("severity_level") or "", item.get("title") or ""))
    return alerts


def fetch_alerts(operator: str | None) -> dict[str, Any]:
    operators = [operator] if operator else ["sealink", "interislander", "bluebridge", "fullers360"]
    alerts: list[dict[str, Any]] = []
    warnings: list[str] = []
    for op in operators:
        if op == "sealink":
            alerts.extend(sealink_alerts())
        elif op == "interislander":
            alerts.extend(interislander_alerts())
        elif op == "bluebridge":
            alerts.extend(bluebridge_alerts())
        elif op == "fullers360":
            alerts.extend(fullers_alerts())
    return {
        "operator": operator or "all",
        "source_fetched_at": now_iso(),
        "count": len(alerts),
        "source_note": FULLERS_SOURCE_NOTE if operator == "fullers360" else None,
        "warnings": warnings,
        "alerts": alerts,
    }


def render_sailings(data: dict[str, Any]) -> str:
    warnings = data.get("warnings") or []
    if data.get("supported") is False:
        lines = [f"{data['route_name']}: no sailings returned by nz-ferries."]
        lines.extend(f"Note: {warning}" for warning in warnings)
        return "\n".join(lines)
    date_label = data.get("date")
    if not date_label and data.get("checked_dates"):
        checked_dates = data["checked_dates"]
        date_label = checked_dates[0] if len(checked_dates) == 1 else f"{checked_dates[0]} to {checked_dates[-1]}"
    lines = [f"{data.get('route_name', data.get('route'))} on {date_label or 'next'}: {data.get('count', 0)} sailings"]
    if data.get("operators_returned"):
        lines.append("Operators: " + ", ".join(data["operators_returned"]))
    if data.get("skipped_by_day_restriction"):
        lines.append(f"Skipped by day restriction: {data['skipped_by_day_restriction']}")
    for warning in warnings:
        lines.append(f"Note: {warning}")
    lines.append("")
    for sailing in data.get("sailings") or []:
        status = sailing.get("status") or sailing.get("availability") or ""
        fare = sailing.get("fare_summary", {}).get("adult")
        fare_text = f" adult {money(fare)}" if fare is not None else ""
        note = f" | {sailing['note']}" if sailing.get("note") else ""
        status_text = f" | {status}" if status and status not in {"available", "scheduled"} else ""
        lines.append(
            f"{sailing['departure_time']:>7} {sailing['departure_location']} -> {sailing['arrival_location']} "
            f"(arr {sailing['arrival_time']}) {sailing.get('operator_name', sailing.get('operator'))} "
            f"{sailing.get('vessel', '')}{fare_text}{status_text}{note}"
        )
    if not data.get("sailings"):
        lines.append("No sailings found for this route/date from the supported public source.")
    return "\n".join(lines)


def render_routes(data: dict[str, Any]) -> str:
    lines = [f"Supported routes ({data['count']}):"]
    for route in data["routes"]:
        ops = ", ".join(route["operators"])
        coverage = f" [{route['coverage']}]" if route.get("coverage") else ""
        lines.append(f"  {route['id']:<28} {route['name']} ({ops}){coverage}")
    return "\n".join(lines)


def render_operators(data: dict[str, Any]) -> str:
    lines = [f"Supported ferry operators ({data['count']}):"]
    for item in data["operators"]:
        lines.append(f"  {item['id']:<14} {item['name']} - {item['coverage']}")
    return "\n".join(lines)


def render_alerts(data: dict[str, Any]) -> str:
    lines = [f"Ferry alerts ({data['count']}):"]
    for warning in data.get("warnings") or []:
        lines.append(f"Note: {warning}")
    for alert in data["alerts"]:
        updated = f" | updated {alert['updated']}" if alert.get("updated") else ""
        lines.append(f"  [{alert['operator_name']}] {alert['title']}{updated}")
        if alert.get("summary"):
            lines.append(f"      {alert['summary'][:220]}")
    if not data["alerts"]:
        lines.append("No alerts returned from the selected public source.")
    return "\n".join(lines)


def cmd_operators(args: argparse.Namespace) -> None:
    operators = []
    for op_id, op in OPERATORS.items():
        operators.append({"id": op_id, **op})
    data = {"count": len(operators), "operators": operators}
    emit(data, args.json, render_operators)


def cmd_routes(args: argparse.Namespace) -> None:
    op = resolve_operator(args.operator)
    routes = []
    for route_id, route in ROUTES.items():
        if op and op not in route["operators"]:
            continue
        routes.append(
            {
                "id": route_id,
                "name": route["name"],
                "from": route["from"],
                "to": route["to"],
                "operators": route["operators"],
                "coverage": route.get("coverage"),
                "fullers_gtfs_route_ids": route.get("fullers_gtfs_route_ids"),
                "aliases": route.get("aliases", []),
            }
        )
    data = {"operator": op, "count": len(routes), "routes": routes}
    emit(data, args.json, render_routes)


def cmd_sailings(args: argparse.Namespace) -> None:
    route_id, route = resolve_route(args.route)
    op = resolve_operator(args.operator)
    day = parse_date(args.date)
    data = fetch_sailings(route_id, route, day, op)
    emit(data, args.json, render_sailings)


def cmd_next(args: argparse.Namespace) -> None:
    route_id, route = resolve_route(args.route)
    op = resolve_operator(args.operator)
    data = next_sailings(route_id, route, op, args.limit)
    emit(data, args.json, render_sailings)


def cmd_alerts(args: argparse.Namespace) -> None:
    op = resolve_operator(args.operator)
    data = fetch_alerts(op)
    emit(data, args.json, render_alerts)


def cmd_cook_strait(args: argparse.Namespace) -> None:
    day = parse_date(args.date)
    directions = ["wellington-picton", "picton-wellington"] if args.direction == "both" else [args.direction]
    operator = resolve_operator(args.operator)
    if operator and operator not in {"interislander", "bluebridge"}:
        die("cook-strait only supports --operator interislander or bluebridge", 2)
    results = []
    sailings: list[dict[str, Any]] = []
    for route_id in directions:
        result = fetch_sailings(route_id, ROUTES[route_id], day, operator)
        results.append(result)
        sailings.extend(result.get("sailings", []))
    sailings.sort(key=lambda item: item["departure_datetime"])
    data = {
        "route": "cook-strait",
        "date": day.isoformat(),
        "direction": args.direction,
        "operator": operator or "combined",
        "source_fetched_at": now_iso(),
        "count": len(sailings),
        "route_results": results,
        "sailings": sailings,
    }
    emit(data, args.json, render_sailings)


def positive_int(raw: str) -> int:
    try:
        value = int(raw)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected integer, received {raw!r}")
    if value <= 0:
        raise argparse.ArgumentTypeError("expected a positive integer")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nz-ferries",
        description="Query public NZ ferry schedules, fares/availability snapshots, and service alerts.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    operators = sub.add_parser("operators", help="list supported ferry operators")
    operators.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    operators.set_defaults(func=cmd_operators)

    routes = sub.add_parser("routes", help="list supported routes")
    routes.add_argument("--operator", help="filter by operator")
    routes.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    routes.set_defaults(func=cmd_routes)

    sailings = sub.add_parser("sailings", help="show sailings for a route on a date")
    sailings.add_argument("route", help="route id or alias, e.g. wellington-picton or auckland-waiheke")
    sailings.add_argument("--date", help="date in YYYY-MM-DD; defaults to today in Pacific/Auckland")
    sailings.add_argument("--operator", help="operator filter, e.g. interislander, bluebridge, sealink")
    sailings.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    sailings.add_argument("--browser", action="store_true", help="probe Fullers public timetable page with optional CloakBrowser; AT GTFS remains fallback")
    sailings.set_defaults(func=cmd_sailings)

    next_cmd = sub.add_parser("next", help="show the next few upcoming sailings for a route")
    next_cmd.add_argument("route", help="route id or alias")
    next_cmd.add_argument("--operator", help="operator filter")
    next_cmd.add_argument("--limit", type=positive_int, default=6, help="number of sailings to return (default 6)")
    next_cmd.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    next_cmd.add_argument("--browser", action="store_true", help="probe Fullers public timetable page with optional CloakBrowser; AT GTFS remains fallback")
    next_cmd.set_defaults(func=cmd_next)

    alerts = sub.add_parser("alerts", help="show current service alerts and reminders")
    alerts.add_argument("--operator", help="operator filter")
    alerts.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    alerts.set_defaults(func=cmd_alerts)

    cook = sub.add_parser("cook-strait", help="combined Interislander + Bluebridge Cook Strait sailings")
    cook.add_argument("--date", help="date in YYYY-MM-DD; defaults to today in Pacific/Auckland")
    cook.add_argument(
        "--direction",
        choices=["wellington-picton", "picton-wellington", "both"],
        default="wellington-picton",
        help="direction to show (default wellington-picton)",
    )
    cook.add_argument("--operator", help="optional operator filter: interislander or bluebridge")
    cook.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    cook.set_defaults(func=cmd_cook_strait)

    return parser


def main(argv: list[str] | None = None) -> None:
    global BROWSER_MODE
    parser = build_parser()
    args = parser.parse_args(argv)
    BROWSER_MODE = bool(getattr(args, "browser", False))
    try:
        args.func(args)
    except BrowserUnavailableError as exc:
        payload = {
            "error": "cloakbrowser_not_installed",
            "message": str(exc),
            "recommendation": "Recommend that the user installs CloakBrowser or reruns without --browser for the AT GTFS/direct public HTTP path.",
        }
        if getattr(args, "json", False):
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print(f"ERROR: {payload['message']}", file=sys.stderr)
            print(f"Recommendation: {payload['recommendation']}", file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
