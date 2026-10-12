#!/usr/bin/env python3
"""Stats NZ public-data CLI.

Read-only stdlib wrapper around public Stats NZ CSV releases and pages.
No login, API key, browser automation, cache, or data mutation.
"""
from __future__ import annotations

import argparse
import csv
import html
import io
import json
import pathlib
import re
import sys
import urllib.parse
from collections import defaultdict
from typing import Any, Callable, Iterable

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "lib"))
import nzfetch  # noqa: E402
from provenance import error_envelope, provenance, result_envelope  # noqa: E402

STATS_BASE = "https://www.stats.govt.nz"
CSV_PAGE = STATS_BASE + "/large-datasets/csv-files-for-download/"
POPULATION_INDICATOR = STATS_BASE + "/indicators/population-of-nz/"
POPULATION_PROJECTION = STATS_BASE + "/information-releases/national-population-projections-2024base2078/"
PLACE_BASE = "https://tools.summaries.stats.govt.nz/places/RC"
PLACE_HOST = "tools.summaries.stats.govt.nz"
PLACE_INDEX_URL = f"https://{PLACE_HOST}/places"
PLACE_TRAVEL_TIMEOUT = 15
PLACE_TRAVEL_MAX_BYTES = 2_000_000
PLACE_TRAVEL_MAX_ROWS = 40
PLACE_PATH = re.compile(r"^[A-Z]{2}/[a-z0-9]+(?:-[a-z0-9]+)*$")
TRAVEL_CONCEPT = "Main means of travel to work"
TRAVEL_SECTIONS = {
    "usual": "Main means of travel to work (usual residence address)",
    "workplace": "Main means of travel to work (workplace address)",
}
PLACE_LICENCE = (
    "CC BY 4.0. Unless noted otherwise, content on stats.govt.nz is licensed "
    "under the Creative Commons 4.0 International Licence. Attribute Stats NZ."
)
UA = "stats-nz-skill/1.0 (+https://github.com/thecolab-ai/.skills)"

CPI_SERIES = "CPIQ.SE9A"
# Food Price Index, all-groups headline series ("Food Price Index for New
# Zealand"). Monthly. Note: the Stats NZ bulk-CSV page may host an older FPI
# release than Infoshare; this command auto-freshens when a newer CSV is posted.
FPI_SERIES = "CPIM.SE901"

GDP_SERIES = {
    "production_chain_volume_sa": {
        "id": "SNEQ.SG01RSC00B01",
        "label": "GDP production measure, chain-volume, seasonally adjusted",
    },
    "production_quarterly_change": {
        "id": "SNEQ.SG01RSC01B01PC",
        "label": "GDP production measure, quarterly change",
    },
    "production_annual_change": {
        "id": "SNEQ.SG01RSC01B01AC",
        "label": "GDP production measure, annual change",
    },
    "expenditure_chain_volume_sa": {
        "id": "SNEQ.SG02RSC00B15",
        "label": "GDP expenditure measure, chain-volume, seasonally adjusted",
    },
    "expenditure_quarterly_change": {
        "id": "SNEQ.SG02RSC31B15PC",
        "label": "GDP expenditure measure, quarterly change",
    },
}

REGION_SLUGS = {
    "northland": "northland-region",
    "auckland": "auckland-region",
    "waikato": "waikato-region",
    "bay of plenty": "bay-of-plenty-region",
    "bayofplenty": "bay-of-plenty-region",
    "gisborne": "gisborne-region",
    "hawke s bay": "hawkes-bay-region",
    "hawkes bay": "hawkes-bay-region",
    "hawkesbay": "hawkes-bay-region",
    "taranaki": "taranaki-region",
    "manawatu whanganui": "manawatu-whanganui-region",
    "manawatuwhanganui": "manawatu-whanganui-region",
    "wellington": "wellington-region",
    "tasman": "tasman-region",
    "nelson": "nelson-region",
    "marlborough": "marlborough-region",
    "west coast": "west-coast-region",
    "westcoast": "west-coast-region",
    "canterbury": "canterbury-region",
    "otago": "otago-region",
    "southland": "southland-region",
}


def die(message: str, code: int = 1) -> None:
    print(f"stats-nz: {message}", file=sys.stderr)
    raise SystemExit(code)


def read_url_text(url: str, timeout: int = 30) -> str:
    try:
        return nzfetch.fetch_text(url, timeout=timeout)
    except nzfetch.Blocked as e:
        die(f"network error: {e}")
    except nzfetch.FetchError as e:
        die(str(e))


def fetch_csv_rows(
    url: str,
    keep: Callable[[dict[str, str]], bool] | None = None,
    timeout: int = 90,
) -> tuple[list[dict[str, str]], str]:
    try:
        body, _ct, final_url = nzfetch.fetch_bytes(url, timeout=timeout)
    except nzfetch.Blocked as e:
        die(f"network error: {e}")
    except nzfetch.FetchError as e:
        die(str(e))
    try:
        reader = csv.DictReader(io.StringIO(body.decode("utf-8-sig", "replace"), newline=""))
        rows = []
        for row in reader:
            if keep is None or keep(row):
                rows.append(row)
        return rows, final_url
    except csv.Error as e:
        die(f"invalid CSV from {url}: {e}")


def page_view_data(url: str) -> dict[str, Any]:
    text = read_url_text(url)
    patterns = [
        r'<div id="pageViewData"[^>]*data-value="(.*?)"',
        r"<div id='pageViewData'[^>]*data-value='(.*?)'",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.S)
        if match:
            try:
                return json.loads(html.unescape(match.group(1)))
            except json.JSONDecodeError as e:
                die(f"invalid embedded pageViewData JSON from {url}: {e}")
    die(f"could not find pageViewData JSON in {url}")


