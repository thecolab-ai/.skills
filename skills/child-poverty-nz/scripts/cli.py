#!/usr/bin/env python3
"""New Zealand child poverty statistics CLI.

Read-only stdlib wrapper around Stats NZ's annual Child Poverty Reduction Act
(CPRA) data releases. Each release is a public ZIP of UTF-8 CSVs (no login, no
API key, no browser). This CLI discovers the latest release from the Stats NZ
CSV-files index, downloads the ZIP into memory, and parses the national and
disaggregated data files. No mutation, no cache, no scraping of paywalled data.
"""
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
import zipfile
from typing import Any, Callable

STATS_BASE = "https://www.stats.govt.nz"
CSV_PAGE = STATS_BASE + "/large-datasets/csv-files-for-download/"
UA = "child-poverty-nz-skill/1.0 (+https://github.com/thecolab-ai/.skills)"

# Plain-English names for the nine CPRA low-income / material-hardship measures.
# Codes and descriptions are taken VERBATIM from the release's cp-csv-codes
# legend (cp-csv-codes.xlsx). Stats NZ skips MEASD. The three primary legislated
# measures are MEASA (BHC<50% moving), MEASB (AHC<50% anchored/base year) and
# MEASC (material hardship). Severe hardship (MEASI) is a subset of material
# hardship (MEASC), so MEASI <= MEASC always.
MEASURES: dict[str, dict[str, str]] = {
    "MEASA": {"short": "BHC<50% (primary, moving)", "name": "Low income: less than 50% of median equivalised disposable household income before housing costs (BHC), moving line"},
    "MEASB": {"short": "AHC<50% (primary, anchored)", "name": "Low income: less than 50% of median equivalised disposable household income after housing costs (AHC), base/anchored financial year line"},
    "MEASC": {"short": "material hardship (primary)", "name": "Material hardship (DEP-17, lacking 6+ of 17 items)"},
    "MEASE": {"short": "BHC<60%", "name": "Low income: less than 60% of median equivalised disposable household income before housing costs (BHC), moving line"},
    "MEASF": {"short": "AHC<60%", "name": "Low income: less than 60% of median equivalised disposable household income after housing costs (AHC), moving line"},
    "MEASG": {"short": "AHC<50% (moving)", "name": "Low income: less than 50% of median equivalised disposable household income after housing costs (AHC), moving line"},
    "MEASH": {"short": "AHC<40%", "name": "Low income: less than 40% of median equivalised disposable household income after housing costs (AHC), moving line"},
    "MEASI": {"short": "severe material hardship", "name": "Severe material hardship (DEP-17, lacking 9+ of 17 items)"},
    "MEASJ": {"short": "low income + hardship (combined)", "name": "Low income and hardship: less than 60% of median income after housing costs (AHC) and in material hardship"},
}

# National datafile EstCodes (cp-national-datafile-csv.csv).
NAT_EST = {
    "A_Proportion": "Proportion of children in the measure (%)",
    "B_ChangeInProportion": "Annual change in proportion (percentage points)",
    "C_Number": "Number of children in the measure (000s)",
    "D_ChangeInNumber": "Annual change in number (000s)",
    "E_Population": "Total number of children (000s)",
}

# Disaggregated datafile EstCodes (cp-reg-eth-dis-datafile.csv).
DEM_EST = {
    "A_Proportion": "Proportion of children in the measure (%)",
    "B_Number": "Number of children in the measure (000s)",
    "C_Population": "Total number of children (000s)",
    "D_Proportion_diff": "Annual change in proportion (percentage points)",
    "E_Number_diff": "Annual change in number (000s)",
}

DEMOGRAPHICS: dict[str, str] = {
    "REGC01": "Northland region",
    "REGC02": "Auckland region",
    "REGC03": "Waikato region",
    "REGC04": "Bay of Plenty region",
    "REGC05": "Gisborne/Hawke's Bay region",
    "REGC06": "Taranaki region",
    "REGC07": "Manawatū-Whanganui region",
    "REGC08": "Wellington region",
    "REGC09": "Tasman / Nelson / Marlborough / West Coast region",
    "REGC10": "Canterbury region",
    "REGC11": "Otago region",
    "REGC12": "Southland region",
    "REGC99": "Total all regions",
    "ETHG01": "European",
    "ETHG02": "Māori",
    "ETHG03": "Pacific peoples",
    "ETHG04": "Asian",
    "ETHG05": "Middle Eastern/Latin American/African",
    "ETHG06": "Other ethnicity",
    "ETHG99": "All ethnicities",
    "DISD01": "Disabled children",
    "DISD02": "Non-disabled children",
    "DISH01": "Children in disabled household",
    "DISH02": "Children in non-disabled household",
    "DISH99": "Total (household disability)",
}

