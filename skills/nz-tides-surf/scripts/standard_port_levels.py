#!/usr/bin/env python3
"""LINZ standard-port tidal levels from one official HTML table.

Heights are published reference levels in metres on Chart Datum. They are not
daily tide-prediction events and not observed sea-level gauge readings.
"""
from __future__ import annotations

import json
import os
import re
import sys
import unicodedata
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parents[2]
sys.path.insert(0, str(_REPO_ROOT / "lib"))
sys.path.insert(0, str(_SCRIPT_DIR))

import nzfetch  # noqa: E402
from provenance import error_envelope, provenance, result_envelope  # noqa: E402

LEVELS_URL = (
    "https://www.linz.govt.nz/guidance/marine-information/"
    "tide-prediction-guidance/standard-port-tidal-levels"
)
LEVELS_PATH = (
    "/guidance/marine-information/tide-prediction-guidance/standard-port-tidal-levels"
)
PUBLISHER = "Toitū Te Whenua Land Information New Zealand"
LICENCE = (
    "Creative Commons Attribution 4.0 International. "
    "Attribute Toitū Te Whenua Land Information New Zealand. "
    "LINZ website content; not a LINZ Data Service dataset licence."
)
ALLOWED_HOSTS = frozenset({"www.linz.govt.nz"})
TIMEOUT_SECONDS = 10
MAX_BYTES = 262144
CACHE_TTL = timedelta(hours=24)
PORT_NAME_LIMIT = 80

EXPECTED_HEADERS = (
    "standardport",
    "mhws",
    "mhwn",
    "mlwn",
    "mlws",
    "springrange",
    "neaprange",
    "msl",
    "hat",
    "lat",
)
VALUE_FIELDS = (
    "mhws_m",
    "mhwn_m",
    "mlwn_m",
    "mlws_m",
    "spring_range_m",
    "neap_range_m",
    "msl_m",
    "hat_m",
    "lat_m",
)
METRES_DATUM_RE = re.compile(
    r"levels, in metres, are referred to Chart Datum, which is the same as the zero of the tidal predictions",
    re.IGNORECASE,
)
MHWS_PERIOD_RE = re.compile(
    r"averages of the levels of all spring and neap tides predicted for the period (.+?) using the harmonic",
    re.IGNORECASE,
)
RANGE_BASIS_RE = re.compile(
    r"values for the spring and neap ranges have been deduced from the spring and neap tidal level values",
    re.IGNORECASE,
)
MSL_BASIS_RE = re.compile(
    r"value of MSL for each port has been derived from the analysis of tidal observations",
    re.IGNORECASE,
)
HAT_PERIOD_RE = re.compile(
    r"highest and lowest tidal levels that are predicted to occur under average meteorological conditions during the period (.+?) using the harmonic",
    re.IGNORECASE,
)
CADASTRAL_RE = re.compile(
    r"not intended to be used for the determination of cadastral or administrative boundaries",
    re.IGNORECASE,
)
NUMBER_RE = re.compile(r"^-?\d+(?:\.\d+)?$")
OBSERVATION_PERIOD_HREF = (
    "/guidance/marine-information/tide-prediction-guidance/standard-port-periods-observation"
)


