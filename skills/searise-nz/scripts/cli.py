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
from collections.abc import Iterable, Iterator
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "lib"))
import nzfetch  # noqa: E402

HOST = "zenodo.org"
RECORD_URL = "https://zenodo.org/records/11398538"
RECORD_API_URL = "https://zenodo.org/api/records/11398538"
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


class SourceSchemaError(ValueError):
    """The upstream response cannot satisfy the published source contract."""


class StructuredArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        print(json.dumps({"error": "invalid_input", "message": message}), file=sys.stderr)
        raise SystemExit(2)


def die(message: str, code: int = 1, error: str = "invalid_input") -> None:
    print(json.dumps({"error": error, "message": message}, ensure_ascii=False), file=sys.stderr)
    raise SystemExit(code)


def fetch_csv(url: str, timeout: int = 120) -> Iterator[dict[str, str]]:
    try:
        text = nzfetch.fetch_text(url, timeout=timeout, accept="text/csv,*/*", allowed_hosts=[HOST])
    except nzfetch.RateLimited as exc:
        die(
            f"network error: rate_limited: retry_after={exc.retry_after}: {exc}",
            4,
            "rate_limited",
        )
    except nzfetch.Blocked as exc:
        die(f"network error: {exc}", 4, "blocked")
    except nzfetch.FetchError as exc:
        die(f"upstream unavailable: {exc}", 5, "source_unavailable")
    return csv.DictReader(io.StringIO(text))


def fetch_record() -> dict[str, Any]:
    try:
        data = nzfetch.fetch_json(RECORD_API_URL, timeout=30, allowed_hosts=[HOST])
    except nzfetch.RateLimited as exc:
        die(
            f"network error: rate_limited: retry_after={exc.retry_after}: {exc}",
            4,
            "rate_limited",
        )
    except nzfetch.Blocked as exc:
        die(f"network error: {exc}", 4, "blocked")
    except nzfetch.FetchError as exc:
        die(f"upstream unavailable: {exc}", 5, "source_unavailable")
    if not isinstance(data, dict):
        raise SourceSchemaError("Zenodo record response must be a JSON object")
    return data


def parse_float(raw: str | None) -> float | None:
    try:
        value = float(raw) if raw not in (None, "") else None
    except (TypeError, ValueError):
        return None
    return value if value is not None and math.isfinite(value) else None


def parse_sites(rows: Iterable[dict[str, str]]) -> list[dict[str, Any]]:
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
    if not (
        math.isfinite(lat)
        and math.isfinite(lon)
        and -90 <= lat <= 90
        and -180 <= lon <= 180
    ):
        die(f"invalid --near {raw!r}: lat must be -90..90, lon -180..180", 2)
    return lat, lon


def scenario_label(row: dict[str, str]) -> str:
    return f"{(row.get('SSP') or '').strip()}-{(row.get('scenario') or '').strip()}"


PROJECTION_COLUMNS = frozenset(
    {"Confidence", "site", "year", "0.17", "0.5", "0.83", "SSP", "scenario"}
)
PROJECTION_YEAR_MIN = 2020
PROJECTION_YEAR_MAX = 2300
PROJECTION_CONFIDENCE = {
    "low_confidence": "low",
    "medium_confidence": "medium",
}
PROJECTION_SCENARIOS = frozenset(
    {"SSP1-1.9", "SSP1-2.6", "SSP2-4.5", "SSP3-7.0", "SSP5-8.5"}
)


def required_projection_text(row: dict[str, str], field: str) -> str:
    raw = row.get(field)
    if not isinstance(raw, str) or not raw.strip():
        raise SourceSchemaError(f"projection CSV {field} must be a non-empty value")
    return raw.strip()


def required_projection_float(row: dict[str, str], field: str) -> float:
    raw = required_projection_text(row, field)
    try:
        value = float(raw)
    except ValueError as exc:
        raise SourceSchemaError(f"projection CSV {field} must be a finite number") from exc
    if not math.isfinite(value):
        raise SourceSchemaError(f"projection CSV {field} must be a finite number")
    return value


