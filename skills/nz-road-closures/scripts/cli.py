#!/usr/bin/env python3
"""NZTA Journey Planner read-only road closures, incidents, and cameras CLI."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

JOURNEY_BASE = "https://www.journeys.nzta.govt.nz"
DATA_BASE = JOURNEY_BASE + "/assets/map-data-cache"
CAMERA_BASE = "https://www.trafficnz.info"
UA = os.environ.get(
    "NZ_ROAD_CLOSURES_USER_AGENT",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
)

EVENT_TYPE_ALIASES = {
    "closure": {"closures"},
    "roadworks": {"roadworks"},
    "incident": {"hazards", "warnings"},
}


class CliError(Exception):
    pass


def fetch_json(filename: str, timeout: int = 30) -> Any:
    url = DATA_BASE + "/" + filename
    headers = {
        "Accept": "application/json",
        "Referer": JOURNEY_BASE + "/highway-conditions",
        "User-Agent": UA,
    }
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            return json.loads(raw)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        raise CliError(f"HTTP {e.code} from {url}: {body[:300]}") from e
    except urllib.error.URLError as e:
        raise CliError(f"network error calling {url}: {e.reason}") from e
    except json.JSONDecodeError as e:
        raise CliError(f"invalid JSON from {url}: {e}") from e


def norm_text(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = text.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def epoch_utc(value: Any) -> str | None:
    try:
        return datetime.fromtimestamp(int(value), timezone.utc).isoformat()
    except Exception:
        return None


def natural_key(value: Any) -> list[Any]:
    parts = re.split(r"(\d+)", str(value or ""))
    return [int(p) if p.isdigit() else p.lower() for p in parts]


def trim(value: Any, limit: int = 220) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def first_coordinate(value: Any) -> list[float] | None:
    if isinstance(value, list):
        if len(value) >= 2 and all(isinstance(x, (int, float)) for x in value[:2]):
            return [float(value[0]), float(value[1])]
        for item in value:
            found = first_coordinate(item)
            if found:
                return found
    return None


def count_coordinates(value: Any) -> int:
    if isinstance(value, list):
        if len(value) >= 2 and all(isinstance(x, (int, float)) for x in value[:2]):
            return 1
        return sum(count_coordinates(item) for item in value)
    return 0


def geometry_summary(geometry: Any) -> dict[str, Any] | None:
    if not isinstance(geometry, dict):
        return None
    return {
        "type": geometry.get("type"),
        "first_coordinate": first_coordinate(geometry.get("coordinates")),
        "coordinate_count": count_coordinates(geometry.get("coordinates")),
    }


def absolute_url(url: Any, base: str) -> str | None:
    if not url:
        return None
    raw = str(url)
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw
    return urllib.parse.urljoin(base, raw)


def load_regions() -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    payload = fetch_json("regions.json")
    regions: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}
    for feature in payload.get("features") or []:
        p = feature.get("properties") or {}
        region = {
            "id": p.get("id"),
            "tas_id": p.get("tasId"),
            "name": p.get("name"),
            "slug": p.get("slug"),
            "published_page": boolish(p.get("publishedPage")),
        }
        regions.append(region)
        if region["id"] is not None:
            by_id[str(region["id"])] = region
        if region["tas_id"] is not None:
            by_id[f"tas:{region['tas_id']}"] = region
    return regions, by_id


def match_region(query: str | None, regions: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not query:
        return None
    raw = str(query).strip()
    target = norm_text(raw)
    matches: list[dict[str, Any]] = []
    for region in regions:
        aliases = [
            region.get("id"),
            region.get("tas_id"),
            region.get("name"),
            region.get("slug"),
        ]
        alias_norms = [norm_text(a) for a in aliases if a is not None]
        alias_raws = {str(a).strip().lower() for a in aliases if a is not None}
        if raw.lower() in alias_raws or target in alias_norms:
            matches.append(region)
            continue
        if any(target and (target in a or a in target) for a in alias_norms if a):
            matches.append(region)
    if not matches:
        choices = ", ".join(r["name"] for r in regions if r.get("name"))
        raise CliError(f"unknown NZTA Journey Planner region: {query}. Known regions: {choices}")
    return {
        "query": query,
        "regions": matches,
        "ids": {str(r["id"]) for r in matches if r.get("id") is not None},
        "tas_ids": {str(r["tas_id"]) for r in matches if r.get("tas_id") is not None},
        "names": {norm_text(r["name"]) for r in matches if r.get("name")},
    }


def region_objects(ids: list[Any], by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for raw in ids:
        region = by_id.get(str(raw))
        if region:
            out.append(region)
        else:
            out.append({"id": raw, "tas_id": None, "name": str(raw), "slug": None, "published_page": False})
    return out


def source_url_for_event(props: dict[str, Any], regions: list[dict[str, Any]]) -> str:
    event_id = props.get("id") or props.get("ExternalId")
    slug = next((r.get("slug") for r in regions if r.get("slug")), None)
    if slug and event_id:
        return f"{JOURNEY_BASE}/regions/{slug}/traffic-updates/{event_id}/details"
    return JOURNEY_BASE + "/highway-conditions/traffic-and-travel-list-view"


def severity_from_event(props: dict[str, Any]) -> str:
    impact = norm_text(props.get("Impact"))
    event_type = norm_text(props.get("EventType"))
    raw_type = props.get("type")
    if "road closed" in impact or raw_type == "closures":
        return "severe"
    if "vehicle restrictions" in impact or "delays" in impact:
        return "moderate"
    if "caution" in impact or raw_type in {"hazards", "warnings"}:
        return "caution"
    if "road work" in event_type:
        return "roadworks"
    return "info"


def normalize_event(feature: dict[str, Any], by_region_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    props = feature.get("properties") or {}
    regions = region_objects(as_list(props.get("regions")), by_region_id)
    raw_type = props.get("type")
    category = "incident" if raw_type in {"hazards", "warnings"} else ("closure" if raw_type == "closures" else raw_type)
    return {
        "id": props.get("id") or props.get("ExternalId"),
        "external_id": props.get("ExternalId"),
        "internal_id": props.get("InternalId"),
        "uniq": props.get("uniq"),
        "type": raw_type,
        "category": category,
        "event_type": props.get("EventType"),
        "impact": props.get("Impact"),
        "severity": severity_from_event(props),
        "status": props.get("Status"),
        "name": props.get("Name"),
        "location": props.get("LocationArea"),
        "description": props.get("EventDescription"),
        "comments": props.get("EventComments"),
        "restrictions": props.get("Restrictions"),
        "detour": props.get("AlternativeRoute"),
        "start": props.get("StartDate"),
        "start_nice": props.get("StartDateNice"),
        "end": props.get("EndDate"),
        "end_nice": props.get("EndDateNice"),
        "expected_resolution": props.get("ExpectedResolution") or props.get("ExpectedResolutionText"),
        "last_edited": props.get("LastEdited"),
        "last_updated_epoch": props.get("lastUpdated"),
        "last_updated_utc": epoch_utc(props.get("lastUpdated")),
        "last_updated_nice": props.get("LastUpdatedNice"),
        "last_updated_ago": props.get("LastUpdatedAgo"),
        "update_due_nice": props.get("UpdateDueNice"),
        "is_planned": boolish(props.get("IsPlanned")),
        "is_pinned": boolish(props.get("IsPinned")),
        "is_critical": boolish(props.get("IsCritical")),
        "island": props.get("EventIsland"),
        "source": props.get("InformationSource") or "NZTA",
        "regions": regions,
        "source_url": source_url_for_event(props, regions),
        "geometry": geometry_summary(feature.get("geometry")),
    }


def normalize_camera(feature: dict[str, Any], by_region_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    props = feature.get("properties") or {}
    region = by_region_id.get(str(props.get("RegionID"))) or by_region_id.get(f"tas:{props.get('TasRegionId')}")
    region_obj = region or {
        "id": props.get("RegionID"),
        "tas_id": props.get("TasRegionId"),
        "name": props.get("RegionID"),
        "slug": None,
        "published_page": False,
    }
    source_url = JOURNEY_BASE + "/traffic-cameras"
    if region_obj.get("slug") and props.get("id"):
        source_url = f"{JOURNEY_BASE}/traffic-cameras/{region_obj['slug']}/{props['id']}"
    return {
        "id": props.get("id"),
        "external_id": props.get("ExternalId"),
        "name": props.get("Name"),
        "description": props.get("Description"),
        "direction": props.get("Direction"),
        "image_url": absolute_url(props.get("ImageUrl"), CAMERA_BASE),
        "thumb_url": absolute_url(props.get("ThumbUrl"), CAMERA_BASE),
        "offline": boolish(props.get("Offline")),
        "under_maintenance": boolish(props.get("UnderMaintenance")),
        "region": region_obj,
        "journey_id": props.get("TasJourneyId"),
        "last_updated_epoch": props.get("lastUpdated"),
        "last_updated_utc": epoch_utc(props.get("lastUpdated")),
        "source": "NZTA Journey Planner / trafficnz.info",
        "source_url": source_url,
        "geometry": geometry_summary(feature.get("geometry")),
    }


def normalize_route(feature: dict[str, Any]) -> dict[str, Any]:
    props = feature.get("properties") or {}
    ways = [{"id": w.get("id"), "name": w.get("name")} for w in as_list(props.get("ways")) if isinstance(w, dict)]
    regions = [{"id": r.get("id"), "name": r.get("name")} for r in as_list(props.get("regions")) if isinstance(r, dict)]
    legs = [
        {"id": leg.get("id"), "name": leg.get("name"), "sort_order": leg.get("sortOrder")}
        for leg in as_list(props.get("legs"))
        if isinstance(leg, dict)
    ]
    return {
        "id": props.get("id"),
        "name": props.get("name"),
        "total_length_km": props.get("totalLength"),
        "current_time": props.get("time"),
        "ways": ways,
        "regions": regions,
        "legs": legs,
        "start": {"lat": props.get("startLatitude"), "lon": props.get("startLongitude")},
        "end": {"lat": props.get("endLatitude"), "lon": props.get("endLongitude")},
        "geometry": geometry_summary(feature.get("geometry")),
    }


def load_events(region_query: str | None = None, event_type: str | None = None) -> dict[str, Any]:
    regions, by_region_id = load_regions()
    region_match = match_region(region_query, regions)
    payload = fetch_json("delays.json")
    wanted_types = EVENT_TYPE_ALIASES.get(event_type or "", set())
    events = []
    for feature in payload.get("features") or []:
        props = feature.get("properties") or {}
        if wanted_types and props.get("type") not in wanted_types:
            continue
        if region_match:
            feature_regions = {str(r) for r in as_list(props.get("regions"))}
            if not feature_regions.intersection(region_match["ids"]):
                continue
        events.append(normalize_event(feature, by_region_id))
    events.sort(key=lambda e: (0 if e.get("is_pinned") else 1, -int(e.get("last_updated_epoch") or 0), natural_key(e.get("location"))))
    return {
        "source": "NZTA / Waka Kotahi Journey Planner",
        "source_url": JOURNEY_BASE + "/highway-conditions/traffic-and-travel-list-view",
        "last_updated_epoch": payload.get("lastUpdated"),
        "last_updated_utc": epoch_utc(payload.get("lastUpdated")),
        "region_filter": region_query,
        "type_filter": event_type,
        "total_matches": len(events),
        "events": events,
    }


def load_cameras(region_query: str | None = None) -> dict[str, Any]:
    regions, by_region_id = load_regions()
    region_match = match_region(region_query, regions)
    payload = fetch_json("cameras.json")
    cameras = []
    for feature in payload.get("features") or []:
        props = feature.get("properties") or {}
        if region_match:
            region_id = str(props.get("RegionID"))
            tas_region_id = str(props.get("TasRegionId"))
            if not (region_id in region_match["ids"] or tas_region_id in region_match["tas_ids"]):
                continue
        cameras.append(normalize_camera(feature, by_region_id))
    cameras.sort(key=lambda c: (c.get("offline"), c.get("under_maintenance"), norm_text(c.get("region", {}).get("name")), natural_key(c.get("name"))))
    return {
        "source": "NZTA / Waka Kotahi Journey Planner",
        "source_url": JOURNEY_BASE + "/traffic-cameras",
        "last_updated_epoch": payload.get("lastUpdated"),
        "last_updated_utc": epoch_utc(payload.get("lastUpdated")),
        "region_filter": region_query,
        "total_matches": len(cameras),
        "cameras": cameras,
    }


def load_routes(region_query: str | None = None) -> dict[str, Any]:
    regions, _ = load_regions()
    region_match = match_region(region_query, regions)
    payload = fetch_json("journeys.json")
    routes = []
    for feature in payload.get("features") or []:
        props = feature.get("properties") or {}
        route_regions = as_list(props.get("regions"))
        if region_match:
            route_ids = {str(r.get("id")) for r in route_regions if isinstance(r, dict)}
            route_names = {norm_text(r.get("name")) for r in route_regions if isinstance(r, dict)}
            if not (route_ids.intersection(region_match["tas_ids"]) or route_names.intersection(region_match["names"])):
                continue
        routes.append(normalize_route(feature))
    routes.sort(key=lambda r: natural_key(r.get("name")))
    return {
        "source": "NZTA / Waka Kotahi Journey Planner",
        "source_url": JOURNEY_BASE + "/highway-conditions",
        "last_updated_epoch": payload.get("lastUpdated"),
        "last_updated_utc": epoch_utc(payload.get("lastUpdated")),
        "region_filter": region_query,
        "total_matches": len(routes),
        "routes": routes,
    }


def limited(data: dict[str, Any], key: str, limit: int | None) -> dict[str, Any]:
    items = data[key]
    if limit is not None:
        items = items[: max(0, limit)]
    return {**data, "returned": len(items), key: items}


def print_events(data: dict[str, Any]) -> None:
    label = "NZTA road events"
    if data.get("region_filter"):
        label += f" for {data['region_filter']}"
    if data.get("type_filter"):
        label += f" ({data['type_filter']})"
    print(f"{label}: {data.get('returned', len(data.get('events', [])))}/{data['total_matches']} shown")
    print(f"Source updated: {data.get('last_updated_utc') or data.get('last_updated_epoch')}")
    if not data.get("events"):
        print("No matching current road events.")
        return
    print()
    for event in data["events"]:
        impact = event.get("impact") or event.get("severity") or "info"
        print(f"{event.get('id')}  [{event.get('category')}] {impact}: {event.get('location')}")
        summary = " - ".join(x for x in [event.get("event_type"), event.get("description")] if x)
        if summary:
            print(f"      {summary}")
        if event.get("comments"):
            print(f"      {trim(event['comments'])}")
        dates = " | ".join(x for x in [event.get("start_nice"), event.get("end_nice")] if x)
        regions = ", ".join(r.get("name") for r in event.get("regions") or [] if r.get("name"))
        footer = " | ".join(x for x in [dates, f"updated {event.get('last_updated_ago')}" if event.get("last_updated_ago") else None, regions] if x)
        if footer:
            print(f"      {footer}")
        detour = event.get("detour")
        if detour and norm_text(detour) not in {"not applicable", "none"}:
            print(f"      Detour: {trim(detour)}")
        print(f"      {event.get('source_url')}")


def print_event_detail(event: dict[str, Any]) -> None:
    print(f"{event.get('id')}  {event.get('name') or event.get('location')}")
    print(f"Type: {event.get('event_type')} ({event.get('category')})")
    print(f"Impact: {event.get('impact') or 'unknown'} | severity: {event.get('severity')}")
    print(f"Status: {event.get('status') or 'unknown'} | planned: {event.get('is_planned')}")
    regions = ", ".join(r.get("name") for r in event.get("regions") or [] if r.get("name"))
    if regions:
        print(f"Regions: {regions}")
    if event.get("start_nice") or event.get("end_nice"):
        print(f"Dates: {event.get('start_nice') or '-'} to {event.get('end_nice') or '-'}")
    if event.get("expected_resolution"):
        print(f"Expected resolution: {event['expected_resolution']}")
    if event.get("description"):
        print(f"\n{event['description']}")
    if event.get("comments"):
        print(f"\n{event['comments']}")
    if event.get("detour") and norm_text(event["detour"]) not in {"not applicable", "none"}:
        print(f"\nDetour: {event['detour']}")
    if event.get("last_updated_nice") or event.get("last_updated_ago"):
        print(f"\nLast updated: {event.get('last_updated_nice') or event.get('last_updated_ago')}")
    print(f"Source: {event.get('source_url')}")


def print_cameras(data: dict[str, Any]) -> None:
    label = "NZTA traffic cameras"
    if data.get("region_filter"):
        label += f" for {data['region_filter']}"
    print(f"{label}: {data.get('returned', len(data.get('cameras', [])))}/{data['total_matches']} shown")
    print(f"Source updated: {data.get('last_updated_utc') or data.get('last_updated_epoch')}")
    if not data.get("cameras"):
        print("No matching traffic cameras.")
        return
    print()
    for cam in data["cameras"]:
        status = "offline" if cam.get("offline") else ("maintenance" if cam.get("under_maintenance") else "online")
        region = (cam.get("region") or {}).get("name") or "-"
        print(f"{cam.get('id')}  {cam.get('name')} ({status})")
        bits = [cam.get("direction"), region, cam.get("description")]
        print("      " + " | ".join(str(x) for x in bits if x))
        if cam.get("image_url"):
            print(f"      Image: {cam['image_url']}")
        print(f"      {cam.get('source_url')}")


def print_routes(data: dict[str, Any]) -> None:
    label = "NZTA highway journeys/routes"
    if data.get("region_filter"):
        label += f" for {data['region_filter']}"
    print(f"{label}: {data.get('returned', len(data.get('routes', [])))}/{data['total_matches']} shown")
    print(f"Source updated: {data.get('last_updated_utc') or data.get('last_updated_epoch')}")
    if not data.get("routes"):
        print("No matching routes.")
        return
    print()
    for route in data["routes"]:
        regions = ", ".join(r.get("name") for r in route.get("regions") or [] if r.get("name"))
        ways = ", ".join(w.get("name") for w in route.get("ways") or [] if w.get("name"))
        length = route.get("total_length_km")
        length_label = f"{float(length):.1f} km" if isinstance(length, (int, float)) else "-"
        print(f"{route.get('id')}  {route.get('name')}  {length_label}")
        print("      " + " | ".join(x for x in [regions, f"ways: {ways}" if ways else None] if x))


def print_regions(data: dict[str, Any]) -> None:
    print(f"NZTA Journey Planner regions: {len(data['regions'])}")
    for region in data["regions"]:
        tas = region.get("tas_id") or "-"
        print(f"{region.get('id'):>3}  tas={tas:<2}  {region.get('name')}  ({region.get('slug')})")


def emit(data: dict[str, Any], as_json: bool, renderer: Any) -> None:
    if as_json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        renderer(data)


def cmd_closures(args: argparse.Namespace) -> None:
    data = limited(load_events(args.region, args.type), "events", args.limit)
    emit(data, args.json, print_events)


def cmd_region(args: argparse.Namespace) -> None:
    data = limited(load_events(args.region, args.type), "events", args.limit)
    emit(data, args.json, print_events)


def cmd_incident(args: argparse.Namespace) -> None:
    data = load_events()
    wanted = str(args.id)
    for event in data["events"]:
        ids = {str(x) for x in [event.get("id"), event.get("external_id"), event.get("internal_id"), event.get("uniq")] if x is not None}
        if wanted in ids:
            emit({"source": data["source"], "source_url": data["source_url"], "event": event}, args.json, lambda d: print_event_detail(d["event"]))
            return
    raise CliError(f"no current NZTA road event found for id: {args.id}")


def cmd_cameras(args: argparse.Namespace) -> None:
    data = limited(load_cameras(args.region), "cameras", args.limit)
    emit(data, args.json, print_cameras)


def cmd_routes(args: argparse.Namespace) -> None:
    data = limited(load_routes(args.region), "routes", args.limit)
    emit(data, args.json, print_routes)


def cmd_regions(args: argparse.Namespace) -> None:
    regions, _ = load_regions()
    data = {"source": "NZTA / Waka Kotahi Journey Planner", "source_url": JOURNEY_BASE + "/regions", "regions": regions}
    emit(data, args.json, print_regions)


def add_event_flags(sp: argparse.ArgumentParser) -> None:
    sp.add_argument("--region", help="Filter by NZTA Journey Planner region name or slug, e.g. Waikato, Wellington")
    sp.add_argument("--type", choices=sorted(EVENT_TYPE_ALIASES), help="Filter events: closure, roadworks, or incident")
    sp.add_argument("--limit", type=int, default=25, help="Maximum rows to return (default 25)")
    sp.add_argument("--json", action="store_true", help="Emit JSON")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Read-only NZTA Journey Planner road closures, incidents, roadworks, routes, and traffic cameras.",
    )
    sub = ap.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("closures", help="list current NZTA road closures, roadworks, incidents, and warnings")
    add_event_flags(sp)
    sp.set_defaults(func=cmd_closures)

    sp = sub.add_parser("incident", help="show detail for one current NZTA road event id")
    sp.add_argument("id", help="Journey Planner event id, external id, internal id, or uniq")
    sp.add_argument("--json", action="store_true", help="Emit JSON")
    sp.set_defaults(func=cmd_incident)

    sp = sub.add_parser("cameras", help="list NZTA traffic cameras")
    sp.add_argument("--region", help="Filter by NZTA Journey Planner region name or slug")
    sp.add_argument("--limit", type=int, default=25, help="Maximum rows to return (default 25)")
    sp.add_argument("--json", action="store_true", help="Emit JSON")
    sp.set_defaults(func=cmd_cameras)

    sp = sub.add_parser("routes", help="list known NZTA highway journeys/routes")
    sp.add_argument("--region", help="Filter by NZTA Journey Planner region name or slug")
    sp.add_argument("--limit", type=int, default=50, help="Maximum rows to return (default 50)")
    sp.add_argument("--json", action="store_true", help="Emit JSON")
    sp.set_defaults(func=cmd_routes)

    sp = sub.add_parser("region", help="list current NZTA road events for one region")
    sp.add_argument("region", help="NZTA Journey Planner region name or slug")
    sp.add_argument("--type", choices=sorted(EVENT_TYPE_ALIASES), help="Filter events: closure, roadworks, or incident")
    sp.add_argument("--limit", type=int, default=25, help="Maximum rows to return (default 25)")
    sp.add_argument("--json", action="store_true", help="Emit JSON")
    sp.set_defaults(func=cmd_region)

    sp = sub.add_parser("regions", help="list NZTA Journey Planner region names and ids")
    sp.add_argument("--json", action="store_true", help="Emit JSON")
    sp.set_defaults(func=cmd_regions)
    return ap


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    started = time.perf_counter()
    try:
        args.func(args)
        return 0
    except CliError as e:
        if getattr(args, "json", False):
            print(json.dumps({"error": str(e), "elapsed_ms": round((time.perf_counter() - started) * 1000)}, indent=2), file=sys.stderr)
        else:
            print(f"nz-road-closures: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
