#!/usr/bin/env python3
"""Check Auckland Council rubbish/recycling/food scraps collection schedules."""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import urllib.parse
import unicodedata
from html.parser import HTMLParser
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "lib"))
import nzfetch  # noqa: E402
from result_contract import utc_now  # noqa: E402

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

def fetch_text(url: str, headers: dict[str, str] | None = None, timeout: int = 10) -> str:
    try:
        return nzfetch.fetch_text(url, headers=headers, timeout=timeout,
                                  allowed_hosts={"www.aucklandcouncil.govt.nz", "experience.aucklandcouncil.govt.nz"})
    except nzfetch.FetchError as exc:
        exc.source_url = url
        raise


def fetch_json(url: str, headers: dict[str, str] | None = None, timeout: int = 10) -> Any:
    try:
        return nzfetch.fetch_json(url, headers=headers, timeout=timeout,
                                  allowed_hosts={"www.aucklandcouncil.govt.nz", "experience.aucklandcouncil.govt.nz"})
    except nzfetch.FetchError as exc:
        exc.source_url = url
        raise


def provenance(url: str) -> dict[str, Any]:
    return {"source_url": url, "publisher": "Auckland Council",
            "retrieved_at": utc_now()}


def current_public_token() -> str:
    html = fetch_text(SEARCH_PAGE)
    match = re.search(r"eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+", html)
    if not match:
        exc = ValueError("Source schema failure: no public API token in the collection-day page")
        exc.source_url = SEARCH_PAGE
        raise exc
    return match.group(0)

def api_headers(token: str) -> dict[str, str]:
    return {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
        "Origin": "https://www.aucklandcouncil.govt.nz",
        "Referer": "https://www.aucklandcouncil.govt.nz/",
    }

def normalised_query(query: str) -> str:
    address = parse_address(query)
    if address is None:
        return query
    prefix = address["unit"] + "/" if address["unit"] else ""
    return (f"{prefix}{address['number']}{address['suffix']} {address['street']} "
            f"{address['type']} {address['suburb']}").strip()


def property_url(query: str, limit: int) -> str:
    return PROPERTY_API + "?" + urllib.parse.urlencode({"query": normalised_query(query).lower(), "pageSize": str(limit)})


def lookup_properties(query: str, limit: int = 10) -> list[dict[str, str]]:
    token = current_public_token()
    url = property_url(query, limit)
    data = fetch_json(url, headers=api_headers(token))
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise ValueError("Source schema failure: property response has no items array")
    items = data["items"]
    if not all(isinstance(item, dict) and isinstance(item.get("id"), str)
               and isinstance(item.get("address"), str) for item in items):
        raise ValueError("Source schema failure: property items need id and address strings")
    return [{**item, **provenance(url)} for item in items]

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
        raise ValueError("Source schema failure: could not parse collection-day page")
    street = lines[idx + 1] if idx + 1 < len(lines) else ""
    suburb = lines[idx + 2] if idx + 2 < len(lines) else ""
    return {
        "property_id": property_id,
        "address": ", ".join([x for x in [street, suburb] if x]),
        "url": url,
        "household": parse_section(lines, "Household collection"),
        "commercial": parse_section(lines, "Commercial collection"),
        "source": "Auckland Council collection-day page",
        **provenance(url),
    }

STREET_TYPES = {
    "rd": "road", "road": "road", "st": "street", "street": "street",
    "ave": "avenue", "av": "avenue", "avenue": "avenue", "dr": "drive", "drive": "drive",
    "pl": "place", "place": "place", "cres": "crescent", "crescent": "crescent",
    "ct": "court", "court": "court", "ln": "lane", "lane": "lane",
    "tce": "terrace", "terrace": "terrace", "pde": "parade", "parade": "parade",
    "way": "way", "cl": "close", "close": "close", "hwy": "highway", "highway": "highway",
    "gr": "grove", "grove": "grove", "rise": "rise", "esplanade": "esplanade",
    "mews": "mews", "walk": "walk", "circuit": "circuit", "square": "square",
}


def normalise_words(value: str) -> str:
    value = "".join(c for c in unicodedata.normalize("NFKD", value.casefold())
                    if not unicodedata.combining(c))
    value = value.replace("’", "").replace("'", "")
    return " ".join(re.sub(r"[^a-z0-9/]+", " ", value).split())


def normalise_name(words: list[str]) -> str:
    words = list(words)
    if words:
        words[0] = {"mt": "mount", "saint": "st"}.get(words[0], words[0])
    return " ".join(words)