BREAKDOWN_PREFIX = {
    "region": "REGC",
    "ethnicity": "ETHG",
    "disability": ("DISD", "DISH"),
}


def die(message: str, code: int = 1) -> None:
    print(f"child-poverty-nz: {message}", file=sys.stderr)
    raise SystemExit(code)


def request(url: str, timeout: int = 90):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    return urllib.request.urlopen(req, timeout=timeout)


def read_url_text(url: str, timeout: int = 60) -> str:
    try:
        with request(url, timeout=timeout) as resp:
            return resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        die(f"HTTP {e.code} from {url}" + (f": {raw[:200].strip()}" if raw.strip() else ""))
    except urllib.error.URLError as e:
        die(f"network error calling {url}: {e.reason}")


def absolute_stats_url(path: str) -> str:
    return urllib.parse.urljoin(STATS_BASE, path)


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


def fmt_pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1f}%"


def fmt_num(value: float | None) -> str:
    return "n/a" if value is None else f"{value:,.1f}"


def emit_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))


def output(payload: dict[str, Any], json_flag: bool, render: Callable[[dict[str, Any]], None]) -> None:
    if json_flag:
        emit_json(payload)
    else:
        render(payload)


# ---------------------------------------------------------------------------
# Release discovery + data loading
# ---------------------------------------------------------------------------

def catalogue_releases() -> list[dict[str, str]]:
    """Scrape the Stats NZ CSV-files index for child-poverty release ZIPs."""
    text = read_url_text(CSV_PAGE)
    match = re.search(r'<div id="pageViewData"[^>]*data-value="(.*?)"', text, re.S)
    if not match:
        die("could not find pageViewData JSON in the Stats NZ CSV-files index")
    try:
        data = json.loads(html.unescape(match.group(1)))
    except json.JSONDecodeError as e:
        die(f"invalid embedded pageViewData JSON: {e}")

    releases: list[dict[str, str]] = []
    for block in data.get("PageBlocks", []):
        for doc in block.get("BlockDocuments") or []:
            title = str(doc.get("Title") or doc.get("Name") or "")
            link = doc.get("DocumentLink")
            if not link or str(doc.get("DocumentExtension") or "").lower() != "zip":
                continue
            low = title.lower()
            # Core CPRA release only; exclude the household-income map extras.
            if "child poverty statistics" not in low:
                continue
            year_m = re.search(r"year ended june\s+(\d{4})", low)
            releases.append(
                {
                    "title": title,
                    "year": year_m.group(1) if year_m else "",
                    "url": absolute_stats_url(str(link)),
                    "size": str(doc.get("DocumentSize") or ""),
                }
            )
    releases.sort(key=lambda r: r["year"], reverse=True)
    return releases


def latest_release() -> dict[str, str]:
    releases = catalogue_releases()
    if not releases:
        die("no child-poverty CSV release found in the Stats NZ CSV-files index")
    return releases[0]


def load_zip(url: str) -> zipfile.ZipFile:
    try:
        with request(url, timeout=120) as resp:
            blob = resp.read()
    except urllib.error.HTTPError as e:
        die(f"HTTP {e.code} downloading release ZIP {url}")
    except urllib.error.URLError as e:
        die(f"network error downloading release ZIP {url}: {e.reason}")
    try:
        return zipfile.ZipFile(io.BytesIO(blob))
    except zipfile.BadZipFile:
        die(f"release at {url} was not a valid ZIP archive")


def _read_csv(zf: zipfile.ZipFile, needle: str, anti: str = "") -> list[dict[str, str]]:
    name = next(
        (n for n in zf.namelist() if needle in n.lower() and n.lower().endswith(".csv") and (not anti or anti not in n.lower())),
        None,
    )
    if name is None:
        die(f"could not find a '{needle}' CSV inside the release ZIP")
    text = zf.read(name).decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(text)))


