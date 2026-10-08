#!/usr/bin/env python3
"""Keyless Auckland housing update, residential capacity and source discovery."""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
import zipfile
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))
import nzfetch  # noqa: E402
from housing import council_records, capacity_records, hud_records, matches, normalise, select_periods, typology_records  # noqa: E402
from provenance import error_envelope, provenance, result_envelope  # noqa: E402
from sources import (  # noqa: E402
    BUSINESS_URL, CAPACITY_URL, COUNCIL, DEMOLITIONS_URL, FEASIBILITY_URL,
    HOSTS, HOUSING_PAGE, HUD, HUD_PAGE, SOURCES,
)
from workbook import SchemaError  # noqa: E402


class InputError(ValueError):
    pass


class UnsupportedError(ValueError):
    pass


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise InputError(message)


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)


def download_link(text, page, marker):
    parser = Links()
    parser.feed(text)
    links = []
    for href in parser.links:
        url = urljoin(page, href)
        parsed = urlparse(url)
        if marker in parsed.path.casefold() and parsed.path.casefold().endswith(".xlsx"):
            if parsed.scheme != "https" or parsed.hostname not in HOSTS or parsed.username or parsed.password:
                raise SchemaError("Download link leaves the declared public source hosts")
            if url not in links:
                links.append(url)
    if len(links) != 1:
        raise SchemaError(f"Expected one current XLSX download on {page}; found {len(links)}")
    return links[0]


def fetch_workbook(url):
    return nzfetch.fetch_bytes(url, timeout=10, allowed_hosts=HOSTS)[0]


def business_inventory(body):
    try:
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            groups = {}
            if len(archive.infolist()) > 10000:
                raise SchemaError("Business archive exceeds the member limit")
            for info in archive.infolist():
                if ".gdb/" in info.filename and not info.is_dir():
                    name = info.filename.split(".gdb/", 1)[0] + ".gdb"
                    group = groups.setdefault(name, {"geodatabase": name, "files": 0, "uncompressed_bytes": 0,
                                                     "record_type": "archive_inventory",
                                                     "note": "Requires GIS software to read features; these are archive member counts."})
                    group["files"] += 1
                    group["uncompressed_bytes"] += info.file_size
            if not groups:
                raise SchemaError("Business ZIP contains no File Geodatabases")
            return list(groups.values())
    except zipfile.BadZipFile as exc:
        raise SchemaError("Business download is not a ZIP archive") from exc


def build_parser():
    parser = ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sources = sub.add_parser("sources", help="list the verified source registry and limitations (offline)")
    sources.add_argument("--json", action="store_true")
    housing = sub.add_parser("housing-update", help="read the latest Council datasheet or HUD delivery download")
    housing.add_argument("--month", help="observation month YYYY-MM; default is latest available per series")
    housing.add_argument("--area", help="local-board/region name substring; accents and punctuation ignored")
    housing.add_argument("--source", choices=("council", "hud"), default="council")
    housing.add_argument("--json", action="store_true")
    capacity = sub.add_parser("capacity", help="read 2022/23 PC78 capacity summaries or the business ZIP inventory")
    capacity.add_argument("--area", help="local-board name substring")
    capacity.add_argument("--zone", help="zone filtering is unavailable in the XLSX summaries; use nz-arcgis for maps")
    capacity.add_argument("--detail", choices=("totals", "typology"), default="totals")
    capacity.add_argument("--dataset", choices=("residential", "business"), default="residential")
    capacity.add_argument("--json", action="store_true")
    demolitions = sub.add_parser("demolitions", help="explain the PDF-only demolition source limitation (exit 7)")
    demolitions.add_argument("--area", help="reserved for a verified structured extract; currently unsupported")
    demolitions.add_argument("--json", action="store_true")
    return parser


def validate_month(value):
    if value is not None:
        if not re.fullmatch(r"\d{4}-\d{2}", value):
            raise InputError("--month must be an observation month in YYYY-MM format")
        try:
            date.fromisoformat(value + "-01")
        except ValueError as exc:
            raise InputError("--month must be a valid observation month in YYYY-MM format") from exc