def projection_from_row(row: dict[str, str]) -> tuple[int, dict[str, Any]]:
    missing = PROJECTION_COLUMNS - set(row)
    if missing:
        raise SourceSchemaError(
            "projection CSV row is missing required columns: " + ", ".join(sorted(missing))
        )

    raw_site_id = required_projection_text(row, "site")
    if not raw_site_id.isdigit():
        raise SourceSchemaError("projection CSV site must be a non-negative integer")
    site_id = int(raw_site_id)

    raw_year = required_projection_text(row, "year")
    if not raw_year.isdigit():
        raise SourceSchemaError("projection CSV year must be an integer")
    year = int(raw_year)
    if not PROJECTION_YEAR_MIN <= year <= PROJECTION_YEAR_MAX:
        raise SourceSchemaError(
            f"projection CSV year must be between {PROJECTION_YEAR_MIN} and {PROJECTION_YEAR_MAX}"
        )

    ssp = required_projection_text(row, "SSP")
    scenario_component = required_projection_text(row, "scenario")
    scenario = f"{ssp}-{scenario_component}"
    if scenario not in PROJECTION_SCENARIOS:
        raise SourceSchemaError(
            f"projection CSV SSP/scenario produced unsupported scenario {scenario!r}"
        )

    raw_confidence = required_projection_text(row, "Confidence")
    confidence = PROJECTION_CONFIDENCE.get(raw_confidence)
    if confidence is None:
        raise SourceSchemaError(
            f"projection CSV Confidence has unsupported value {raw_confidence!r}"
        )

    return site_id, {
        "scenario": scenario,
        "confidence": confidence,
        "year": int(year),
        "p17_m": required_projection_float(row, "0.17"),
        "p50_m": required_projection_float(row, "0.5"),
        "p83_m": required_projection_float(row, "0.83"),
    }


def scan_projection_rows(
    rows: Iterable[dict[str, str]], site_ids: Iterable[int]
) -> dict[int, list[dict[str, Any]]]:
    requested = set(site_ids)
    grouped: dict[int, list[dict[str, Any]]] = {site_id: [] for site_id in requested}
    fieldnames = getattr(rows, "fieldnames", None)
    if fieldnames is not None:
        missing = PROJECTION_COLUMNS - set(fieldnames)
        if missing:
            raise SourceSchemaError(
                "projection CSV is missing required columns: " + ", ".join(sorted(missing))
            )

    source_rows = 0
    for row in rows:
        if not isinstance(row, dict):
            raise SourceSchemaError("projection CSV yielded a non-object row")
        site_id, projection = projection_from_row(row)
        source_rows += 1
        if site_id in grouped:
            grouped[site_id].append(projection)
    if source_rows == 0:
        raise SourceSchemaError("projection CSV contained no valid projection rows")
    return grouped


def parse_projection_rows(
    rows: Iterable[dict[str, str]], site_id: int
) -> list[dict[str, Any]]:
    """Backward-compatible single-site parser used by existing smoke coverage."""
    return scan_projection_rows(rows, [site_id])[site_id]


def normalize_record(data: dict[str, Any]) -> dict[str, Any]:
    metadata = data.get("metadata")
    files = data.get("files")
    if not isinstance(metadata, dict):
        raise SourceSchemaError("Zenodo record metadata must be a JSON object")
    if not isinstance(files, list):
        raise SourceSchemaError("Zenodo record files must be a JSON list")

    creators = []
    raw_creators = metadata.get("creators")
    if raw_creators is not None and not isinstance(raw_creators, list):
        raise SourceSchemaError("Zenodo record metadata.creators must be a JSON list")
    for creator in raw_creators or []:
        if not isinstance(creator, dict) or not isinstance(creator.get("name"), str):
            raise SourceSchemaError("Zenodo record contains a malformed creator")
        normalized_creator = {"name": creator["name"]}
        for key in ("affiliation", "orcid"):
            if isinstance(creator.get(key), str) and creator[key]:
                normalized_creator[key] = creator[key]
        creators.append(normalized_creator)

    licence = metadata.get("license")
    if isinstance(licence, dict):
        licence = licence.get("id") or licence.get("title")
    if licence is not None and not isinstance(licence, str):
        raise SourceSchemaError("Zenodo record metadata.license is malformed")

    normalized_files = []
    for file_entry in files:
        if not isinstance(file_entry, dict):
            raise SourceSchemaError("Zenodo record contains a malformed file entry")
        links = file_entry.get("links")
        if not isinstance(links, dict):
            raise SourceSchemaError("Zenodo record file links must be a JSON object")
        download_url = links.get("download") or links.get("content") or links.get("self")
        if not isinstance(file_entry.get("key"), str) or not isinstance(download_url, str):
            raise SourceSchemaError("Zenodo record file is missing its key or download link")
        size = file_entry.get("size")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise SourceSchemaError("Zenodo record file size must be a non-negative integer")
        checksum = file_entry.get("checksum")
        if checksum is not None and not isinstance(checksum, str):
            raise SourceSchemaError("Zenodo record file checksum is malformed")
        normalized_files.append(
            {
                "key": file_entry["key"],
                "size": size,
                "checksum": checksum,
                "download_url": download_url,
            }
        )

    record_id = data.get("id")
    doi = data.get("doi") or metadata.get("doi")
    title = metadata.get("title")
    version = metadata.get("version")
    if version is None:
        relations = metadata.get("relations")
        version_relations = relations.get("version") if isinstance(relations, dict) else None
        version_relation = version_relations[0] if isinstance(version_relations, list) and version_relations else None
        version_index = version_relation.get("index") if isinstance(version_relation, dict) else None
        if isinstance(version_index, int) and not isinstance(version_index, bool) and version_index >= 0:
            version = str(version_index + 1)
    if not isinstance(record_id, int) or isinstance(record_id, bool):
        raise SourceSchemaError("Zenodo record id must be an integer")
    for label, value in (
        ("doi", doi),
        ("version", version),
        ("publication_date", metadata.get("publication_date")),
        ("title", title),
    ):
        if not isinstance(value, str) or not value:
            raise SourceSchemaError(f"Zenodo record {label} must be a non-empty string")

    return {
        "kind": "record",
        "source": SOURCE_NAME,
        "source_url": RECORD_API_URL,
        "record_url": RECORD_URL,
        "record_id": record_id,
        "doi": doi,
        "version": version,
        "publication_date": metadata["publication_date"],
        "title": title,
        "creators": creators,
        "licence": licence,
        "file_count": len(normalized_files),
        "files": normalized_files,
    }


