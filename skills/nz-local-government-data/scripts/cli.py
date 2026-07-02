#!/usr/bin/env python3
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
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from typing import Any

UA = "Mozilla/5.0 (compatible; nz-local-government-data-skill/1.0)"
TIMEOUT = 10
CKAN = "https://catalogue.data.govt.nz/api/3/action/"
LOCALCOUNCILS_INDEX = "http://www.localcouncils.govt.nz/lgip.nsf/wpg_url/Resources-Download-Data-Index"
LOCALCOUNCILS_HTTPS_INDEX = "https://www.localcouncils.govt.nz/lgip.nsf/wpg_url/Resources-Download-Data-Index"
DIA_PERFORMANCE = "https://www.dia.govt.nz/local-government-performance-metrics"
OAG_INSIGHTS = "https://oag.parliament.nz/2025/local-govt"
PERFORMANCE_XLSX_HINT = "Data release for council profiles"

SOURCES = [
    {
        "id": "stats-nz-local-authority-statistics",
        "name": "Stats NZ local authority statistics on data.govt.nz",
        "agency": "Stats NZ / data.govt.nz",
        "url": "https://catalogue.data.govt.nz/dataset/groups/local-authority-statistics",
        "api_url": "https://catalogue.data.govt.nz/api/3/action/package_search?fq=groups:local-and-regional-government&q=local%20authority%20statistics",
        "formats": ["CKAN metadata", "CSV/XLSX/PDF where resources expose them"],
        "licence_notes": "Per-resource licence metadata in data.govt.nz; check each dataset before reuse.",
        "cadence": "Dataset-specific; metadata_modified is returned where discoverable.",
        "notes": "The issue source URL currently redirects/404s in CKAN, so the CLI uses the live data.govt.nz Local and regional government group plus search terms.",
    },
    {
        "id": "dia-local-council-downloads",
        "name": "DIA Local Councils downloadable data index",
        "agency": "Department of Internal Affairs",
        "url": LOCALCOUNCILS_HTTPS_INDEX,
        "fallback_url": LOCALCOUNCILS_INDEX,
        "formats": ["CSV", "XLSX", "HTML"],
        "licence_notes": "Not consistently declared on the legacy page; retain source URL and check page terms for reuse.",
        "cadence": "Dataset-specific; page includes rates rebates, dog control, LTP and related downloads.",
        "notes": "The HTTPS host can fail with old TLS/SNI behaviour; the CLI falls back to HTTP read-only fetches.",
    },
    {
        "id": "dia-performance-metrics",
        "name": "DIA local government performance metrics / council profiles",
        "agency": "Department of Internal Affairs",
        "url": DIA_PERFORMANCE,
        "formats": ["XLSX data release", "PDF group profiles", "HTML"],
        "licence_notes": "Source page does not expose a machine-readable licence in page metadata; cite DIA page and workbook/PDF URL.",
        "cadence": "Current page references July 2025 council profile data release.",
        "notes": "Machine-readable XLSX is parsed with Python stdlib to list councils and preview metrics.",
    },
    {
        "id": "oag-local-government-insights-2024",
        "name": "Office of the Auditor-General insights into local government 2024",
        "agency": "Office of the Auditor-General",
        "url": OAG_INSIGHTS,
        "formats": ["HTML", "PDF/report pages where available"],
        "licence_notes": "Use as official analysis context; do not treat narrative report pages as structured council-level data.",
        "cadence": "Annual/periodic insight reporting.",
        "notes": "Some automated HTTP clients receive 403; listed as an official source and fetched only for metadata when available.",
    },
]

CODE_LABELS = {
    "A": "Auckland Council group",
    "U": "unitary authority group",
    "RC": "regional council group",
    "M": "large metro group",
    "MP": "small metro / large provincial group",
    "PR": "small provincial / rural group",
    "CI": "Chatham Islands Council",
}

