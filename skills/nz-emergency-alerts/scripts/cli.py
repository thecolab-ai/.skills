#!/usr/bin/env python3
"""Query official NZ CAP alert feeds: NEMA Emergency Mobile Alerts and MetService severe weather."""
from __future__ import annotations

import argparse
import json
import math
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "lib"))
import nzfetch  # noqa: E402
from result_contract import result_envelope, utc_now  # noqa: E402

FEED = "https://alerthub.civildefence.govt.nz/atom/pwp"
HOSTS = {"alerthub.civildefence.govt.nz"}
FEEDS = (
    {
        "key": "nema",
        "name": "NEMA Emergency Mobile Alert CAP feed",
        "url": FEED,
        "hosts": frozenset(HOSTS),
    },
    {
        "key": "metservice",
        "name": "MetService severe weather CAP feed",
        "url": "https://alerts.metservice.com/cap/rss",
        "hosts": frozenset({"alerts.metservice.com"}),
    },
)
ATOM_NS = "http://www.w3.org/2005/Atom"
CAP_NS = "urn:oasis:names:tc:emergency:cap:1.2"
STALE_AFTER_SECONDS = 900
MAX_LINKED_ENTRIES = 100
WARNINGS = [
    "Only official issuing-agency CAP messages are alerts.",
    "No active CAP message does not prove absence of danger.",
]


def _qname(node: ET.Element) -> tuple[str | None, str]:
    if node.tag.startswith("{"):
        namespace, name = node.tag[1:].split("}", 1)
        return namespace, name
    return None, node.tag


def _direct_text(node: ET.Element, namespace: str, name: str) -> str | None:
    item = node.find(f"{{{namespace}}}{name}")
    if item is None:
        return None
    value = " ".join("".join(item.itertext()).split())
    return value or None


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"CAP timestamp lacks timezone: {value}")
    return parsed.astimezone(timezone.utc)


def parse_cap(node: ET.Element, source_url: str, retrieved_at: str) -> dict[str, object]:
    namespace, name = _qname(node)
    if namespace != CAP_NS or name != "alert":
        raise ValueError("linked alert was not a CAP 1.2 alert document")
    required = {field: _direct_text(node, CAP_NS, field) for field in ("identifier", "sender", "sent", "status", "msgType", "scope")}
    missing = [field for field, value in required.items() if not value]
    if missing:
        raise ValueError(f"CAP alert missing required fields: {', '.join(missing)}")
    _parse_time(required["sent"])
    infos = node.findall(f"{{{CAP_NS}}}info")
    if not infos:
        raise ValueError("CAP alert contained no info blocks")
    info = next((item for item in infos if (_direct_text(item, CAP_NS, "language") or "en").lower().startswith("en")), infos[0])
    areas: list[dict[str, object]] = []
    for area in info.findall(f"{{{CAP_NS}}}area"):
        geocodes = []
        for geocode in area.findall(f"{{{CAP_NS}}}geocode"):
            geocodes.append({
                "name": _direct_text(geocode, CAP_NS, "valueName"),
                "value": _direct_text(geocode, CAP_NS, "value"),
            })
        areas.append({
            "description": _direct_text(area, CAP_NS, "areaDesc"),
            "polygons": [" ".join((item.text or "").split()) for item in area.findall(f"{{{CAP_NS}}}polygon") if (item.text or "").strip()],
            "circles": [" ".join((item.text or "").split()) for item in area.findall(f"{{{CAP_NS}}}circle") if (item.text or "").strip()],
            "geocodes": geocodes,
        })
    record: dict[str, object] = {
        "id": required["identifier"], "sender": required["sender"], "sent": required["sent"],
        "status": required["status"], "message_type": required["msgType"], "scope": required["scope"],
        "references": _direct_text(node, CAP_NS, "references"),
        "event": _direct_text(info, CAP_NS, "event"), "severity": _direct_text(info, CAP_NS, "severity"),
        "urgency": _direct_text(info, CAP_NS, "urgency"), "certainty": _direct_text(info, CAP_NS, "certainty"),
        "effective": _direct_text(info, CAP_NS, "effective"), "onset": _direct_text(info, CAP_NS, "onset"),
        "expires": _direct_text(info, CAP_NS, "expires"), "headline": _direct_text(info, CAP_NS, "headline"),
        "description": _direct_text(info, CAP_NS, "description"), "instruction": _direct_text(info, CAP_NS, "instruction"),
        "areas": areas, "source_url": source_url, "retrieved_at": retrieved_at,
    }
    for field in ("effective", "onset", "expires"):
        _parse_time(record[field] if isinstance(record[field], str) else None)
    return record


