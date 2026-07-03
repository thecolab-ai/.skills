#!/usr/bin/env python3
"""Read-only CLI for MBIE / Tenancy Services rental-bond and market-rent data."""
from __future__ import annotations

import argparse
import csv
import html
import io
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any

SOURCE_NAME = "MBIE / Tenancy Services"
UA = "rental-bond-nz-skill/1.0 (+https://github.com/thecolab-ai/.skills)"
DEFAULT_TIMEOUT = 30
MAX_TIMEOUT = 120

TENANCY_DATA_PAGE = "https://www.tenancy.govt.nz/about-tenancy-services/data-and-statistics/rental-bond-data/"
TENANCY_BOND_DATASETS = {
    "tla": {
        "url": "https://www.tenancy.govt.nz/assets/Uploads/Tenancy/Rental-bond-data/detailed-monthly-tla-tenancy-v2.csv?m=bef970379280bdcf81464c5e8a29ab88f4ae7bca4",
        "label": "Rental bond data by Territorial Authority (monthly)",
        "scope": "tla",
    },
    "region": {
        "url": "https://www.tenancy.govt.nz/assets/Uploads/Tenancy/Rental-bond-data/detailed-monthly-region-tenancy-v2.csv?m=f5a009ae246bab76553a0965e4933f454b880a4d",
        "label": "Rental bond data by Region (monthly)",
        "scope": "region",
    },
    "quarter": {
        "url": "https://www.tenancy.govt.nz/assets/Uploads/Tenancy/Rental-bond-data/detailed-quarterly-tenancy-2020-to-2026.csv?m=f5a32807fa4875a5c8ee819bfa77ecfa0b9aca67",
        "label": "Rental bond data by quarter (detailed)",
        "scope": "quarter",
    },
}

CKAN_BASE = "https://catalogue.data.govt.nz"
CKAN_ACTION = CKAN_BASE + "/api/3/action/"
MARKET_RENT_PAGE = "https://www.tenancy.govt.nz/rent-bond-and-bills/market-rent/"
MARKET_RENT_SUGGEST = MARKET_RENT_PAGE + "suggestLocations"
MARKET_RENT_UPDATE = MARKET_RENT_PAGE + "updateMarketValueLocation/"
MONTH_INDEX = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


class UpstreamUnavailable(RuntimeError):
    pass


def die(message: str, code: int = 1) -> None:
    print(f"rental-bond-nz: {message}", file=sys.stderr)
    raise SystemExit(code)


def now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).lower()


def as_int(value: Any) -> int | None:
    text = str(value or "").replace(",", "").strip()
    if not text or text.lower() in {"n/a", "na", "-", "..", "c"}:
        return None
    try:
        return int(round(float(text)))
    except ValueError:
        return None


def as_money(value: Any) -> int | None:
    text = str(value or "").replace("$", "").replace(",", "").strip()
    if not text or text.lower() in {"n/a", "na", "-", "..", "c", "suppressed"}:
        return None
    try:
        return int(round(float(text)))
    except ValueError:
        return None