class LevelsError(Exception):
    def __init__(self, code: int, message: str, *, retry_after: str | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retry_after = retry_after


def schema_error(message: str) -> LevelsError:
    return LevelsError(6, f"source schema: {message}")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _stamp(moment: datetime | None = None) -> str:
    current = moment or _now()
    return current.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse_stamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def _header_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _port_key(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold()).strip()


def cache_enabled() -> bool:
    return os.environ.get("NZ_TIDES_SURF_LEVELS_CACHE", "1") != "0"


def cache_file() -> Path:
    override = os.environ.get("NZ_TIDES_SURF_LEVELS_CACHE_DIR")
    base = Path(override) if override else Path.home() / ".cache" / "thecolab" / "nz-tides-surf"
    return base / "standard-port-tidal-levels.json"


def validate_port_argument(port: str | None) -> str | None:
    """Reject a query that cannot be a published port name before any fetch."""
    if port is None:
        return None
    cleaned = port.strip()
    if not cleaned or len(cleaned) > PORT_NAME_LIMIT:
        raise LevelsError(2, "port must be a published standard-port name, or omit it to list the table")
    if any(unicodedata.category(char).startswith("C") for char in cleaned):
        raise LevelsError(2, "port must be a published standard-port name, or omit it to list the table")
    if "://" in cleaned or "/" in cleaned or "\\" in cleaned:
        raise LevelsError(2, "port must be a published standard-port name, or omit it to list the table")
    return cleaned


def assert_official_levels_url(url: str) -> None:
    parts = urlsplit(url)
    path = parts.path.rstrip("/") or "/"
    if (
        parts.scheme != "https"
        or (parts.hostname or "").lower() != "www.linz.govt.nz"
        or path != LEVELS_PATH
        or parts.query
        or parts.fragment
        or parts.username
        or parts.password
    ):
        raise LevelsError(
            5,
            "network error: levels page resolved away from the official standard-port table",
        )


class _LevelsHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[str]]] = []
        self.notes: list[str] = []
        self.observation_href: str | None = None
        self._skip_depth = 0
        self._table_depth = 0
        self._current: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._in_h2 = False
        self._h2: list[str] = []
        self._capture_notes = False
        self._ol_depth = 0
        self._in_li = False
        self._li: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in {"script", "style"}:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag == "table":
            self._table_depth += 1
            if self._table_depth == 1:
                self._current = []
            return
        if self._table_depth == 1 and tag == "tr":
            self._row = []
            return
        if self._table_depth == 1 and tag in {"td", "th"} and self._row is not None:
            self._cell = []
            return
        if tag == "br" and self._cell is not None:
            self._cell.append(" ")
            return
        if tag == "h2":
            self._in_h2 = True
            self._h2 = []
            return
        if tag == "ol" and self._capture_notes:
            self._ol_depth += 1
            return
        if tag == "li" and self._capture_notes and self._ol_depth:
            self._in_li = True
            self._li = []
            return
        if tag == "a" and self._in_li:
            href = ""
            for key, value in attrs:
                if key.lower() == "href" and value:
                    href = value
            if _observation_page(href):
                self.observation_href = href
            return
        if tag == "br" and self._in_li:
            self._li.append(" ")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style"} and self._skip_depth:
            self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if tag in {"td", "th"} and self._cell is not None and self._row is not None:
            self._row.append(re.sub(r"\s+", " ", "".join(self._cell)).strip())
            self._cell = None
            return
        if tag == "tr" and self._table_depth == 1 and self._row is not None and self._current is not None:
            if any(self._row):
                self._current.append(self._row)
            self._row = None
            return
        if tag == "table" and self._table_depth:
            self._table_depth -= 1
            if self._table_depth == 0 and self._current is not None:
                self.tables.append(self._current)
                self._current = None
            return
        if tag == "h2" and self._in_h2:
            self._in_h2 = False
            heading = re.sub(r"\s+", " ", "".join(self._h2)).strip().casefold()
            self._capture_notes = heading == "notes"
            return
        if tag == "ol" and self._capture_notes and self._ol_depth:
            self._ol_depth -= 1
            if self._ol_depth == 0:
                self._capture_notes = False
            return
        if tag == "li" and self._in_li:
            text = re.sub(r"\s+", " ", "".join(self._li)).strip()
            if text:
                self.notes.append(text)
            self._in_li = False

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._cell is not None:
            self._cell.append(data)
        if self._in_h2:
            self._h2.append(data)
        if self._in_li:
            self._li.append(data)


def _matching_table(tables: list[list[list[str]]]) -> list[list[str]]:
    matches = []
    for table in tables:
        if not table:
            continue
        header = [_header_key(cell) for cell in table[0]]
        if header == list(EXPECTED_HEADERS):
            matches.append(table)
    if not matches:
        raise schema_error("standard-port tidal-level table was not found")
    if len(matches) != 1:
        raise schema_error("more than one standard-port tidal-level table was found")
    return matches[0]


def _metres(token: str, port: str, field: str) -> float:
    if not NUMBER_RE.fullmatch(token):
        raise schema_error(f"non-numeric {field} for {port or 'a port row'}")
    return float(token)


def _observation_page(href: str | None) -> str | None:
    """Record the cited observation-period page without fetching it."""
    if not href:
        return None
    parts = urlsplit(href)
    if parts.scheme or parts.netloc:
        if parts.scheme != "https" or (parts.hostname or "").lower() != "www.linz.govt.nz":
            return None
        path = parts.path
    else:
        path = parts.path or href
    path = path.split("?", 1)[0].split("#", 1)[0]
    if path.rstrip("/") != OBSERVATION_PERIOD_HREF:
        return None
    return "https://www.linz.govt.nz" + OBSERVATION_PERIOD_HREF


