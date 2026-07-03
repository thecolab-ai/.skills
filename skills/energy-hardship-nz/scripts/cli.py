#!/usr/bin/env python3
"""Energy hardship CLI for New Zealand.

Read-only stdlib wrapper over three public sources:

- MBIE's "Report on Energy Hardship Measures" workbook (energy hardship
  measures, published as a single .xlsx release with no CSV sibling).
- Stats NZ Household Economic Survey (HES) household expenditure statistics,
  distributed on data.govt.nz via the public CKAN API (electricity/domestic
  fuel spend as a share of income, by decile/quintile).
- Electricity Authority EMI "Disconnections for Non-Payment" dataset
  (quarterly domestic disconnection counts).

No login, API key, browser automation, or data mutation. The MBIE workbook is
parsed by hand with zipfile + xml.etree (an .xlsx is a zip of XML) since the
repo is Python-stdlib-only. Source layouts can shift release to release, so
every command degrades to a clearly-flagged raw/partial result instead of
crashing when an assumption about column names or file naming doesn't hold.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from typing import Any, Callable

UA = "energy-hardship-nz-skill/1.0 (+https://github.com/thecolab-ai/.skills)"

CKAN_BASE = "https://catalogue.data.govt.nz/api/3/action"
MBIE_PAGE = (
    "https://www.mbie.govt.nz/building-and-energy/energy-and-natural-resources/"
    "energy-statistics-and-modelling/energy-publications-and-technical-papers/"
    "reporting-on-energy-hardship-measures"
)
HES_SEARCH_QUERY = "household expenditure statistics"
EMI_DISCONNECTIONS_PAGE = "https://www.emi.ea.govt.nz/Retail/Datasets/Disconnections"

TIMEOUT_API = 15
TIMEOUT_DOWNLOAD = 45

XLSX_SKIP_SHEETS = ("guide", "cover", "notes", "readme", "contents")
ENERGY_KEYWORDS = ("electric", "power", "domestic fuel", "energy")


def die(message: str, code: int = 1) -> None:
    print(f"energy-hardship-nz: {message}", file=sys.stderr)
    raise SystemExit(code)


def http_get(url: str, timeout: int, accept: str = "*/*"):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept})
    return urllib.request.urlopen(req, timeout=timeout)


def fetch_text(url: str, timeout: int = TIMEOUT_API) -> str:
    with http_get(url, timeout, "text/html,application/xml,*/*") as resp:
        return resp.read().decode("utf-8", "replace")


def fetch_bytes(url: str, timeout: int = TIMEOUT_DOWNLOAD) -> bytes:
    with http_get(url, timeout) as resp:
        return resp.read()


def safe_fetch_text(url: str, timeout: int = TIMEOUT_API) -> tuple[str | None, str | None]:
    try:
        return fetch_text(url, timeout), None
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}"
    except urllib.error.URLError as e:
        return None, f"network error: {e.reason}"
    except Exception as e:  # pragma: no cover - defensive
        return None, str(e)


def safe_fetch_bytes(url: str, timeout: int = TIMEOUT_DOWNLOAD) -> tuple[bytes | None, str | None]:
    try:
        return fetch_bytes(url, timeout), None
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}"
    except urllib.error.URLError as e:
        return None, f"network error: {e.reason}"
    except Exception as e:  # pragma: no cover - defensive
        return None, str(e)


def read_text(url: str, timeout: int = TIMEOUT_API) -> str:
    text, err = safe_fetch_text(url, timeout)
    if err:
        die(f"failed calling {url}: {err}")
    return text


def read_bytes(url: str, timeout: int = TIMEOUT_DOWNLOAD) -> bytes:
    data, err = safe_fetch_bytes(url, timeout)
    if err:
        die(f"failed downloading {url}: {err}")
    return data


def safe_ckan(action: str, params: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    url = f"{CKAN_BASE}/{action}?" + urllib.parse.urlencode(params)
    text, err = safe_fetch_text(url, TIMEOUT_API)
    if err:
        return None, err
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None, f"invalid JSON from {url}"
    if not payload.get("success"):
        return None, f"CKAN API reported failure for {url}"
    return payload["result"], None


def ckan(action: str, params: dict[str, Any]) -> dict[str, Any]:
    result, err = safe_ckan(action, params)
    if err:
        die(err)
    return result


def find_links(html: str, base_url: str, ext: str) -> list[str]:
    hrefs = re.findall(r'href=["\']([^"\']+)["\']', html, re.IGNORECASE)
    out: list[str] = []
    seen: set[str] = set()
    for href in hrefs:
        if href.split("?")[0].lower().endswith(ext):
            absolute = urllib.parse.urljoin(base_url, href)
            if absolute not in seen:
                seen.add(absolute)
                out.append(absolute)
    return out


def find_csv_files(html: str, base_url: str) -> list[str]:
    names = re.findall(r"[\w\-.]+\.csv", html, re.IGNORECASE)
    out: list[str] = []
    seen: set[str] = set()
    for name in names:
        absolute = urllib.parse.urljoin(base_url + "/", name)
        if absolute not in seen:
            seen.add(absolute)
            out.append(absolute)
    return out


def parse_xlsx(data: bytes, max_rows: int = 2000) -> dict[str, Any]:
    """Parse the first non-boilerplate sheet of an .xlsx into raw rows.

    An .xlsx is a zip of XML parts, so this uses zipfile + xml.etree only
    (no pip dependency). Layout assumptions are intentionally minimal: pick
    the first sheet whose name doesn't look like a cover/guide page, and
    return every populated row verbatim rather than guessing column meaning.
    """
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        die("downloaded workbook is not a valid .xlsx (zip) file")
    ns = {
        "a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
        "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    }
    shared: list[str] = []
    if "xl/sharedStrings.xml" in z.namelist():
        root = ET.fromstring(z.read("xl/sharedStrings.xml"))
        for si in root.findall(".//a:si", ns):
            shared.append("".join(t.text or "" for t in si.findall(".//a:t", ns)))
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    relmap = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels}
    sheet_entries: list[tuple[str, str]] = []
    for s in wb.findall(".//a:sheet", ns):
        name = s.attrib.get("name", "")
        rid = s.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
        path = "xl/" + relmap.get(rid, "").lstrip("/")
        sheet_entries.append((name, path))
    if not sheet_entries:
        die("workbook has no sheets")
    chosen = next(
        (entry for entry in sheet_entries if not any(kw in entry[0].lower() for kw in XLSX_SKIP_SHEETS)),
        sheet_entries[0],
    )
    name, path = chosen
    if path not in z.namelist():
        die(f"could not find worksheet data for {name!r}")
    root = ET.fromstring(z.read(path))
    rows: list[list[str]] = []
    for row in root.findall(".//a:sheetData/a:row", ns):
        values: list[str] = []
        for c in row.findall("a:c", ns):
            cell_type = c.attrib.get("t")
            v = c.find("a:v", ns)
            text = ""
            if cell_type == "s" and v is not None:
                idx = int(v.text or 0)
                text = shared[idx] if idx < len(shared) else ""
            elif cell_type == "inlineStr":
                text = "".join(x.text or "" for x in c.findall(".//a:t", ns))
            elif v is not None:
                text = v.text or ""
            values.append(text)
        if any(v not in ("", None) for v in values):
            rows.append(values)
        if len(rows) >= max_rows:
            break
    return {"sheets": [n for n, _ in sheet_entries], "sheet": name, "rows": rows}


def rows_to_records(rows: list[list[str]]) -> tuple[list[str], list[dict[str, str]]]:
    header_idx = next((i for i, r in enumerate(rows) if sum(1 for v in r if v.strip()) >= 2), None)
    if header_idx is None:
        return [], []
    header = [h.strip() or f"col{i + 1}" for i, h in enumerate(rows[header_idx])]
    records: list[dict[str, str]] = []
    for r in rows[header_idx + 1 :]:
        if not any(v.strip() for v in r):
            continue
        records.append({(header[i] if i < len(header) else f"col{i + 1}"): v for i, v in enumerate(r)})
    return header, records


def csv_records_from_bytes(data: bytes) -> list[dict[str, str]]:
    if data[:2] == b"PK":
        try:
            z = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile:
            die("downloaded resource is not a valid zip archive")
        names = [n for n in z.namelist() if n.lower().endswith(".csv")]
        if not names:
            die("zip archive did not contain a CSV file")
        raw = z.read(names[0])
    else:
        raw = data
    text = raw.decode("utf-8-sig", "replace")
    return list(csv.DictReader(io.StringIO(text)))


def pick_resource(resources: list[dict[str, Any]], keywords: list[str]) -> dict[str, Any] | None:
    best: dict[str, Any] | None = None
    best_score = 0
    for r in resources:
        haystack = " ".join(str(r.get(k, "")) for k in ("name", "url", "format")).lower()
        score = sum(1 for kw in keywords if kw.lower() in haystack)
        if score > best_score:
            best_score = score
            best = r
    return best


def parse_year(raw: str, label: str) -> str:
    if not re.fullmatch(r"\d{4}", raw):
        die(f"expected {label} as YYYY, received: {raw}")
    return raw


def parse_yyyymm(raw: str, label: str) -> str:
    if not re.fullmatch(r"\d{4}-\d{2}", raw):
        die(f"expected {label} as YYYY-MM, received: {raw}")
    return raw


def emit(data: dict[str, Any], as_json: bool, render: Callable[[dict[str, Any]], str]) -> None:
    if as_json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(render(data))


def render_datasets(d: dict[str, Any]) -> str:
    lines = ["Energy hardship data sources:"]
    for s in d["sources"]:
        state = "available" if s["available"] else "unavailable"
        lines.append(f"- {s['id']} [{state}]: {s['title']}")
        if s.get("note"):
            lines.append(f"    note: {s['note']}")
    return "\n".join(lines)


def render_measures(d: dict[str, Any]) -> str:
    lines = [f"MBIE energy hardship measures — sheet {d['sheet']!r} ({d['count']} rows)"]
    if d.get("note"):
        lines.append(f"note: {d['note']}")
    for r in d["records"][:20]:
        lines.append("- " + " | ".join(f"{k}={v}" for k, v in list(r.items())[:6]))
    return "\n".join(lines)


def render_burden(d: dict[str, Any]) -> str:
    lines = [f"HES household expenditure — {d['breakdown']} ({d['count']} rows)"]
    if d.get("note"):
        lines.append(f"note: {d['note']}")
    for r in d["records"][:20]:
        lines.append("- " + " | ".join(f"{k}={v}" for k, v in list(r.items())[:6]))
    return "\n".join(lines)


def render_disconnections(d: dict[str, Any]) -> str:
    if not d["available"]:
        return f"EMI disconnections dataset unavailable: {d['note']}"
    lines = [f"EMI disconnections for non-payment ({d['count']} rows)"]
    for r in d["records"][:20]:
        lines.append("- " + " | ".join(f"{k}={v}" for k, v in list(r.items())[:6]))
    return "\n".join(lines)


def cmd_datasets(args: argparse.Namespace) -> None:
    sources = []

    mbie_text, mbie_err = safe_fetch_text(MBIE_PAGE)
    mbie_links = find_links(mbie_text, MBIE_PAGE, ".xlsx") if mbie_text else []
    sources.append(
        {
            "id": "mbie-energy-hardship-measures",
            "title": "MBIE Report on Energy Hardship Measures",
            "page_url": MBIE_PAGE,
            "workbook_url": mbie_links[0] if mbie_links else None,
            "available": bool(mbie_links),
            "note": None if mbie_links else (mbie_err or "no .xlsx link found on the page"),
        }
    )

    hes_result, hes_err = safe_ckan("package_search", {"q": HES_SEARCH_QUERY, "rows": 10})
    hes_matches = []
    if hes_result:
        for pkg in hes_result.get("results", []):
            if "expenditure" in (pkg.get("title") or "").lower():
                hes_matches.append(
                    {
                        "name": pkg.get("name"),
                        "title": pkg.get("title"),
                        "url": f"https://catalogue.data.govt.nz/dataset/{pkg.get('name')}",
                    }
                )
    sources.append(
        {
            "id": "stats-nz-hes-expenditure",
            "title": "Stats NZ Household Expenditure Statistics (HES) via CKAN",
            "page_url": f"{CKAN_BASE}/package_search?q=" + urllib.parse.quote(HES_SEARCH_QUERY),
            "datasets": hes_matches,
            "available": bool(hes_matches),
            "note": None if hes_matches else (hes_err or "no matching dataset found"),
        }
    )

    emi_text, emi_err = safe_fetch_text(EMI_DISCONNECTIONS_PAGE)
    emi_files = find_csv_files(emi_text, EMI_DISCONNECTIONS_PAGE) if emi_text else []
    sources.append(
        {
            "id": "ea-emi-disconnections",
            "title": "Electricity Authority EMI — Disconnections for Non-Payment",
            "page_url": EMI_DISCONNECTIONS_PAGE,
            "files": emi_files[:10],
            "available": bool(emi_files),
            "note": None if emi_files else (emi_err or "no CSV files found in the dataset listing"),
        }
    )

    emit({"kind": "datasets", "source": "energy-hardship-nz", "sources": sources}, args.json, render_datasets)


def cmd_measures(args: argparse.Namespace) -> None:
    year_ended = parse_year(args.year_ended, "--year-ended") if args.year_ended else None

    html = read_text(MBIE_PAGE)
    links = find_links(html, MBIE_PAGE, ".xlsx")
    if not links:
        die("could not find an .xlsx workbook link on the MBIE energy hardship measures page")
    workbook_url = links[0]
    data = read_bytes(workbook_url)
    parsed = parse_xlsx(data)
    header, records = rows_to_records(parsed["rows"])

    matched = records
    note = None
    if year_ended:
        year_hits = [r for r in records if any(year_ended in str(v) for v in r.values())]
        if year_hits:
            matched = year_hits
        else:
            note = f"no rows/columns matched year-ended {year_ended}; returning the full table instead"

    emit(
        {
            "kind": "measures",
            "source": "MBIE Report on Energy Hardship Measures",
            "source_url": workbook_url,
            "page_url": MBIE_PAGE,
            "sheet": parsed["sheet"],
            "sheets": parsed["sheets"],
            "headers": header,
            "year_ended": year_ended,
            "count": len(matched),
            "records": matched,
            "note": note,
        },
        args.json,
        render_measures,
    )


def cmd_burden(args: argparse.Namespace) -> None:
    year = parse_year(args.year, "--year")

    result = ckan("package_search", {"q": HES_SEARCH_QUERY, "rows": 10})
    candidates = [p for p in result.get("results", []) if "expenditure" in (p.get("title") or "").lower()]
    if not candidates:
        die(f"no Stats NZ household expenditure dataset found for query {HES_SEARCH_QUERY!r}")
    dataset = candidates[0]
    pkg = ckan("package_show", {"id": dataset["name"]})
    resources = pkg.get("resources", [])
    resource = pick_resource(resources, ["detailed", "expenditure", year]) or pick_resource(
        resources, ["detailed", "expenditure"]
    )
    if resource is None:
        die(f"no matching expenditure CSV resource found in dataset {dataset['name']!r}")

    data = read_bytes(resource["url"])
    records = csv_records_from_bytes(data)
    if not records:
        die("downloaded expenditure resource had no CSV rows")

    breakdown_kw = "decile" if args.breakdown == "income-decile" else "quintile"

    def row_matches(row: dict[str, str]) -> bool:
        haystack = " ".join(str(v) for v in row.values()).lower()
        return any(kw in haystack for kw in ENERGY_KEYWORDS) and (breakdown_kw in haystack or year in haystack)

    matched = [r for r in records if row_matches(r)]
    note = None
    if not matched:
        matched = records[:20]
        note = (
            f"no rows matched an electricity/domestic-fuel category with {args.breakdown}; "
            "showing the first 20 raw rows so you can inspect the actual column names"
        )

    emit(
        {
            "kind": "burden",
            "source": "Stats NZ Household Expenditure Statistics (HES)",
            "source_url": resource["url"],
            "dataset": dataset["name"],
            "breakdown": args.breakdown,
            "year": year,
            "count": len(matched),
            "records": matched,
            "note": note,
        },
        args.json,
        render_burden,
    )


def cmd_disconnections(args: argparse.Namespace) -> None:
    from_ = parse_yyyymm(args.from_, "--from") if args.from_ else None
    to = parse_yyyymm(args.to, "--to") if args.to else None

    html = read_text(EMI_DISCONNECTIONS_PAGE)
    files = find_csv_files(html, EMI_DISCONNECTIONS_PAGE)
    if not files:
        emit(
            {
                "kind": "disconnections",
                "source": "Electricity Authority EMI — Disconnections for Non-Payment",
                "source_url": EMI_DISCONNECTIONS_PAGE,
                "available": False,
                "note": "no downloadable CSV found in the EMI disconnections dataset listing; check the page directly",
                "records": [],
            },
            args.json,
            render_disconnections,
        )
        return

    all_records: list[dict[str, str]] = []
    fetched_files: list[str] = []
    for url in files[:6]:
        raw, err = safe_fetch_bytes(url)
        if raw is None:
            continue
        fetched_files.append(url)
        all_records.extend(csv_records_from_bytes(raw))

    if not all_records:
        die("found CSV file links but could not download or parse any of them")

    date_col = next((k for k in all_records[0].keys() if re.search(r"date|month|period", k, re.IGNORECASE)), None)
    matched = all_records
    if date_col and (from_ or to):

        def in_range(rec: dict[str, str]) -> bool:
            raw_val = str(rec.get(date_col, ""))
            m = re.search(r"(\d{4})[-/](\d{2})", raw_val)
            if not m:
                return True
            ym = f"{m.group(1)}-{m.group(2)}"
            if from_ and ym < from_:
                return False
            if to and ym > to:
                return False
            return True

        matched = [r for r in all_records if in_range(r)]

    emit(
        {
            "kind": "disconnections",
            "source": "Electricity Authority EMI — Disconnections for Non-Payment",
            "source_url": EMI_DISCONNECTIONS_PAGE,
            "files": fetched_files,
            "available": True,
            "date_column": date_col,
            "from": from_,
            "to": to,
            "count": len(matched),
            "records": matched[:500],
        },
        args.json,
        render_disconnections,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="energy-hardship-nz",
        description="Query NZ energy/electricity hardship data: MBIE hardship measures, "
        "HES household electricity expenditure burden, and EMI disconnection counts.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_datasets = sub.add_parser("datasets", help="List the underlying data sources and their current availability")
    p_datasets.add_argument("--json", action="store_true")
    p_datasets.set_defaults(func=cmd_datasets)

    p_measures = sub.add_parser("measures", help="MBIE's energy hardship measures from the published workbook")
    p_measures.add_argument("--year-ended", help="Filter/annotate for a year-ended value, e.g. 2024")
    p_measures.add_argument("--json", action="store_true")
    p_measures.set_defaults(func=cmd_measures)

    p_burden = sub.add_parser("burden", help="HES electricity/domestic-fuel spend as a share of income or expenditure")
    p_burden.add_argument("--breakdown", choices=["income-decile", "income-quintile"], required=True)
    p_burden.add_argument("--year", required=True, help="Year ended, e.g. 2023")
    p_burden.add_argument("--json", action="store_true")
    p_burden.set_defaults(func=cmd_burden)

    p_disconnections = sub.add_parser("disconnections", help="EMI domestic disconnections for non-payment")
    p_disconnections.add_argument("--from", dest="from_", help="Start month, YYYY-MM")
    p_disconnections.add_argument("--to", help="End month, YYYY-MM")
    p_disconnections.add_argument("--json", action="store_true")
    p_disconnections.set_defaults(func=cmd_disconnections)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