def clean_html(value: Any) -> str:
    text = re.sub(r"<[^>]+>", " ", str(value))
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def parse_year_month(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    match = re.fullmatch(r"(19|20)\d{2}-(0[1-9]|1[0-2])", value)
    return value if match else None


def request(url: str, timeout: int, headers: dict[str, str] | None = None) -> urllib.request.Request:
    merged_headers = {
        "User-Agent": UA,
        "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-NZ,en;q=0.9",
    }
    if headers:
        merged_headers.update(headers)
    return urllib.request.Request(url, headers=merged_headers)


def fetch_bytes(url: str, timeout: int, headers: dict[str, str] | None = None) -> tuple[bytes, str]:
    try:
        with urllib.request.urlopen(request(url, timeout=timeout, headers=headers), timeout=timeout) as response:
            return response.read(), response.geturl()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:320]
        raise UpstreamUnavailable(f"HTTP {exc.code} from {url}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise UpstreamUnavailable(f"network error calling {url}: {exc.reason}") from exc
    except TimeoutError as exc:
        raise UpstreamUnavailable(f"timeout calling {url}") from exc


def fetch_text(url: str, timeout: int, headers: dict[str, str] | None = None) -> tuple[str, str]:
    data, final_url = fetch_bytes(url, timeout=timeout, headers=headers)
    return data.decode("utf-8", "replace"), final_url


def fetch_json(url: str, timeout: int, headers: dict[str, str] | None = None) -> tuple[dict[str, Any], str]:
    text, final_url = fetch_text(url, timeout=timeout, headers=headers)
    try:
        return json.loads(text), final_url
    except json.JSONDecodeError as exc:
        raise UpstreamUnavailable(f"invalid JSON from {url}: {exc}") from exc


def fetch_csv_rows(url: str, timeout: int, keep: Any | None = None, headers: dict[str, str] | None = None) -> tuple[list[dict[str, str]], str]:
    raw, final_url = fetch_bytes(url, timeout=timeout, headers=headers)
    rows: list[dict[str, str]] = []
    with io.TextIOWrapper(io.BytesIO(raw), encoding="utf-8-sig", newline="") as text:
        reader = csv.DictReader(text)
        for row in reader:
            if keep is None or keep(row):
                rows.append(row)
    return rows, final_url


def ckan_request(action: str, params: dict[str, Any], timeout: int) -> tuple[dict[str, Any], str]:
    query = urllib.parse.urlencode(params)
    url = CKAN_ACTION + action + ("?" + query if query else "")
    payload, final_url = fetch_json(url, timeout=timeout)
    if not payload.get("success"):
        raise UpstreamUnavailable(f"CKAN {action} returned success=false: {payload.get('error')}")
    return payload, final_url


def discover_tenancy_links(timeout: int, query_filter: str) -> list[dict[str, str]]:
    html, _ = fetch_text(TENANCY_DATA_PAGE, timeout=timeout)
    rows: list[dict[str, str]] = []
    seen: set[str] = set()

    for href, text in re.findall(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html, re.S | re.I):
        if "assets/Uploads/Tenancy/Rental-bond-data/" not in href:
            continue
        if not re.search(r"\.(csv|zip)(\?|$)", href, re.I):
            continue
        link_text = clean_html(text) or "Untitled"
        if query_filter:
            haystack = norm(" ".join([link_text, href]))
            if query_filter not in haystack:
                continue

        final = href
        if final.startswith("/"):
            final = "https://www.tenancy.govt.nz" + final

        if final in seen:
            continue
        seen.add(final)
        rows.append(
            {
                "name": link_text,
                "url": final,
                "source": "tenancy.govt.nz",
                "category": "direct",
            }
        )

    rows.sort(key=lambda row: norm(row["name"]))
    return rows


def discover_ckan_packages(timeout: int, query: str, limit: int) -> list[dict[str, Any]]:
    payload, _ = ckan_request("package_search", {"q": query, "rows": min(limit, 50)}, timeout=timeout)
    result = payload.get("result", {})
    packages = []

    for package in result.get("results", []):
        csv_resources = []
        for resource in package.get("resources", []):
            url = (resource.get("url") or "").strip()
            fmt = (resource.get("format") or "").lower()
            if not url:
                continue
            if fmt == "csv" or url.lower().endswith(".csv"):
                csv_resources.append(
                    {
                        "id": resource.get("id"),
                        "name": resource.get("name"),
                        "format": resource.get("format"),
                        "url": url,
                        "last_modified": resource.get("last_modified") or resource.get("created"),
                    }
                )

        packages.append(
            {
                "name": package.get("name"),
                "title": package.get("title"),
                "notes": package.get("notes"),
                "organization": (package.get("organization") or {}).get("title"),
                "package_url": CKAN_BASE + f"/dataset/{package.get('id')}",
                "metadata_modified": package.get("metadata_modified"),
                "source": "data.govt.nz (CKAN)",
                "resource_count": len(package.get("resources", []) or []),
                "csv_resources": csv_resources,
            }
        )

    packages.sort(key=lambda row: norm(row["name"]))
    return packages


def parse_suggested_areas(timeout: int, query: str) -> list[dict[str, str]]:
    if query and len(query) < 2:
        query = query + query
    if not query:
        query = "au"

    query_url = MARKET_RENT_SUGGEST + "?" + urllib.parse.urlencode({"query": query})
    headers = {
        "X-Requested-With": "XMLHttpRequest",
        "Referer": MARKET_RENT_PAGE,
        "Accept": "application/json,text/javascript,*/*;q=0.8",
    }
    payload, _ = fetch_json(query_url, timeout=timeout, headers=headers)

    seen: set[str] = set()
    suggestions: list[dict[str, str]] = []
    for item in payload.get("suggestions", []):
        value = clean_html(item.get("value"))
        city = clean_html((item.get("data") or {}).get("city"))
        if not value:
            continue
        key = norm(value)
        if key in seen:
            continue
        seen.add(key)
        suggestions.append({"value": value, "city": city})

    suggestions.sort(key=lambda item: norm(item["value"]))
    return suggestions


def parse_area(value: str) -> tuple[str, str]:
    if " - " not in value:
        raise ValueError(f"market-rent area '{value}' is not in required 'City - Suburb' format")
    city, suburb = value.split(" - ", 1)
    return city.strip(), suburb.strip()


def resolve_market_area(area: str, city: str | None, timeout: int) -> tuple[str, str]:
    if city:
        city = city.strip()
        if not area.strip():
            raise ValueError("when using --city, provide --suburb")
        suburb = area.strip()
        return city, suburb

    if " - " in area:
        return parse_area(area)

    query = area.strip()
    suggestions = parse_suggested_areas(timeout=timeout, query=query)
    if not suggestions:
        raise ValueError(f"No area suggestions for '{query}'. Use market rent with explicit City - Suburb text")

    exact = [s for s in suggestions if norm(s["value"]) == norm(query)]
    if exact:
        value = exact[0]["value"]
        return parse_area(value)

    suburb_matches = [s for s in suggestions if norm(s["value"]).endswith(" - " + norm(query))]
    if len(suburb_matches) == 1:
        return parse_area(suburb_matches[0]["value"])

    if suburb_matches:
        sample = ", ".join(item["value"] for item in suburb_matches[:5])
        raise ValueError(
            f"Area '{query}' is ambiguous. Include city, for example: --area 'Auckland - {query}'. "
            f"Suggestions: {sample}"
        )

    raise ValueError(
        f"No unique market-rent area for '{query}'. Use explicit format: --area 'City - Suburb' "
        "or pass --city with --suburb."
    )


def parse_market_frame(period_text: str | None) -> tuple[str | None, str | None]:
    if not period_text:
        return None, None
    match = re.search(
        r"(\d{2})\s+([A-Za-z]{3})\s+(20\d{2})\s+-\s+(\d{2})\s+([A-Za-z]{3})\s+(20\d{2})",
        period_text,
    )
    if not match:
        return None, None
    start_month = MONTH_INDEX.get(match.group(2).lower()[:3], 0)
    end_month = MONTH_INDEX.get(match.group(4).lower()[:3], 0)
    start = f"{match.group(3)}-{start_month:02d}" if start_month else None
    end = f"{match.group(6)}-{end_month:02d}" if end_month else None
    return start, end


def parse_market_rent_table(table_html: str) -> tuple[list[dict[str, Any]], dict[str, str | None], str | None]:
    heading = re.search(r"<h5>(.*?)<span class=\"search_details\">([^<]+)</span></h5>", table_html, re.I | re.S)
    area = clean_html(heading.group(1)) if heading else None
    period_label = clean_html(heading.group(2)) if heading else None
    period_start, period_end = parse_market_frame(period_label)

    rows: list[dict[str, Any]] = []
    section_headers = list(
        re.finditer(
            r'<td[^>]*class="head_type"[^>]*>\s*<h5>(.*?)</h5>\s*</td>',
            table_html,
            re.I | re.S,
        )
    )

    if not section_headers:
        return rows, {"area": area, "period_label": period_label}, period_start

    for i, header in enumerate(section_headers):
        property_type = clean_html(header.group(1))
        section_start = header.end()
        section_end = section_headers[i + 1].start() if i + 1 < len(section_headers) else len(table_html)
        section = table_html[section_start:section_end]

        for row_html in re.finditer(r"<tr[^>]*>(.*?)</tr>", section, re.I | re.S):
            columns = [
                clean_html(cell)
                for cell in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row_html.group(1), re.I | re.S)
            ]
            if len(columns) != 5:
                continue
            size, active, lower, median, upper = columns
            if not re.search(r"\d", size):
                continue
            if norm(size) in {"size", "active bonds"}:
                continue
            rows.append(
                {
                    "area": area,
                    "property_type": property_type,
                    "size": size,
                    "active_bonds": as_int(active),
                    "lower_quartile_rent": as_money(lower),
                    "median_rent": as_money(median),
                    "upper_quartile_rent": as_money(upper),
                    "period_start": period_start,
                    "period_end": period_end,
                }
            )

    return rows, {"area": area, "period_label": period_label}, period_start


