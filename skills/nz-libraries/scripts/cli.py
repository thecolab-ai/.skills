#!/usr/bin/env python3
"""Read-only CLI for selected New Zealand public library networks."""

from __future__ import annotations

import argparse
import html as html_lib
import json
import pathlib
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "lib"))
import nzfetch  # noqa: E402


USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
)

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

NETWORKS = {
    "auckland": {
        "name": "Auckland Libraries",
        "aliases": ["akl", "auckland-libraries"],
        "backend": "Vega / Innovative Interfaces",
        "homepage": "https://www.aucklandlibraries.govt.nz/",
        "catalogue": "https://discover.aucklandlibraries.govt.nz/",
        "catalogue_search": True,
        "branch_hours": True,
        "availability": "Branch-level availability via Vega drawer endpoints for physical tabs",
        "notes": "56-branch Auckland Council Libraries network.",
    },
    "wellington": {
        "name": "Wellington City Libraries",
        "aliases": ["wcl", "wellington-city"],
        "backend": "Spydus",
        "homepage": "https://www.wcl.govt.nz/",
        "catalogue": "https://catalogue.wcl.govt.nz/",
        "catalogue_search": True,
        "branch_hours": True,
        "availability": "Branch/item availability via public Spydus XHLD tables for ids returned by search",
        "notes": "Branch hours and detail pages are served by wcl.govt.nz.",
    },
    "christchurch": {
        "name": "Christchurch City Libraries",
        "aliases": ["chch", "ccc"],
        "backend": "BiblioCommons",
        "homepage": "https://christchurchcitylibraries.com/",
        "catalogue": "https://christchurch.bibliocommons.com/",
        "catalogue_search": True,
        "branch_hours": True,
        "availability": "BiblioCommons bib-level status and copy counts; branch-level item table not exposed by this lightweight parser",
        "notes": "BiblioCommons catalogue plus public locations fragment.",
    },
    "hamilton": {
        "name": "Hamilton City Libraries",
        "aliases": ["hcl"],
        "backend": "SirsiDynix Enterprise / Kotui",
        "homepage": "https://hamiltonlibraries.co.nz/",
        "catalogue": "https://ent.kotui.org.nz/client/en_AU/hamilton/",
        "catalogue_search": True,
        "branch_hours": False,
        "availability": "Sirsi Enterprise detail item fields when available; branch-hours page not wired",
        "profile": "hamilton",
        "notes": "Catalogue uses the Kotui Enterprise tenant.",
    },
    "dunedin": {
        "name": "Dunedin Public Libraries",
        "aliases": ["dpl"],
        "backend": "SirsiDynix Enterprise / Kotui",
        "homepage": "https://www.dunedinlibraries.govt.nz/",
        "catalogue": "https://ent.kotui.org.nz/client/en_AU/dunedin/",
        "catalogue_search": True,
        "branch_hours": False,
        "availability": "Sirsi Enterprise detail item fields when available; branch-hours page not wired",
        "profile": "dunedin",
        "notes": "Catalogue uses the Kotui Enterprise tenant.",
    },
    "tauranga": {
        "name": "Tauranga City Libraries",
        "aliases": ["tga", "tauranga-city"],
        "backend": "SirsiDynix Enterprise / Kotui",
        "homepage": "https://library.tauranga.govt.nz/",
        "catalogue": "https://ent.kotui.org.nz/client/en_AU/tauranga/",
        "catalogue_search": True,
        "branch_hours": False,
        "availability": "Sirsi Enterprise detail item fields when available; branch-hours page not wired",
        "profile": "tauranga",
        "notes": "Catalogue uses the Kotui Enterprise tenant.",
    },
}

ALIASES = {}
for key, cfg in NETWORKS.items():
    ALIASES[key] = key
    for alias in cfg.get("aliases", []):
        ALIASES[alias] = key

AUCKLAND_DISCOVER = "https://discover.aucklandlibraries.govt.nz"
AUCKLAND_API = "https://ap.iiivega.com"
AUCKLAND_SITE = "https://www.aucklandlibraries.govt.nz/en/locations-and-services.html"
_AUCKLAND_CUSTOMER_DOMAIN = None

WCL_BASE = "https://www.wcl.govt.nz"
WCL_LOCATIONS = f"{WCL_BASE}/visit/locations/"
WCL_HOURS = f"{WCL_BASE}/visit/opening-hours/"
WCL_CATALOGUE = "https://catalogue.wcl.govt.nz"

BIBLIO_COMMONS = {
    "christchurch": "christchurch.bibliocommons.com",
}


class SkillError(Exception):
    pass


def die(message: str, code: int = 1) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(code)


def clean_text(value) -> str:
    if value is None:
        return ""
    text = str(value)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = html_lib.unescape(text)
    text = text.replace("\xa0", " ")
    return re.sub(r"[ \t\r\f\v]+", " ", text).strip()


def clean_address(value) -> str:
    text = re.sub(r"(?i)<br\s*/?>", ", ", str(value or ""))
    text = clean_text(text)
    text = re.sub(r"\s*,\s*", ", ", text)
    text = re.sub(r"(,\s*)+", ", ", text)
    return text.strip(" ,")


def compact(value):
    if isinstance(value, str):
        return clean_text(value)
    if isinstance(value, list):
        return [compact(v) for v in value if compact(v)]
    return value