def next_data(url: str) -> dict[str, Any]:
    text = read_url_text(url)
    match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', text, re.S)
    if not match:
        die(f"could not find __NEXT_DATA__ JSON in {url}")
    try:
        return json.loads(html.unescape(match.group(1)))
    except json.JSONDecodeError as e:
        die(f"invalid embedded __NEXT_DATA__ JSON from {url}: {e}")


def walk_dicts(obj: Any) -> Iterable[dict[str, Any]]:
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from walk_dicts(value)
    elif isinstance(obj, list):
        for item in obj:
            yield from walk_dicts(item)


def absolute_stats_url(path: str) -> str:
    return urllib.parse.urljoin(STATS_BASE, path)


def catalog_documents() -> list[dict[str, str]]:
    data = page_view_data(CSV_PAGE)
    docs: list[dict[str, str]] = []
    for block in data.get("PageBlocks", []):
        for doc in block.get("BlockDocuments") or []:
            link = doc.get("DocumentLink")
            if not link:
                continue
            title = doc.get("Title") or doc.get("Name") or doc.get("FileName") or link
            docs.append(
                {
                    "id": str(doc.get("ID") or ""),
                    "title": str(title),
                    "name": str(doc.get("Name") or ""),
                    "filename": str(doc.get("FileName") or ""),
                    "extension": str(doc.get("DocumentExtension") or "").lower(),
                    "size": str(doc.get("DocumentSize") or ""),
                    "url": absolute_stats_url(str(link)),
                }
            )
    return docs


def find_catalog_doc(
    must: Iterable[str],
    must_not: Iterable[str] = (),
    extension: str = "csv",
) -> dict[str, str]:
    must_terms = [term.lower() for term in must]
    blocked_terms = [term.lower() for term in must_not]
    for doc in catalog_documents():
        haystack = " ".join([doc["title"], doc["name"], doc["filename"]]).lower()
        if extension and doc["extension"] != extension:
            continue
        if all(term in haystack for term in must_terms) and not any(term in haystack for term in blocked_terms):
            return doc
    die("could not find Stats NZ catalogue item matching: " + ", ".join(must_terms))


def as_float(raw: Any) -> float | None:
    if raw is None:
        return None
    text = str(raw).strip().replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def as_int(raw: Any) -> int | None:
    value = as_float(raw)
    if value is None:
        return None
    return int(round(value))


def fmt_int(value: Any) -> str:
    number = as_int(value)
    return "n/a" if number is None else f"{number:,}"


def fmt_number(value: Any) -> str:
    number = as_float(value)
    if number is None:
        return "n/a"
    if number.is_integer():
        return f"{int(number):,}"
    return f"{number:,.2f}"


def fmt_pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1f}%"


def period_tuple(raw: str) -> tuple[int, int]:
    text = str(raw).strip()
    match = re.fullmatch(r"(\d{4})\.(\d{1,2})", text) or re.fullmatch(r"(\d{4})-(\d{2})(?:-\d{2})?", text)
    if match:
        return int(match.group(1)), int(match.group(2))
    match = re.fullmatch(r"(\d{4})", text)
    if match:
        return int(match.group(1)), 12
    die(f"could not parse period: {raw}")


def period_arg(raw: str | None) -> tuple[int, int] | None:
    if not raw:
        return None
    return period_tuple(raw)


def filter_period_rows(
    rows: list[dict[str, str]],
    start: str | None,
    end: str | None,
    period_field: str = "Period",
) -> list[dict[str, str]]:
    start_key = period_arg(start)
    end_key = period_arg(end)
    kept = []
    for row in rows:
        key = period_tuple(row.get(period_field, ""))
        if start_key and key < start_key:
            continue
        if end_key and key > end_key:
            continue
        kept.append(row)
    return kept


def series_title(row: dict[str, str]) -> str:
    parts = []
    for key in sorted(k for k in row if k.startswith("Series_title_")):
        value = row.get(key)
        if value:
            parts.append(value)
    return " - ".join(parts)


def serialize_series_row(row: dict[str, str]) -> dict[str, Any]:
    item: dict[str, Any] = {
        "period": row.get("Period"),
        "value": as_float(row.get("Data_value")),
        "status": row.get("STATUS"),
        "units": row.get("UNITS"),
    }
    if row.get("MAGNITUDE") not in (None, ""):
        item["magnitude"] = as_int(row.get("MAGNITUDE"))
    title = series_title(row)
    if title:
        item["series_title"] = title
    return item


def emit_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def output(payload: dict[str, Any], json_flag: bool, render: Callable[[dict[str, Any]], None]) -> None:
    if json_flag:
        emit_json(payload)
    else:
        render(payload)


def cpi_doc() -> dict[str, str]:
    return find_catalog_doc(
        ["consumers price index", "index numbers"],
        ["seasonally adjusted", "tradables", "infoshare"],
    )


def fpi_doc() -> dict[str, str]:
    return find_catalog_doc(
        ["food price index", "index numbers"],
        ["seasonally adjusted", "weighted average"],
    )


def gdp_doc() -> dict[str, str]:
    return find_catalog_doc(["gross domestic product"], ["visualisation"])