def parse_bedrooms(value: str | None) -> tuple[int, bool] | None:
    if not value:
        return None
    match = re.fullmatch(r"(\d+)\s*(\+)?", norm(value))
    if not match:
        return None
    return int(match.group(1)), bool(match.group(2))


def parse_bedrooms_arg(value: str) -> tuple[int, bool]:
    parsed = parse_bedrooms(value)
    if not parsed:
        raise ValueError("--bedrooms must be N or N+ (for example: 2 or 3+)")
    return parsed


def match_bedrooms(size: str, target: tuple[int, bool]) -> bool:
    parsed = parse_bedrooms(size)
    if not parsed:
        return False
    row_n, _ = parsed
    target_n, target_plus = target
    if target_plus:
        return row_n >= target_n
    return row_n == target_n


def parse_market_rent_payload(payload: dict[str, Any], period_filter: str | None, property_filter: str | None,
                             bedrooms_filter: tuple[int, bool] | None) -> list[dict[str, Any]]:
    table_html = payload.get("Table", "") or ""
    rows, meta, period_start = parse_market_rent_table(table_html)
    out: list[dict[str, Any]] = []

    target_property = norm(property_filter) if property_filter else ""
    target_period = period_filter

    for row in rows:
        if target_property and target_property not in norm(row["property_type"]):
            continue
        if bedrooms_filter and not match_bedrooms(row["size"], bedrooms_filter):
            continue
        if target_period and row.get("period_start") != target_period:
            continue
        out.append(row)

    return out