def parse_address(value: str) -> dict[str, str] | None:
    """Parse only number[/unit], suffix, street type and optional suburb; never fuzzy match."""
    if re.search(r"\d\s*[-–]\s*\d", value):
        return None  # A number range is not an exact individual property address.
    value = normalise_words(value)
    match = re.fullmatch(r"(?:unit )?(?:(\d+[a-z]?)/)?(\d+)([a-z]?) (.+)", value)
    if not match:
        return None
    unit, number, suffix, tail = match.groups()
    words = tail.split()
    # A suburb's leading St is a name prefix, not the street-type boundary.
    saint_suburbs = {("st", "heliers"), ("st", "johns"), ("st", "marys"), ("st", "lukes")}
    positions = [i for i, word in enumerate(words) if i > 0 and word in STREET_TYPES
                 and tuple(words[i:i + 2]) not in saint_suburbs]
    if not positions:
        return None
    index = positions[-1]
    suburb = words[index + 1:]
    if suburb and re.fullmatch(r"\d{4}", suburb[-1]):
        suburb.pop()
    if suburb and suburb[-1] == "auckland":
        suburb.pop()
    return {"unit": unit or "", "number": str(int(number)), "suffix": suffix,
            "street": normalise_name(words[:index]), "type": STREET_TYPES[words[index]],
            "suburb": normalise_name(suburb)}


def exact_properties(items: list[dict[str, str]], query: str) -> list[dict[str, str]]:
    wanted = parse_address(query)
    if wanted is None:
        return []
    matches = []
    for item in items:
        found = parse_address(item.get("address", ""))
        if found is None:
            continue
        if not all(found[key] == wanted[key] for key in ("number", "suffix", "street", "type")):
            continue
        if wanted["unit"] and found["unit"] != wanted["unit"]:
            continue
        if wanted["suburb"] and found["suburb"] != wanted["suburb"]:
            continue
        matches.append(item)
    return list({item["id"]: item for item in matches}.values())


def choose_property(items: list[dict[str, str]], query: str) -> dict[str, str] | None:
    matches = exact_properties(items, query)
    if len(matches) != 1:
        return None
    wanted, found = parse_address(query), parse_address(matches[0]["address"])
    if not wanted["unit"] and found["unit"]:
        return None
    return matches[0]


MATCH_WEIGHTS = {"number": 25, "suffix": 10, "street": 30, "type": 15,
                 "suburb": 15, "unit": 5}