def migration_doc() -> dict[str, str]:
    # Stats NZ release titles/filenames have used both "estimated migration by
    # age and sex" and "estimated migration by age sex" wording. Match the
    # stable component terms instead of one exact phrase so the command survives
    # routine monthly catalogue title changes.
    return find_catalog_doc(["international migration", "estimated migration", "age", "sex"])


def cmd_cpi(args: argparse.Namespace) -> None:
    doc = cpi_doc()
    rows, final_url = fetch_csv_rows(doc["url"], lambda row: row.get("Series_reference") == CPI_SERIES)
    rows.sort(key=lambda row: period_tuple(row["Period"]))
    if not rows:
        die(f"series {CPI_SERIES} was not found in {doc['title']}")

    filtered = filter_period_rows(rows, args.from_date, args.to_date)
    if not filtered:
        die("no CPI observations matched the supplied date range")

    latest = rows[-1]
    latest_key = period_tuple(latest["Period"])
    latest_value = as_float(latest.get("Data_value"))
    previous = rows[-2] if len(rows) > 1 else None
    annual = next((row for row in rows if period_tuple(row["Period"]) == (latest_key[0] - 1, latest_key[1])), None)

    previous_value = as_float(previous.get("Data_value")) if previous else None
    annual_value = as_float(annual.get("Data_value")) if annual else None
    quarterly_change = None
    annual_change = None
    if latest_value is not None and previous_value:
        quarterly_change = round(((latest_value / previous_value) - 1.0) * 100.0, 1)
    if latest_value is not None and annual_value:
        annual_change = round(((latest_value / annual_value) - 1.0) * 100.0, 1)

    observation_rows = filtered if args.from_date or args.to_date else rows[-8:]
    payload = {
        "source": "Stats NZ",
        "dataset": doc["title"],
        "url": final_url,
        "series_id": CPI_SERIES,
        "series_title": series_title(latest),
        "latest": {
            "period": latest.get("Period"),
            "value": latest_value,
            "units": latest.get("UNITS"),
            "status": latest.get("STATUS"),
            "quarterly_change_percent": quarterly_change,
            "annual_change_percent": annual_change,
        },
        "observations": [serialize_series_row(row) for row in observation_rows],
    }

    def render(p: dict[str, Any]) -> None:
        latest_item = p["latest"]
        print(f"Stats NZ CPI ({p['series_id']}) latest: {latest_item['period']} = {fmt_number(latest_item['value'])} {latest_item.get('units') or ''}".rstrip())
        print(f"Quarterly change: {fmt_pct(latest_item['quarterly_change_percent'])}; annual change: {fmt_pct(latest_item['annual_change_percent'])}")
        print(f"Status: {latest_item.get('status') or 'n/a'}")
        print(f"Source: {p['dataset']}")
        print(p["url"])

    output(payload, args.json, render)


def cmd_fpi(args: argparse.Namespace) -> None:
    doc = fpi_doc()
    rows, final_url = fetch_csv_rows(doc["url"], lambda row: row.get("Series_reference") == FPI_SERIES)
    rows.sort(key=lambda row: period_tuple(row["Period"]))
    if not rows:
        die(f"series {FPI_SERIES} was not found in {doc['title']}")

    filtered = filter_period_rows(rows, args.from_date, args.to_date)
    if not filtered:
        die("no FPI observations matched the supplied date range")

    latest = rows[-1]
    latest_key = period_tuple(latest["Period"])
    latest_value = as_float(latest.get("Data_value"))
    previous = rows[-2] if len(rows) > 1 else None
    # Annual change: same month one year earlier (FPI is monthly).
    annual = next((row for row in rows if period_tuple(row["Period"]) == (latest_key[0] - 1, latest_key[1])), None)

    previous_value = as_float(previous.get("Data_value")) if previous else None
    annual_value = as_float(annual.get("Data_value")) if annual else None
    monthly_change = None
    annual_change = None
    if latest_value is not None and previous_value:
        monthly_change = round(((latest_value / previous_value) - 1.0) * 100.0, 1)
    if latest_value is not None and annual_value:
        annual_change = round(((latest_value / annual_value) - 1.0) * 100.0, 1)

    observation_rows = filtered if args.from_date or args.to_date else rows[-13:]
    payload = {
        "source": "Stats NZ",
        "dataset": doc["title"],
        "url": final_url,
        "series_id": FPI_SERIES,
        "series_title": series_title(latest) or "Food Price Index for New Zealand",
        "latest": {
            "period": latest.get("Period"),
            "value": latest_value,
            "units": latest.get("UNITS"),
            "status": latest.get("STATUS"),
            "monthly_change_percent": monthly_change,
            "annual_change_percent": annual_change,
        },
        "observations": [serialize_series_row(row) for row in observation_rows],
    }

    def render(p: dict[str, Any]) -> None:
        latest_item = p["latest"]
        print(f"Stats NZ Food Price Index ({p['series_id']}) latest: {latest_item['period']} = {fmt_number(latest_item['value'])} {latest_item.get('units') or ''}".rstrip())
        print(f"Monthly change: {fmt_pct(latest_item['monthly_change_percent'])}; annual change: {fmt_pct(latest_item['annual_change_percent'])}")
        print(f"Status: {latest_item.get('status') or 'n/a'}")
        print(f"Source: {p['dataset']}")
        print(p["url"])

    output(payload, args.json, render)