def emit(payload: dict[str, Any], as_json: bool, lines: list[str]) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        for line in lines:
            print(line)


def cmd_record(args: argparse.Namespace) -> None:
    try:
        payload = normalize_record(fetch_record())
    except SourceSchemaError as exc:
        die(str(exc), 6, "source_schema_failure")
    lines = [
        f"{payload['title']} (version {payload['version']}, published {payload['publication_date']})",
        f"DOI: {payload['doi']}; licence: {payload['licence']}",
        f"Files: {payload['file_count']}",
    ]
    for file_entry in payload["files"]:
        lines.append(
            f"- {file_entry['key']}: {file_entry['size']} bytes, "
            f"{file_entry['checksum'] or 'no checksum supplied'}"
        )
    emit(payload, args.json, lines)


def load_sites() -> list[dict[str, Any]]:
    sites = parse_sites(fetch_csv(VLM_URL, timeout=60))
    if not sites:
        die(
            "no site rows parsed from the VLM CSV; the published columns may have changed",
            6,
            "source_schema_failure",
        )
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


def filtered_projection_rows(
    rows: list[dict[str, Any]], args: argparse.Namespace
) -> list[dict[str, Any]]:
    selected = rows
    if args.scenario is not None:
        wanted = args.scenario.upper().replace(" ", "")
        selected = [row for row in selected if row["scenario"].upper() == wanted]
    if args.confidence != "all":
        selected = [row for row in selected if row["confidence"] == args.confidence]
    if args.year is not None:
        selected = [row for row in selected if row["year"] == args.year]
    return sorted(selected, key=lambda row: (row["scenario"], row["confidence"], row["year"]))


def single_projection_payload(
    rows: list[dict[str, Any]],
    site_id: int,
    url: str,
    args: argparse.Namespace,
) -> dict[str, Any]:
    if not rows:
        die(
            f"no projection rows for site {site_id}: check the id with `sites --near lat,lon` "
            "(the download is ~54 MB; a truncated transfer also lands here)",
            2,
            "site_not_found",
        )
    available_scenarios = sorted({row["scenario"] for row in rows})
    selected = rows
    if args.scenario is not None:
        wanted = args.scenario.upper().replace(" ", "")
        selected = [row for row in selected if row["scenario"].upper() == wanted]
        if not selected:
            die(
                f"scenario {args.scenario!r} not present for this site; "
                f"available: {', '.join(available_scenarios)}",
                2,
                "empty_result",
            )
    if args.confidence != "all":
        selected = [row for row in selected if row["confidence"] == args.confidence]
        if not selected:
            die(
                f"no {args.confidence}-confidence rows for this selection; "
                "try --confidence all",
                2,
                "empty_result",
            )
    if args.year is not None:
        selected = [row for row in selected if row["year"] == args.year]
        if not selected:
            die(
                f"year {args.year} not present; the dataset projects decadal steps 2020-2300",
                2,
                "empty_result",
            )
    selected.sort(key=lambda row: (row["scenario"], row["confidence"], row["year"]))
    return {
        "kind": "projections",
        "source": SOURCE_NAME,
        "source_url": url,
        "licence": ATTRIBUTION,
        "note": CITATION_NOTE,
        "site_id": site_id,
        "vlm_included": not args.no_vlm,
        "available_scenarios": available_scenarios,
        "row_count": len(selected),
        "projections": selected,
    }