def national_rows(zf: zipfile.ZipFile) -> list[dict[str, str]]:
    return _read_csv(zf, "national")


def dem_rows(zf: zipfile.ZipFile) -> list[dict[str, str]]:
    return _read_csv(zf, "reg-eth-dis")


def resolve_release(year: str | None) -> dict[str, str]:
    if not year:
        return latest_release()
    for rel in catalogue_releases():
        if rel["year"] == str(year):
            return rel
    die(f"no child-poverty release found for year ended June {year}")


def valid_measure(code: str) -> str:
    code = code.strip().upper()
    if code not in MEASURES:
        die("unknown measure code; valid codes: " + ", ".join(MEASURES))
    return code


def source_block(rel: dict[str, str]) -> dict[str, Any]:
    return {
        "source": "Stats NZ",
        "release": rel["title"],
        "release_year": rel["year"],
        "url": rel["url"],
        "catalogue": CSV_PAGE,
    }


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_measures(args: argparse.Namespace) -> None:
    payload = {
        "source": "Stats NZ (Child Poverty Reduction Act measures)",
        "count": len(MEASURES),
        "measures": [
            {"code": code, "short": m["short"], "name": m["name"]}
            for code, m in MEASURES.items()
        ],
    }

    def render(p: dict[str, Any]) -> None:
        print("NZ child poverty CPRA measures:")
        for m in p["measures"]:
            print(f"  {m['code']}  {m['short']:<26} {m['name']}")

    output(payload, args.json, render)


def cmd_national(args: argparse.Namespace) -> None:
    measure = valid_measure(args.measure)
    rel = resolve_release(args.year)
    zf = load_zip(rel["url"])
    rows = [r for r in national_rows(zf) if r.get("MsCode") == measure]
    if not rows:
        die(f"measure {measure} not present in {rel['title']}")

    by_year: dict[int, dict[str, dict[str, Any]]] = {}
    for r in rows:
        yr = int(r["Year"])
        est = r.get("EstCode", "")
        if est not in NAT_EST:
            continue
        by_year.setdefault(yr, {})[est] = {
            "estimate": as_float(r.get("Estimate")),
            "se": as_float(r.get("SE")),
            "lower_ci": as_float(r.get("LowerCIB")),
            "upper_ci": as_float(r.get("UpperCIB")),
            "flag": r.get("Flag") or None,
        }

    years = sorted(by_year)
    start = int(args.from_year) if args.from_year else (int(args.year) if args.year else years[0])
    end = int(args.to_year) if args.to_year else (int(args.year) if args.year else years[-1])
    selected = [y for y in years if start <= y <= end]
    if not selected:
        die("no observations matched the supplied year range")

    def pack(yr: int) -> dict[str, Any]:
        d = by_year[yr]
        prop = d.get("A_Proportion", {})
        num = d.get("C_Number", {})
        return {
            "year": yr,
            "proportion_percent": prop.get("estimate"),
            "proportion_lower_ci": prop.get("lower_ci"),
            "proportion_upper_ci": prop.get("upper_ci"),
            "proportion_se": prop.get("se"),
            "number_000s": num.get("estimate"),
            "annual_change_proportion_pp": d.get("B_ChangeInProportion", {}).get("estimate"),
            "annual_change_number_000s": d.get("D_ChangeInNumber", {}).get("estimate"),
            "child_population_000s": d.get("E_Population", {}).get("estimate"),
        }

    observations = [pack(y) for y in selected]
    payload = {
        **source_block(rel),
        "measure": measure,
        "measure_short": MEASURES[measure]["short"],
        "measure_name": MEASURES[measure]["name"],
        "scope": "national",
        "year_range": [selected[0], selected[-1]],
        "latest": observations[-1],
        "observations": observations,
    }

    def render(p: dict[str, Any]) -> None:
        print(f"NZ child poverty — {p['measure']} ({p['measure_short']})")
        print(p["measure_name"])
        for o in p["observations"]:
            ci = ""
            if o["proportion_lower_ci"] is not None:
                ci = f" (CI {fmt_pct(o['proportion_lower_ci'])}–{fmt_pct(o['proportion_upper_ci'])})"
            print(f"  {o['year']}: {fmt_pct(o['proportion_percent'])}{ci}  ~{fmt_num(o['number_000s'])}k children")
        print(f"Source: {p['release']}")
        print(p["url"])

    output(payload, args.json, render)