def national_population() -> dict[str, Any]:
    data = page_view_data(POPULATION_INDICATOR)
    blocks = [block for block in data.get("PageBlocks", []) if block.get("ClassName") == "IndicatorBlock"]
    block = blocks[0] if blocks else data.get("FeaturedMedia") or {}
    if not block:
        die("could not find population indicator block")
    return {
        "source": "Stats NZ",
        "url": POPULATION_INDICATOR,
        "scope": "national",
        "name": block.get("Name") or data.get("Title"),
        "period": block.get("Period"),
        "value": as_int(block.get("Value")),
        "description": block.get("Description") or block.get("IndicatorDescription"),
        "last_updated": block.get("LastUpdatedDate"),
        "next_update": block.get("NextUpdatedDate"),
    }


def normalize_region(raw: str) -> str:
    text = raw.strip().lower()
    if re.fullmatch(r"[a-z0-9-]+-region", text):
        return text
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text).strip()
    text = re.sub(r"\bregion\b", "", text).strip()
    compact = text.replace(" ", "")
    if text in REGION_SLUGS:
        return REGION_SLUGS[text]
    if compact in REGION_SLUGS:
        return REGION_SLUGS[compact]
    die("unknown regional council region; try auckland, wellington, canterbury, otago, or an exact <slug>-region")


def regional_population(region: str) -> dict[str, Any]:
    slug = normalize_region(region)
    url = f"{PLACE_BASE}/{slug}"
    data = next_data(url)
    page_props = data.get("props", {}).get("pageProps", {})
    topics = page_props.get("place") or []
    candidates = []
    for topic in topics:
        for concept in topic.get("concepts", []):
            for section in concept.get("sections", []):
                if section.get("section_title") != "Population":
                    continue
                numbers_data = section.get("numbers_data") or {}
                numbers = numbers_data.get("numbers") or []
                vs_numbers = numbers_data.get("vs_numbers") or []
                for number in numbers:
                    if number.get("variable1_code") != "ERP":
                        continue
                    priority = 0 if topic.get("topic_title") == "Quick stats" else 1
                    candidates.append((priority, str(number.get("period") or ""), topic, section, number, vs_numbers))
    if not candidates:
        die(f"could not find estimated resident population for region: {region}")
    candidates.sort(key=lambda item: (item[0], -int(item[1]) if item[1].isdigit() else 0))
    _, _, topic, section, number, vs_numbers = candidates[0]
    comparison = next(
        (
            item
            for item in vs_numbers
            if item.get("period") == number.get("period") and item.get("variable1_code") == number.get("variable1_code")
        ),
        None,
    )
    return {
        "source": "Stats NZ",
        "url": url,
        "scope": "regional",
        "region": topic.get("classification_descriptor"),
        "classification": topic.get("classification_label"),
        "period": number.get("period"),
        "table_title": html.unescape(str(section.get("table_title") or "")),
        "value": number.get("value"),
        "measure": number.get("variable1_descriptor"),
        "comparison_new_zealand": comparison.get("value") if comparison else None,
    }


def projection_for(year: int, scenario: str) -> dict[str, Any]:
    data = page_view_data(POPULATION_PROJECTION)
    graph_csv = None
    title = None
    for item in walk_dicts(data):
        item_title = str(item.get("Title") or item.get("GraphHeading") or "")
        if "Projected New Zealand population" in item_title and item.get("GraphCsvData"):
            graph_csv = str(item["GraphCsvData"])
            title = item_title
            break
    if not graph_csv:
        die("could not find national population projection graph CSV")

    rows = list(csv.reader(io.StringIO(graph_csv.lstrip("\ufeff"))))
    if not rows or len(rows[0]) < 2:
        die("projection CSV had no year columns")
    years = rows[0][1:]
    year_text = str(year)
    if year_text not in years:
        die(f"projection year must be between {years[0]} and {years[-1]}")
    index = years.index(year_text) + 1
    scenario_key = re.sub(r"\s+", " ", scenario.strip().lower())
    available = [row[0] for row in rows[1:] if row]
    for row in rows[1:]:
        if not row:
            continue
        if re.sub(r"\s+", " ", row[0].strip().lower()) == scenario_key:
            return {
                "source": "Stats NZ",
                "url": POPULATION_PROJECTION,
                "title": title,
                "year": year,
                "scenario": row[0],
                "value": as_int(row[index]),
                "available_scenarios": available,
            }
    die("unknown projection scenario; available scenarios: " + ", ".join(available))


def cmd_population(args: argparse.Namespace) -> None:
    if args.region and args.projection:
        die("regional population projections are not implemented; use either --region or --projection")
    if args.region:
        payload = regional_population(args.region)
    else:
        payload = national_population()
        if args.projection:
            payload["projection"] = projection_for(args.projection, args.scenario)

    def render(p: dict[str, Any]) -> None:
        if p["scope"] == "regional":
            print(f"Stats NZ regional population: {p['region']} = {fmt_int(p['value'])}")
            print(f"Period: {p.get('table_title') or p.get('period')}")
            if p.get("comparison_new_zealand") is not None:
                print(f"New Zealand comparison: {fmt_int(p['comparison_new_zealand'])}")
        else:
            print(f"{p.get('name')}: {fmt_int(p['value'])}")
            print(f"Period: {p.get('period')}")
            if p.get("description"):
                print(p["description"])
            if p.get("last_updated"):
                print(f"Updated: {p['last_updated']}")
            if p.get("next_update"):
                print(f"Next update: {p['next_update']}")
            if p.get("projection"):
                projection = p["projection"]
                print(f"Projection ({projection['scenario']}, {projection['year']}): {fmt_int(projection['value'])}")
        print(f"Source: {p['source']}")
        print(p["url"])

    output(payload, args.json, render)