def request_text(url, *, headers=None, data=None, method=None, timeout=35, opener=None) -> str:
    req_headers = {
        "User-Agent": USER_AGENT,
        # HTML-shaped default (no "json" token) so nzfetch treats an ordinary page
        # fetch as HTML, not JSON-expected. JSON callers (Auckland Vega) pass their
        # own "application/json" Accept, which correctly flips the challenge check.
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.5",
        "Accept-Language": "en-NZ,en;q=0.9",
    }
    if headers:
        req_headers.update(headers)
    if isinstance(data, (dict, list)):
        data = json.dumps(data).encode("utf-8")
        req_headers.setdefault("Content-Type", "application/json")
    if opener is not None:
        # A caller-supplied opener (e.g. the Sirsi cookie-jar processor) needs
        # urllib's request path; nzfetch can't take a custom opener.
        req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
        try:
            with opener.open(req, timeout=timeout) as response:
                body = response.read()
                charset = response.headers.get_content_charset() or "utf-8"
                return body.decode(charset, "replace")
        except urllib.error.HTTPError as exc:
            body = exc.read(800).decode("utf-8", "replace")
            raise SkillError(f"{url} returned HTTP {exc.code}: {clean_text(body)[:240]}") from exc
        except urllib.error.URLError as exc:
            raise SkillError(f"{url} failed: {exc.reason}") from exc
    # Route the ordinary path through the shared nzfetch helper. The Accept header
    # drives nzfetch's JSON-vs-HTML challenge check, so hand it over as `accept=`.
    accept = req_headers.pop("Accept")
    try:
        return nzfetch.fetch_text(
            url, headers=req_headers, accept=accept, data=data, method=method, timeout=timeout
        )
    except nzfetch.Blocked as exc:
        raise SkillError(f"{url} failed: network error ({exc})") from exc
    except nzfetch.FetchError as exc:
        raise SkillError(f"{url} failed: {exc}") from exc


def request_json(url, *, headers=None, data=None, method=None, timeout=35, opener=None):
    text = request_text(url, headers=headers, data=data, method=method, timeout=timeout, opener=opener)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise SkillError(f"{url} did not return JSON") from exc


def emit(payload, json_flag: bool, printer) -> None:
    if json_flag:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        printer(payload)


def resolve_network(value: str | None) -> str | None:
    if not value:
        return None
    key = value.strip().lower()
    if key in ALIASES:
        return ALIASES[key]
    die(f"unknown network {value!r}; run networks to list supported networks")


def split_scoped_id(value: str, network: str | None):
    if ":" in value:
        first, rest = value.split(":", 1)
        if first.lower() in ALIASES:
            return resolve_network(first), rest
    if network:
        return resolve_network(network), value
    die("book ids are network-scoped; pass --network or use an id returned by search, e.g. auckland:<id>")


def scoped_id(network: str, raw_id: str) -> str:
    return f"{network}:{raw_id}"


def first(value, default=""):
    if isinstance(value, list):
        return value[0] if value else default
    return value if value is not None else default


def print_networks(payload) -> None:
    for item in payload["networks"]:
        print(f"{item['key']:13} {item['name']} ({item['backend']})")
        print(f"  catalogue: {'yes' if item['catalogue_search'] else 'no'} | branches/hours: {'yes' if item['branch_hours'] else 'no'}")
        print(f"  catalogue URL: {item['catalogue']}")


def cmd_networks(args) -> None:
    payload = {
        "networks": [
            {
                "key": key,
                "name": cfg["name"],
                "backend": cfg["backend"],
                "homepage": cfg["homepage"],
                "catalogue": cfg["catalogue"],
                "catalogue_search": cfg["catalogue_search"],
                "branch_hours": cfg["branch_hours"],
                "availability": cfg["availability"],
                "notes": cfg["notes"],
            }
            for key, cfg in NETWORKS.items()
        ]
    }
    emit(payload, args.json, print_networks)


def auckland_customer_domain() -> str:
    global _AUCKLAND_CUSTOMER_DOMAIN
    if _AUCKLAND_CUSTOMER_DOMAIN:
        return _AUCKLAND_CUSTOMER_DOMAIN
    try:
        code = request_text(f"{AUCKLAND_DISCOVER}/lookup", headers={"Accept": "text/plain,*/*"}).strip()
        if re.match(r"^[a-z0-9-]+$", code):
            _AUCKLAND_CUSTOMER_DOMAIN = f"{code}.ap.iiivega.com"
            return _AUCKLAND_CUSTOMER_DOMAIN
    except SkillError:
        pass
    _AUCKLAND_CUSTOMER_DOMAIN = "elgar.ap.iiivega.com"
    return _AUCKLAND_CUSTOMER_DOMAIN


def auckland_headers(version="2", json_content=False):
    headers = {
        "Accept": "application/json, text/plain, */*",
        "api-version": version,
        "Origin": AUCKLAND_DISCOVER,
        "Referer": f"{AUCKLAND_DISCOVER}/",
        "iii-customer-domain": auckland_customer_domain(),
        "iii-host-domain": "discover.aucklandlibraries.govt.nz",
    }
    if json_content:
        headers["Content-Type"] = "application/json"
    return headers


def normalize_auckland_format_group(fg, network="auckland"):
    tabs = []
    for tab in fg.get("materialTabs") or []:
        availability = tab.get("availability") or {}
        status = availability.get("status") or {}
        tabs.append(
            {
                "name": tab.get("name"),
                "type": tab.get("type"),
                "status": status.get("general") or status.get("electronicLocator"),
                "item_count": tab.get("itemCount"),
                "location_count": tab.get("locationsTotalResults"),
                "record_ids": tab.get("recordIds") or [],
            }
        )
    identifiers = fg.get("identifiers") or {}
    isbn = identifiers.get("isbn") or first((fg.get("identifiedBy") or {}).get("isbn") or [])
    return {
        "network": network,
        "network_name": NETWORKS[network]["name"],
        "id": scoped_id(network, fg.get("id", "")),
        "raw_id": fg.get("id"),
        "title": fg.get("title"),
        "author": (fg.get("primaryAgent") or {}).get("label"),
        "year": fg.get("publicationDate"),
        "format": ", ".join([t["name"] for t in tabs if t.get("name")]),
        "isbn": isbn,
        "availability": "; ".join(
            [
                f"{t['name']}: {t.get('status') or 'unknown'}"
                + (f" ({t['item_count']} items)" if t.get("item_count") is not None else "")
                for t in tabs
                if t.get("name")
            ]
        ),
        "tabs": tabs,
        "url": f"{AUCKLAND_DISCOVER}/search?query={urllib.parse.quote(fg.get('title') or '')}",
        "source": "Vega search API",
    }