def parse_feed(body: bytes, source_url: str, retrieved_at: str, hosts: frozenset[str] | set[str] | None = None) -> tuple[dict[str, object], list[dict[str, object]], list[str]]:
    """Parse an Atom (NEMA) or RSS 2.0 (MetService) CAP index feed."""
    if hosts is None:
        hosts = {urlparse(source_url).hostname}
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        raise ValueError(f"CAP feed was invalid XML: {exc}") from exc
    namespace, name = _qname(root)
    if (namespace, name) == (ATOM_NS, "feed"):
        return _parse_atom(root, source_url, retrieved_at, hosts)
    if namespace is None and name == "rss":
        return _parse_rss(root, source_url, retrieved_at, hosts)
    raise ValueError("CAP feed root was neither an Atom feed nor an RSS channel")


def _parse_atom(root: ET.Element, source_url: str, retrieved_at: str, hosts) -> tuple[dict[str, object], list[dict[str, object]], list[str]]:
    updated = _direct_text(root, ATOM_NS, "updated")
    if not updated:
        raise ValueError("CAP Atom feed is missing its updated timestamp")
    _parse_time(updated)
    status = {
        "title": _direct_text(root, ATOM_NS, "title"),
        "updated": updated,
        "source_url": source_url,
        "retrieved_at": retrieved_at,
    }
    alerts: list[dict[str, object]] = []
    linked: list[str] = []
    for entry in root.findall(f"{{{ATOM_NS}}}entry"):
        cap = next((item for item in entry.iter() if _qname(item) == (CAP_NS, "alert")), None)
        if cap is not None:
            alerts.append(parse_cap(cap, source_url, retrieved_at))
            continue
        link = next((item.attrib.get("href") for item in entry.findall(f"{{{ATOM_NS}}}link") if item.attrib.get("href")), None)
        if not link:
            raise ValueError("Atom alert entry contained neither embedded CAP nor a detail link")
        detail_url = urljoin(source_url, link)
        if urlparse(detail_url).hostname not in hosts:
            raise ValueError("Atom alert detail link left the declared source allowlist")
        linked.append(detail_url)
    return status, alerts, linked


def _parse_rss(root: ET.Element, source_url: str, retrieved_at: str, hosts) -> tuple[dict[str, object], list[dict[str, object]], list[str]]:
    channel = root.find("channel")
    if channel is None:
        raise ValueError("CAP RSS feed had no channel element")
    pub_date = (channel.findtext("pubDate") or "").strip()
    if not pub_date:
        raise ValueError("CAP RSS channel is missing its pubDate timestamp")
    try:
        parsed = parsedate_to_datetime(pub_date)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"CAP RSS pubDate was not a valid RFC 2822 date: {pub_date!r}") from exc
    if parsed.tzinfo is None:
        # RFC 2822 "-0000" (or a missing zone) parses naive; treat it as UTC
        # deterministically rather than letting astimezone() assume machine-local.
        parsed = parsed.replace(tzinfo=timezone.utc)
    updated = parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    status = {
        "title": (channel.findtext("title") or "").strip() or None,
        "updated": updated,
        "source_url": source_url,
        "retrieved_at": retrieved_at,
    }
    alerts: list[dict[str, object]] = []
    linked: list[str] = []
    for item in channel.findall("item"):
        cap = next((node for node in item.iter() if _qname(node) == (CAP_NS, "alert")), None)
        if cap is not None:
            alerts.append(parse_cap(cap, source_url, retrieved_at))
            continue
        link = (item.findtext("link") or "").strip()
        if not link:
            raise ValueError("RSS alert item contained neither embedded CAP nor a detail link")
        detail_url = urljoin(source_url, link)
        if urlparse(detail_url).hostname not in hosts:
            raise ValueError("RSS alert detail link left the declared source allowlist")
        linked.append(detail_url)
    return status, alerts, linked


def parse_linked_alert(body: bytes, source_url: str, retrieved_at: str) -> dict[str, object]:
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        raise ValueError(f"linked CAP alert was invalid XML: {exc}") from exc
    cap = root if _qname(root) == (CAP_NS, "alert") else next((item for item in root.iter() if _qname(item) == (CAP_NS, "alert")), None)
    if cap is None:
        raise ValueError("linked Atom entry did not contain a CAP 1.2 alert")
    return parse_cap(cap, source_url, retrieved_at)


