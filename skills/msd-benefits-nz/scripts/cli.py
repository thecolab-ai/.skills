#!/usr/bin/env python3
"""MSD (Ministry of Social Development) benefit statistics CLI.

Read-only stdlib wrapper around the public MSD quarterly benefit-fact-sheet
CSV releases. No login, API key, browser automation, cache, or data mutation.

IMPORTANT: the wired CSVs are the December 2019 "benefit fact sheets" release.
This is a frozen historical series whose latest quarter is Dec_19. It is the
last release published in this exact flat-CSV schema and is treated here as a
stable historical reference set, not a live current-quarter feed.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import pathlib
import re
import sys
from collections import defaultdict
from typing import Any, Callable

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "lib"))
import nzfetch  # noqa: E402

BASE = (
    "https://www.msd.govt.nz/documents/about-msd-and-our-work/"
    "publications-resources/statistics/benefit/2019/"
)

DATASETS = {
    "national": {
        "url": BASE + "national-level-benefit-data-dec-19.csv",
        "label": "MSD national-level benefit data (Dec 2019 release)",
        "age_field": "Age_Group",
    },
    "nzs": {
        "url": BASE + "new-zealand-superannuation-and-veteran-s-pension-dec-19.csv",
        "label": "MSD NZ Superannuation and Veteran's Pension data (Dec 2019 release)",
        "age_field": "Age_group2",
    },
    "region": {
        "url": BASE + "work-and-income-region-level-benefit-data-dec-19.csv",
        "label": "MSD Work and Income region-level benefit data (Dec 2019 release)",
        "age_field": "Age_Group",
    },
}

# Latest quarter present across the wired release (the Dec 2019 release runs
# through the Dec_19 quarter).
LATEST_QUARTER = "Dec_19"

UA = "msd-benefits-nz-skill/1.0 (+https://github.com/thecolab-ai/.skills)"

QUARTER_MONTH = {"Mar": 1, "Jun": 2, "Sep": 3, "Dec": 4}


def die(message: str, code: int = 1) -> None:
    print(f"msd-benefits-nz: {message}", file=sys.stderr)
    raise SystemExit(code)


def fetch_csv_rows(
    url: str,
    keep: Callable[[dict[str, str]], bool] | None = None,
    timeout: int = 180,
) -> tuple[list[dict[str, str]], str]:
    try:
        body, _ct, final_url = nzfetch.fetch_bytes(url, timeout=timeout)
    except nzfetch.Blocked as e:
        die(f"network error calling {url}: {e}")
    except nzfetch.FetchError as e:
        die(str(e))
    try:
        reader = csv.DictReader(io.StringIO(body.decode("utf-8-sig", "replace")))
        rows = [row for row in reader if keep is None or keep(row)]
        return rows, final_url
    except csv.Error as e:
        die(f"invalid CSV from {url}: {e}")
    return [], url  # unreachable; keeps type checkers happy


def quarter_key(raw: str) -> tuple[int, int]:
    match = re.fullmatch(r"([A-Za-z]{3})_(\d{2})", str(raw).strip())
    if not match or match.group(1).title() not in QUARTER_MONTH:
        return (0, 0)
    return (2000 + int(match.group(2)), QUARTER_MONTH[match.group(1).title()])


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


def ci_eq(a: str, b: str) -> bool:
    return a.strip().lower() == b.strip().lower()


def resolve_group(rows: list[dict[str, str]], wanted: str | None) -> str | None:
    """Map a user-supplied --group to an exact Benefit_Group value (case-insensitive)."""
    if not wanted:
        return None
    groups = sorted({row["Benefit_Group"] for row in rows})
    for g in groups:
        if ci_eq(g, wanted):
            return g
    # substring fallback
    matches = [g for g in groups if wanted.strip().lower() in g.lower()]
    if len(matches) == 1:
        return matches[0]
    die(
        f"unknown benefit group '{wanted}'. Available: " + ", ".join(groups)
    )
    return None


def resolve_region(rows: list[dict[str, str]], wanted: str) -> str:
    regions = sorted({row["Region"] for row in rows})
    for r in regions:
        if ci_eq(r, wanted):
            return r
    matches = [r for r in regions if wanted.strip().lower() in r.lower()]
    if len(matches) == 1:
        return matches[0]
    die(f"unknown region '{wanted}'. Available: " + ", ".join(regions))
    return ""


def aggregate(
    rows: list[dict[str, str]],
    dims: list[str],
) -> list[dict[str, Any]]:
    """Sum Count grouped by the requested dimension fields."""
    buckets: dict[tuple, int] = defaultdict(int)
    for row in rows:
        count = as_int(row.get("Count"))
        if count is None:
            continue
        key = tuple(row.get(dim, "") for dim in dims)
        buckets[key] += count
    breakdown = []
    for key, total in buckets.items():
        item = {dim: val for dim, val in zip(dims, key)}
        item["count"] = total
        breakdown.append(item)
    breakdown.sort(key=lambda x: (-x["count"], tuple(str(x.get(d, "")) for d in dims)))
    return breakdown


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #


def cmd_list_quarters(args: argparse.Namespace) -> None:
    ds = DATASETS[args.csv]
    rows, final_url = fetch_csv_rows(ds["url"])
    quarters = sorted({row["Quarter"] for row in rows}, key=quarter_key)
    payload = {
        "source": "Ministry of Social Development",
        "dataset": ds["label"],
        "csv": args.csv,
        "url": final_url,
        "quarters": quarters,
        "latest_quarter": quarters[-1] if quarters else None,
        "note": "Frozen historical release; latest quarter is the last in this series.",
    }

    def render(p: dict[str, Any]) -> None:
        print(f"MSD {p['csv']} quarters: {', '.join(p['quarters'])}")
        print(f"Latest available quarter: {p['latest_quarter']}")
        print(f"Source: {p['dataset']}")
        print(p["url"])

    output(payload, args.json, render)


def cmd_main_benefits(args: argparse.Namespace) -> None:
    ds = DATASETS["national"]
    quarter = args.quarter or LATEST_QUARTER
    rows, final_url = fetch_csv_rows(ds["url"], lambda r: r.get("Quarter") == quarter)
    if not rows:
        all_rows, _ = fetch_csv_rows(ds["url"])
        quarters = sorted({r["Quarter"] for r in all_rows}, key=quarter_key)
        die(f"no rows for quarter '{quarter}'. Available quarters: {', '.join(quarters)}")

    group = resolve_group(rows, args.group)
    if group:
        rows = [r for r in rows if r["Benefit_Group"] == group]

    dims: list[str] = []
    if args.gender:
        dims.append("Gender")
    if args.ethnicity:
        dims.append("Ethnicity")
    if args.age:
        dims.append("Age_Group")
    if not (args.group or dims):
        dims = ["Benefit_Group"]

    total = sum(as_int(r.get("Count")) or 0 for r in rows)
    breakdown = aggregate(rows, dims) if dims else []
    payload = {
        "source": "Ministry of Social Development",
        "dataset": ds["label"],
        "url": final_url,
        "quarter": quarter,
        "benefit_group": group or "All main benefits",
        "total_recipients": total,
        "breakdown_dimensions": dims,
        "breakdown": breakdown,
        "note": "Counts include 'suppressed'/'Unspecified' categories where MSD applied confidentiality.",
    }

    def render(p: dict[str, Any]) -> None:
        print(f"MSD main benefits {p['quarter']} - {p['benefit_group']}: {fmt_int(p['total_recipients'])} recipients")
        for item in p["breakdown"]:
            label = " / ".join(str(item[d]) for d in p["breakdown_dimensions"])
            print(f"  {label}: {fmt_int(item['count'])}")
        print(f"Source: {p['dataset']}")
        print(p["url"])

    output(payload, args.json, render)


def cmd_nz_super(args: argparse.Namespace) -> None:
    ds = DATASETS["nzs"]
    quarter = args.quarter or LATEST_QUARTER
    rows, final_url = fetch_csv_rows(ds["url"], lambda r: r.get("Quarter") == quarter)
    if not rows:
        all_rows, _ = fetch_csv_rows(ds["url"])
        quarters = sorted({r["Quarter"] for r in all_rows}, key=quarter_key)
        die(f"no rows for quarter '{quarter}'. Available quarters: {', '.join(quarters)}")

    group = resolve_group(rows, args.group)
    if group:
        rows = [r for r in rows if r["Benefit_Group"] == group]

    dims: list[str] = ["Benefit_Group"] if not args.group else []
    if args.age_group:
        dims.append("Age_group2")
    if args.ethnicity:
        dims.append("Ethnicity")

    total = sum(as_int(r.get("Count")) or 0 for r in rows)
    breakdown = aggregate(rows, dims) if dims else []
    payload = {
        "source": "Ministry of Social Development",
        "dataset": ds["label"],
        "url": final_url,
        "quarter": quarter,
        "benefit_group": group or "NZ Superannuation and Veteran's Pension",
        "total_recipients": total,
        "breakdown_dimensions": dims,
        "breakdown": breakdown,
    }

    def render(p: dict[str, Any]) -> None:
        print(f"MSD NZ Super/Veteran's Pension {p['quarter']} - {p['benefit_group']}: {fmt_int(p['total_recipients'])} recipients")
        for item in p["breakdown"]:
            label = " / ".join(str(item[d]) for d in p["breakdown_dimensions"])
            print(f"  {label}: {fmt_int(item['count'])}")
        print(f"Source: {p['dataset']}")
        print(p["url"])

    output(payload, args.json, render)


def cmd_region(args: argparse.Namespace) -> None:
    ds = DATASETS["region"]
    quarter = args.quarter or LATEST_QUARTER
    rows, final_url = fetch_csv_rows(ds["url"], lambda r: r.get("Quarter") == quarter)
    if not rows:
        all_rows, _ = fetch_csv_rows(ds["url"])
        quarters = sorted({r["Quarter"] for r in all_rows}, key=quarter_key)
        die(f"no rows for quarter '{quarter}'. Available quarters: {', '.join(quarters)}")

    region = resolve_region(rows, args.region)
    rows = [r for r in rows if r["Region"] == region]

    group = resolve_group(rows, args.group)
    if group:
        rows = [r for r in rows if r["Benefit_Group"] == group]

    dims = ["Benefit_Group"] if not args.group else []
    if args.gender:
        dims.append("Gender")
    if args.ethnicity:
        dims.append("Ethnicity")
    if args.age:
        dims.append("Age_Group")

    total = sum(as_int(r.get("Count")) or 0 for r in rows)
    breakdown = aggregate(rows, dims) if dims else []
    payload = {
        "source": "Ministry of Social Development",
        "dataset": ds["label"],
        "url": final_url,
        "quarter": quarter,
        "region": region,
        "benefit_group": group or "All main benefits",
        "total_recipients": total,
        "breakdown_dimensions": dims,
        "breakdown": breakdown,
        "note": "Region values are MSD Work and Income service regions, not regional councils.",
    }

    def render(p: dict[str, Any]) -> None:
        print(f"MSD region {p['region']} {p['quarter']} - {p['benefit_group']}: {fmt_int(p['total_recipients'])} recipients")
        for item in p["breakdown"]:
            label = " / ".join(str(item[d]) for d in p["breakdown_dimensions"])
            print(f"  {label}: {fmt_int(item['count'])}")
        print(f"Source: {p['dataset']}")
        print(p["url"])

    output(payload, args.json, render)


GENDER_ALIASES = {
    "f": "Female", "female": "Female",
    "m": "Male", "male": "Male",
}


def cmd_trend(args: argparse.Namespace) -> None:
    ds = DATASETS["national"]
    rows, final_url = fetch_csv_rows(ds["url"])
    group = resolve_group(rows, args.group)
    keep = [r for r in rows if r["Benefit_Group"] == group]

    gender = None
    if args.gender:
        gender = GENDER_ALIASES.get(args.gender.strip().lower())
        if gender is None:
            die("--gender must be F/Female or M/Male")
        keep = [r for r in keep if r["Gender"] == gender]

    by_quarter: dict[str, int] = defaultdict(int)
    for r in keep:
        c = as_int(r.get("Count"))
        if c is not None:
            by_quarter[r["Quarter"]] += c
    series = [
        {"quarter": q, "count": by_quarter[q]}
        for q in sorted(by_quarter, key=quarter_key)
    ]
    payload = {
        "source": "Ministry of Social Development",
        "dataset": ds["label"],
        "url": final_url,
        "benefit_group": group,
        "gender": gender or "All",
        "series": series,
        "latest": series[-1] if series else None,
    }

    def render(p: dict[str, Any]) -> None:
        print(f"MSD trend - {p['benefit_group']} (gender: {p['gender']})")
        for item in p["series"]:
            print(f"  {item['quarter']}: {fmt_int(item['count'])}")
        print(f"Source: {p['dataset']}")
        print(p["url"])

    output(payload, args.json, render)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only CLI for public MSD quarterly benefit statistics (Dec 2019 release, frozen historical series)."
    )
    sub = parser.add_subparsers(dest="command")

    lq = sub.add_parser("list-quarters", help="List distinct Quarter values in a CSV")
    lq.add_argument("--csv", choices=sorted(DATASETS), default="national", help="Which CSV to inspect")
    lq.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    lq.set_defaults(func=cmd_list_quarters)

    mb = sub.add_parser("main-benefits", help="National main-benefit recipient counts")
    mb.add_argument("--quarter", help=f"Quarter like Sep_19 (default {LATEST_QUARTER})")
    mb.add_argument("--group", help="Benefit_Group, e.g. 'Jobseeker Support'")
    mb.add_argument("--gender", action="store_true", help="Break down by gender")
    mb.add_argument("--ethnicity", action="store_true", help="Break down by ethnicity")
    mb.add_argument("--age", action="store_true", help="Break down by age group")
    mb.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    mb.set_defaults(func=cmd_main_benefits)

    ns = sub.add_parser("nz-super", help="NZ Superannuation and Veteran's Pension counts")
    ns.add_argument("--quarter", help=f"Quarter like Sep_19 (default {LATEST_QUARTER})")
    ns.add_argument("--group", help="Benefit_Group: 'New Zealand Superannuation' or \"Veteran's Pension\"")
    ns.add_argument("--age-group", action="store_true", help="Break down by Under 65 / 65 and over")
    ns.add_argument("--ethnicity", action="store_true", help="Break down by ethnicity")
    ns.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    ns.set_defaults(func=cmd_nz_super)

    rg = sub.add_parser("region", help="Work and Income region-level main-benefit counts")
    rg.add_argument("--quarter", help=f"Quarter like Sep_19 (default {LATEST_QUARTER})")
    rg.add_argument("--region", required=True, help="MSD service region, e.g. 'Auckland Metro', 'Wellington'")
    rg.add_argument("--group", help="Benefit_Group, e.g. 'Jobseeker Support'")
    rg.add_argument("--gender", action="store_true", help="Break down by gender")
    rg.add_argument("--ethnicity", action="store_true", help="Break down by ethnicity")
    rg.add_argument("--age", action="store_true", help="Break down by age group")
    rg.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    rg.set_defaults(func=cmd_region)

    tr = sub.add_parser("trend", help="Time series of Count for a benefit group across quarters")
    tr.add_argument("--group", required=True, help="Benefit_Group, e.g. 'Sole Parent Support'")
    tr.add_argument("--gender", help="Optional gender filter: F/Female or M/Male")
    tr.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    tr.set_defaults(func=cmd_trend)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 2
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