def auckland_search(query: str, limit: int):
    payload = {
        "searchText": query,
        "searchType": "everything",
        "pageNum": 0,
        "pageSize": limit,
        "resourceType": "FormatGroup",
    }
    data = request_json(
        f"{AUCKLAND_API}/api/search-result/search/format-groups",
        headers=auckland_headers("2", json_content=True),
        data=payload,
        method="POST",
    )
    return {
        "network": "auckland",
        "total_results": data.get("totalResults"),
        "results": [normalize_auckland_format_group(fg) for fg in data.get("data", [])[:limit]],
    }


def auckland_book(raw_id: str):
    fg = request_json(
        f"{AUCKLAND_API}/api/search-result/search/format-groups/{urllib.parse.quote(raw_id)}",
        headers=auckland_headers("2"),
    )
    item = normalize_auckland_format_group(fg)
    editions = []
    for tab in fg.get("materialTabs") or []:
        for edition in tab.get("editions") or []:
            editions.append(
                {
                    "tab": tab.get("name"),
                    "edition_id": edition.get("id"),
                    "record_id": edition.get("recordId"),
                    "publisher": edition.get("publisher"),
                    "physical_description": edition.get("physicalDescription"),
                    "call_number": edition.get("callNumber"),
                    "availability_status": edition.get("availabilityStatus"),
                }
            )
    item["editions"] = editions
    return item


def auckland_availability(raw_id: str):
    book = auckland_book(raw_id)
    locations = []
    errors = []
    for tab in book.get("tabs", []):
        if tab.get("type") != "physical":
            continue
        tab_name = tab.get("name")
        if not tab_name:
            continue
        url = (
            f"{AUCKLAND_API}/api/search-result/drawer/format-groups/"
            f"{urllib.parse.quote(raw_id)}/locations?tab={urllib.parse.quote(tab_name)}"
        )
        try:
            data = request_json(url, headers=auckland_headers("1"))
        except SkillError as exc:
            errors.append({"tab": tab_name, "error": str(exc)})
            continue
        for status_key in ("available", "unavailable"):
            for loc in data.get(status_key) or []:
                locations.append(
                    {
                        "tab": tab_name,
                        "status": "available" if status_key == "available" else "unavailable",
                        "branch_code": loc.get("code"),
                        "branch": loc.get("label"),
                        "item_location": loc.get("itemLocationLabel"),
                        "item_location_code": loc.get("itemLocationCode"),
                        "call_number": loc.get("callNumber"),
                    }
                )
    return {
        "network": "auckland",
        "id": scoped_id("auckland", raw_id),
        "title": book.get("title"),
        "author": book.get("author"),
        "summary": book.get("availability"),
        "locations": locations,
        "errors": errors,
        "source": "Vega drawer locations endpoint",
    }


def parse_auckland_branches():
    text = request_text(AUCKLAND_SITE)
    matches = list(re.finditer(r"<h3[^>]*>(.*?)</h3>", text, re.I | re.S))
    branches = []
    seen = set()
    for index, match in enumerate(matches):
        name = clean_text(match.group(1))
        if "library" not in name.lower():
            continue
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        block = text[match.end() : end]
        hours = {}
        for item in re.findall(r"<li[^>]*>(.*?)</li>", block, re.I | re.S):
            line = clean_text(item)
            day_match = re.match(r"^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+(.+)$", line, re.I)
            if day_match:
                day = day_match.group(1).capitalize()
                hours[day] = day_match.group(2)
        paragraphs = [clean_address(p) for p in re.findall(r"<p[^>]*>(.*?)</p>", block, re.I | re.S)]
        useful = [p for p in paragraphs if p and "more information" not in p.lower() and p != "\xa0"]
        bad_address = re.compile(r"council services available|go to timetable|read more|visits to .*cancelled|^note:", re.I)
        address_candidates = [
            p
            for p in useful
            if not bad_address.search(p)
            and re.search(r"\d| road\b| rd\b| street\b| st\b| avenue\b| ave\b| drive\b| mall\b| square\b| terrace\b| centre\b| reserve\b| civic\b| cnr\b", p, re.I)
        ]
        address = address_candidates[-1] if address_candidates else next((p for p in reversed(useful) if not bad_address.search(p)), "")
        alternate_name = next((p for p in useful if p != address and not bad_address.search(p) and len(p) < 90), "")
        dedupe_key = (name.lower(), address.lower())
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        link_match = re.search(r'<a[^>]+href="([^"]+)"[^>]*>[^<]*More information', block, re.I | re.S)
        branches.append(
            {
                "network": "auckland",
                "name": name,
                "alternate_name": alternate_name,
                "address": address,
                "hours": hours,
                "url": html_lib.unescape(link_match.group(1)) if link_match else AUCKLAND_SITE,
                "source": AUCKLAND_SITE,
            }
        )
    return branches


def bibliocommons_state(domain: str, path: str):
    url = f"https://{domain}{path}"
    text = request_text(url)
    match = re.search(r'<script type="application/json" data-iso-key="_0">(.*?)</script>', text, re.S)
    if not match:
        raise SkillError(f"{url} did not expose BiblioCommons application JSON")
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise SkillError(f"{url} exposed invalid BiblioCommons JSON") from exc


def bibliocommons_bibs(state):
    bibs = {}
    for container in (state.get("entities") or {}, state.get("bibs") or {}, state.get("catalogBibs") or {}):
        value = container.get("bibs") if isinstance(container, dict) else None
        if isinstance(value, dict):
            bibs.update(value)
    return bibs