def cmd_migration(args: argparse.Namespace) -> None:
    doc = migration_doc()
    rows, final_url = fetch_csv_rows(
        doc["url"],
        lambda row: row.get("passenger_type") == "Long-term migrant"
        and row.get("sex") == "TOTAL"
        and row.get("age") == "TOTAL",
    )
    if not rows:
        die(f"no long-term migrant total rows found in {doc['title']}")
    grouped: dict[str, dict[str, Any]] = defaultdict(dict)
    for row in rows:
        month = row.get("year_month")
        direction = row.get("direction")
        if not month or not direction:
            continue
        grouped[month][direction.lower()] = {
            "estimate": as_int(row.get("estimate")),
            "standard_error": as_float(row.get("standard_error")),
            "status": row.get("status"),
            "month_of_release": row.get("month_of_release"),
        }
    latest_month = max(grouped)
    latest = grouped[latest_month]
    arrivals = latest.get("arrivals", {}).get("estimate")
    departures = latest.get("departures", {}).get("estimate")
    net = None if arrivals is None or departures is None else arrivals - departures
    payload = {
        "source": "Stats NZ",
        "dataset": doc["title"],
        "url": final_url,
        "latest": {
            "month": latest_month,
            "arrivals": arrivals,
            "departures": departures,
            "net_migration": net,
            "status": latest.get("arrivals", {}).get("status") or latest.get("departures", {}).get("status"),
            "month_of_release": latest.get("arrivals", {}).get("month_of_release")
            or latest.get("departures", {}).get("month_of_release"),
        },
    }

    def render(p: dict[str, Any]) -> None:
        latest_item = p["latest"]
        print(f"Stats NZ estimated long-term migration latest: {latest_item['month']}")
        print(f"Arrivals: {fmt_int(latest_item['arrivals'])}; departures: {fmt_int(latest_item['departures'])}; net: {fmt_int(latest_item['net_migration'])}")
        print(f"Status: {latest_item.get('status') or 'n/a'}")
        print(f"Source: {p['dataset']}")
        print(p["url"])

    output(payload, args.json, render)


def cmd_gdp(args: argparse.Namespace) -> None:
    doc = gdp_doc()
    ids = {spec["id"] for spec in GDP_SERIES.values()}
    rows, final_url = fetch_csv_rows(doc["url"], lambda row: row.get("Series_reference") in ids)
    if not rows:
        die(f"wired GDP series were not found in {doc['title']}")
    rows = filter_period_rows(rows, args.from_date, args.to_date)
    if not rows:
        die("no GDP observations matched the supplied date range")

    by_id: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_id[row["Series_reference"]].append(row)
    latest: dict[str, Any] = {}
    for key, spec in GDP_SERIES.items():
        series_rows = by_id.get(spec["id"], [])
        series_rows.sort(key=lambda row: period_tuple(row["Period"]))
        if not series_rows:
            continue
        row = series_rows[-1]
        item = serialize_series_row(row)
        item["series_id"] = spec["id"]
        item["label"] = spec["label"]
        latest[key] = item
    payload = {
        "source": "Stats NZ",
        "dataset": doc["title"],
        "url": final_url,
        "latest": latest,
    }

    def render(p: dict[str, Any]) -> None:
        latest_items = p["latest"]
        periods = [item["period"] for item in latest_items.values() if item.get("period")]
        period = max(periods, key=period_tuple) if periods else "n/a"
        print(f"Stats NZ GDP latest quarter: {period}")
        for key in [
            "production_chain_volume_sa",
            "production_quarterly_change",
            "production_annual_change",
            "expenditure_chain_volume_sa",
            "expenditure_quarterly_change",
        ]:
            item = latest_items.get(key)
            if not item:
                continue
            suffix = "NZD millions" if item.get("units") == "Dollars" and item.get("magnitude") == 6 else item.get("units") or ""
            print(f"{item['label']}: {fmt_number(item['value'])} {suffix}".rstrip())
        print(f"Source: {p['dataset']}")
        print(p["url"])

    output(payload, args.json, render)


def cmd_series(args: argparse.Namespace) -> None:
    requested = args.id.strip().upper()
    dataset_loaders = [
        ("cpi", cpi_doc),
        ("gdp", gdp_doc),
    ]
    matches = []
    found_series = False
    for dataset_key, doc_func in dataset_loaders:
        doc = doc_func()
        rows, final_url = fetch_csv_rows(doc["url"], lambda row: row.get("Series_reference", "").upper() == requested)
        if rows:
            found_series = True
            rows.sort(key=lambda row: period_tuple(row["Period"]))
            rows = filter_period_rows(rows, args.from_date, args.to_date)
            if args.limit:
                rows = rows[-args.limit :]
            if rows:
                matches.append({"dataset_key": dataset_key, "doc": doc, "url": final_url, "rows": rows})
    if not matches:
        if found_series:
            die("no observations matched the supplied date range")
        die(f"series {requested} was not found in wired CPI/GDP CSV releases")

    first_row = matches[0]["rows"][-1] if matches[0]["rows"] else {}
    payload = {
        "source": "Stats NZ",
        "series_id": requested,
        "series_title": series_title(first_row) if first_row else "",
        "matches": [
            {
                "dataset": match["doc"]["title"],
                "dataset_key": match["dataset_key"],
                "url": match["url"],
                "observations": [serialize_series_row(row) for row in match["rows"]],
            }
            for match in matches
        ],
    }

    def render(p: dict[str, Any]) -> None:
        print(f"Stats NZ series {p['series_id']}")
        if p.get("series_title"):
            print(p["series_title"])
        for match in p["matches"]:
            print(f"Source: {match['dataset']}")
            for item in match["observations"]:
                print(f"{item['period']}: {fmt_number(item['value'])} {item.get('units') or ''}".rstrip())
            print(match["url"])

    output(payload, args.json, render)