METRIC_ALIASES = {
    "rates": ["Total rates revenue for 2024 ($000)", "Total rates revenue for 2023 ($000)", "Total forecast rates revenue for 2025 ($000)"],
    "forecast-rates": ["Total forecast rates revenue for 2025 ($000)", "Total forecast rates revenue for 2026 ($000)"],
    "population": ["Population for 2024 (no.)", "Population for 2023 (no.)"],
    "land-area": ["Land area for 2025 (km²)"],
    "debt": ["Total debt for 2024 ($000)", "Total forecast debt for 2025 ($000)", "Total liabilities for 2024 ($000)"],
    "capital-expenditure": ["Capital expenditure for 2024 ($000)", "Total capital expenditure for 2024 ($000)"],
}


def die(message: str, code: int = 1) -> None:
    print(f"nz-local-government-data: {message}", file=sys.stderr)
    raise SystemExit(code)


def fetch_bytes(url: str, timeout: int = TIMEOUT) -> tuple[bytes, str, str | None]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read(), resp.geturl(), resp.headers.get("content-type")
    except urllib.error.HTTPError as exc:
        body = exc.read(300).decode("utf-8", "replace")
        raise RuntimeError(f"HTTP {exc.code} fetching {url}: {body}") from exc
    except Exception as exc:
        raise RuntimeError(f"failed fetching {url}: {exc}") from exc


def fetch_text(url: str, timeout: int = TIMEOUT) -> tuple[str, str, str | None]:
    data, final_url, ctype = fetch_bytes(url, timeout=timeout)
    return data.decode("utf-8", "replace"), final_url, ctype


def ckan_get(action: str, params: dict[str, Any], timeout: int = TIMEOUT) -> tuple[dict[str, Any], str]:
    url = CKAN + action + "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    data, final_url, _ = fetch_bytes(url, timeout=timeout)
    payload = json.loads(data.decode("utf-8"))
    if not payload.get("success"):
        raise RuntimeError(f"CKAN success=false for {final_url}: {payload.get('error')}")
    return payload.get("result") or {}, final_url