def normalize_bibliocommons_bib(network: str, bib_id: str, bib):
    brief = bib.get("briefInfo") or {}
    availability = bib.get("availability") or {}
    authors = brief.get("authors") or []
    if isinstance(authors, list):
        author = ", ".join([clean_text(a) for a in authors if a])
    else:
        author = clean_text(authors)
    status = availability.get("status")
    copies = []
    if availability.get("availableCopies") is not None:
        copies.append(f"{availability.get('availableCopies')} available")
    if availability.get("totalCopies") is not None:
        copies.append(f"{availability.get('totalCopies')} total")
    return {
        "network": network,
        "network_name": NETWORKS[network]["name"],
        "id": scoped_id(network, bib_id),
        "raw_id": bib_id,
        "title": brief.get("title"),
        "subtitle": brief.get("subtitle"),
        "author": author,
        "year": brief.get("publicationDate"),
        "format": brief.get("format"),
        "isbn": first(brief.get("isbns") or []),
        "publisher": brief.get("publisher"),
        "description": clean_text(brief.get("description")),
        "call_number": brief.get("callNumber"),
        "availability": " - ".join([p for p in [status, ", ".join(copies)] if p]),
        "availability_detail": availability,
        "url": f"https://{BIBLIO_COMMONS[network]}/v2/record/{bib_id}",
        "source": "BiblioCommons SSR JSON",
    }


def bibliocommons_search(network: str, query: str, limit: int):
    domain = BIBLIO_COMMONS[network]
    state = bibliocommons_state(domain, f"/v2/search?query={urllib.parse.quote(query)}&searchType=smart")
    results = ((state.get("search") or {}).get("catalogSearch") or {}).get("results") or []
    bibs = bibliocommons_bibs(state)
    items = []
    seen = set()
    for result in results:
        candidate_ids = [result.get("representative")] + (result.get("manifestations") or [])
        for bib_id in candidate_ids:
            if bib_id and bib_id in bibs and bib_id not in seen:
                items.append(normalize_bibliocommons_bib(network, bib_id, bibs[bib_id]))
                seen.add(bib_id)
                break
        if len(items) >= limit:
            break
    return {"network": network, "total_results": len(results), "results": items}


def bibliocommons_book(network: str, raw_id: str):
    domain = BIBLIO_COMMONS[network]
    state = bibliocommons_state(domain, f"/v2/record/{urllib.parse.quote(raw_id)}")
    bibs = bibliocommons_bibs(state)
    bib = bibs.get(raw_id)
    if not bib and bibs:
        bib = next(iter(bibs.values()))
        raw_id = bib.get("id") or raw_id
    if not bib:
        raise SkillError(f"{NETWORKS[network]['name']} did not return bib {raw_id}")
    return normalize_bibliocommons_bib(network, raw_id, bib)


def bibliocommons_availability(network: str, raw_id: str):
    book = bibliocommons_book(network, raw_id)
    availability = book.get("availability_detail") or {}
    return {
        "network": network,
        "id": scoped_id(network, raw_id),
        "title": book.get("title"),
        "author": book.get("author"),
        "status": availability.get("status"),
        "status_type": availability.get("statusType"),
        "available_copies": availability.get("availableCopies"),
        "total_copies": availability.get("totalCopies"),
        "held_copies": availability.get("heldCopies"),
        "on_order_copies": availability.get("onOrderCopies"),
        "single_branch": availability.get("singleBranch"),
        "locations": [],
        "note": "BiblioCommons SSR JSON exposes title-level copy counts here; this lightweight CLI does not fetch the authenticated-style item drawer.",
        "source": "BiblioCommons record SSR JSON",
    }


def parse_christchurch_branches():
    text = request_text("https://christchurch.bibliocommons.com/locations/locations?limit=0&fragment=true")
    chunks = re.split(r'<li class="location-information row"', text)
    branches = []
    for chunk in chunks[1:]:
        block = '<li class="location-information row"' + chunk
        name_match = re.search(r'itemprop="name"[^>]*>(.*?)</a>', block, re.I | re.S)
        if not name_match:
            continue
        href_match = re.search(r'<a[^>]+href="([^"]+)"[^>]*itemprop="name"', block, re.I | re.S)
        address_parts = []
        for prop in ("streetAddress", "addressLocality", "addressRegion", "postalCode"):
            match = re.search(rf'itemprop="{prop}"[^>]*>(.*?)</span>', block, re.I | re.S)
            part = clean_text(match.group(1)) if match else ""
            if part:
                address_parts.append(part)
        hours = {}
        for day, cell in re.findall(
            r'<tr[^>]*>\s*<th[^>]*class="weekday-label"[^>]*>([^<:]+):</th>.*?<td[^>]*class="weekday-hours"[^>]*>(.*?)</td>',
            block,
            re.I | re.S,
        ):
            hours[day.strip().capitalize()] = clean_text(cell)
        facilities = []
        for title in ("Facilities", "Features"):
            match = re.search(rf'<ul[^>]+title="{title}"[^>]*>(.*?)</ul>', block, re.I | re.S)
            if match:
                facilities.extend([clean_text(li) for li in re.findall(r"<li[^>]*>(.*?)</li>", match.group(1), re.I | re.S)])
        phone_match = re.search(r'itemprop="telephone"[^>]*>(.*?)</', block, re.I | re.S)
        email_match = re.search(r'href="mailto:([^"]+)"', block, re.I)
        status_match = re.search(r'<div[^>]+status-indicator[^>]*>(.*?)</div>', block, re.I | re.S)
        branches.append(
            {
                "network": "christchurch",
                "name": clean_text(name_match.group(1)),
                "address": ", ".join(address_parts),
                "hours": hours,
                "status": clean_text(status_match.group(1)) if status_match else "",
                "phone": clean_text(phone_match.group(1)) if phone_match else "",
                "email": email_match.group(1) if email_match else "",
                "facilities": [f for f in facilities if f],
                "url": urllib.parse.urljoin("https://christchurch.bibliocommons.com", html_lib.unescape(href_match.group(1))) if href_match else "",
                "source": "https://christchurch.bibliocommons.com/locations/",
            }
        )
    return branches


def wcl_headers():
    return {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-NZ,en;q=0.9",
    }