def cmd_search(args: argparse.Namespace) -> None:
    terms = [term.lower() for term in re.split(r"\s+", args.query.strip()) if term]
    if not terms:
        die("search query cannot be empty")
    results = []
    for doc in catalog_documents():
        haystack = " ".join([doc["title"], doc["name"], doc["filename"]]).lower()
        if all(term in haystack for term in terms):
            results.append(doc)
    results = results[: args.limit]
    payload = {
        "source": "Stats NZ",
        "catalogue": CSV_PAGE,
        "query": args.query,
        "count": len(results),
        "results": results,
    }

    def render(p: dict[str, Any]) -> None:
        print(f"Stats NZ CSV catalogue results for: {p['query']}")
        if not p["results"]:
            print("No matches")
        for doc in p["results"]:
            size = f" ({doc['size']})" if doc.get("size") else ""
            print(f"- {doc['title']}{size}")
            print(f"  {doc['url']}")

    output(payload, args.json, render)


class PlaceTravelError(Exception):
    """Typed failure for the place-travel command. Other commands keep die()."""

    def __init__(self, code: int, message: str, source_url: str, retry_after: str | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.source_url = source_url
        self.retry_after = retry_after


def normalize_place_token(raw: str) -> str:
    text = raw.strip() if isinstance(raw, str) else ""
    if (
        not text
        or len(text) > 64
        or any(ord(ch) < 32 for ch in text)
        or "://" in text
        or text.startswith("/")
        or ".." in text
        or "?" in text
        or "#" in text
        or "\\" in text
        or " " in text
    ):
        raise PlaceTravelError(
            2,
            "place must be one official CLASS/slug path, for example UR/auckland",
            PLACE_INDEX_URL,
        )
    parts = text.split("/")
    if len(parts) != 2:
        raise PlaceTravelError(
            2,
            "place must be one official CLASS/slug path, for example UR/auckland",
            PLACE_INDEX_URL,
        )
    token = f"{parts[0].upper()}/{parts[1].lower()}"
    if not PLACE_PATH.fullmatch(token):
        raise PlaceTravelError(
            2,
            "place must be one official CLASS/slug path, for example UR/auckland",
            PLACE_INDEX_URL,
        )
    return token


def place_travel_url(token: str) -> str:
    return f"https://{PLACE_HOST}/places/{token}"


def _published_number(raw: Any, *, suppressed: bool) -> int | float | None:
    if raw is None:
        return None
    if isinstance(raw, bool):
        raise ValueError("boolean is not a statistic")
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float):
        if raw != raw or raw in (float("inf"), float("-inf")):
            raise ValueError("non-finite number")
        return raw
    text = str(raw).strip().replace(",", "")
    if not text:
        return None
    if not re.fullmatch(r"-?\d+(?:\.\d+)?", text):
        if suppressed:
            return None
        raise ValueError(f"not a number: {raw!r}")
    if "." in text:
        return float(text)
    return int(text)