def _notes_context(notes: list[str], observation_href: str | None) -> dict[str, Any]:
    text = " ".join(notes)
    if not METRES_DATUM_RE.search(text):
        raise schema_error("page does not state metres on Chart Datum, the zero of the tidal predictions")
    mhws_period = MHWS_PERIOD_RE.search(text)
    hat_period = HAT_PERIOD_RE.search(text)
    if not mhws_period or not RANGE_BASIS_RE.search(text):
        raise schema_error("page does not state the predicted spring and neap level period")
    if not MSL_BASIS_RE.search(text):
        raise schema_error("page does not state that MSL is derived from tidal observations")
    if not hat_period:
        raise schema_error("page does not state the predicted HAT and LAT period")
    if not CADASTRAL_RE.search(text):
        raise schema_error("page does not state the cadastral-boundary limitation")
    observation_page = _observation_page(observation_href)
    return {
        "unit": "m",
        "datum": "Chart Datum",
        "datum_note": (
            "Levels are in metres referred to Chart Datum, which is the same as the zero of the tidal predictions."
        ),
        "mhws_mhwn_mlwn_mlws_period": mhws_period.group(1).strip(),
        "hat_lat_period": hat_period.group(1).strip(),
        "msl_observation_period": None,
        "msl_observation_period_page": observation_page,
        "msl_observation_period_page_fetched": False,
        "level_basis": {
            "mhws_mhwn_mlwn_mlws": "averages of predicted spring and neap tides",
            "spring_range_neap_range": "deduced from the spring and neap tidal level values",
            "msl": "derived from analysis of tidal observations",
            "hat_lat": "highest and lowest tidal levels predicted under average meteorological conditions",
        },
        "cadastral_or_administrative_boundary_use": False,
    }


def parse_levels_document(html: str) -> dict[str, Any]:
    if not html or not html.strip():
        raise schema_error("standard-port page was empty")
    if len(html.encode("utf-8")) > MAX_BYTES:
        raise schema_error("standard-port page exceeded the byte cap before parsing")
    parser = _LevelsHTMLParser()
    try:
        parser.feed(html)
        parser.close()
    except LevelsError:
        raise
    except Exception as exc:
        raise schema_error("standard-port page could not be parsed") from exc
    table = _matching_table(parser.tables)
    context = _notes_context(parser.notes, parser.observation_href)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in table[1:]:
        if len(raw) != len(EXPECTED_HEADERS):
            raise schema_error("a standard-port row does not have the published columns")
        port = raw[0].strip()
        if not port:
            raise schema_error("a standard-port row has no port name")
        identity = _port_key(port)
        if identity in seen:
            raise schema_error(f"duplicate standard port {port}")
        seen.add(identity)
        values = {
            field: _metres(raw[index + 1], port, field)
            for index, field in enumerate(VALUE_FIELDS)
        }
        rows.append(
            {
                "standard_port": port,
                "kind": "standard_port_reference_level",
                "observed_gauge_reading": False,
                "tide_prediction_event": False,
                **values,
                **context,
            }
        )
    if not rows:
        raise schema_error("standard-port table has no port rows")
    return {"rows": rows, "context": context}


def select_ports(rows: list[dict[str, Any]], port: str | None) -> list[dict[str, Any]]:
    cleaned = validate_port_argument(port)
    if cleaned is None:
        return rows
    needle = _port_key(cleaned)
    matches = [row for row in rows if _port_key(row["standard_port"]) == needle]
    if len(matches) == 1:
        return matches
    if len(matches) > 1:
        raise schema_error(f"duplicate standard port {cleaned}")
    names = [row["standard_port"] for row in rows]
    folded = cleaned.casefold()
    close = [name for name in names if folded in name.casefold() or name.casefold() in folded]
    hint = f" Closest names: {', '.join(close[:3])}." if close else ""
    known = ", ".join(names)
    raise LevelsError(
        2,
        f"unknown standard port {cleaned!r}.{hint} Published ports: {known}. "
        "Surf-beach names are not standard ports, and this command does not read tide predictions.",
    )


def latest_data_text(context: dict[str, Any]) -> str:
    return (
        "MHWS, MHWN, MLWN and MLWS are averages of predicted spring and neap tides for "
        f"{context['mhws_mhwn_mlwn_mlws_period']}; spring and neap ranges are deduced from those levels; "
        "MSL is derived from tidal observations and its observation period is not on this page; "
        "HAT and LAT are predicted under average meteorological conditions for "
        f"{context['hat_lat_period']}. Heights are metres above Chart Datum."
    )