def parse_wellington_hours():
    text = request_text(WCL_HOURS, headers=wcl_headers())
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", text, re.I | re.S)
    hours_by_name = {}
    for row in rows:
        cells = [clean_text(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.I | re.S)]
        if len(cells) < 8 or cells[0].lower() == "location":
            continue
        hours_by_name[cells[0]] = dict(zip(DAYS, cells[1:8]))
    return hours_by_name


def parse_wellington_branches():
    text = request_text(WCL_LOCATIONS, headers=wcl_headers())
    hours_by_name = parse_wellington_hours()
    branches = []
    for href, title in re.findall(r'<a class="tile__link" href="([^"]+)".*?<h2 class="tile__title">(.*?)</h2>', text, re.I | re.S):
        name = clean_text(title)
        url = urllib.parse.urljoin(WCL_BASE, html_lib.unescape(href))
        hours = match_wellington_hours(name, hours_by_name)
        branches.append(
            {
                "network": "wellington",
                "name": name,
                "address": "",
                "hours": hours,
                "url": url,
                "source": WCL_LOCATIONS,
            }
        )
    return [enrich_wellington_branch(branch) for branch in branches]


def wcl_name_key(name: str) -> str:
    key = name.lower()
    key = re.sub(r"\blibrary\b|\bcentral\b", "", key)
    key = re.sub(r"[^a-z0-9]+", " ", key)
    return key.strip()


def wcl_name_keys(name: str):
    keys = [wcl_name_key(name)]
    keys.extend(wcl_name_key(part) for part in name.split("|"))
    return [key for key in keys if key]


def match_wellington_hours(name, hours_by_name):
    keys = wcl_name_keys(name)
    for hours_name, hours in hours_by_name.items():
        hour_keys = wcl_name_keys(hours_name)
        for key in keys:
            for hkey in hour_keys:
                if key == hkey or key in hkey or hkey in key:
                    return hours
    return {}


def enrich_wellington_branch(branch):
    try:
        text = request_text(branch["url"], headers=wcl_headers())
    except SkillError:
        return branch
    addr_match = re.search(
        r'<span class="bilingual-h2__text--en">\s*Address\s*</span>.*?<div class="rich-text"[^>]*>(.*?)</div>',
        text,
        re.I | re.S,
    )
    if addr_match:
        paragraphs = [p for p in re.findall(r"<p[^>]*>(.*?)</p>", addr_match.group(1), re.I | re.S)]
        addr = next((clean_address(p) for p in paragraphs if "google maps" not in clean_text(p).lower()), "")
        branch["address"] = addr
    phone_match = re.search(r'href=tel:([^>\s]+)>\s*Phone\s*([^<]+)', text, re.I)
    email_match = re.search(r'href=mailto:([^>\s]+)>\s*Email\s*([^<]+)', text, re.I)
    if phone_match:
        branch["phone"] = clean_text(phone_match.group(2))
    if email_match:
        branch["email"] = clean_text(email_match.group(2))
    return branch


def wellington_search(query: str, limit: int):
    params = urllib.parse.urlencode(
        {
            "ENTRY": query,
            "ENTRY_NAME": "BS",
            "ENTRY_TYPE": "K",
            "SORTS": "SQL_REL_BIB",
            "GQ": query,
            "NRECS": str(max(limit, 10)),
        }
    )
    url = f"{WCL_CATALOGUE}/cgi-bin/spydus.exe/ENQ/OPAC/BIBENQ?{params}"
    text = request_text(url, headers=wcl_headers())
    blocks = re.findall(r'(<fieldset class="card card-list".*?</fieldset>)', text, re.I | re.S)
    results = []
    for block in blocks:
        link = re.search(r'href="([^"]*/FULL/OPAC/BIBENQ/(\d+)/(\d+),(\d+)[^"]*)"', block, re.I)
        if not link:
            continue
        set_id, record_id = link.group(2), link.group(3)
        title_match = re.search(r'<h3[^>]*>.*?<a[^>]*>.*?<span[^>]*>(.*?)</span>', block, re.I | re.S)
        title = clean_text(title_match.group(1)) if title_match else ""
        summary_match = re.search(r'<div class="card-text summary"[^>]*>(.*?)</div>', block, re.I | re.S)
        recdetails_match = re.search(r'<div class="card-text recdetails"[^>]*>(.*?)</div>', block, re.I | re.S)
        detail_lines = []
        if recdetails_match:
            detail_lines = [
                re.sub(r"\s+([,.;:])", r"\1", clean_text(line))
                for line in re.split(r'<span class="d-block"[^>]*>', recdetails_match.group(1), flags=re.I)[1:]
            ]
        author = detail_lines[0] if detail_lines else ""
        year = next((line for line in reversed(detail_lines) if re.fullmatch(r"(?:19|20)\d{2}", line)), "")
        format_match = re.search(r'class="[^"]*recfrmt-icon[^"]*"[^>]+title="([^"]+)"', block, re.I)
        results.append(
            {
                "network": "wellington",
                "network_name": NETWORKS["wellington"]["name"],
                "id": scoped_id("wellington", f"{set_id}:{record_id}"),
                "raw_id": f"{set_id}:{record_id}",
                "title": title,
                "author": author,
                "year": year,
                "format": clean_text(format_match.group(1)) if format_match else "",
                "isbn": "",
                "availability": "Use availability with this search-scoped id",
                "summary": clean_text(summary_match.group(1)) if summary_match else "",
                "url": urllib.parse.urljoin(WCL_CATALOGUE, html_lib.unescape(link.group(1))),
                "source": "Spydus BIBENQ HTML",
            }
        )
        if len(results) >= limit:
            break
    return {"network": "wellington", "total_results": len(results), "results": results}


def parse_spydus_id(raw_id: str):
    parts = raw_id.split(":")
    if len(parts) != 2 or not all(p.isdigit() for p in parts):
        raise SkillError("Wellington ids are search-scoped as <set-id>:<record-id>; use an id returned by search")
    return parts[0], parts[1]


