#!/usr/bin/env python3
"""Household hardship and wellbeing CLI for New Zealand.

Read-only stdlib wrapper around the Stats NZ Household Economic Survey (HES)
"Household Wellbeing" releases, distributed on data.govt.nz via the CKAN API.
Covers material hardship, income adequacy, housing affordability, low-income
counts, and the Gini coefficient of income inequality — by region or ethnicity,
with 95% confidence intervals.

No login, API key, browser automation, cache, or data mutation. Each dataset
ships as a ZIP-of-CSV unpacked with stdlib zipfile + csv only.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import pathlib
import re
import sys
import urllib.parse
import zipfile
from typing import Any, Callable

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "lib"))
import nzfetch  # noqa: E402

CKAN_BASE = "https://catalogue.data.govt.nz/api/3/action"
# Default release: the most recent HES "Household Wellbeing" dataset confirmed to
# carry the full material-hardship / affordability / income-adequacy table set.
DEFAULT_DATASET = "household-economic-survey-2020-2021-household-wellbeing-including-maori-households"
UA = "household-hardship-nz-skill/1.0 (+https://github.com/thecolab-ai/.skills)"

# Resource (ZIP) selection inside a dataset. The CKAN package lists several
# resources; we pick by substring of the resource name.
RESOURCE_HOUSEHOLDS = "household - income series"
RESOURCE_LOWINCOME = "households - low income series"


def die(message: str, code: int = 1) -> None:
    print(f"household-hardship-nz: {message}", file=sys.stderr)
    raise SystemExit(code)


def read_json(url: str, timeout: int = 60) -> dict[str, Any]:
    try:
        payload = nzfetch.fetch_json(url, timeout=timeout)
    except nzfetch.Blocked as e:
        die(f"network error calling {url}: {e}")
    except nzfetch.FetchError as e:
        die(str(e))
    if not payload.get("success"):
        die(f"CKAN API reported failure for {url}")
    return payload["result"]


def read_bytes(url: str, timeout: int = 90) -> bytes:
    try:
        body, _ct, _final = nzfetch.fetch_bytes(url, timeout=timeout)
    except nzfetch.Blocked as e:
        die(f"network error calling {url}: {e}")
    except nzfetch.FetchError as e:
        die(str(e))
    return body


def package_show(dataset: str) -> dict[str, Any]:
    url = f"{CKAN_BASE}/package_show?" + urllib.parse.urlencode({"id": dataset})
    return read_json(url)


def resource_url(dataset: str, name_substr: str) -> str:
    result = package_show(dataset)
    wanted = name_substr.lower()
    for res in result.get("resources", []):
        if wanted in str(res.get("name", "")).lower():
            return str(res["url"])
    available = ", ".join(str(r.get("name", "")) for r in result.get("resources", []))
    die(f"dataset '{dataset}' has no resource matching '{name_substr}' (available: {available})")


def zip_csv(url: str, member_substr: str) -> list[dict[str, str]]:
    """Download a ZIP-of-CSV and return rows from the first member whose name
    contains member_substr, as a list of dict rows (DictReader)."""
    data = read_bytes(url)
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as e:
        die(f"invalid ZIP archive from {url}: {e}")
    wanted = member_substr.lower()
    target = next((n for n in archive.namelist() if wanted in n.lower()), None)
    if target is None:
        die(f"ZIP from {url} has no CSV matching '{member_substr}' (members: {', '.join(archive.namelist())})")
    with archive.open(target) as raw:
        text = io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")
        try:
            return list(csv.DictReader(text))
        except csv.Error as e:
            die(f"invalid CSV {target} in {url}: {e}")


def as_int(raw: Any) -> int | None:
    if raw is None:
        return None
    text = str(raw).strip().replace(",", "")
    if not text:
        return None
    try:
        return int(round(float(text)))
    except ValueError:
        return None


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


def fmt_int(value: Any) -> str:
    number = as_int(value)
    return "n/a" if number is None else f"{number:,}"


def emit_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def output(payload: dict[str, Any], json_flag: bool, render: Callable[[dict[str, Any]], None]) -> None:
    if json_flag:
        emit_json(payload)
    else:
        render(payload)


def norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(text).lower())


def filter_rows(rows: list[dict[str, str]], key: str, value: str | None) -> list[dict[str, str]]:
    if not value:
        return rows
    want = norm(value)
    matched = [r for r in rows if norm(r.get(key, "")) == want]
    if matched:
        return matched
    # fall back to substring match (e.g. "hawkes bay" vs "Hawke's Bay")
    matched = [r for r in rows if want in norm(r.get(key, ""))]
    if not matched:
        available = sorted({r.get(key, "") for r in rows})
        die(f"no rows where {key} matches '{value}'; available: {', '.join(available)}")
    return matched


def serialize_estimate(row: dict[str, str], extra: dict[str, str]) -> dict[str, Any]:
    item: dict[str, Any] = {
        "households": as_int(row.get("Households")),
        "lci": as_int(row.get("LCI")),
        "uci": as_int(row.get("UCI")),
        "rse_percent": as_float(row.get("RSE")),
        "flag": row.get("Flag") or None,
    }
    for out_key, in_key in extra.items():
        item[out_key] = row.get(in_key)
    return item


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_search(args: argparse.Namespace) -> None:
    url = f"{CKAN_BASE}/package_search?" + urllib.parse.urlencode(
        {"q": args.query, "rows": args.limit}
    )
    result = read_json(url)
    datasets = [
        {"name": r.get("name"), "title": r.get("title"), "organisation": (r.get("organization") or {}).get("title")}
        for r in result.get("results", [])
    ]
    payload = {
        "source": "Stats NZ / data.govt.nz (CKAN)",
        "query": args.query,
        "total_matches": result.get("count"),
        "count": len(datasets),
        "datasets": datasets,
    }

    def render(p: dict[str, Any]) -> None:
        print(f"data.govt.nz HES wellbeing search for: {p['query']} ({p['total_matches']} total)")
        for d in p["datasets"]:
            print(f"- {d['title']}")
            print(f"  id: {d['name']}")

    output(payload, args.json, render)


def cmd_datasets(args: argparse.Namespace) -> None:
    url = f"{CKAN_BASE}/package_search?" + urllib.parse.urlencode(
        {"q": "household economic survey wellbeing", "rows": 50}
    )
    result = read_json(url)
    datasets = [
        {"name": r.get("name"), "title": r.get("title")}
        for r in result.get("results", [])
        if "wellbeing" in str(r.get("title", "")).lower() or "warm and dry" in str(r.get("title", "")).lower()
    ]
    payload = {
        "source": "Stats NZ / data.govt.nz (CKAN)",
        "default_dataset": DEFAULT_DATASET,
        "count": len(datasets),
        "datasets": datasets,
    }

    def render(p: dict[str, Any]) -> None:
        print(f"HES Household Wellbeing releases (default: {p['default_dataset']})")
        for d in p["datasets"]:
            print(f"- {d['title']}")
            print(f"  id: {d['name']}")

    output(payload, args.json, render)


def cmd_hardship(args: argparse.Namespace) -> None:
    url = resource_url(args.dataset, RESOURCE_HOUSEHOLDS)
    if args.ethnicity:
        rows = zip_csv(url, "t2a_hardship_eth.csv")
        rows = filter_rows(rows, "Ethnicity", args.ethnicity if args.ethnicity is not True else None)
        group_field, group_in = "ethnicity", "Ethnicity"
    else:
        rows = zip_csv(url, "t2a_hardship_rc.csv")
        rows = filter_rows(rows, "Region", args.region)
        group_field, group_in = "region", "Region"
    estimates = [
        serialize_estimate(r, {group_field: group_in, "hardship": "Hardship"})
        for r in rows
    ]
    payload = {
        "source": "Stats NZ Household Economic Survey (Household Wellbeing)",
        "dataset": args.dataset,
        "measure": "material hardship",
        "grouping": group_field,
        "count": len(estimates),
        "estimates": estimates,
    }

    def render(p: dict[str, Any]) -> None:
        print(f"Material hardship households by {p['grouping']} ({p['dataset']})")
        for e in p["estimates"]:
            label = e.get("region") or e.get("ethnicity")
            print(f"- {label} | {e['hardship']}: {fmt_int(e['households'])} (95% CI {fmt_int(e['lci'])}-{fmt_int(e['uci'])})")

    output(payload, args.json, render)


def cmd_income_adequacy(args: argparse.Namespace) -> None:
    url = resource_url(args.dataset, RESOURCE_HOUSEHOLDS)
    if args.ethnicity:
        rows = zip_csv(url, "t3b_adeqinc_eth.csv")
        rows = filter_rows(rows, "Ethnicity", args.ethnicity if args.ethnicity is not True else None)
        group_field, group_in = "ethnicity", "Ethnicity"
    else:
        rows = zip_csv(url, "t3a_adeqinc_reg.csv")
        rows = filter_rows(rows, "Region", args.region)
        group_field, group_in = "region", "Region"
    estimates = [
        serialize_estimate(r, {group_field: group_in, "income_adequacy": "AdeqInc"})
        for r in rows
    ]
    payload = {
        "source": "Stats NZ Household Economic Survey (Household Wellbeing)",
        "dataset": args.dataset,
        "measure": "income adequacy",
        "grouping": group_field,
        "count": len(estimates),
        "estimates": estimates,
    }

    def render(p: dict[str, Any]) -> None:
        print(f"Income adequacy households by {p['grouping']} ({p['dataset']})")
        for e in p["estimates"]:
            label = e.get("region") or e.get("ethnicity")
            print(f"- {label} | {e['income_adequacy']}: {fmt_int(e['households'])} (95% CI {fmt_int(e['lci'])}-{fmt_int(e['uci'])})")

    output(payload, args.json, render)


def cmd_affordability(args: argparse.Namespace) -> None:
    resource = RESOURCE_LOWINCOME if args.lowincome else RESOURCE_HOUSEHOLDS
    url = resource_url(args.dataset, resource)
    suffix = "_lowincome" if args.lowincome else ""
    if args.ethnicity:
        rows = zip_csv(url, f"t1c_affordability_eth{suffix}.csv")
        rows = filter_rows(rows, "Ethnicity", args.ethnicity if args.ethnicity is not True else None)
        group_field, group_in = "ethnicity", "Ethnicity"
    elif args.tenure:
        rows = zip_csv(url, f"t1b_affordability_ten{suffix}.csv")
        rows = filter_rows(rows, "Tenure", args.tenure if args.tenure is not True else None)
        group_field, group_in = "tenure", "Tenure"
    else:
        rows = zip_csv(url, f"t1a_affordability_reg{suffix}.csv")
        rows = filter_rows(rows, "Region", args.region)
        group_field, group_in = "region", "Region"
    if args.threshold:
        threshold = args.threshold.strip().rstrip("%") + "%"
        want = norm(f"More than {threshold}")
        rows = [r for r in rows if norm(r.get("Affordability", "")) == want]
        if not rows:
            die(f"no affordability rows for threshold '{args.threshold}' (try 30%, 40%, or 50%)")
    estimates = [
        serialize_estimate(r, {group_field: group_in, "affordability": "Affordability"})
        for r in rows
    ]
    payload = {
        "source": "Stats NZ Household Economic Survey (Household Wellbeing)",
        "dataset": args.dataset,
        "measure": "housing affordability (housing cost as share of income)",
        "low_income_only": bool(args.lowincome),
        "grouping": group_field,
        "count": len(estimates),
        "estimates": estimates,
    }

    def render(p: dict[str, Any]) -> None:
        scope = " (low-income households)" if p["low_income_only"] else ""
        print(f"Housing affordability by {p['grouping']}{scope} ({p['dataset']})")
        for e in p["estimates"]:
            label = e.get("region") or e.get("ethnicity") or e.get("tenure")
            print(f"- {label} | {e['affordability']}: {fmt_int(e['households'])} (95% CI {fmt_int(e['lci'])}-{fmt_int(e['uci'])})")

    output(payload, args.json, render)


def cmd_low_income(args: argparse.Namespace) -> None:
    url = resource_url(args.dataset, RESOURCE_HOUSEHOLDS)
    if args.ethnicity:
        rows = zip_csv(url, "t4b_lowinc_eth.csv")
        rows = filter_rows(rows, "Ethnicity", args.ethnicity if args.ethnicity is not True else None)
        group_field, group_in = "ethnicity", "Ethnicity"
    else:
        rows = zip_csv(url, "t4a_lowinc_reg.csv")
        rows = filter_rows(rows, "Region", args.region)
        group_field, group_in = "region", "Region"
    estimates = [
        serialize_estimate(r, {group_field: group_in, "low_income_status": "LowHhldIncAHC"})
        for r in rows
    ]
    payload = {
        "source": "Stats NZ Household Economic Survey (Household Wellbeing)",
        "dataset": args.dataset,
        "measure": "low-income households (after housing costs)",
        "grouping": group_field,
        "count": len(estimates),
        "estimates": estimates,
    }

    def render(p: dict[str, Any]) -> None:
        print(f"Low-income households by {p['grouping']} ({p['dataset']})")
        for e in p["estimates"]:
            label = e.get("region") or e.get("ethnicity")
            print(f"- {label} | {e['low_income_status']}: {fmt_int(e['households'])} (95% CI {fmt_int(e['lci'])}-{fmt_int(e['uci'])})")

    output(payload, args.json, render)


def cmd_gini(args: argparse.Namespace) -> None:
    url = resource_url(args.dataset, RESOURCE_HOUSEHOLDS)
    if args.ethnicity:
        rows = zip_csv(url, "t5b_gini_eth.csv")
        rows = filter_rows(rows, "Ethnicity", args.ethnicity if args.ethnicity is not True else None)
        group_field, group_in = "ethnicity", "Ethnicity"
    else:
        rows = zip_csv(url, "t5a_gini_reg.csv")
        rows = filter_rows(rows, "Region", args.region)
        group_field, group_in = "region", "Region"
    estimates = []
    for r in rows:
        item: dict[str, Any] = {
            group_field: r.get(group_in),
            "gini": as_float(r.get("Gini")),
            "lci": as_float(r.get("LCI")),
            "uci": as_float(r.get("UCI")),
            "rse_percent": as_float(r.get("RSE")),
            "flag": r.get("Flag") or None,
        }
        estimates.append(item)
    payload = {
        "source": "Stats NZ Household Economic Survey (Household Wellbeing)",
        "dataset": args.dataset,
        "measure": "Gini coefficient of disposable household income inequality",
        "grouping": group_field,
        "count": len(estimates),
        "estimates": estimates,
    }

    def render(p: dict[str, Any]) -> None:
        print(f"Gini coefficient by {p['grouping']} ({p['dataset']})")
        for e in p["estimates"]:
            label = e.get("region") or e.get("ethnicity")
            gini = e["gini"]
            print(f"- {label}: {gini if gini is not None else 'n/a'} (95% CI {e['lci']}-{e['uci']})")

    output(payload, args.json, render)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only CLI for NZ household hardship and wellbeing (Stats NZ HES via data.govt.nz)."
    )
    sub = parser.add_subparsers(dest="command")

    def add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--dataset", default=DEFAULT_DATASET, help="CKAN dataset id (default: 2020-2021 wellbeing release)")
        p.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    search = sub.add_parser("search", help="Search data.govt.nz for HES wellbeing/hardship datasets")
    search.add_argument("query", help="Search terms")
    search.add_argument("--limit", type=int, default=10, help="Maximum datasets to return")
    search.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    search.set_defaults(func=cmd_search)

    datasets = sub.add_parser("datasets", help="List available HES Household Wellbeing releases")
    datasets.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    datasets.set_defaults(func=cmd_datasets)

    hardship = sub.add_parser("hardship", help="Material hardship household counts by region or ethnicity")
    hardship.add_argument("--region", help="Filter to a region, for example auckland")
    hardship.add_argument("--ethnicity", nargs="?", const=True, default=False, help="Group by ethnicity (optionally a single ethnicity)")
    add_common(hardship)
    hardship.set_defaults(func=cmd_hardship)

    adequacy = sub.add_parser("income-adequacy", help="Income adequate vs not adequate, by region or ethnicity")
    adequacy.add_argument("--region", help="Filter to a region, for example wellington")
    adequacy.add_argument("--ethnicity", nargs="?", const=True, default=False, help="Group by ethnicity (optionally a single ethnicity)")
    add_common(adequacy)
    adequacy.set_defaults(func=cmd_income_adequacy)

    afford = sub.add_parser("affordability", help="Households spending over 30/40/50 percent of income on housing")
    afford.add_argument("--region", help="Filter to a region")
    afford.add_argument("--ethnicity", nargs="?", const=True, default=False, help="Group by ethnicity (optionally a single ethnicity)")
    afford.add_argument("--tenure", nargs="?", const=True, default=False, help="Group by tenure (Owned / Renting)")
    afford.add_argument("--threshold", help="Housing cost share of income threshold: 30, 40, or 50 (percent)")
    afford.add_argument("--lowincome", action="store_true", help="Restrict to low-income households")
    add_common(afford)
    afford.set_defaults(func=cmd_affordability)

    lowinc = sub.add_parser("low-income", help="Low-income household counts (after housing costs) by region or ethnicity")
    lowinc.add_argument("--region", help="Filter to a region")
    lowinc.add_argument("--ethnicity", nargs="?", const=True, default=False, help="Group by ethnicity (optionally a single ethnicity)")
    add_common(lowinc)
    lowinc.set_defaults(func=cmd_low_income)

    gini = sub.add_parser("gini", help="Gini coefficient of income inequality by region or ethnicity")
    gini.add_argument("--region", help="Filter to a region")
    gini.add_argument("--ethnicity", nargs="?", const=True, default=False, help="Group by ethnicity (optionally a single ethnicity)")
    add_common(gini)
    gini.set_defaults(func=cmd_gini)

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
