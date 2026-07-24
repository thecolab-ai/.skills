#!/usr/bin/env python3
"""NZ SeaRise sea-level rise and vertical land movement projections (read-only).

Reads the official NZ SeaRise dataset published on Zenodo (Naish et al. 2024,
record 11398538, CC BY 4.0): per-site vertical land movement rates and
sea-level projections to 2300 for ~7,500 sites spaced every 2 km along the
Aotearoa New Zealand coastline.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import pathlib
import sys
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "lib"))
import nzfetch  # noqa: E402

HOST = "zenodo.org"
RECORD_URL = "https://zenodo.org/records/11398538"
VLM_URL = RECORD_URL + "/files/NZ_VLM_final_May24.csv"
PROJ_VLM_URL = RECORD_URL + "/files/NZSeaRise_proj_vlm.csv"
PROJ_NOVLM_URL = RECORD_URL + "/files/NZSeaRise_proj_novlm.csv"
SOURCE_NAME = "NZ SeaRise projections (Zenodo record 11398538)"
ATTRIBUTION = (
    "CC BY 4.0 — cite Naish et al. (2024), New Zealand Vertical Land Movement "
    "and Sea Rise Projections, https://zenodo.org/records/11398538"
)
CITATION_NOTE = (
    "projections are research outputs with uncertainty bounds (17th/50th/83rd "
    "percentiles); use the percentile range, not the median alone, for planning"
)


def die(message: str, code: int = 1) -> None:
    print(f"searise-nz: {message}", file=sys.stderr)
    raise SystemExit(code)


def fetch_csv(url: str, timeout: int = 120) -> list[dict[str, str]]:
    try:
        text = nzfetch.fetch_text(url, timeout=timeout, accept="text/csv,*/*", allowed_hosts=[HOST])
    except nzfetch.RateLimited as exc:
        die(f"network error: rate_limited: retry_after={exc.retry_after}: {exc}", 4)
    except nzfetch.Blocked as exc:
        die(f"network error: {exc}", 4)
    except nzfetch.FetchError as exc:
        die(f"upstream unavailable: {exc}", 5)
    return list(csv.DictReader(io.StringIO(text)))


def parse_float(raw: str | None) -> float | None:
    try:
        value = float(raw) if raw not in (None, "") else None
    except (TypeError, ValueError):
        return None
    return value if value is not None and math.isfinite(value) else None


def parse_sites(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    sites = []
    for row in rows:
        site_id = (row.get("Site ID") or "").strip()
        lon = parse_float(row.get("Lon"))
        lat = parse_float(row.get("Lat"))
        if not site_id.isdigit() or lon is None or lat is None:
            continue
        sites.append(
            {
                "site_id": int(site_id),
                "lon": lon,
                "lat": lat,
                "vlm_mm_yr": parse_float(row.get("Vertical Rate (mm/yr)")),
                "vlm_bop_corrected_mm_yr": parse_float(row.get("Vertical Rate - BOP corrected (mm/yr)")),
                "vlm_1sigma_mm_yr": parse_float(row.get("1-sigma uncertainty (mm/yr)")),
                "observation_count": parse_float(row.get("Number of obs")),
                "quality_factor": parse_float(row.get("Quality Factor")),
            }
        )
    return sites


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlon / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(a))


def parse_latlon(raw: str) -> tuple[float, float]:
    parts = raw.split(",")
    if len(parts) != 2:
        die(f"invalid --near {raw!r}: expected lat,lon", 2)
    try:
        lat, lon = float(parts[0]), float(parts[1])
    except ValueError:
        die(f"invalid --near {raw!r}: expected two numbers", 2)
    if not (-90 <= lat <= 90 and -180 <= lon <= 360):
        die(f"invalid --near {raw!r}: lat must be -90..90, lon -180..360", 2)
    return lat, lon


def scenario_label(row: dict[str, str]) -> str:
    return f"{(row.get('SSP') or '').strip()}-{(row.get('scenario') or '').strip()}"


def parse_projection_rows(rows: list[dict[str, str]], site_id: int) -> list[dict[str, Any]]:
    out = []
    for row in rows:
        if (row.get("site") or "").strip() != str(site_id):
            continue
        year = (row.get("year") or "").strip()
        if not year.isdigit():
            continue
        out.append(
            {
                "scenario": scenario_label(row),
                "confidence": (row.get("Confidence") or "").replace("_confidence", ""),
                "year": int(year),
                "p17_m": parse_float(row.get("0.17")),
                "p50_m": parse_float(row.get("0.5")),
                "p83_m": parse_float(row.get("0.83")),
            }
        )
    return out


def emit(payload: dict[str, Any], as_json: bool, lines: list[str]) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        for line in lines:
            print(line)


def load_sites() -> list[dict[str, Any]]:
    sites = parse_sites(fetch_csv(VLM_URL, timeout=60))
    if not sites:
        die("source schema failure: no site rows parsed from the VLM CSV; the published columns may have changed", 6)
    return sites


def cmd_sites(args: argparse.Namespace) -> None:
    sites = load_sites()
    total = len(sites)
    near = None
    if args.near:
        lat, lon = parse_latlon(args.near)
        near = {"lat": lat, "lon": lon}
        for site in sites:
            site["distance_km"] = round(haversine_km(lat, lon, site["lat"], site["lon"]), 2)
        sites.sort(key=lambda s: s["distance_km"])
    shown = sites[: args.limit]
    payload = {
        "kind": "sites",
        "source": SOURCE_NAME,
        "source_url": VLM_URL,
        "licence": ATTRIBUTION,
        "near": near,
        "total_sites": total,
        "sites": shown,
    }
    lines = [f"NZ SeaRise coastal sites: {len(shown)} shown of {total}" + (f" (nearest to {args.near})" if near else "")]
    for s in shown:
        dist = f" {s['distance_km']} km away," if "distance_km" in s else ""
        lines.append(
            f"- site {s['site_id']}:{dist} ({s['lat']}, {s['lon']}), VLM {s['vlm_mm_yr']} mm/yr"
        )
    emit(payload, args.json, lines)


def cmd_vlm(args: argparse.Namespace) -> None:
    sites = load_sites()
    match = next((s for s in sites if s["site_id"] == args.site_id), None)
    if match is None:
        die(f"unknown site id {args.site_id}: ids run 0..{max(s['site_id'] for s in sites)}; find one with `sites --near lat,lon`", 2)
    payload = {
        "kind": "vlm",
        "source": SOURCE_NAME,
        "source_url": VLM_URL,
        "licence": ATTRIBUTION,
        "note": "negative VLM is subsidence (adds to relative sea-level rise); rates are 2003-2011 estimates with uncertainty",
        "site": match,
    }
    lines = [
        f"Site {match['site_id']} ({match['lat']}, {match['lon']}):",
        f"  vertical land movement: {match['vlm_mm_yr']} mm/yr (±{match['vlm_1sigma_mm_yr']} 1σ)",
        f"  BOP-corrected rate: {match['vlm_bop_corrected_mm_yr']} mm/yr",
        f"  quality factor: {match['quality_factor']} (observations: {match['observation_count']})",
    ]
    emit(payload, args.json, lines)


def cmd_projections(args: argparse.Namespace) -> None:
    url = PROJ_NOVLM_URL if args.no_vlm else PROJ_VLM_URL
    rows = parse_projection_rows(fetch_csv(url, timeout=120), args.site_id)
    if not rows:
        die(
            f"no projection rows for site {args.site_id}: check the id with `sites --near lat,lon` "
            "(the download is ~54 MB; a truncated transfer also lands here)",
            2,
        )
    available_scenarios = sorted({r["scenario"] for r in rows})
    if args.scenario:
        wanted = args.scenario.upper().replace(" ", "")
        rows = [r for r in rows if r["scenario"].upper() == wanted]
        if not rows:
            die(f"scenario {args.scenario!r} not present for this site; available: {', '.join(available_scenarios)}", 2)
    if args.confidence != "all":
        rows = [r for r in rows if r["confidence"] == args.confidence]
        if not rows:
            die(f"no {args.confidence}-confidence rows for this selection; try --confidence all", 2)
    if args.year:
        rows = [r for r in rows if r["year"] == args.year]
        if not rows:
            die(f"year {args.year} not present; the dataset projects decadal steps 2020-2300", 2)
    rows.sort(key=lambda r: (r["scenario"], r["confidence"], r["year"]))
    payload = {
        "kind": "projections",
        "source": SOURCE_NAME,
        "source_url": url,
        "licence": ATTRIBUTION,
        "note": CITATION_NOTE,
        "site_id": args.site_id,
        "vlm_included": not args.no_vlm,
        "available_scenarios": available_scenarios,
        "row_count": len(rows),
        "projections": rows,
    }
    lines = [
        f"Sea-level projections for site {args.site_id} "
        f"({'with' if not args.no_vlm else 'without'} vertical land movement): {len(rows)} rows"
    ]
    for r in rows[:40]:
        lines.append(
            f"- {r['scenario']} ({r['confidence']}) {r['year']}: "
            f"{r['p50_m']} m (p17 {r['p17_m']}, p83 {r['p83_m']})"
        )
    if len(rows) > 40:
        lines.append(f"... {len(rows) - 40} more (use --json for full output)")
    emit(payload, args.json, lines)


def positive_int(maximum: int):
    def parse(raw: str) -> int:
        try:
            value = int(raw)
        except ValueError:
            raise argparse.ArgumentTypeError(f"{raw!r} is not an integer")
        if not 1 <= value <= maximum:
            raise argparse.ArgumentTypeError(f"must be between 1 and {maximum}")
        return value

    return parse


def main() -> None:
    parser = argparse.ArgumentParser(
        description="NZ SeaRise sea-level rise and vertical land movement projections (read-only)"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    s = sub.add_parser("sites", help="list coastal projection sites (2 km spacing), optionally nearest-first")
    s.add_argument("--near", help="lat,lon to sort sites by distance, e.g. \"-41.29,174.78\"")
    s.add_argument("--limit", type=positive_int(500), default=10, help="maximum sites (default 10)")
    s.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    s.set_defaults(func=cmd_sites)

    s = sub.add_parser("vlm", help="vertical land movement detail for one site")
    s.add_argument("site_id", type=int, help="site id from `sites`")
    s.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    s.set_defaults(func=cmd_vlm)

    s = sub.add_parser(
        "projections",
        help="sea-level projections to 2300 for one site (downloads a ~54 MB CSV)",
    )
    s.add_argument("site_id", type=int, help="site id from `sites`")
    s.add_argument("--scenario", help="filter to one SSP scenario, e.g. SSP2-4.5")
    s.add_argument(
        "--confidence",
        choices=["low", "medium", "all"],
        default="all",
        help="projection confidence band (default all)",
    )
    s.add_argument("--year", type=int, help="filter to one decadal year, e.g. 2100")
    s.add_argument("--no-vlm", action="store_true", help="use projections without vertical land movement")
    s.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    s.set_defaults(func=cmd_projections)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