def fetch_market_rent(city: str, suburb: str, timeout: int) -> tuple[dict[str, Any], str]:
    query = urllib.parse.urlencode({"ajax_city": city, "ajax_suburb": suburb})
    url = MARKET_RENT_UPDATE + "?" + query
    headers = {
        "X-Requested-With": "XMLHttpRequest",
        "Referer": MARKET_RENT_PAGE,
        "Accept": "application/json,text/html;q=0.8,*/*;q=0.2",
    }
    payload, final_url = fetch_json(url, timeout=timeout, headers=headers)
    if not isinstance(payload, dict) or "Finder" not in payload or "Table" not in payload:
        raise UpstreamUnavailable(f"Unexpected market-rent response from {url}")
    return payload, final_url


def emit(payload: dict[str, Any], as_json: bool, render) -> None:
    if as_json:
        print(json.dumps(payload, sort_keys=True, indent=2))
    else:
        render(payload)


def cmd_datasets(args: argparse.Namespace) -> dict[str, Any]:
    filter_value = norm(args.query)
    direct = discover_tenancy_links(timeout=args.timeout, query_filter=filter_value)
    ckan = discover_ckan_packages(timeout=args.timeout, query="rental bond data", limit=args.limit)

    return {
        "kind": "tenancy_bond_datasets",
        "source": {
            "name": SOURCE_NAME,
            "tenancy_data_page": TENANCY_DATA_PAGE,
            "ckan_search": CKAN_BASE + "/api/3/action/package_search",
        },
        "generated_at": now_iso(),
        "query": args.query,
        "tenancy_asset_datasets": direct,
        "ckan_packages": ckan,
        "tenancy_asset_count": len(direct),
        "ckan_count": len(ckan),
    }


