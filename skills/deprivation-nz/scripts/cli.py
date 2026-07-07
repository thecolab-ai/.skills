#!/usr/bin/env python3
"""New Zealand Index of Deprivation 2023 (NZDep2023) CLI.

Read-only stdlib wrapper around the public University of Auckland / Stats NZ
hosted ArcGIS Feature Service for NZDep2023. No login, API key, browser
automation, cache, or data mutation.

Two layers:
  /0  Statistical Area 1 (SA1)  - 32,746 areas, per-area decile + raw score + population
  /1  Statistical Area 2 (SA2)  - averaged decile/score + parent SA3 region

Standard ArcGIS REST query API: where=, outFields=, resultRecordCount=,
returnGeometry=false, returnCountOnly=true, f=json.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import urllib.parse
from typing import Any, Callable

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "lib"))
import nzfetch  # noqa: E402

SERVICE = (
    "https://services6.arcgis.com/ZVM1rEuVZjtC1Wwk/arcgis/rest/services/"
    "New_Zealand_Index_of_Deprivation_2023_WFL1/FeatureServer"
)
SA1_LAYER = SERVICE + "/0/query"
SA2_LAYER = SERVICE + "/1/query"
ITEM_PAGE = "https://www.arcgis.com/home/item.html?id=d0caefba5f8f42d6918fc52faacec00b"

SA1_FIELDS = "SA12023_code,NZDep2023,NZDep2023_Score,URPopnSA1_2023,SA22023_name"
SA2_FIELDS = (
    "SA22023_code,SA22023_name,SA2_average_NZDep2023,"
    "SA2_average_NZDep2023_score,SA32023_name,SA32023_code"
)

SA1_CODE_RE = re.compile(r"^\d{7}$")
SA2_CODE_RE = re.compile(r"^\d{6}$")
# Permissive name filter: letters, digits, spaces, and a few safe punctuation
# marks. Used to build ArcGIS LIKE clauses without injecting SQL.
SAFE_TEXT_RE = re.compile(r"^[A-Za-z0-9 ()'\-/.,&]+$")


def die(message: str, code: int = 1) -> None:
    print(f"deprivation-nz: {message}", file=sys.stderr)
    raise SystemExit(code)


def query(layer_url: str, params: dict[str, str], timeout: int = 45) -> dict[str, Any]:
    """Run an ArcGIS REST query and return the decoded JSON body."""
    base = {"f": "json", "returnGeometry": "false"}
    base.update(params)
    url = layer_url + "?" + urllib.parse.urlencode(base, safe="=,'%")
    try:
        data = nzfetch.fetch_json(
            url, timeout=timeout, accept="application/json"
        )
    except nzfetch.Blocked as e:
        die(f"network error calling feature service: {e}")
    except nzfetch.FetchError as e:
        die(str(e))
    if isinstance(data, dict) and data.get("error"):
        err = data["error"]
        detail = err.get("message") or err
        details = err.get("details") or []
        if details:
            detail = f"{detail} ({'; '.join(map(str, details))})"
        die(f"feature service error: {detail}")
    return data


def features(data: dict[str, Any]) -> list[dict[str, Any]]:
    return [f.get("attributes", {}) for f in data.get("features", [])]


def as_int(raw: Any) -> int | None:
    if raw is None:
        return None
    try:
        return int(round(float(raw)))
    except (TypeError, ValueError):
        return None


def as_float(raw: Any) -> float | None:
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def like_clause(field: str, text: str) -> str:
    """Build a case-insensitive ArcGIS LIKE clause, validating the input."""
    cleaned = text.strip()
    if not cleaned:
        die("search text cannot be empty")
    if not SAFE_TEXT_RE.match(cleaned):
        die("search text contains unsupported characters")
    # ArcGIS hosted services support UPPER() for case-insensitive matching.
    return f"UPPER({field}) LIKE UPPER('%{cleaned}%')"


def emit_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def output(payload: dict[str, Any], json_flag: bool, render: Callable[[dict[str, Any]], None]) -> None:
    if json_flag:
        emit_json(payload)
    else:
        render(payload)


def decile_band(decile: int | None) -> str:
    if decile is None:
        return "unknown"
    if decile <= 3:
        return "least deprived (deciles 1-3)"
    if decile <= 7:
        return "mid (deciles 4-7)"
    return "most deprived (deciles 8-10)"


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #

def cmd_sa1(args: argparse.Namespace) -> None:
    code = args.code.strip()
    if not SA1_CODE_RE.match(code):
        die("SA1 code must be a 7-digit Statistical Area 1 code, e.g. 7000000")
    data = query(SA1_LAYER, {"where": f"SA12023_code='{code}'", "outFields": SA1_FIELDS})
    rows = features(data)
    if not rows:
        die(f"no SA1 area found for code {code}")
    row = rows[0]
    decile = as_int(row.get("NZDep2023"))
    payload = {
        "source": "NZDep2023 (University of Auckland / Stats NZ)",
        "url": ITEM_PAGE,
        "level": "SA1",
        "sa1_code": row.get("SA12023_code"),
        "sa2_name": row.get("SA22023_name"),
        "nzdep2023_decile": decile,
        "nzdep2023_score": as_float(row.get("NZDep2023_Score")),
        "population_2023": as_int(row.get("URPopnSA1_2023")),
        "deprivation_band": decile_band(decile),
    }

    def render(p: dict[str, Any]) -> None:
        print(f"NZDep2023 SA1 {p['sa1_code']} ({p.get('sa2_name') or 'n/a'})")
        print(f"Decile: {p['nzdep2023_decile']}/10 - {p['deprivation_band']}")
        print(f"Score: {p['nzdep2023_score']}")
        print(f"Usually resident population (2023): {p['population_2023']}")
        print(f"Source: {p['source']}")

    output(payload, args.json, render)


def cmd_sa2(args: argparse.Namespace) -> None:
    code = args.code.strip()
    if not SA2_CODE_RE.match(code):
        die("SA2 code must be a 6-digit Statistical Area 2 code, e.g. 127100")
    data = query(SA2_LAYER, {"where": f"SA22023_code='{code}'", "outFields": SA2_FIELDS})
    rows = features(data)
    if not rows:
        die(f"no SA2 area found for code {code}")
    row = rows[0]
    decile = as_int(row.get("SA2_average_NZDep2023"))
    payload = {
        "source": "NZDep2023 (University of Auckland / Stats NZ)",
        "url": ITEM_PAGE,
        "level": "SA2",
        "sa2_code": row.get("SA22023_code"),
        "sa2_name": row.get("SA22023_name"),
        "sa3_code": row.get("SA32023_code"),
        "sa3_name": row.get("SA32023_name"),
        "average_nzdep2023_decile": decile,
        "average_nzdep2023_score": as_float(row.get("SA2_average_NZDep2023_score")),
        "deprivation_band": decile_band(decile),
    }

    def render(p: dict[str, Any]) -> None:
        print(f"NZDep2023 SA2 {p['sa2_code']} - {p.get('sa2_name') or 'n/a'}")
        print(f"Average decile: {p['average_nzdep2023_decile']}/10 - {p['deprivation_band']}")
        print(f"Average score: {p['average_nzdep2023_score']}")
        print(f"SA3 region: {p.get('sa3_name') or 'n/a'} ({p.get('sa3_code') or 'n/a'})")
        print(f"Source: {p['source']}")

    output(payload, args.json, render)


def cmd_search(args: argparse.Namespace) -> None:
    level = args.level
    limit = args.limit
    if level == "sa2":
        clause = like_clause("SA22023_name", args.name)
        data = query(
            SA2_LAYER,
            {"where": clause, "outFields": SA2_FIELDS, "resultRecordCount": str(limit)},
        )
        results = []
        for row in features(data):
            decile = as_int(row.get("SA2_average_NZDep2023"))
            results.append(
                {
                    "level": "SA2",
                    "sa2_code": row.get("SA22023_code"),
                    "sa2_name": row.get("SA22023_name"),
                    "sa3_name": row.get("SA32023_name"),
                    "average_nzdep2023_decile": decile,
                    "average_nzdep2023_score": as_float(row.get("SA2_average_NZDep2023_score")),
                    "deprivation_band": decile_band(decile),
                }
            )
    else:
        clause = like_clause("SA22023_name", args.name)
        data = query(
            SA1_LAYER,
            {"where": clause, "outFields": SA1_FIELDS, "resultRecordCount": str(limit)},
        )
        results = []
        for row in features(data):
            decile = as_int(row.get("NZDep2023"))
            results.append(
                {
                    "level": "SA1",
                    "sa1_code": row.get("SA12023_code"),
                    "sa2_name": row.get("SA22023_name"),
                    "nzdep2023_decile": decile,
                    "nzdep2023_score": as_float(row.get("NZDep2023_Score")),
                    "population_2023": as_int(row.get("URPopnSA1_2023")),
                    "deprivation_band": decile_band(decile),
                }
            )
    payload = {
        "source": "NZDep2023 (University of Auckland / Stats NZ)",
        "url": ITEM_PAGE,
        "query": args.name,
        "level": level,
        "count": len(results),
        "results": results,
    }

    def render(p: dict[str, Any]) -> None:
        print(f"NZDep2023 {p['level'].upper()} areas matching SA2 name '{p['query']}': {p['count']}")
        for r in p["results"]:
            if r["level"] == "SA2":
                print(f"- {r['sa2_code']} {r['sa2_name']} | avg decile {r['average_nzdep2023_decile']}/10 | SA3 {r.get('sa3_name') or 'n/a'}")
            else:
                print(f"- {r['sa1_code']} ({r['sa2_name']}) | decile {r['nzdep2023_decile']}/10 | pop {r['population_2023']}")

    output(payload, args.json, render)


def cmd_decile(args: argparse.Namespace) -> None:
    value = args.value
    if value < 1 or value > 10:
        die("--value must be a decile from 1 (least deprived) to 10 (most deprived)")
    limit = args.limit
    if args.level == "sa2":
        data = query(
            SA2_LAYER,
            {
                "where": f"SA2_average_NZDep2023={value}",
                "outFields": SA2_FIELDS,
                "resultRecordCount": str(limit),
                "orderByFields": "SA22023_name",
            },
        )
        results = [
            {
                "level": "SA2",
                "sa2_code": row.get("SA22023_code"),
                "sa2_name": row.get("SA22023_name"),
                "sa3_name": row.get("SA32023_name"),
                "average_nzdep2023_decile": as_int(row.get("SA2_average_NZDep2023")),
                "average_nzdep2023_score": as_float(row.get("SA2_average_NZDep2023_score")),
            }
            for row in features(data)
        ]
    else:
        data = query(
            SA1_LAYER,
            {
                "where": f"NZDep2023={value}",
                "outFields": SA1_FIELDS,
                "resultRecordCount": str(limit),
                "orderByFields": "SA12023_code",
            },
        )
        results = [
            {
                "level": "SA1",
                "sa1_code": row.get("SA12023_code"),
                "sa2_name": row.get("SA22023_name"),
                "nzdep2023_decile": as_int(row.get("NZDep2023")),
                "nzdep2023_score": as_float(row.get("NZDep2023_Score")),
                "population_2023": as_int(row.get("URPopnSA1_2023")),
            }
            for row in features(data)
        ]
    payload = {
        "source": "NZDep2023 (University of Auckland / Stats NZ)",
        "url": ITEM_PAGE,
        "level": args.level,
        "decile": value,
        "deprivation_band": decile_band(value),
        "count": len(results),
        "results": results,
    }

    def render(p: dict[str, Any]) -> None:
        print(f"NZDep2023 {p['level'].upper()} areas in decile {p['decile']}/10 - {p['deprivation_band']} (showing {p['count']})")
        for r in p["results"]:
            if r["level"] == "SA2":
                print(f"- {r['sa2_code']} {r['sa2_name']} | SA3 {r.get('sa3_name') or 'n/a'}")
            else:
                print(f"- {r['sa1_code']} ({r['sa2_name']}) | score {r['nzdep2023_score']} | pop {r['population_2023']}")

    output(payload, args.json, render)


def cmd_region(args: argparse.Namespace) -> None:
    clause = like_clause("SA32023_name", args.sa3)
    data = query(
        SA2_LAYER,
        {
            "where": clause,
            "outFields": SA2_FIELDS,
            "resultRecordCount": str(args.limit),
            "orderByFields": "SA22023_name",
        },
    )
    results = []
    for row in features(data):
        decile = as_int(row.get("SA2_average_NZDep2023"))
        results.append(
            {
                "sa2_code": row.get("SA22023_code"),
                "sa2_name": row.get("SA22023_name"),
                "sa3_name": row.get("SA32023_name"),
                "sa3_code": row.get("SA32023_code"),
                "average_nzdep2023_decile": decile,
                "average_nzdep2023_score": as_float(row.get("SA2_average_NZDep2023_score")),
                "deprivation_band": decile_band(decile),
            }
        )
    if not results:
        die(f"no SA2 areas found for SA3 region matching '{args.sa3}'")
    deciles = [r["average_nzdep2023_decile"] for r in results if r["average_nzdep2023_decile"] is not None]
    avg = round(sum(deciles) / len(deciles), 2) if deciles else None
    payload = {
        "source": "NZDep2023 (University of Auckland / Stats NZ)",
        "url": ITEM_PAGE,
        "query": args.sa3,
        "level": "SA2",
        "count": len(results),
        "mean_average_decile": avg,
        "results": results,
    }

    def render(p: dict[str, Any]) -> None:
        print(f"NZDep2023 SA2 areas within SA3 region '{p['query']}': {p['count']} (mean avg decile {p['mean_average_decile']})")
        for r in p["results"]:
            print(f"- {r['sa2_code']} {r['sa2_name']} | avg decile {r['average_nzdep2023_decile']}/10 | score {r['average_nzdep2023_score']}")

    output(payload, args.json, render)


def cmd_stats(args: argparse.Namespace) -> None:
    total_data = query(SA1_LAYER, {"where": "1=1", "returnCountOnly": "true"})
    total = total_data.get("count")
    distribution = []
    for decile in range(1, 11):
        d = query(SA1_LAYER, {"where": f"NZDep2023={decile}", "returnCountOnly": "true"})
        count = d.get("count")
        distribution.append(
            {
                "decile": decile,
                "sa1_count": count,
                "share_percent": round(count / total * 100, 1) if total and count is not None else None,
                "deprivation_band": decile_band(decile),
            }
        )
    payload = {
        "source": "NZDep2023 (University of Auckland / Stats NZ)",
        "url": ITEM_PAGE,
        "level": "SA1",
        "total_sa1_areas": total,
        "distribution": distribution,
    }

    def render(p: dict[str, Any]) -> None:
        print(f"NZDep2023 SA1 decile distribution (total {p['total_sa1_areas']} areas)")
        print("decile  sa1_count  share")
        for d in p["distribution"]:
            print(f"  {d['decile']:>2}    {d['sa1_count']:>8}   {d['share_percent']}%")
        print(f"Source: {p['source']}")

    output(payload, args.json, render)


# --------------------------------------------------------------------------- #
# Parser
# --------------------------------------------------------------------------- #

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only CLI for the NZ Index of Deprivation 2023 (NZDep2023).",
    )
    sub = parser.add_subparsers(dest="command")

    sa1 = sub.add_parser("sa1", help="Look up NZDep2023 decile, score, population for a Statistical Area 1")
    sa1.add_argument("--code", required=True, help="7-digit SA1 code, e.g. 7000000")
    sa1.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    sa1.set_defaults(func=cmd_sa1)

    sa2 = sub.add_parser("sa2", help="Look up averaged NZDep2023 decile/score for a Statistical Area 2")
    sa2.add_argument("--code", required=True, help="6-digit SA2 code, e.g. 127100")
    sa2.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    sa2.set_defaults(func=cmd_sa2)

    search = sub.add_parser("search", help="Find areas whose SA2 name matches text")
    search.add_argument("--name", required=True, help="Text to match against SA2 name, e.g. Auckland")
    search.add_argument("--level", choices=["sa1", "sa2"], default="sa2", help="Return SA1 or SA2 areas (default sa2)")
    search.add_argument("--limit", type=int, default=20, help="Maximum areas to return")
    search.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    search.set_defaults(func=cmd_search)

    decile = sub.add_parser("decile", help="List areas in a given deprivation decile")
    decile.add_argument("--value", type=int, required=True, help="Decile 1 (least) to 10 (most deprived)")
    decile.add_argument("--level", choices=["sa1", "sa2"], default="sa2", help="Return SA1 or SA2 areas (default sa2)")
    decile.add_argument("--limit", type=int, default=20, help="Maximum areas to return")
    decile.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    decile.set_defaults(func=cmd_decile)

    region = sub.add_parser("region", help="List SA2 areas within an SA3 region with their deprivation")
    region.add_argument("--sa3", required=True, help="SA3 region name, e.g. Northcote (Auckland)")
    region.add_argument("--limit", type=int, default=50, help="Maximum SA2 areas to return")
    region.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    region.set_defaults(func=cmd_region)

    stats = sub.add_parser("stats", help="Summary distribution of deciles across all SA1 areas")
    stats.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    stats.set_defaults(func=cmd_stats)

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