def wellington_book(raw_id: str):
    set_id, record_id = parse_spydus_id(raw_id)
    url = f"{WCL_CATALOGUE}/cgi-bin/spydus.exe/FULL/OPAC/BIBENQ/{set_id}/{record_id},1"
    text = request_text(url, headers=wcl_headers())
    data = {}
    for script in re.findall(r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>', text, re.I | re.S):
        try:
            parsed = json.loads(script.strip())
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict) and (parsed.get("@type") or "").lower() in {"book", "creativework"}:
            data = parsed
            break
    title = clean_text(data.get("name") or data.get("title") or "")
    if not title:
        title_match = re.search(r"<title>(.*?)</title>", text, re.I | re.S)
        title = clean_text(title_match.group(1)) if title_match else ""
    author = data.get("author")
    if isinstance(author, dict):
        author = author.get("name")
    elif isinstance(author, list):
        author = ", ".join([a.get("name") if isinstance(a, dict) else str(a) for a in author])
    return {
        "network": "wellington",
        "network_name": NETWORKS["wellington"]["name"],
        "id": scoped_id("wellington", raw_id),
        "raw_id": raw_id,
        "title": title,
        "author": clean_text(author),
        "year": clean_text(data.get("datePublished")),
        "publisher": clean_text(data.get("publisher")),
        "isbn": data.get("isbn"),
        "description": clean_text(data.get("description")),
        "url": url,
        "source": "Spydus FULL HTML / JSON-LD",
    }


def wellington_availability(raw_id: str):
    set_id, record_id = parse_spydus_id(raw_id)
    url = f"{WCL_CATALOGUE}/cgi-bin/spydus.exe/XHLD/OPAC/BIBENQ/{set_id}/{record_id}?RECDISP=REC"
    text = request_text(url, headers=wcl_headers())
    rows = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", text, re.I | re.S):
        cells = [clean_text(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.I | re.S)]
        if len(cells) >= 4:
            rows.append(
                {
                    "branch": cells[0],
                    "collection": cells[1],
                    "call_number": cells[2],
                    "status": cells[3],
                }
            )
    book = wellington_book(raw_id)
    return {
        "network": "wellington",
        "id": scoped_id("wellington", raw_id),
        "title": book.get("title"),
        "author": book.get("author"),
        "locations": rows,
        "source": "Spydus XHLD availability table",
    }


def sirsi_profile(network: str) -> str:
    return NETWORKS[network]["profile"]


def sirsi_raw_from_ent(value: str) -> str:
    value = html_lib.unescape(value)
    if value.startswith("ent://"):
        value = value[len("ent://") :]
    if "/0/" in value:
        return value.split("/0/", 1)[1]
    return value.rsplit("/", 1)[-1]


def sirsi_ent_path(raw_id: str) -> str:
    source = raw_id.split(":", 1)[0]
    return f"ent:$002f$002f{source}$002f0$002f{raw_id}"


def sirsi_url(network: str, path: str) -> str:
    return f"https://ent.kotui.org.nz/client/en_AU/{sirsi_profile(network)}{path}"


def sirsi_field(block: str, field: str) -> str:
    index = block.find(field)
    if index < 0:
        return ""
    segment = block[index : index + 1600]
    match = re.search(r'<div class="displayElementText[^"]*"[^>]*>(.*?)</div>', segment, re.I | re.S)
    return clean_text(match.group(1)) if match else ""


def sirsi_search(network: str, query: str, limit: int):
    url = sirsi_url(network, f"/search/results?qu={urllib.parse.quote(query)}")
    text = request_text(url)
    pattern = re.compile(
        r'<div id="results_cell(\d+)" class="results_cell">(.*?)(?=<div id="results_cell\d+" class="results_cell">|<div id="results_wrapper_bottom"|$)',
        re.I | re.S,
    )
    results = []
    for _, block in pattern.findall(text):
        ent_match = re.search(r'value="(ent://[^"]+)"', block, re.I)
        if not ent_match:
            continue
        raw_id = sirsi_raw_from_ent(ent_match.group(1))
        title_match = re.search(r'id="detailLink\d+"[^>]*title="([^"]+)"', block, re.I | re.S)
        title = clean_text(title_match.group(1)) if title_match else ""
        if not title:
            title_match = re.search(r'id="detailLink\d+"[^>]*>(.*?)</a>', block, re.I | re.S)
            title = clean_text(title_match.group(1)) if title_match else ""
        fmt_match = re.search(r'class="formatText"[^>]*>(.*?)</span>', block, re.I | re.S)
        isbn_match = re.search(r'class="isbnValue"[^>]+value="([^"]+)"', block, re.I)
        results.append(
            {
                "network": network,
                "network_name": NETWORKS[network]["name"],
                "id": scoped_id(network, raw_id),
                "raw_id": raw_id,
                "title": title,
                "author": sirsi_field(block, "INITIAL_AUTHOR_SRCH") or sirsi_field(block, "AUTHOR"),
                "year": sirsi_field(block, "PUBDATE_RANGE"),
                "format": clean_text(fmt_match.group(1)) if fmt_match else "",
                "isbn": isbn_match.group(1) if isbn_match else "",
                "availability": "Use availability for detail item fields",
                "summary": sirsi_field(block, "BIBSUMMARY"),
                "url": sirsi_url(network, f"/search/detailnonmodal/{sirsi_ent_path(raw_id)}/one"),
                "source": "SirsiDynix Enterprise search HTML",
            }
        )
        if len(results) >= limit:
            break
    return {"network": network, "total_results": len(results), "results": results}


def sirsi_detail_page(network: str, raw_id: str):
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
    url = sirsi_url(network, f"/search/detailnonmodal/{sirsi_ent_path(raw_id)}/one")
    return url, request_text(url, opener=opener), opener