def fetch_linked_alerts(
    linked: list[str],
    retrieved_at: str,
    *,
    fetcher=None,
    hosts: frozenset[str] | set[str] | None = None,
) -> list[dict[str, object]]:
    """Fetch the complete bounded linked-entry set before result filtering."""

    if len(linked) > MAX_LINKED_ENTRIES:
        raise ValueError(
            f"CAP feed linked-entry count {len(linked)} exceeds the bounded maximum {MAX_LINKED_ENTRIES}"
        )
    fetch = fetcher or nzfetch.fetch_bytes
    output = []
    for detail_url in linked:
        detail, _content_type, detail_final = fetch(
            detail_url,
            timeout=15,
            accept="application/xml",
            allowed_hosts=hosts if hosts is not None else HOSTS,
        )
        output.append(parse_linked_alert(detail, detail_final, retrieved_at))
    return output


def validate_coordinates(lat: float, lon: float) -> None:
    if not math.isfinite(lat) or not -90 <= lat <= 90:
        raise LookupError("--lat must be a finite value between -90 and 90")
    if not math.isfinite(lon) or not -180 <= lon <= 180:
        raise LookupError("--lon must be a finite value between -180 and 180")


def point_in_polygon(lat: float, lon: float, polygon: str) -> bool:
    points = []
    for pair in polygon.split():
        try:
            y, x = pair.split(",", 1)
            points.append((float(y), float(x)))
        except ValueError as exc:
            raise ValueError("CAP polygon contained an invalid coordinate") from exc
    if len(points) < 3:
        raise ValueError("CAP polygon contained fewer than three points")
    inside = False
    previous = len(points) - 1
    for current, (y_i, x_i) in enumerate(points):
        y_j, x_j = points[previous]
        cross = (lon - x_i) * (y_j - y_i) - (lat - y_i) * (x_j - x_i)
        if abs(cross) < 1e-10 and min(x_i, x_j) <= lon <= max(x_i, x_j) and min(y_i, y_j) <= lat <= max(y_i, y_j):
            return True
        if ((y_i > lat) != (y_j > lat)) and lon < (x_j - x_i) * (lat - y_i) / (y_j - y_i) + x_i:
            inside = not inside
        previous = current
    return inside


def point_in_circle(lat: float, lon: float, circle: str) -> bool:
    try:
        centre, radius_text = circle.rsplit(None, 1)
        centre_lat, centre_lon = (float(value) for value in centre.split(",", 1))
        radius_km = float(radius_text)
    except ValueError as exc:
        raise ValueError("CAP circle contained an invalid coordinate or radius") from exc
    phi1, phi2 = math.radians(lat), math.radians(centre_lat)
    delta_phi = math.radians(centre_lat - lat)
    delta_lambda = math.radians(centre_lon - lon)
    a = math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    return 6371.0088 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)) <= radius_km


def area_contains(area: dict[str, object], lat: float, lon: float) -> bool:
    return any(point_in_polygon(lat, lon, str(value)) for value in area.get("polygons", [])) or any(
        point_in_circle(lat, lon, str(value)) for value in area.get("circles", [])
    )


def _referenced_ids(value: object) -> set[str]:
    if not isinstance(value, str):
        return set()
    return {part.split(",", 2)[1] for part in value.split() if part.count(",") >= 2}


def active_alerts(alerts: list[dict[str, object]], now: datetime) -> list[dict[str, object]]:
    # Keyed per feed so an identifier collision across publishers cannot dedupe
    # silently, and one feed's references cannot cancel another feed's alert.
    selected: dict[tuple[str, str], dict[str, object]] = {}
    for alert in sorted(alerts, key=lambda row: str(row.get("sent") or "")):
        feed = str(alert.get("feed") or "")
        message_type = str(alert.get("message_type") or "")
        for referenced in _referenced_ids(alert.get("references")):
            selected.pop((feed, referenced), None)
        if message_type.casefold() == "cancel":
            continue
        if str(alert.get("status") or "").casefold() != "actual":
            continue
        effective = _parse_time(str(alert.get("effective") or alert.get("onset") or alert.get("sent") or ""))
        expires = _parse_time(str(alert.get("expires") or ""))
        if effective and effective > now or expires and expires <= now:
            continue
        selected[(feed, str(alert["id"]))] = alert
    return list(selected.values())