def cmd_latest(args: argparse.Namespace) -> None:
    rel = latest_release()
    zf = load_zip(rel["url"])
    rows = national_rows(zf)
    latest_year = max(int(r["Year"]) for r in rows)
    index: dict[str, dict[str, dict[str, Any]]] = {}
    for r in rows:
        if int(r["Year"]) != latest_year:
            continue
        index.setdefault(r["MsCode"], {})[r.get("EstCode", "")] = r

    measures = []
    for code, m in MEASURES.items():
        d = index.get(code, {})
        prop = d.get("A_Proportion", {})
        num = d.get("C_Number", {})
        measures.append(
            {
                "code": code,
                "short": m["short"],
                "name": m["name"],
                "proportion_percent": as_float(prop.get("Estimate")),
                "proportion_lower_ci": as_float(prop.get("LowerCIB")),
                "proportion_upper_ci": as_float(prop.get("UpperCIB")),
                "number_000s": as_float(num.get("Estimate")),
            }
        )

    payload = {
        **source_block(rel),
        "scope": "national",
        "year": latest_year,
        "measures": measures,
    }

    def render(p: dict[str, Any]) -> None:
        print(f"NZ child poverty — headline measures, year ended June {p['year']}:")
        for m in p["measures"]:
            ci = ""
            if m["proportion_lower_ci"] is not None:
                ci = f" (CI {fmt_pct(m['proportion_lower_ci'])}–{fmt_pct(m['proportion_upper_ci'])})"
            print(f"  {m['code']} {m['short']:<26} {fmt_pct(m['proportion_percent'])}{ci}")
        print(f"Source: {p['release']}")
        print(p["url"])

    output(payload, args.json, render)


def cmd_breakdown(args: argparse.Namespace) -> None:
    measure = valid_measure(args.measure)
    prefix = BREAKDOWN_PREFIX[args.by]
    prefixes = prefix if isinstance(prefix, tuple) else (prefix,)
    rel = resolve_release(args.year)
    zf = load_zip(rel["url"])
    rows = dem_rows(zf)

    years = sorted({int(r["Year"]) for r in rows})
    target_year = int(args.year) if args.year else years[-1]

    grouped: dict[str, dict[str, Any]] = {}
    for r in rows:
        if r.get("MsCode") != measure or int(r["Year"]) != target_year:
            continue
        dem = r.get("DemCode", "")
        if not any(dem.startswith(p) for p in prefixes):
            continue
        est = r.get("EstCode", "")
        entry = grouped.setdefault(
            dem, {"code": dem, "label": DEMOGRAPHICS.get(dem, dem)}
        )
        val = as_float(r.get("Estimate"))
        if est == "A_Proportion":
            entry["proportion_percent"] = val
            entry["proportion_lower_ci"] = as_float(r.get("LowerCIB"))
            entry["proportion_upper_ci"] = as_float(r.get("UpperCIB"))
        elif est == "B_Number":
            entry["number_000s"] = val
        elif est == "C_Population":
            entry["child_population_000s"] = val

    if not grouped:
        die(f"no {args.by} breakdown for {measure} in year {target_year}")

    items = sorted(grouped.values(), key=lambda x: x["code"])
    payload = {
        **source_block(rel),
        "measure": measure,
        "measure_short": MEASURES[measure]["short"],
        "scope": args.by,
        "year": target_year,
        "breakdown": items,
    }

    def render(p: dict[str, Any]) -> None:
        print(f"NZ child poverty — {p['measure']} ({p['measure_short']}) by {p['scope']}, year ended June {p['year']}:")
        for it in p["breakdown"]:
            ci = ""
            if it.get("proportion_lower_ci") is not None:
                ci = f" (CI {fmt_pct(it['proportion_lower_ci'])}–{fmt_pct(it['proportion_upper_ci'])})"
            print(f"  {it['label']}: {fmt_pct(it.get('proportion_percent'))}{ci}  ~{fmt_num(it.get('number_000s'))}k")
        print(f"Source: {p['release']}")
        print(p["url"])

    output(payload, args.json, render)