def sirsi_detail_field(text: str, field: str) -> str:
    match = re.search(rf'<div id="detail\d+_{re.escape(field)}".*?<div class="{re.escape(field)}_value">(.*?)</div>', text, re.I | re.S)
    return clean_text(match.group(1)) if match else ""


def sirsi_book(network: str, raw_id: str):
    url, text, _ = sirsi_detail_page(network, raw_id)
    title = sirsi_detail_field(text, "TITLE")
    if not title:
        title_match = re.search(r"<title>(.*?)</title>", text, re.I | re.S)
        title = clean_text(title_match.group(1)) if title_match else ""
    items = sirsi_items_from_detail(text)
    return {
        "network": network,
        "network_name": NETWORKS[network]["name"],
        "id": scoped_id(network, raw_id),
        "raw_id": raw_id,
        "title": title,
        "author": sirsi_detail_field(text, "AUTHOR") or sirsi_detail_field(text, "INITIAL_AUTHOR_SRCH"),
        "year": sirsi_detail_field(text, "PUBDATE_RANGE"),
        "publisher": sirsi_detail_field(text, "PUBINFO"),
        "format": sirsi_detail_field(text, "FORMAT"),
        "isbn": sirsi_detail_field(text, "ISBN"),
        "items": items,
        "url": url,
        "source": "SirsiDynix Enterprise detail HTML",
    }


def sirsi_items_from_detail(text: str):
    rows = {}
    for idx, field, value in re.findall(
        r'id="detail\d+_child(\d+)_([A-Z_]+)".*?<div class="\2_value">(.*?)</div>',
        text,
        re.I | re.S,
    ):
        row = rows.setdefault(idx, {})
        row[field.lower()] = clean_text(value)
    return list(rows.values())


def sirsi_availability(network: str, raw_id: str):
    book = sirsi_book(network, raw_id)
    locations = []
    for item in book.get("items") or []:
        locations.append(
            {
                "branch_or_collection": item.get("location"),
                "call_number": item.get("callnum") or item.get("call_number"),
                "barcode": item.get("barcode"),
                "item_type": item.get("itype"),
                "raw": item,
            }
        )
    return {
        "network": network,
        "id": scoped_id(network, raw_id),
        "title": book.get("title"),
        "author": book.get("author"),
        "locations": locations,
        "note": "Kotui/Sirsi exposes item fields in the public detail page; exact branch/status availability can vary by tenant and record.",
        "source": "SirsiDynix Enterprise detail HTML",
    }


def search_network(network: str, query: str, limit: int):
    if network == "auckland":
        return auckland_search(query, limit)
    if network == "wellington":
        return wellington_search(query, limit)
    if network in BIBLIO_COMMONS:
        return bibliocommons_search(network, query, limit)
    if NETWORKS[network]["backend"].startswith("SirsiDynix"):
        return sirsi_search(network, query, limit)
    raise SkillError(f"catalogue search is not wired for {NETWORKS[network]['name']}")


def get_book(network: str, raw_id: str):
    if network == "auckland":
        return auckland_book(raw_id)
    if network == "wellington":
        return wellington_book(raw_id)
    if network in BIBLIO_COMMONS:
        return bibliocommons_book(network, raw_id)
    if NETWORKS[network]["backend"].startswith("SirsiDynix"):
        return sirsi_book(network, raw_id)
    raise SkillError(f"book detail is not wired for {NETWORKS[network]['name']}")


def get_availability(network: str, raw_id: str):
    if network == "auckland":
        return auckland_availability(raw_id)
    if network == "wellington":
        return wellington_availability(raw_id)
    if network in BIBLIO_COMMONS:
        return bibliocommons_availability(network, raw_id)
    if NETWORKS[network]["backend"].startswith("SirsiDynix"):
        return sirsi_availability(network, raw_id)
    raise SkillError(f"availability is not wired for {NETWORKS[network]['name']}")


def all_branches_for(network: str):
    if network == "auckland":
        return parse_auckland_branches()
    if network == "wellington":
        return parse_wellington_branches()
    if network == "christchurch":
        return parse_christchurch_branches()
    raise SkillError(f"branch locations/hours are not wired for {NETWORKS[network]['name']}")


def unsupported_branch_payload(network: str):
    return {
        "network": network,
        "network_name": NETWORKS[network]["name"],
        "supported": False,
        "branches": [],
        "message": f"Branch locations/hours are not wired for {NETWORKS[network]['name']}; catalogue search is supported.",
    }


def print_search(payload):
    for result in payload["results"]:
        print(f"{result['id']}  {result.get('title') or '(untitled)'}")
        detail = " | ".join(
            [p for p in [result.get("network_name"), result.get("author"), result.get("year"), result.get("format")] if p]
        )
        if detail:
            print(f"  {detail}")
        if result.get("availability"):
            print(f"  {result['availability']}")


def cmd_search(args):
    network = resolve_network(args.network)
    errors = []
    results = []
    networks = [network] if network else [key for key, cfg in NETWORKS.items() if cfg["catalogue_search"]]
    for key in networks:
        try:
            data = search_network(key, args.query, args.limit)
            results.extend(data["results"])
        except SkillError as exc:
            errors.append({"network": key, "error": str(exc)})
    payload = {"query": args.query, "network": network, "count": len(results), "results": results, "errors": errors}
    if not results and errors and network:
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            raise SystemExit(1)
        die(errors[0]["error"])
    emit(payload, args.json, print_search)


def print_book(payload):
    print(f"{payload['id']}  {payload.get('title') or '(untitled)'}")
    for label, key in [
        ("Network", "network_name"),
        ("Author", "author"),
        ("Year", "year"),
        ("Format", "format"),
        ("Publisher", "publisher"),
        ("ISBN", "isbn"),
        ("URL", "url"),
    ]:
        if payload.get(key):
            print(f"{label}: {payload[key]}")
    if payload.get("description"):
        print(f"Description: {payload['description'][:500]}")