def cmd_areas(args: argparse.Namespace) -> dict[str, Any]:
    suggestions = parse_suggested_areas(timeout=args.timeout, query=args.query or "au")
    if args.city:
        suggestions = [item for item in suggestions if norm(item["city"]) == norm(args.city)]
    if args.limit and args.limit > 0:
        suggestions = suggestions[:args.limit]

    return {
        "kind": "tenancy_market_rent_areas",
        "source": "tenancy.govt.nz",
        "generated_at": now_iso(),
        "query": args.query,
        "count": len(suggestions),
        "areas": suggestions,
    }


def cmd_bonds(args: argparse.Namespace) -> dict[str, Any]:
    from_ = parse_year_month(args.from_)
    to_ = parse_year_month(args.to)
    if args.from_ and not from_:
        raise ValueError("--from must be YYYY-MM")
    if args.to and not to_:
        raise ValueError("--to must be YYYY-MM")

    dataset = TENANCY_BOND_DATASETS[args.scope]
    rows, source_url = fetch_csv_rows(dataset["url"], timeout=args.timeout)

    wanted_area = args.area.strip() if args.area else "all"

    filtered: list[dict[str, Any]] = []
    for row in rows:
        time_frame = (row.get("Time Frame") or "")[:7]
        if from_ and time_frame < from_:
            continue
        if to_ and time_frame > to_:
            continue

        location = row.get("Location", "")
        if args.area:
            if norm(wanted_area) not in norm(location):
                continue
        else:
            # default to all-row trend for manageable output
            if norm(location) != "all":
                continue

        filtered.append(
            {
                "time_frame": time_frame,
                "location_id": (row.get("Location Id") or "").strip(),
                "location": location,
                "lodged_bonds": as_int(row.get("Lodged Bonds")),
                "active_bonds": as_int(row.get("Active Bonds")),
                "closed_bonds": as_int(row.get("Closed Bonds")),
                "median_rent": as_money(row.get("Median Rent")),
                "geometric_mean_rent": as_money(row.get("Geometric Mean Rent")),
                "upper_quartile_rent": as_money(row.get("Upper Quartile Rent")),
                "lower_quartile_rent": as_money(row.get("Lower Quartile Rent")),
            }
        )

    filtered.sort(key=lambda row: row["time_frame"])

    if args.limit and args.limit > 0:
        filtered = filtered[: args.limit]

    return {
        "kind": "tenancy_bond_series",
        "source": SOURCE_NAME,
        "source_url": source_url,
        "scope": args.scope,
        "label": dataset["label"],
        "generated_at": now_iso(),
        "from": from_,
        "to": to_,
        "requested_area": args.area,
        "returned": len(filtered),
        "records": filtered,
    }


def cmd_market_rent(args: argparse.Namespace) -> dict[str, Any]:
    city, suburb = resolve_market_area(args.area, args.city, args.timeout)
    if args.suburb:
        suburb = args.suburb

    payload, source_url = fetch_market_rent(city=city, suburb=suburb, timeout=args.timeout)
    table_rows, finder_meta, period_start = parse_market_rent_table(payload.get("Table", ""))

    bedrooms = parse_bedrooms_arg(args.bedrooms) if args.bedrooms else None
    period = parse_year_month(args.period) if args.period else None

    filtered = parse_market_rent_payload(
        payload=payload,
        period_filter=period,
        property_filter=args.property_type,
        bedrooms_filter=bedrooms,
    )

    return {
        "kind": "tenancy_market_rent",
        "source": SOURCE_NAME,
        "source_url": source_url,
        "generated_at": now_iso(),
        "area": {
            "city": city,
            "suburb": suburb,
            "label": f"{city} - {suburb}",
        },
        "requested": {
            "area": args.area,
            "property_type": args.property_type,
            "bedrooms": args.bedrooms,
            "period": args.period,
        },
        "finder": {
            "raw": finder_meta.get("period_label"),
            "period": period_start,
        },
        "returned": len(filtered),
        "records": filtered,
    }