def normalise_url(href: str, base: str) -> str:
    href = html.unescape(href.strip())
    if href.startswith("diawebsite.nsf/"):
        href = "/" + href
    return urllib.parse.urljoin(base, href)


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[dict[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "a":
            attrs_d = dict(attrs)
            self._href = attrs_d.get("href")
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._href is not None:
            label = re.sub(r"\s+", " ", html.unescape("".join(self._text))).strip()
            self.links.append({"href": self._href, "label": label})
            self._href = None
            self._text = []


def extract_links(page_url: str, timeout: int = TIMEOUT) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    tried = []
    last_error = "unknown error"
    for url in ([page_url, LOCALCOUNCILS_INDEX] if page_url.startswith("https://www.localcouncils") else [page_url]):
        tried.append(url)
        try:
            text, final_url, ctype = fetch_text(url, timeout=timeout)
            parser = LinkParser()
            parser.feed(text)
            links = []
            for item in parser.links:
                href = item["href"]
                full = normalise_url(href, final_url)
                label = item["label"] or full.rsplit("/", 1)[-1]
                ext = urllib.parse.urlparse(full).path.rsplit(".", 1)[-1].upper() if "." in urllib.parse.urlparse(full).path else "HTML"
                if ext == "XLS":
                    ext = "XLS"
                links.append({"label": label, "url": full, "format": ext, "source_page": final_url})
            meta = {"source_url": final_url, "content_type": ctype, "tried": tried, "status": "ok"}
            return links, meta
        except Exception as exc:
            last_error = str(exc)
            continue
    return [], {"source_url": page_url, "tried": tried, "status": "fetch_error", "error": last_error}


def interesting_download(link: dict[str, Any]) -> bool:
    url = link.get("url", "").lower()
    label = link.get("label", "").lower()
    return any(token in url for token in ("$file", ".csv", ".xlsx", ".xls", ".pdf")) or any(
        token in label for token in ("data", "statistics", "metrics", "profile", "download", "glossary", "ltp")
    )


def dia_downloads(timeout: int = TIMEOUT) -> list[dict[str, Any]]:
    links, meta = extract_links(LOCALCOUNCILS_HTTPS_INDEX, timeout=timeout)
    rows = [x for x in links if interesting_download(x)]
    for row in rows:
        row["source"] = "DIA Local Councils downloadable data index"
        row["fetch_status"] = meta["status"]
        if meta.get("tried"):
            row["fetch_tried"] = meta["tried"]
    return rows


def performance_links(timeout: int = TIMEOUT) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    links, meta = extract_links(DIA_PERFORMANCE, timeout=timeout)
    rows = [x for x in links if interesting_download(x)]
    for row in rows:
        row["source"] = "DIA local government performance metrics"
        row["fetch_status"] = meta["status"]
    return rows, meta


def performance_workbook_url(timeout: int = TIMEOUT) -> str:
    rows, _ = performance_links(timeout=timeout)
    candidates = [r for r in rows if PERFORMANCE_XLSX_HINT.lower() in r.get("label", "").lower() and r.get("url", "").lower().endswith(".xlsx")]
    # Prefer the UTF-8 named workbook when present because it is a compact one-sheet data release.
    candidates.sort(key=lambda r: ("csv-utf-8" not in r.get("url", "").lower(), r.get("url", "")))
    if not candidates:
        raise RuntimeError("could not find DIA council profiles XLSX data release link on performance metrics page")
    return candidates[0]["url"]


def col_index(ref: str) -> int:
    letters = re.sub(r"[^A-Z]", "", ref.upper())
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - 64)
    return max(n - 1, 0)


def xlsx_rows(url: str, limit: int | None = None, timeout: int = TIMEOUT) -> tuple[list[list[str]], dict[str, Any]]:
    data, final_url, ctype = fetch_bytes(url, timeout=timeout)
    ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in zf.namelist():
            root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for si in root.findall(ns + "si"):
                shared.append("".join(t.text or "" for t in si.iter(ns + "t")))
        root = ET.fromstring(zf.read("xl/worksheets/sheet1.xml"))
        rows: list[list[str]] = []
        for row in root.iter(ns + "row"):
            values: dict[int, str] = {}
            for cell in row.findall(ns + "c"):
                idx = col_index(cell.get("r", "A"))
                val_node = cell.find(ns + "v")
                value = "" if val_node is None else (val_node.text or "")
                if cell.get("t") == "s" and value:
                    try:
                        value = shared[int(value)]
                    except (ValueError, IndexError):
                        pass
                values[idx] = value
            if values:
                max_idx = max(values)
                rows.append([values.get(i, "") for i in range(max_idx + 1)])
            if limit is not None and len(rows) >= limit:
                break
    return rows, {"source_url": final_url, "content_type": ctype, "bytes": len(data), "format": "XLSX"}


def performance_table(timeout: int = TIMEOUT) -> tuple[list[dict[str, str]], dict[str, Any]]:
    url = performance_workbook_url(timeout=timeout)
    rows, meta = xlsx_rows(url, timeout=timeout)
    if not rows:
        return [], meta
    headers = rows[0]
    table: list[dict[str, str]] = []
    for row in rows[1:]:
        rec = {headers[i]: row[i] if i < len(row) else "" for i in range(len(headers))}
        if rec.get("Council"):
            table.append(rec)
    meta["headers"] = headers
    meta["record_count"] = len(table)
    meta["licence_notes"] = SOURCES[2]["licence_notes"]
    meta["cadence"] = SOURCES[2]["cadence"]
    return table, meta


def ckan_dataset_summary(pkg: dict[str, Any]) -> dict[str, Any]:
    org = pkg.get("organization") or {}
    resources = pkg.get("resources") or []
    return {
        "id": pkg.get("id"),
        "name": pkg.get("name"),
        "title": pkg.get("title"),
        "organisation": org.get("title") or org.get("name") if isinstance(org, dict) else org,
        "metadata_modified": pkg.get("metadata_modified"),
        "licence": pkg.get("license_title") or pkg.get("license_id"),
        "notes": re.sub(r"\s+", " ", pkg.get("notes") or "").strip()[:400],
        "url": f"https://catalogue.data.govt.nz/dataset/{pkg.get('name')}",
        "resources": [
            {
                "id": r.get("id"),
                "name": r.get("name"),
                "format": r.get("format"),
                "url": r.get("url"),
                "datastore_active": r.get("datastore_active"),
                "last_modified": r.get("last_modified"),
            }
            for r in resources[:12]
        ],
        "resource_count": len(resources),
    }


def stats_datasets(
    query: str = "local authority statistics",
    limit: int = 10,
    timeout: int = TIMEOUT,
    fq: str = "groups:local-and-regional-government",
) -> dict[str, Any]:
    try:
        result, url = ckan_get(
            "package_search",
            {"q": query, "fq": fq, "rows": limit},
            timeout=timeout,
        )
    except Exception:
        result, url = ckan_get("package_search", {"q": query, "rows": limit}, timeout=timeout)
    return {
        "source": "data.govt.nz CKAN",
        "source_url": url,
        "query": query,
        "filter_query": fq,
        "count": result.get("count"),
        "datasets": [ckan_dataset_summary(pkg) for pkg in result.get("results", [])],
    }


def preview_csv_url(url: str, limit: int, timeout: int = TIMEOUT) -> dict[str, Any]:
    data, final_url, ctype = fetch_bytes(url, timeout=timeout)
    text = data[:250000].decode("utf-8-sig", "replace")
    reader = csv.DictReader(io.StringIO(text))
    records = []
    for idx, row in enumerate(reader):
        if idx >= limit:
            break
        records.append(dict(row))
    return {"source_url": final_url, "content_type": ctype, "fields": reader.fieldnames or [], "records": records, "format": "CSV"}


def output(data: Any, as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return
    kind = data.get("kind") if isinstance(data, dict) else None
    if kind == "datasets":
        print("Official NZ local government data sources")
        for src in data["sources"]:
            print(f"- {src['id']}: {src['name']}")
            print(f"  {src['url']}")
            print(f"  formats: {', '.join(src.get('formats', []))}; cadence: {src.get('cadence', '-')}")
        print(f"\nDiscovered data.govt.nz datasets: {data['stats_nz'].get('count')} total, {len(data['stats_nz'].get('datasets', []))} shown")
        for ds in data["stats_nz"].get("datasets", [])[:5]:
            print(f"- {ds.get('title')} ({ds.get('name')}) | {ds.get('organisation')} | {ds.get('metadata_modified', '')[:10]}")
    elif kind == "downloads":
        print(f"DIA downloadable resources: {len(data['downloads'])} shown")
        for item in data["downloads"]:
            print(f"- {item.get('label')} [{item.get('format')}] {item.get('url')}")
    elif kind == "performance-metrics":
        print(f"DIA performance metrics: {data['record_count']} councils, {len(data['metrics'])} columns")
        print(f"source: {data['source_url']}")
        print("metrics preview: " + ", ".join(data["metrics"][:10]))
        for row in data["records"][: data.get("limit", 5)]:
            print(f"- {row.get('Council')} ({row.get('Code')}): population 2024={row.get('Population for 2024 (no.)')}, rates 2024 $000={row.get('Total rates revenue for 2024 ($000)')}")
    elif kind == "councils":
        print(f"Councils from DIA performance data: {len(data['councils'])}")
        for c in data["councils"]:
            print(f"- {c['name']} [{c['code']}: {c['type']}] population_2024={c.get('population_2024')} source_id={c.get('source_id')}")
    elif kind == "local-authority-stats":
        print(f"data.govt.nz local authority statistics search: {data['query']!r}; {data.get('count')} total")
        for ds in data.get("datasets", []):
            print(f"- {ds.get('title')} ({ds.get('name')}) | resources={ds.get('resource_count')} | licence={ds.get('licence')}")
            print(f"  {ds.get('url')}")
        if data.get("preview"):
            print("preview:")
            for rec in data["preview"].get("records", [])[:5]:
                print("- " + json.dumps(rec, ensure_ascii=False)[:300])
    elif kind == "compare":
        print(f"Compare metric {data['metric']}: {data['metric_column']}")
        for row in data["results"]:
            print(f"- {row['council']}: {row.get('value')} ({row.get('code')})")
    else:
        print(json.dumps(data, indent=2, ensure_ascii=False))


def cmd_datasets(args: argparse.Namespace) -> None:
    stats = stats_datasets(limit=args.limit, timeout=args.timeout)
    perf_links, perf_meta = performance_links(timeout=args.timeout)
    downloads = dia_downloads(timeout=args.timeout)
    data = {
        "kind": "datasets",
        "sources": SOURCES,
        "stats_nz": stats,
        "dia_download_count": len(downloads),
        "dia_downloads_preview": downloads[:5],
        "performance_resource_count": len(perf_links),
        "performance_resources_preview": perf_links[:8],
        "performance_fetch": perf_meta,
        "caveat": "Discovery lists official sources and machine-readable resources where available; PDF-only/report sources are not converted into structured data.",
    }
    output(data, args.json)


def cmd_downloads(args: argparse.Namespace) -> None:
    rows = dia_downloads(timeout=args.timeout)
    if args.format:
        rows = [r for r in rows if (r.get("format") or "").lower() == args.format.lower()]
    output({"kind": "downloads", "source": SOURCES[1], "downloads": rows[: args.limit], "total_discovered": len(rows)}, args.json)


def cmd_performance(args: argparse.Namespace) -> None:
    table, meta = performance_table(timeout=args.timeout)
    records = table
    if args.council:
        q = args.council.lower()
        records = [r for r in records if q in r.get("Council", "").lower()]
    limit = args.limit
    data = {
        "kind": "performance-metrics",
        "source": SOURCES[2],
        "source_url": meta.get("source_url"),
        "record_count": len(table),
        "matched_count": len(records),
        "metrics": meta.get("headers", []),
        "limit": limit,
        "records": records[:limit],
        "licence_notes": meta.get("licence_notes"),
        "cadence": meta.get("cadence"),
    }
    output(data, args.json)


def cmd_councils(args: argparse.Namespace) -> None:
    table, meta = performance_table(timeout=args.timeout)
    councils = []
    for idx, row in enumerate(table, start=1):
        code = row.get("Code", "")
        name = row.get("Council", "")
        if args.query and args.query.lower() not in name.lower() and args.query.lower() not in code.lower():
            continue
        councils.append(
            {
                "source_id": f"dia-performance-{idx}",
                "name": name,
                "code": code,
                "type": CODE_LABELS.get(code, "DIA council profile group"),
                "population_2024": row.get("Population for 2024 (no.)"),
                "land_area_2025_km2": row.get("Land area for 2025 (km²)"),
                "source_url": meta.get("source_url"),
            }
        )
    output({"kind": "councils", "source": SOURCES[2], "councils": councils, "count": len(councils)}, args.json)


def datastore_preview(resource_id: str, limit: int, timeout: int = TIMEOUT) -> dict[str, Any]:
    result, url = ckan_get("datastore_search", {"resource_id": resource_id, "limit": limit}, timeout=timeout)
    return {"source_url": url, "resource_id": resource_id, "total": result.get("total"), "fields": result.get("fields"), "records": result.get("records", []), "format": "CKAN datastore"}


def cmd_local_authority_stats(args: argparse.Namespace) -> None:
    query_parts = ["local authority statistics"]
    if args.council:
        query_parts.append(args.council)
    if args.query:
        query_parts.append(args.query)
    query = " ".join(query_parts)
    stats = stats_datasets(query=query, limit=args.limit, timeout=args.timeout, fq="organization:stats-nz")
    preview = None
    if args.preview and stats.get("datasets"):
        for ds in stats["datasets"]:
            for res in ds.get("resources", []):
                try:
                    if res.get("datastore_active") and res.get("id"):
                        preview = datastore_preview(res["id"], args.preview, timeout=args.timeout)
                    elif (res.get("format") or "").lower() == "csv" and res.get("url"):
                        preview = preview_csv_url(res["url"], args.preview, timeout=args.timeout)
                    if preview:
                        preview["dataset"] = {"name": ds.get("name"), "title": ds.get("title"), "resource": res}
                        raise StopIteration
                except StopIteration:
                    break
                except Exception as exc:
                    preview = {"status": "preview_error", "error": str(exc), "dataset": ds.get("name"), "resource": res.get("name")}
            if preview:
                break
    payload = {"kind": "local-authority-stats", **stats, "preview": preview, "council_filter": args.council}
    output(payload, args.json)


def resolve_metric_column(metric: str, headers: list[str]) -> str:
    candidates = METRIC_ALIASES.get(metric.lower(), [metric])
    lower_headers = {h.lower(): h for h in headers}
    for candidate in candidates:
        if candidate.lower() in lower_headers:
            return lower_headers[candidate.lower()]
    for h in headers:
        if metric.lower() in h.lower():
            return h
    die(f"unknown metric {metric!r}; try one of {', '.join(sorted(METRIC_ALIASES))} or a column name from performance-metrics")
    return metric


def cmd_compare(args: argparse.Namespace) -> None:
    table, meta = performance_table(timeout=args.timeout)
    headers = meta.get("headers", [])
    column = resolve_metric_column(args.metric, headers)
    wanted = [c.strip().lower() for c in args.councils.split(",") if c.strip()]
    if not wanted:
        die("--councils must contain at least one council name")
    results = []
    for want in wanted:
        matches = [r for r in table if want in r.get("Council", "").lower()]
        if not matches:
            results.append({"query": want, "status": "not_found"})
        else:
            row = matches[0]
            results.append({"query": want, "status": "ok", "council": row.get("Council"), "code": row.get("Code"), "type": CODE_LABELS.get(row.get("Code", ""), "DIA council profile group"), "metric_column": column, "value": row.get(column), "source_url": meta.get("source_url")})
    output({"kind": "compare", "metric": args.metric, "metric_column": column, "results": results, "source": SOURCES[2]}, args.json)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Discover and preview official NZ local government finance, performance, and statistics datasets.")
    parser.add_argument("--timeout", type=int, default=TIMEOUT, help="network timeout seconds (default: 10)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("datasets", help="discover official source catalogues and key datasets")
    p.add_argument("--limit", type=int, default=8)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_datasets)

    p = sub.add_parser("downloads", help="enumerate DIA localcouncils.govt.nz downloadable resources")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--format", help="filter by format, e.g. CSV, XLSX, PDF")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_downloads)

    p = sub.add_parser("performance-metrics", help="preview DIA council performance profile data release")
    p.add_argument("--council", help="filter council name")
    p.add_argument("--limit", type=int, default=5)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_performance)

    p = sub.add_parser("councils", help="list councils and DIA profile group identifiers")
    p.add_argument("--query", help="filter by council name or code")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_councils)

    p = sub.add_parser("local-authority-stats", help="query data.govt.nz for Stats NZ/local authority statistics resources")
    p.add_argument("--council", help="add a council name to the dataset search")
    p.add_argument("--query", help="additional search terms, e.g. finance, rates, population")
    p.add_argument("--limit", type=int, default=8)
    p.add_argument("--preview", type=int, default=5, help="preview this many records from first CSV/datastore resource; 0 disables")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_local_authority_stats)

    p = sub.add_parser("compare", help="simple DIA performance metric comparison across councils")
    p.add_argument("--metric", required=True, help="metric alias (rates, population, debt, land-area) or exact/partial column name")
    p.add_argument("--councils", required=True, help="comma-separated council name fragments, e.g. Auckland,Wellington")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_compare)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
        return 0
    except RuntimeError as exc:
        die(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