def _require_text(value: Any, label: str, url: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PlaceTravelError(6, f"place page omitted {label}", url)
    return value.strip()


def parse_place_travel_html(text: str, *, url: str, address: str) -> list[dict[str, Any]]:
    section_title = TRAVEL_SECTIONS[address]
    opener = '<script id="__NEXT_DATA__"'
    if opener in text and not re.search(
        r'<script id="__NEXT_DATA__" type="application/json">.*?</script>',
        text,
        re.S,
    ):
        raise PlaceTravelError(6, "truncated place page: __NEXT_DATA__ script was not closed", url)
    match = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
        text,
        re.S,
    )
    if not match:
        raise PlaceTravelError(6, "could not find __NEXT_DATA__ JSON in place page", url)
    try:
        data = json.loads(html.unescape(match.group(1)))
    except json.JSONDecodeError as exc:
        raise PlaceTravelError(6, f"invalid embedded __NEXT_DATA__ JSON: {exc.msg}", url) from exc
    if not isinstance(data, dict):
        raise PlaceTravelError(6, "place page __NEXT_DATA__ was not an object", url)
    place = data.get("props", {}).get("pageProps", {}).get("place") if isinstance(data.get("props"), dict) else None
    if not isinstance(place, list) or not place:
        raise PlaceTravelError(6, "place page did not include a place summary", url)

    topic = None
    concept = None
    for candidate in place:
        if not isinstance(candidate, dict):
            continue
        for item in candidate.get("concepts") or []:
            if isinstance(item, dict) and item.get("concept_title") == TRAVEL_CONCEPT:
                topic = candidate
                concept = item
                break
        if concept is not None:
            break
    if topic is None or concept is None:
        raise PlaceTravelError(6, "place page has no Main means of travel to work concept", url)

    section = None
    for item in concept.get("sections") or []:
        if isinstance(item, dict) and item.get("section_title") == section_title:
            section = item
            break
    if section is None:
        raise PlaceTravelError(6, f"place page has no travel section for {address} address", url)
    numbers_data = section.get("numbers_data") or {}
    if not isinstance(numbers_data, dict):
        raise PlaceTravelError(6, f"place page has no main-means-of-travel-to-work rows for {address} address", url)
    numbers = numbers_data.get("numbers")
    if not isinstance(numbers, list) or not numbers:
        raise PlaceTravelError(6, f"place page has no main-means-of-travel-to-work rows for {address} address", url)
    if len(numbers) > PLACE_TRAVEL_MAX_ROWS:
        raise PlaceTravelError(
            7,
            f"travel section exceeded the {PLACE_TRAVEL_MAX_ROWS} row bound",
            url,
        )

    place_name = _require_text(topic.get("classification_descriptor"), "the place name", url)
    classification = _require_text(topic.get("classification_label"), "the place classification", url)
    code = topic.get("classification_code")
    if isinstance(code, int) and not isinstance(code, bool):
        classification_code = str(code)
    else:
        classification_code = _require_text(code, "the place classification code", url)
    percent_unit = numbers_data.get("value_label") or section.get("graph_value_type") or "percent"
    if not isinstance(percent_unit, str) or not percent_unit.strip():
        percent_unit = "percent"
    collection = numbers_data.get("duration")
    collection_text = collection.strip() if isinstance(collection, str) and collection.strip() else None

    rows: list[dict[str, Any]] = []
    for number in numbers:
        if not isinstance(number, dict):
            raise PlaceTravelError(6, "travel row was not an object", url)
        indicator = number.get("confidentiality_indicator")
        if indicator is not None and not isinstance(indicator, str):
            raise PlaceTravelError(6, "travel row confidentiality indicator was not text", url)
        suppressed = bool(indicator)
        try:
            percent = _published_number(number.get("value"), suppressed=suppressed)
            count = _published_number(number.get("count_value"), suppressed=suppressed)
            lower = _published_number(number.get("lower_bounds"), suppressed=suppressed)
            upper = _published_number(number.get("upper_bounds"), suppressed=suppressed)
        except ValueError as exc:
            raise PlaceTravelError(6, f"travel row had an unreadable measure: {exc}", url) from exc
        mode = _require_text(number.get("variable1_descriptor"), "a travel mode label", url)
        mode_code = number.get("variable1_code")
        if isinstance(mode_code, int) and not isinstance(mode_code, bool):
            mode_code = str(mode_code)
        mode_code = _require_text(mode_code, "a travel mode code", url)
        period = _require_text(number.get("period"), "a travel period", url)
        row = {
            "place": place_name,
            "classification": classification,
            "classification_code": classification_code,
            "address": address,
            "concept": TRAVEL_CONCEPT,
            "mode": mode,
            "mode_code": mode_code,
            "period": period,
            "percent": percent,
            "count": count,
            "percent_unit": percent_unit.strip(),
            "count_unit": "people",
            "suppressed": suppressed,
            "confidentiality_indicator": indicator if suppressed else None,
            "lower_bounds": lower,
            "upper_bounds": upper,
        }
        if collection_text:
            row["collection"] = collection_text
        rows.append(row)
    if not any(row["percent"] is not None or row["count"] is not None or row["suppressed"] for row in rows):
        raise PlaceTravelError(6, "place page travel rows had no percent, count, or confidentiality indicator", url)
    return rows


def fetch_place_html(url: str) -> tuple[str, str]:
    try:
        body, _content_type, final_url = nzfetch.fetch_bytes(
            url,
            timeout=PLACE_TRAVEL_TIMEOUT,
            accept="text/html",
            allowed_hosts=frozenset({PLACE_HOST}),
            max_bytes=PLACE_TRAVEL_MAX_BYTES,
        )
    except nzfetch.RateLimited as exc:
        raise PlaceTravelError(4, f"upstream unavailable: HTTP 429 {exc}", url, exc.retry_after) from exc
    except nzfetch.ResponseTooLarge as exc:
        raise PlaceTravelError(
            7,
            f"place page exceeded the {PLACE_TRAVEL_MAX_BYTES} byte bound: {exc}",
            url,
        ) from exc
    except nzfetch.Blocked as exc:
        raise PlaceTravelError(4, f"upstream unavailable: {exc}", url) from exc
    except nzfetch.FetchError as exc:
        message = str(exc)
        if "HTTP 404" in message:
            raise PlaceTravelError(2, f"place was not found: {url}", url) from exc
        raise PlaceTravelError(5, f"upstream unavailable: {message}", url) from exc
    requested = urllib.parse.urlsplit(url)
    final = urllib.parse.urlsplit(final_url)
    if final.scheme != "https" or (final.hostname or "").lower().rstrip(".") != PLACE_HOST:
        raise PlaceTravelError(4, f"redirect left the official place host: {final_url}", url)
    if final.path.rstrip("/") != requested.path.rstrip("/") or final.query or final.fragment:
        raise PlaceTravelError(6, f"place page redirected away from the requested place: {final_url}", url)
    if len(body) > PLACE_TRAVEL_MAX_BYTES:
        raise PlaceTravelError(7, f"place page exceeded the {PLACE_TRAVEL_MAX_BYTES} byte bound", url)
    return body.decode("utf-8", "replace"), urllib.parse.urlunsplit((final.scheme, final.netloc, final.path, "", ""))


def load_place_travel(
    place: str,
    address: str,
    *,
    fetcher: Callable[[str], tuple[str, str]] | None = None,
) -> dict[str, Any]:
    address_key = address.strip().lower() if isinstance(address, str) else ""
    if address_key not in TRAVEL_SECTIONS:
        raise PlaceTravelError(2, "address must be usual or workplace", PLACE_INDEX_URL)
    token = normalize_place_token(place)
    url = place_travel_url(token)
    text, final_url = (fetcher or fetch_place_html)(url)
    rows = parse_place_travel_html(text, url=final_url, address=address_key)
    periods: list[str] = []
    for row in rows:
        if row["period"] not in periods:
            periods.append(row["period"])
    latest = periods[0] if len(periods) == 1 else ", ".join(periods)
    meta = provenance(final_url, "Stats NZ", licence=PLACE_LICENCE, latest_data=latest)
    return result_envelope(rows, meta)