def multi_projection_payload(
    grouped: dict[int, list[dict[str, Any]]],
    requested_site_ids: list[int],
    url: str,
    args: argparse.Namespace,
) -> dict[str, Any]:
    results = []
    for site_id in requested_site_ids:
        raw_rows = grouped[site_id]
        available_scenarios = sorted({row["scenario"] for row in raw_rows})
        selected = filtered_projection_rows(raw_rows, args)
        status = "ok" if selected else ("empty" if raw_rows else "not_found")
        results.append(
            {
                "site_id": site_id,
                "status": status,
                "available_scenarios": available_scenarios,
                "row_count": len(selected),
                "projections": selected,
            }
        )
    return {
        "kind": "projections",
        "source": SOURCE_NAME,
        "source_url": url,
        "licence": ATTRIBUTION,
        "note": CITATION_NOTE,
        "requested_site_ids": requested_site_ids,
        "vlm_included": not args.no_vlm,
        "sites": results,
    }


def cmd_projections(args: argparse.Namespace) -> None:
    url = PROJ_NOVLM_URL if args.no_vlm else PROJ_VLM_URL
    try:
        grouped = scan_projection_rows(fetch_csv(url, timeout=120), args.site_ids)
    except SourceSchemaError as exc:
        die(str(exc), 6, "source_schema_failure")
    if len(args.site_ids) == 1:
        site_id = args.site_ids[0]
        payload = single_projection_payload(grouped[site_id], site_id, url, args)
        lines = [
            f"Sea-level projections for site {site_id} "
            f"({'with' if not args.no_vlm else 'without'} vertical land movement): "
            f"{payload['row_count']} rows"
        ]
        for row in payload["projections"][:40]:
            lines.append(
                f"- {row['scenario']} ({row['confidence']}) {row['year']}: "
                f"{row['p50_m']} m (p17 {row['p17_m']}, p83 {row['p83_m']})"
            )
        if payload["row_count"] > 40:
            lines.append(f"... {payload['row_count'] - 40} more (use --json for full output)")
    else:
        payload = multi_projection_payload(grouped, args.site_ids, url, args)
        lines = [
            f"Sea-level projections for {len(args.site_ids)} requested site IDs "
            f"({'with' if not args.no_vlm else 'without'} vertical land movement):"
        ]
        for site in payload["sites"]:
            lines.append(
                f"- site {site['site_id']}: {site['status']}, {site['row_count']} rows"
            )
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


def site_id(raw: str) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"{raw!r} is not an integer") from exc
    if value < 0:
        raise argparse.ArgumentTypeError("site ids must be non-negative integers")
    return value


def projection_year(raw: str) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"{raw!r} is not an integer") from exc
    if not PROJECTION_YEAR_MIN <= value <= PROJECTION_YEAR_MAX:
        raise argparse.ArgumentTypeError(
            f"must be between {PROJECTION_YEAR_MIN} and {PROJECTION_YEAR_MAX}"
        )
    return value


def parse_cli_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = StructuredArgumentParser(
        description="NZ SeaRise sea-level rise and vertical land movement projections (read-only)"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    s = sub.add_parser("record", help="show Zenodo record metadata and file inventory")
    s.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    s.set_defaults(func=cmd_record)

    s = sub.add_parser("sites", help="list coastal projection sites (2 km spacing), optionally nearest-first")
    s.add_argument("--near", help="lat,lon to sort sites by distance, e.g. \"-41.29,174.78\"")
    s.add_argument("--limit", type=positive_int(500), default=10, help="maximum sites (default 10)")
    s.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    s.set_defaults(func=cmd_sites)

    s = sub.add_parser("vlm", help="vertical land movement detail for one site")
    s.add_argument("site_id", type=site_id, help="site id from `sites`")
    s.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    s.set_defaults(func=cmd_vlm)

    s = sub.add_parser(
        "projections",
        help="sea-level projections to 2300 for one or more sites (one ~54 MB download)",
    )
    s.add_argument("site_ids", type=site_id, nargs="+", help="one or more site ids from `sites`")
    s.add_argument("--scenario", help="filter to one SSP scenario, e.g. SSP2-4.5")
    s.add_argument(
        "--confidence",
        choices=["low", "medium", "all"],
        default="all",
        help="projection confidence band (default all)",
    )
    s.add_argument(
        "--year",
        type=projection_year,
        help=f"filter to one projection year ({PROJECTION_YEAR_MIN}..{PROJECTION_YEAR_MAX})",
    )
    s.add_argument("--no-vlm", action="store_true", help="use projections without vertical land movement")
    s.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    s.set_defaults(func=cmd_projections)

    raw_args = list(sys.argv[1:] if argv is None else argv)
    for index in range(len(raw_args) - 1):
        value = raw_args[index + 1]
        if raw_args[index] == "--near" and value.startswith("-") and "," in value:
            raw_args[index : index + 2] = [f"--near={value}"]
            break
    return parser.parse_args(raw_args)


def main() -> None:
    args = parse_cli_args()
    args.func(args)


if __name__ == "__main__":
    main()