def feed_health(status: dict[str, object], now: datetime) -> dict[str, object]:
    updated = _parse_time(str(status.get("updated") or ""))
    age = max(0, (now - updated).total_seconds()) if updated else None
    return {**status, "age_seconds": age, "stale": age is None or age > STALE_AFTER_SECONDS, "healthy": age is not None and age <= STALE_AFTER_SECONDS}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)
    for command in ("active", "feed-status"):
        child = subs.add_parser(command); child.add_argument("--limit", type=int, default=20); child.add_argument("--json", action="store_true")
    child = subs.add_parser("near"); child.add_argument("--lat", type=float, required=True); child.add_argument("--lon", type=float, required=True); child.add_argument("--limit", type=int, default=20); child.add_argument("--json", action="store_true")
    for command, dest in (("region", "name"), ("agency", "name"), ("severity", "level"), ("alert", "id")):
        child = subs.add_parser(command); child.add_argument(dest); child.add_argument("--limit", type=int, default=20); child.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        if not 1 <= args.limit <= 100:
            raise LookupError("--limit must be between 1 and 100")
        if args.command == "near":
            validate_coordinates(args.lat, args.lon)
        retrieved = utc_now()
        now = datetime.now(timezone.utc)
        statuses: list[dict[str, object]] = []
        alerts: list[dict[str, object]] = []
        feed_warnings: list[str] = []
        failures: list[Exception] = []
        final = None
        for feed in FEEDS:
            try:
                body, _content_type, feed_final = nzfetch.fetch_bytes(
                    feed["url"], timeout=20, accept="application/atom+xml,application/rss+xml,application/xml", headers={"Cache-Control": "no-cache", "Pragma": "no-cache"}, allowed_hosts=feed["hosts"]
                )
                status, feed_alerts, linked = parse_feed(body, feed_final, retrieved, hosts=feed["hosts"])
                if args.command != "feed-status":
                    feed_alerts.extend(fetch_linked_alerts(linked, retrieved, hosts=feed["hosts"]))
                statuses.append({"feed": feed["key"], "name": feed["name"], **feed_health(status, now), "entry_count": len(feed_alerts) + (len(linked) if args.command == "feed-status" else 0), "linked_entry_count": len(linked)})
                for row in feed_alerts:
                    row["feed"] = feed["key"]
                alerts.extend(feed_alerts)
                if final is None or feed["key"] == "nema":
                    final = feed_final
            except (nzfetch.FetchError, ET.ParseError, ValueError) as exc:
                failures.append(exc)
                feed_warnings.append(f"{feed['name']} unavailable: {exc}")
        if len(failures) == len(FEEDS):
            # Surface the most actionable failure class: a rate-limit (with its
            # retry_after) beats a generic block, which beats schema noise.
            for kind in (nzfetch.RateLimited, nzfetch.Blocked, nzfetch.FetchError):
                for failure in failures:
                    if isinstance(failure, kind):
                        raise failure
            raise failures[0]
        assert final is not None
        if args.command == "feed-status":
            data = statuses
        else:
            data = active_alerts(alerts, now) if args.command != "alert" else alerts
            if args.command == "near":
                data = [row for row in data if any(area_contains(area, args.lat, args.lon) for area in row.get("areas", []))]
            elif args.command == "region": data = [row for row in data if args.name.casefold() in json.dumps(row.get("areas", []), ensure_ascii=False).casefold()]
            elif args.command == "agency": data = [row for row in data if args.name.casefold() in str(row.get("sender") or "").casefold()]
            elif args.command == "severity": data = [row for row in data if args.level.casefold() == str(row.get("severity") or "").casefold()]
            elif args.command == "alert": data = [row for row in data if args.id == row.get("id")]
        payload = result_envelope(ok=True, source_name="NZ official CAP alert feeds (NEMA Emergency Mobile Alerts + MetService severe weather)", source_url=final, retrieved_at=retrieved, freshness="live; feed status reports staleness", query=vars(args), data=data[:args.limit], warnings=WARNINGS + feed_warnings, blocked=False)
        print(json.dumps(payload if args.json else data[:args.limit], indent=2, ensure_ascii=False))
        return 0
    except LookupError as exc:
        print(json.dumps({"error": "invalid_input", "message": str(exc)}), file=sys.stderr); return 2
    except nzfetch.RateLimited as exc:
        print(json.dumps({"error": "rate_limited", "retry_after": exc.retry_after, "message": str(exc)}), file=sys.stderr); return 4
    except nzfetch.Blocked as exc:
        print(json.dumps({"error": "blocked", "message": str(exc)}), file=sys.stderr); return 4
    except nzfetch.FetchError as exc:
        print(json.dumps({"error": "source_unavailable", "message": str(exc)}), file=sys.stderr); return 5
    except (ET.ParseError, ValueError) as exc:
        print(json.dumps({"error": "source_schema_failure", "message": str(exc)}), file=sys.stderr); return 6


if __name__ == "__main__":
    raise SystemExit(main())