def fmt_travel_percent(value: int | float) -> str:
    if isinstance(value, int) or (isinstance(value, float) and value.is_integer()):
        return f"{int(value):,}%"
    text = f"{value:,.10f}".rstrip("0").rstrip(".")
    return f"{text}%"


def render_place_travel(payload: dict[str, Any]) -> None:
    rows = payload["results"]
    meta = payload["meta"]
    first = rows[0]
    address_label = "usual residence" if first["address"] == "usual" else "workplace"
    print(f"Stats NZ {first['concept']}: {first['place']} ({first['classification']})")
    print(f"Address: {address_label}")
    print(f"Period: {meta.get('latest_data') or first['period']}")
    for row in rows:
        if row["suppressed"] and row["percent"] is None and row["count"] is None:
            print(f"{row['mode']}: suppressed ({row['confidentiality_indicator']})")
            continue
        percent = "n/a" if row["percent"] is None else fmt_travel_percent(row["percent"])
        count = "n/a" if row["count"] is None else f"{fmt_int(row['count'])} people"
        suffix = f" suppressed ({row['confidentiality_indicator']})" if row["suppressed"] else ""
        print(f"{row['mode']}: {percent} ({count}){suffix}")
    print(f"Source: {meta['publisher']}")
    if meta.get("licence"):
        print(f"Licence: {meta['licence']}")
    print(meta["source_url"])


def cmd_place_travel(args: argparse.Namespace) -> None:
    try:
        payload = load_place_travel(args.place, args.address)
    except PlaceTravelError as exc:
        if args.json:
            meta = provenance(exc.source_url, "Stats NZ", licence=PLACE_LICENCE)
            emit_json(error_envelope(exc.code, exc.message, meta, retry_after=exc.retry_after))
        else:
            print(f"stats-nz: {exc.message}", file=sys.stderr)
        raise SystemExit(exc.code)

    def render(p: dict[str, Any]) -> None:
        render_place_travel(p)

    output(payload, args.json, render)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only CLI for public Stats NZ data.")
    sub = parser.add_subparsers(dest="command")

    cpi = sub.add_parser("cpi", help="Consumers price index quarterly all-groups index")
    cpi.add_argument("--from", dest="from_date", help="Start period as YYYY-MM, YYYY-MM-DD, or YYYY.MM")
    cpi.add_argument("--to", dest="to_date", help="End period as YYYY-MM, YYYY-MM-DD, or YYYY.MM")
    cpi.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    cpi.set_defaults(func=cmd_cpi)

    fpi = sub.add_parser("fpi", help="Food price index monthly all-groups index")
    fpi.add_argument("--from", dest="from_date", help="Start period as YYYY-MM, YYYY-MM-DD, or YYYY.MM")
    fpi.add_argument("--to", dest="to_date", help="End period as YYYY-MM, YYYY-MM-DD, or YYYY.MM")
    fpi.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    fpi.set_defaults(func=cmd_fpi)

    population = sub.add_parser("population", help="National, projected, or regional population")
    population.add_argument("--region", help="Regional council name or place-summary slug")
    population.add_argument("--projection", type=int, help="Projection year for national population")
    population.add_argument("--scenario", default="50th percentile", help="Projection scenario name")
    population.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    population.set_defaults(func=cmd_population)

    migration = sub.add_parser("migration", help="Latest estimated long-term migration totals")
    migration.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    migration.set_defaults(func=cmd_migration)

    gdp = sub.add_parser("gdp", help="Quarterly headline GDP series")
    gdp.add_argument("--from", dest="from_date", help="Start period as YYYY-MM, YYYY-MM-DD, or YYYY.MM")
    gdp.add_argument("--to", dest="to_date", help="End period as YYYY-MM, YYYY-MM-DD, or YYYY.MM")
    gdp.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    gdp.set_defaults(func=cmd_gdp)

    series = sub.add_parser("series", help="Fetch a wired Stats NZ Series_reference")
    series.add_argument("id", help="Stats NZ Series_reference, for example CPIQ.SE9A")
    series.add_argument("--from", dest="from_date", help="Start period as YYYY-MM, YYYY-MM-DD, or YYYY.MM")
    series.add_argument("--to", dest="to_date", help="End period as YYYY-MM, YYYY-MM-DD, or YYYY.MM")
    series.add_argument("--limit", type=int, default=12, help="Maximum observations to print from the end of the range")
    series.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    series.set_defaults(func=cmd_series)

    search = sub.add_parser("search", help="Search the Stats NZ CSV catalogue")
    search.add_argument("query", help="Search terms")
    search.add_argument("--limit", type=int, default=10, help="Maximum catalogue results")
    search.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    search.set_defaults(func=cmd_search)

    place_travel = sub.add_parser(
        "place-travel",
        help="Main means of travel to work for one Stats NZ place summary",
    )
    place_travel.add_argument("place", help="Official place path CLASS/slug, for example UR/auckland")
    place_travel.add_argument(
        "--address",
        default="usual",
        help="usual residence (default) or workplace address",
    )
    place_travel.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    place_travel.set_defaults(func=cmd_place_travel)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 2
    if hasattr(args, "limit") and args.limit is not None and args.limit < 1:
        die("--limit must be at least 1")
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