def cmd_trend(args: argparse.Namespace) -> None:
    measure = valid_measure(args.measure)
    rel = latest_release()
    zf = load_zip(rel["url"])

    series = []
    if args.demographic:
        dem = args.demographic.strip().upper()
        if dem not in DEMOGRAPHICS:
            die("unknown demographic code; valid codes: " + ", ".join(DEMOGRAPHICS))
        for r in dem_rows(zf):
            if r.get("MsCode") == measure and r.get("DemCode") == dem and r.get("EstCode") == "A_Proportion":
                series.append(
                    {
                        "year": int(r["Year"]),
                        "proportion_percent": as_float(r.get("Estimate")),
                        "lower_ci": as_float(r.get("LowerCIB")),
                        "upper_ci": as_float(r.get("UpperCIB")),
                    }
                )
        scope = DEMOGRAPHICS[dem]
    else:
        for r in national_rows(zf):
            if r.get("MsCode") == measure and r.get("EstCode") == "A_Proportion":
                series.append(
                    {
                        "year": int(r["Year"]),
                        "proportion_percent": as_float(r.get("Estimate")),
                        "lower_ci": as_float(r.get("LowerCIB")),
                        "upper_ci": as_float(r.get("UpperCIB")),
                    }
                )
        scope = "national"

    series.sort(key=lambda x: x["year"])
    if not series:
        die(f"no trend data for measure {measure}" + (f" / {args.demographic}" if args.demographic else ""))

    payload = {
        **source_block(rel),
        "measure": measure,
        "measure_short": MEASURES[measure]["short"],
        "scope": scope,
        "demographic": args.demographic.upper() if args.demographic else None,
        "series": series,
    }

    def render(p: dict[str, Any]) -> None:
        print(f"NZ child poverty trend — {p['measure']} ({p['measure_short']}), {p['scope']}:")
        for s in p["series"]:
            print(f"  {s['year']}: {fmt_pct(s['proportion_percent'])}")
        print(f"Source: {p['release']}")
        print(p["url"])

    output(payload, args.json, render)


def cmd_releases(args: argparse.Namespace) -> None:
    releases = catalogue_releases()
    payload = {
        "source": "Stats NZ",
        "catalogue": CSV_PAGE,
        "count": len(releases),
        "releases": releases,
    }

    def render(p: dict[str, Any]) -> None:
        print(f"Child poverty CSV releases ({p['count']}):")
        for r in p["releases"]:
            size = f" ({r['size']})" if r.get("size") else ""
            print(f"  Year ended June {r['year'] or '?'}{size}")
            print(f"    {r['url']}")

    output(payload, args.json, render)


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only CLI for NZ child poverty statistics (Stats NZ / CPRA).")
    sub = parser.add_subparsers(dest="command")

    m = sub.add_parser("measures", help="List the nine CPRA measure codes with plain-English names")
    m.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    m.set_defaults(func=cmd_measures)

    n = sub.add_parser("national", help="National proportion, number, change and population for a measure")
    n.add_argument("--measure", default="MEASA", help="Measure code (default MEASA / BHC<50%)")
    n.add_argument("--year", help="Single year ended June (e.g. 2025)")
    n.add_argument("--from", dest="from_year", help="Start year")
    n.add_argument("--to", dest="to_year", help="End year")
    n.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    n.set_defaults(func=cmd_national)

    la = sub.add_parser("latest", help="Most recent year headline proportion + CI for all nine measures")
    la.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    la.set_defaults(func=cmd_latest)

    b = sub.add_parser("breakdown", help="Disaggregated proportion/number by region, ethnicity or disability")
    b.add_argument("--measure", default="MEASA", help="Measure code (default MEASA)")
    b.add_argument("--by", required=True, choices=["region", "ethnicity", "disability"], help="Demographic dimension")
    b.add_argument("--year", help="Year ended June (default latest available, 2019-2025)")
    b.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    b.set_defaults(func=cmd_breakdown)

    t = sub.add_parser("trend", help="Full time series for a measure (optionally by demographic) for charting")
    t.add_argument("--measure", default="MEASA", help="Measure code (default MEASA)")
    t.add_argument("--demographic", help="Demographic code (e.g. REGC02, ETHG02, DISD01) for disaggregated trend")
    t.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    t.set_defaults(func=cmd_trend)

    r = sub.add_parser("releases", help="List available child-poverty CSV releases and their ZIP URLs")
    r.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    r.set_defaults(func=cmd_releases)

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
