#!/usr/bin/env python3
"""Check Auckland Council rubbish/recycling/food scraps collection schedules."""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from typing import Any

SEARCH_PAGE = "https://www.aucklandcouncil.govt.nz/en/rubbish-recycling/rubbish-recycling-collections/rubbish-recycling-collection-days.html"
PROPERTY_API = "https://experience.aucklandcouncil.govt.nz/nextapi/property"
DETAIL_URL = "https://www.aucklandcouncil.govt.nz/en/rubbish-recycling/rubbish-recycling-collections/rubbish-recycling-collection-days/{property_id}.html"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"

class VisibleText(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self.skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self.skip_depth:
            self.skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self.skip_depth:
            return
        text = data.strip("\ufeff \n\r\t")
        if text:
            self.parts.append(text)

def fetch_text(url: str, headers: dict[str, str] | None = None, timeout: int = 30) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")

def fetch_json(url: str, headers: dict[str, str] | None = None, timeout: int = 30) -> Any:
    return json.loads(fetch_text(url, headers=headers, timeout=timeout))

def current_public_token() -> str:
    html = fetch_text(SEARCH_PAGE)
    match = re.search(r"eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+", html)
    if not match:
        raise RuntimeError("Could not find Auckland Council public API bearer token in the collection-day page")
    return match.group(0)

def api_headers(token: str) -> dict[str, str]:
    return {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
        "Origin": "https://www.aucklandcouncil.govt.nz",
        "Referer": "https://www.aucklandcouncil.govt.nz/",
    }

def lookup_properties(query: str, limit: int = 10) -> list[dict[str, str]]:
    token = current_public_token()
    url = PROPERTY_API + "?" + urllib.parse.urlencode({"query": query.lower(), "pageSize": str(limit)})
    data = fetch_json(url, headers=api_headers(token))
    return data.get("items", [])

def visible_lines(html: str) -> list[str]:
    parser = VisibleText()
    parser.feed(html)
    # Collapse runs of repeated nav labels lightly, but preserve order.
    return [p.strip() for p in parser.parts if p.strip()]

def first_after(lines: list[str], label: str, start: int, stop: int) -> str | None:
    labels = {"Rubbish:", "Food scraps:", "Recycling:", "How often do I put my bins out:"}
    for i in range(start, stop):
        if lines[i] == label:
            for j in range(i + 1, stop):
                if lines[j] in labels:
                    return None
                if lines[j].strip():
                    return lines[j]
    return None

def parse_frequency(lines: list[str], service: str, start: int, stop: int) -> str | None:
    for i in range(start, stop):
        if lines[i] == service:
            window = lines[i + 1 : min(stop, i + 8)]
            if "Collection day:" in window:
                k = i + 1 + window.index("Collection day:")
                bits: list[str] = []
                for x in lines[k + 1 : min(stop, k + 7)]:
                    if x in {"Rubbish", "Food scraps", "Recycling", "Where you can put your rubbish, food scraps and recycling for collection"}:
                        break
                    if x == ".":
                        break
                    bits.append(x)
                return " ".join(bits).replace("  ", " ") or None
            # Sometimes service has a prose no-service/private-service message instead.
            msg = []
            for x in window[:4]:
                if x in {"Rubbish", "Food scraps", "Recycling", "Where you can put your rubbish, food scraps and recycling for collection"}:
                    break
                msg.append(x)
            return " ".join(msg) or None
    return None

def section_bounds(lines: list[str], name: str) -> tuple[int, int] | None:
    try:
        start = lines.index(name)
    except ValueError:
        return None
    stops = [len(lines)]
    for marker in ["Commercial collection", "Household rubbish", "Where you can put your rubbish, food scraps and recycling for collection"]:
        try:
            idx = lines.index(marker, start + 1)
            stops.append(idx)
        except ValueError:
            pass
    return start, min(stops)

def parse_section(lines: list[str], name: str) -> dict[str, Any] | None:
    bounds = section_bounds(lines, name)
    if not bounds:
        return None
    start, stop = bounds
    services = ["Rubbish", "Food scraps", "Recycling"] if name.startswith("Household") else ["Rubbish", "Recycling"]
    next_dates = {svc.lower().replace(" ", "_"): first_after(lines, f"{svc}:", start, stop) for svc in services}
    frequencies = {svc.lower().replace(" ", "_"): parse_frequency(lines, svc, start, stop) for svc in services}
    put_out = None
    for i in range(start, stop):
        if lines[i].startswith("Put bins out"):
            put_out = lines[i]
            break
    return {"next_dates": next_dates, "frequency": frequencies, "put_out": put_out}

def get_schedule(property_id: str) -> dict[str, Any]:
    url = DETAIL_URL.format(property_id=property_id)
    html = fetch_text(url)
    lines = visible_lines(html)
    try:
        household_idx = lines.index("Household collection")
        candidates = [i for i, line in enumerate(lines[:household_idx]) if line == "Your collection day"]
        idx = candidates[-1]
    except (ValueError, IndexError):
        raise RuntimeError("Could not parse collection-day page; page shape changed")
    street = lines[idx + 1] if idx + 1 < len(lines) else ""
    suburb = lines[idx + 2] if idx + 2 < len(lines) else ""
    return {
        "property_id": property_id,
        "address": ", ".join([x for x in [street, suburb] if x]),
        "url": url,
        "household": parse_section(lines, "Household collection"),
        "commercial": parse_section(lines, "Commercial collection"),
        "source": "Auckland Council collection-day page",
    }

def choose_property(items: list[dict[str, str]], query: str) -> dict[str, str]:
    if not items:
        raise RuntimeError(f"No Auckland Council property matches found for: {query}")
    normalized = re.sub(r"\W+", " ", query.lower()).strip()
    for item in items:
        addr = re.sub(r"\W+", " ", item.get("address", "").lower()).strip()
        if normalized and normalized in addr:
            return item
    return items[0]

def print_human(result: dict[str, Any], alternatives: list[dict[str, str]]) -> None:
    print(f"{result['address']}")
    print(f"Source: {result['url']}")
    for section_name in ["household", "commercial"]:
        sec = result.get(section_name)
        if not sec:
            continue
        print(f"\n{section_name.title()} collection")
        if sec.get("put_out"):
            print(f"  Put out: {sec['put_out']}")
        print("  Next dates:")
        for svc, date in sec.get("next_dates", {}).items():
            print(f"    {svc.replace('_', ' ').title()}: {date or '—'}")
        print("  Frequency:")
        for svc, freq in sec.get("frequency", {}).items():
            print(f"    {svc.replace('_', ' ').title()}: {freq or '—'}")
    if alternatives:
        print("\nOther address matches:")
        for item in alternatives[:5]:
            print(f"  {item['id']}: {item['address']}")

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Check Auckland Council rubbish, recycling and food scraps collection schedules.")
    ap.add_argument("address", nargs="*", help="Auckland property address to search, e.g. '12 Tawa Road Onehunga'")
    ap.add_argument("--property-id", help="Auckland Council property/rating account id, if already known")
    ap.add_argument("--json", action="store_true", help="Emit JSON")
    ap.add_argument("--list", action="store_true", help="List matching properties only")
    ap.add_argument("--limit", type=int, default=10, help="Address lookup result limit")
    args = ap.parse_args(argv)

    try:
        query = " ".join(args.address).strip()
        if args.property_id:
            chosen = {"id": args.property_id, "address": args.property_id}
            matches: list[dict[str, str]] = []
        else:
            if not query:
                ap.error("provide an address or --property-id")
            matches = lookup_properties(query, args.limit)
            if args.list:
                print(json.dumps({"query": query, "matches": matches}, indent=2) if args.json else "\n".join(f"{m['id']}\t{m['address']}" for m in matches))
                return 0
            chosen = choose_property(matches, query)
        result = get_schedule(chosen["id"])
        result["matched_property"] = chosen
        alternatives = [m for m in matches if m.get("id") != chosen.get("id")]
        if args.json:
            print(json.dumps({**result, "alternatives": alternatives}, indent=2, ensure_ascii=False))
        else:
            print_human(result, alternatives)
        return 0
    except Exception as e:
        if args.json:
            print(json.dumps({"error": str(e)}, indent=2), file=sys.stderr)
        else:
            print(f"bin-schedule: {e}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