def cmd_book(args):
    network, raw_id = split_scoped_id(args.book_id, args.network)
    try:
        payload = get_book(network, raw_id)
    except SkillError as exc:
        if args.json:
            print(json.dumps({"error": str(exc), "network": network, "id": raw_id}, ensure_ascii=False, indent=2))
            raise SystemExit(1)
        die(str(exc))
    emit(payload, args.json, print_book)


def print_availability(payload):
    print(f"{payload['id']}  {payload.get('title') or '(untitled)'}")
    if payload.get("summary"):
        print(payload["summary"])
    if payload.get("status"):
        print(f"Status: {payload['status']}")
    for loc in payload.get("locations") or []:
        name = loc.get("branch") or loc.get("branch_or_collection") or loc.get("collection") or loc.get("item_location") or "(unknown)"
        status = loc.get("status") or loc.get("item_type") or ""
        call = loc.get("call_number") or ""
        suffix = " | ".join([p for p in [status, call] if p])
        print(f"- {name}" + (f" ({suffix})" if suffix else ""))
    if payload.get("note"):
        print(f"Note: {payload['note']}")


def cmd_availability(args):
    network, raw_id = split_scoped_id(args.book_id, args.network)
    try:
        payload = get_availability(network, raw_id)
    except SkillError as exc:
        if args.json:
            print(json.dumps({"error": str(exc), "network": network, "id": raw_id}, ensure_ascii=False, indent=2))
            raise SystemExit(1)
        die(str(exc))
    emit(payload, args.json, print_availability)


def print_branches(payload):
    if not payload.get("supported", True):
        print(payload["message"])
        return
    for branch in payload["branches"]:
        print(f"{branch['network']:13} {branch.get('name')}")
        if branch.get("address"):
            print(f"  {branch['address']}")
        if branch.get("status"):
            print(f"  {branch['status']}")
        if branch.get("hours"):
            hours = "; ".join([f"{day[:3]} {branch['hours'].get(day)}" for day in DAYS if branch["hours"].get(day)])
            print(f"  {hours}")


def cmd_branches(args):
    network = resolve_network(args.network)
    if network and not NETWORKS[network]["branch_hours"]:
        emit(unsupported_branch_payload(network), args.json, print_branches)
        return
    networks = [network] if network else [key for key, cfg in NETWORKS.items() if cfg["branch_hours"]]
    branches = []
    errors = []
    for key in networks:
        try:
            branches.extend(all_branches_for(key))
        except SkillError as exc:
            errors.append({"network": key, "error": str(exc)})
    payload = {"supported": True, "network": network, "count": len(branches), "branches": branches, "errors": errors}
    emit(payload, args.json, print_branches)


def branch_score(name: str, query: str) -> int:
    n = name.lower()
    q = query.lower()
    if n == q:
        return 100
    if q in n:
        return 80
    words = [w for w in re.split(r"\W+", q) if w]
    return sum(10 for w in words if w in n)


def print_branch(payload):
    if not payload.get("supported", True):
        print(payload["message"])
        return
    branch = payload["branch"]
    print(f"{branch.get('name')} ({NETWORKS[branch['network']]['name']})")
    for key, label in [("alternate_name", "Also"), ("address", "Address"), ("phone", "Phone"), ("email", "Email"), ("status", "Status"), ("url", "URL")]:
        if branch.get(key):
            print(f"{label}: {branch[key]}")
    if branch.get("hours"):
        print("Hours:")
        for day in DAYS:
            if branch["hours"].get(day):
                print(f"  {day}: {branch['hours'][day]}")
    if branch.get("facilities"):
        print("Facilities: " + ", ".join(branch["facilities"]))


def cmd_branch(args):
    network = resolve_network(args.network)
    if network and not NETWORKS[network]["branch_hours"]:
        emit(unsupported_branch_payload(network), args.json, print_branch)
        return
    networks = [network] if network else [key for key, cfg in NETWORKS.items() if cfg["branch_hours"]]
    candidates = []
    for key in networks:
        try:
            candidates.extend(all_branches_for(key))
        except SkillError:
            continue
    scored = sorted(((branch_score(b.get("name", ""), args.name), b) for b in candidates), key=lambda item: item[0], reverse=True)
    if not scored or scored[0][0] <= 0:
        if args.json:
            print(json.dumps({"error": f"no branch matched {args.name!r}", "query": args.name}, ensure_ascii=False, indent=2))
            raise SystemExit(1)
        die(f"no branch matched {args.name!r}")
    branch = scored[0][1]
    if branch["network"] == "wellington":
        branch = enrich_wellington_branch(branch)
    emit({"supported": True, "query": args.name, "branch": branch}, args.json, print_branch)


def print_hours(payload):
    print_branches(payload)


def cmd_hours(args):
    cmd_branches(args)


def build_parser():
    parser = argparse.ArgumentParser(description="Read-only NZ public libraries catalogue and branch CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("networks", help="list supported library networks")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_networks)

    p = sub.add_parser("search", help="search catalogues")
    p.add_argument("query")
    p.add_argument("--network", help="network key or alias")
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("book", help="fetch book/bib detail")
    p.add_argument("book_id")
    p.add_argument("--network", help="network key or alias")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_book)

    p = sub.add_parser("availability", help="fetch availability for a book id")
    p.add_argument("book_id")
    p.add_argument("--network", help="network key or alias")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_availability)

    p = sub.add_parser("branches", help="list branch locations and hours")
    p.add_argument("--network", help="network key or alias")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_branches)

    p = sub.add_parser("branch", help="fetch one branch by name")
    p.add_argument("name")
    p.add_argument("--network", help="network key or alias")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_branch)

    p = sub.add_parser("hours", help="list opening hours")
    p.add_argument("--network", help="network key or alias")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_hours)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if hasattr(args, "limit") and args.limit < 1:
        die("--limit must be at least 1")
    if hasattr(args, "limit") and args.limit > 50:
        die("--limit must be 50 or less")
    try:
        args.func(args)
    except SkillError as exc:
        die(str(exc))


if __name__ == "__main__":
    main()