def emit(payload, json_output):
    if json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    elif "error" in payload:
        print(payload["error"]["message"], file=sys.stderr)
    else:
        print(f"{len(payload['results'])} result(s) — {payload['meta']['publisher']}")
        print(f"Source: {payload['meta']['source_url']}")
        for record in payload["results"]:
            if "id" in record:
                print(f"{record['id']}: {record['format']} — {record['status']}")
                print(f"  {record.get('download_url', record['source_url'])}")
            elif "measures" in record:
                print(f"{record['period']} | {record['area']} | {record['sheet']}")
                print("  " + "; ".join(f"{key.replace('_', ' ')}: {value:,}" if value is not None
                                       else f"{key.replace('_', ' ')}: unavailable"
                                       for key, value in record["measures"].items()))
            elif "plan_enabled_capacity" in record:
                print(f"{record['area']}: {record['plan_enabled_capacity']:,} plan-enabled; "
                      f"{record['feasible_capacity']:,} feasible dwellings ({record['scenario']})")
            elif "built_form" in record:
                value = record['feasible_capacity']
                print(f"{record['area']} | {record['selection']} | {record['built_form']}: "
                      f"{value:,} feasible dwellings" if value is not None else f"{record['area']}: unavailable")
            elif "geodatabase" in record:
                print(f"{record['geodatabase']}: {record['files']} files, "
                      f"{record['uncompressed_bytes']:,} uncompressed bytes")
            else:
                dimensions = "; ".join(f"{d['name']}: {d['value']}" for d in record["dimensions"])
                print(f"{record['period']} | {record['area']} | {dimensions}: {record['value']} homes")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    json_output = "--json" in argv
    meta = provenance(HOUSING_PAGE, COUNCIL)
    try:
        args = build_parser().parse_args(argv)
        if args.command == "sources":
            stamp = meta["retrieved_at"]
            results = [{**record, "retrieved_at": stamp, "retrieval_kind": "source_registry",
                        "verified_on": "2026-10-08"} for record in SOURCES]
        elif args.command == "demolitions":
            meta = provenance(DEMOLITIONS_URL, "Kāinga Ora — Homes and Communities", latest_data="2025")
            raise UnsupportedError("Demolished social housing sites are published as a PDF OIA release, not a verified structured keyless download. Live PDF access was blocked on 8 October 2026. No site records or area filter are available. See " + DEMOLITIONS_URL)
        elif args.command == "housing-update":
            hud = args.source == "hud"
            page = HUD_PAGE if hud else HOUSING_PAGE
            publisher = HUD if hud else COUNCIL
            licence = "CC BY 4.0, except identified third-party material" if hud else None
            meta = provenance(page, publisher, licence=licence)
            validate_month(args.month)
            if args.area is not None and not normalise(args.area):
                raise InputError("--area must contain a name")
            marker = "housing-dashboard-data-download" if hud else "housing-update-datasheet"
            text = nzfetch.fetch_text(page, timeout=10, allowed_hosts=HOSTS)
            url = download_link(text, page, marker)
            meta = provenance(url, publisher, licence=licence)
            body = fetch_workbook(url)
            if hud:
                results, latest = hud_records(body, args.area or "Auckland", args.month)
            else:
                records = council_records(body)
                latest = max(r["period"] for r in records)
                results = [r for r in select_periods(records, args.month) if matches(r["area"], args.area)]
            meta = provenance(url, publisher, licence=licence, latest_data=latest)
        else:
            url = BUSINESS_URL if args.dataset == "business" else FEASIBILITY_URL if args.detail == "typology" else CAPACITY_URL
            meta = provenance(url, COUNCIL, latest_data="2023" if url != CAPACITY_URL else "October 2023")
            if args.zone is not None:
                raise UnsupportedError("Zone filtering requires site-level GIS data; these workbooks publish local-board summaries. Use nz-arcgis for PC120 zoning maps; the 2023 capacity model is a different baseline.")
            if args.area is not None and not normalise(args.area):
                raise InputError("--area must contain a name")
            if args.dataset == "business":
                if args.area or args.detail != "totals":
                    raise UnsupportedError("Business capacity is a File Geodatabase ZIP. Area/typology filtering requires GIS software; this command returns its archive inventory.")
                results = business_inventory(fetch_workbook(url))
            else:
                parser = typology_records if args.detail == "typology" else capacity_records
                results = [r for r in parser(fetch_workbook(url)) if matches(r["area"], args.area)]
        emit(result_envelope(results, meta), json_output)
        return 0
    except (InputError, UnsupportedError, SchemaError, nzfetch.FetchError) as exc:
        retry_after = None
        if isinstance(exc, InputError):
            code = 2
        elif isinstance(exc, UnsupportedError):
            code = 7
        elif isinstance(exc, SchemaError):
            code = 6
        elif isinstance(exc, nzfetch.Blocked):
            code = 4
            retry_after = getattr(exc, "retry_after", None)
        else:
            code = 5
        message = "network error: " + str(exc) if isinstance(exc, nzfetch.FetchError) else str(exc)
        emit(error_envelope(code, message, meta, retry_after=retry_after), json_output)
        return code


if __name__ == "__main__":
    raise SystemExit(main())