def render_human(payload: dict[str, Any]) -> None:
    kind = payload.get("kind")

    if kind == "tenancy_bond_datasets":
        print(f"Source: {payload['source']['name']}")
        print(f"Direct assets: {payload['tenancy_asset_count']}")
        for row in payload.get("tenancy_asset_datasets", []):
            print(f"- {row['name']}: {row['url']}")
        print(f"CKAN packages: {payload['ckan_count']}")
        return

    if kind == "tenancy_market_rent_areas":
        print(f"Areas matching '{payload['query']}': {payload['count']}")
        for row in payload.get("areas", []):
            print(f"- {row['value']}")
        return

    if kind == "tenancy_bond_series":
        print(f"source_url: {payload['source_url']}")
        print(f"returned: {payload['returned']}")
        for row in payload.get("records", []):
            print(
                f"{row['time_frame']} {row['location']}: "
                f"active={row['active_bonds']} lodged={row['lodged_bonds']} closed={row['closed_bonds']}"
            )
        return

    if kind == "tenancy_market_rent":
        print(f"area: {payload['area']['city']} - {payload['area']['suburb']}")
        print(f"returned: {payload['returned']}")
        for row in payload.get("records", []):
            print(
                f"{row['property_type']} | {row['size']} | "
                f"active={row['active_bonds']} median={row['median_rent']} "
                f"lower={row['lower_quartile_rent']} upper={row['upper_quartile_rent']}"
            )
        return

    print(json.dumps(payload, indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Query MBIE / Tenancy Services rental bond and market rent data")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="network timeout seconds")

    sub = parser.add_subparsers(dest="command", required=True)

    datasets = sub.add_parser("datasets", help="discover Tenancy bond release URLs and CKAN resources")
    datasets.add_argument("--query", default="", help="optional query filter")
    datasets.add_argument("--limit", type=int, default=20, help="max CKAN package rows")
    datasets.add_argument("--json", action="store_true", help="emit JSON")
    datasets.set_defaults(func=cmd_datasets)

    areas = sub.add_parser("areas", help="discover city and suburb values for market-rent")
    areas.add_argument("--query", default="au", help="autocomplete text")
    areas.add_argument("--city", help="optional city filter")
    areas.add_argument("--limit", type=int, default=60, help="max suggestions")
    areas.add_argument("--json", action="store_true", help="emit JSON")
    areas.set_defaults(func=cmd_areas)

    bonds = sub.add_parser("bonds", help="query monthly/quarterly tenancy bond series")
    bonds.add_argument("--from", dest="from_", help="start month YYYY-MM")
    bonds.add_argument("--to", help="end month YYYY-MM")
    bonds.add_argument("--area", help="location substring match")
    bonds.add_argument("--scope", choices=["tla", "region"], default="tla", help="dataset scope")
    bonds.add_argument("--limit", type=int, default=0, help="max rows (0 = all)")
    bonds.add_argument("--json", action="store_true", help="emit JSON")
    bonds.set_defaults(func=cmd_bonds)

    market = sub.add_parser("market-rent", help="query market-rent rows by suburb")
    market.add_argument("--area", required=True, help="area (preferred: 'City - Suburb')")
    market.add_argument("--city", help="optional city override")
    market.add_argument("--suburb", help="optional suburb override")
    market.add_argument("--property-type", dest="property_type", help="filter property type")
    market.add_argument("--bedrooms", help="filter bedroom size, e.g. 1 or 3+")
    market.add_argument("--period", help="filter by period start month YYYY-MM")
    market.add_argument("--json", action="store_true", help="emit JSON")
    market.set_defaults(func=cmd_market_rent)

    args = parser.parse_args(argv)

    if args.timeout <= 0:
        die("--timeout must be > 0")
    if args.timeout > MAX_TIMEOUT:
        args.timeout = MAX_TIMEOUT

    if args.command == "market-rent" and args.bedrooms:
        parse_bedrooms_arg(args.bedrooms)

    if args.command == "market-rent" and args.period:
        period_value = parse_year_month(args.period)
        if not period_value:
            die("--period must be YYYY-MM")

    try:
        payload = args.func(args)
        emit(payload, getattr(args, "json", False), render_human)
        return 0
    except UpstreamUnavailable as exc:
        message = {"error": "upstream_unavailable", "message": str(exc)}
        if getattr(args, "json", False):
            print(json.dumps(message, indent=2, sort_keys=True))
        else:
            print(f"upstream unavailable: {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        die(str(exc))
        return 1


if __name__ == "__main__":
    sys.exit(main())