def rank_properties(items: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    """Score component equality, not fuzzy similarity; 100 requires a full address."""
    wanted = parse_address(query)
    exact_ids = {item["id"] for item in exact_properties(items, query)}
    ranked = []
    for item in {item["id"]: item for item in items}.values():
        found = parse_address(item["address"])
        components = {key: bool(wanted is not None and found is not None
                                and wanted[key] == found[key]
                                and (key != "suburb" or wanted[key]))
                      for key in MATCH_WEIGHTS}
        score = sum(weight for key, weight in MATCH_WEIGHTS.items() if components[key])
        ranked.append({**item, "match_score": score, "match_components": components,
                       "exact_match": item["id"] in exact_ids,
                       "auto_selectable": all(components.values())})
    ranked.sort(key=lambda item: (-item["match_score"], normalise_words(item["address"]), item["id"]))
    return [{**item, "candidate_number": i} for i, item in enumerate(ranked, 1)]


def print_candidates(items: list[dict[str, Any]]) -> None:
    for item in items:
        print(f"{item['candidate_number']}\t{item['match_score']}/100\t{item['id']}\t{item['address']}")


def print_human(result: dict[str, Any], alternatives: list[dict[str, str]]) -> None:
    print(f"{result['address']}")
    matched = result.get("matched_property", {})
    if "candidate_number" in matched:
        print(f"Address match: candidate {matched['candidate_number']}, score {matched['match_score']}/100")
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
        print_candidates(alternatives)

class InvalidInput(ValueError):
    pass


class ContractParser(argparse.ArgumentParser):
    def error(self, message):
        raise InvalidInput(message)


def emit_error(json_mode: bool, code: int, message: str, url: str, retry_after=None) -> int:
    error = {"code": code, "type": {2: "invalid_input", 4: "blocked", 5: "upstream_unavailable",
             6: "schema_failure"}[code], "message": message}
    if retry_after is not None:
        error["retry_after"] = retry_after
    if json_mode:
        print(json.dumps({"meta": provenance(url), "results": [], "error": error}))
    else:
        print(f"bin-schedule: {message}", file=sys.stderr)
    return code


def build_parser() -> argparse.ArgumentParser:
    ap = ContractParser(description=__doc__)
    commands = ap.add_subparsers(dest="command", required=True)
    for name in ("schedule", "lookup"):
        child = commands.add_parser(name)
        child.add_argument("address", nargs="*", help="Exact address, e.g. '12 Tawa Road Onehunga'")
        child.add_argument("--property-id", help="Known Auckland Council property/rating account id")
        child.add_argument("--json", action="store_true", help="Emit JSON with source provenance")
        child.add_argument("--list", action="store_true", help="List candidates only (legacy lookup alias)")
        child.add_argument("--limit", type=int, default=10, help="Search limit, 1–20 (Council cap); a full page requires refinement")
        child.add_argument("--pick", type=int, help="Fetch candidate N from the scored list (1-based); schedule only")
    return ap


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    # Preserve the established address/--list/--property-id invocation.
    if argv and argv[0] not in {"schedule", "lookup", "--help", "-h"}:
        argv.insert(0, "schedule")
    ap = build_parser()
    source_url = SEARCH_PAGE
    try:
        args = ap.parse_args(argv)
        query = " ".join(args.address).strip()
        if not 1 <= args.limit <= 20:
            ap.error("--limit must be between 1 and 20")
        if args.property_id and not re.fullmatch(r"[0-9]+", args.property_id):
            ap.error("--property-id must contain digits only")
        if args.property_id and (query or args.command == "lookup" or args.list):
            ap.error("--property-id is for a schedule without an address or --list")
        if args.pick is not None and (args.pick < 1 or args.pick > args.limit):
            ap.error("--pick must be between 1 and --limit")
        if args.pick is not None and (args.property_id or args.command == "lookup" or args.list):
            ap.error("--pick is for a schedule address query without --property-id or --list")
        if not args.property_id and not query:
            ap.error("provide an address or --property-id")
    except InvalidInput as exc:
        return emit_error("--json" in argv, 2, str(exc), source_url)
    try:
        if args.property_id:
            chosen = {"id": args.property_id, **provenance(DETAIL_URL.format(property_id=args.property_id))}
            matches = []
        else:
            source_url = property_url(query, args.limit)
            items = lookup_properties(query, args.limit)
            matches = rank_properties(items, query)
            exact = exact_properties(matches, query)
            chosen = choose_property(matches, query) if len(items) < args.limit else None
            if chosen and not chosen["auto_selectable"]:
                chosen = None  # Full component equality is required for unattended selection.
            if args.pick is not None:
                if args.pick > len(matches):
                    return emit_error(args.json, 2, f"--pick {args.pick} is outside the {len(matches)} returned candidates", source_url)
                chosen = matches[args.pick - 1]
            if args.command == "lookup" or args.list or chosen is None:
                status = ("search_limit" if len(items) >= args.limit else
                          "ambiguous" if exact and chosen is None else
                          "exact" if chosen else "no_exact_match")
                result = {"query": query, "status": status, "matches": matches,
                          "exact_matches": exact}
                if args.json:
                    print(json.dumps({"meta": provenance(source_url), "results": [result]}, indent=2, ensure_ascii=False))
                else:
                    print(f"Address search: {status}. Refine the address, use --pick N or a confirmed --property-id.")
                    print_candidates(matches)
                return 0
        source_url = DETAIL_URL.format(property_id=chosen["id"])
        result = get_schedule(chosen["id"])
        result["matched_property"] = chosen
        alternatives = [m for m in matches if m.get("id") != chosen.get("id")]
        if args.json:
            status = "picked" if args.pick is not None else "exact"
            print(json.dumps({"meta": provenance(source_url), "results": [{**result, "status": status, "alternatives": alternatives}]}, indent=2, ensure_ascii=False))
        else:
            print_human(result, alternatives)
        return 0
    except nzfetch.RateLimited as exc:
        return emit_error(args.json, 4, str(exc), getattr(exc, "source_url", source_url), exc.retry_after)
    except nzfetch.Blocked as exc:
        return emit_error(args.json, 4, str(exc), getattr(exc, "source_url", source_url))
    except nzfetch.FetchError as exc:
        code = 6 if re.search(r"HTTP (?:400|401|404|405|410|422)\b", str(exc), re.I) else 5
        return emit_error(args.json, code, str(exc), getattr(exc, "source_url", source_url))
    except (ValueError, IndexError) as exc:
        return emit_error(args.json, 6, str(exc), getattr(exc, "source_url", source_url))


if __name__ == "__main__":
    raise SystemExit(main())