def build_envelope(rows: list[dict[str, Any]], *, retrieved_at: str, cached: bool) -> dict[str, Any]:
    if not rows:
        raise schema_error("standard-port table has no port rows")
    meta = provenance(
        LEVELS_URL,
        PUBLISHER,
        licence=LICENCE,
        latest_data=latest_data_text(rows[0]),
        retrieved_at=retrieved_at,
    )
    meta["cached"] = "true" if cached else "false"
    return result_envelope(rows, meta)


def _read_cache(now: datetime) -> dict[str, str] | None:
    path = cache_file()
    try:
        if not path.is_file() or path.stat().st_size > MAX_BYTES + 4096:
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return None
    if not isinstance(payload, dict):
        return None
    html = payload.get("html")
    retrieved_at = payload.get("retrieved_at")
    source_url = payload.get("source_url")
    if not isinstance(html, str) or not isinstance(retrieved_at, str) or source_url != LEVELS_URL:
        return None
    try:
        fetched = _parse_stamp(retrieved_at)
    except ValueError:
        return None
    if fetched - now > timedelta(minutes=5) or now - fetched > CACHE_TTL:
        return None
    return {"html": html, "retrieved_at": _stamp(fetched)}


def _write_cache(html: str, retrieved_at: str) -> None:
    path = cache_file()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(
                {"source_url": LEVELS_URL, "retrieved_at": retrieved_at, "html": html},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        temporary.replace(path)
    except OSError:
        return


def map_fetch_error(exc: Exception) -> LevelsError:
    if isinstance(exc, nzfetch.RateLimited):
        retry_after = exc.retry_after
        suffix = f" retry_after={retry_after}" if retry_after else ""
        return LevelsError(4, f"network error: rate_limited:{suffix} {exc}".rstrip(), retry_after=retry_after)
    if isinstance(exc, nzfetch.Blocked):
        return LevelsError(4, f"network error: blocked: {exc}")
    if isinstance(exc, nzfetch.ResponseTooLarge):
        return LevelsError(5, f"network error: standard-port page exceeded {MAX_BYTES} bytes")
    if isinstance(exc, nzfetch.FetchError):
        return LevelsError(5, f"network error: {exc}")
    return LevelsError(5, f"network error: {exc}")


def live_fetch() -> tuple[str, str]:
    retrieved_at = _stamp()
    try:
        body, content_type, final_url = nzfetch.fetch_bytes(
            LEVELS_URL,
            timeout=TIMEOUT_SECONDS,
            accept="text/html,application/xhtml+xml",
            allowed_hosts=ALLOWED_HOSTS,
            max_bytes=MAX_BYTES,
            expect_json=False,
        )
    except LevelsError:
        raise
    except Exception as exc:
        raise map_fetch_error(exc) from exc
    assert_official_levels_url(final_url)
    if "html" not in (content_type or "").lower():
        raise schema_error("standard-port page was not HTML")
    if not body:
        raise schema_error("standard-port page was empty")
    charset = "utf-8"
    matched = re.search(r"charset=([\w.-]+)", content_type or "", re.IGNORECASE)
    if matched:
        charset = matched.group(1)
    return body.decode(charset, "replace"), retrieved_at


def load_levels_table(
    port: str | None = None,
    *,
    fetch: Callable[[], tuple[str, str]] | None = None,
) -> dict[str, Any]:
    validate_port_argument(port)
    now = _now()
    cached_payload = _read_cache(now) if cache_enabled() else None
    if cached_payload is not None:
        try:
            document = parse_levels_document(cached_payload["html"])
            rows = select_ports(document["rows"], port)
            return build_envelope(rows, retrieved_at=cached_payload["retrieved_at"], cached=True)
        except LevelsError as exc:
            if exc.code != 6:
                raise
            cached_payload = None
    try:
        html, retrieved_at = (fetch or live_fetch)()
    except LevelsError:
        raise
    except Exception as exc:
        raise map_fetch_error(exc) from exc
    document = parse_levels_document(html)
    if cache_enabled():
        _write_cache(html, retrieved_at)
    rows = select_ports(document["rows"], port)
    return build_envelope(rows, retrieved_at=retrieved_at, cached=False)


def error_payload(exc: LevelsError) -> dict[str, Any]:
    meta = provenance(LEVELS_URL, PUBLISHER, licence=LICENCE)
    return error_envelope(exc.code, exc.message, meta, retry_after=exc.retry_after)
