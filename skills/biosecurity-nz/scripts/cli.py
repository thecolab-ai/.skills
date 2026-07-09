#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import pathlib
import re
import sys
import urllib.parse
from html.parser import HTMLParser
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "lib"))
import nzfetch  # noqa: E402

TIMEOUT = 10

ONZPR_BASE = "https://onzpr.mpi.govt.nz"
PEST_REGISTER_BASE = "https://pierpestregister.mpi.govt.nz"
PIER_SEARCH_BASE = "https://piersearch.mpi.govt.nz"
CKAN_BASE = "https://catalogue.data.govt.nz/api/3/action"
ACTIVE_RESPONSES_URL = (
    "https://www.mpi.govt.nz/biosecurity/exotic-pests-and-diseases-in-new-zealand/"
    "active-biosecurity-responses-to-pests-and-diseases"
)

ONZPR_PACKAGE = "the-official-new-zealand-pest-register"
PIER_PACKAGE = "product-import-export-requirements"


class SkillError(Exception):
    pass


class BlockedSource(Exception):
    def __init__(self, url: str, status: int | None = None, reason: str = "incapsula_blocked"):
        self.url = url
        self.status = status
        self.reason = reason
        super().__init__(reason)


def die(message: str, code: int = 1) -> None:
    print(f"biosecurity-nz: {message}", file=sys.stderr)
    raise SystemExit(code)


def clean_text(value: str) -> str:
    value = html.unescape(value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def snake(label: str) -> str:
    label = clean_text(label).strip(":")
    label = re.sub(r"[^A-Za-z0-9]+", "_", label).strip("_").lower()
    return label or "field"


def absolutise(base: str, href: str | None) -> str | None:
    if not href:
        return None
    return urllib.parse.urljoin(base, html.unescape(href))


def fetch_text(url: str, *, data: dict[str, str] | None = None) -> tuple[str, str]:
    body = None
    method = None
    accept = "application/json,text/html;q=0.9,*/*;q=0.8"
    headers = {"Accept": accept}
    if data is not None:
        body = urllib.parse.urlencode(data).encode("utf-8")
        method = "POST"
        headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
        headers["X-Requested-With"] = "XMLHttpRequest"
    try:
        raw, _content_type, final_url = nzfetch.fetch_bytes(
            url,
            timeout=TIMEOUT,
            accept=accept,
            headers=headers,
            data=body,
            method=method,
            expect_json=False,
        )
    except nzfetch.Blocked as exc:
        # Transient Incapsula/IP-reputation wall — surface via the skill's own
        # graceful blocked_payload path (callers catch BlockedSource).
        raise BlockedSource(url) from exc
    except nzfetch.FetchError as exc:
        raise SkillError(str(exc)) from exc
    return raw.decode("utf-8", "replace"), final_url


def fetch_json(url: str, *, data: dict[str, str] | None = None) -> tuple[Any, str]:
    text, final_url = fetch_text(url, data=data)
    try:
        return json.loads(text), final_url
    except json.JSONDecodeError as exc:
        raise SkillError(f"expected JSON from {final_url}: {exc}")


def boolish(value: Any) -> bool | None:
    if value is None:
        return None
    lower = str(value).strip().lower()
    if lower in ("1", "true", "yes"):
        return True
    if lower in ("0", "false", "no"):
        return False
    return None


def ckan_package(package_id: str) -> dict[str, Any]:
    url = f"{CKAN_BASE}/package_show?{urllib.parse.urlencode({'id': package_id})}"
    payload, final_url = fetch_json(url)
    if not payload.get("success"):
        raise SkillError(f"CKAN returned success=false for {package_id}: {payload.get('error')}")
    result = payload["result"]
    return {
        "id": result.get("id"),
        "name": result.get("name"),
        "title": result.get("title"),
        "notes": result.get("notes"),
        "author": result.get("author"),
        "license_title": result.get("license_title"),
        "isopen": result.get("isopen"),
        "frequency_of_update": result.get("frequency_of_update"),
        "metadata_modified": result.get("metadata_modified"),
        "modified": result.get("modified"),
        "url": result.get("url"),
        "source_identifier": result.get("source_identifier"),
        "source_url": final_url,
        "resources": [
            {
                "id": r.get("id"),
                "name": r.get("name"),
                "format": r.get("format"),
                "url": r.get("url"),
                "datastore_active": r.get("datastore_active"),
                "metadata_modified": r.get("metadata_modified"),
            }
            for r in result.get("resources", [])
        ],
    }


def onzpr_table(params: dict[str, Any], *, limit: int, start: int = 0) -> dict[str, Any]:
    url = f"{ONZPR_BASE}/pest-api.php?method=GetTableDataAjax"
    data = {
        "param": json.dumps(params, separators=(",", ":")),
        "draw": "1",
        "start": str(start),
        "length": str(max(0, min(limit, 1000))),
    }
    payload, final_url = fetch_json(url, data=data)
    records = [normalise_pest_record(row) for row in payload.get("data", [])]
    return {
        "kind": "pest_search",
        "status": "ok",
        "source": "Official New Zealand Pest Register",
        "source_url": final_url,
        "query_parameters": params,
        "records_total": payload.get("recordsTotal"),
        "records_filtered": payload.get("recordsFiltered"),
        "records": records,
    }


def normalise_pest_record(row: dict[str, Any]) -> dict[str, Any]:
    scientific: list[str] = []
    common: list[str] = []
    names = row.get("organismNames") or []
    for item in names:
        name = item.get("organismName")
        if not name:
            continue
        if str(item.get("organismNameTypeID", "")).lower() == "common":
            common.append(name)
        else:
            scientific.append(name)
    pest_id = row.get("pestId")
    return {
        "pest_id": pest_id,
        "pest_name": row.get("pestName"),
        "preferred_scientific_name": row.get("nzPreferredScientificName"),
        "scientific_names": scientific,
        "common_names": common,
        "organism_type": row.get("organismType"),
        "regulatory_status": row.get("regulatoryStatus"),
        "unwanted": boolish(row.get("unwanted")),
        "notifiable": boolish(row.get("notifiable")),
        "regulatory_country": row.get("regulatoryCountry"),
        "freedom_status": row.get("freedomStatus"),
        "hsno_status": row.get("hsnoStatus"),
        "detail_url": (
            f"{PEST_REGISTER_BASE}/pest-register-importing/pest-details/?id={pest_id}"
            if pest_id is not None
            else None
        ),
    }


class DetailParser(HTMLParser):
    def __init__(self, base_url: str):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.title = ""
        self.current_label: str | None = None
        self.fields: dict[str, list[str]] = {}
        self.links: list[dict[str, str | None]] = []
        self.quarantine_countries: list[str] = []
        self._capture: str | None = None
        self._parts: list[str] = []
        self._link: dict[str, str | None] | None = None
        self._link_parts: list[str] = []
        self._in_quarantine = False

    def handle_starttag(self, tag: str, attrs_list: list[tuple[str, str | None]]) -> None:
        attrs = dict(attrs_list)
        if tag == "h1" and attrs.get("id") == "page-title":
            self._start("h1")
        elif tag in ("dt", "dd"):
            self._start(tag)
        elif tag == "a":
            self._link = {
                "url": absolutise(self.base_url, attrs.get("href")),
                "title": attrs.get("title"),
                "text": "",
            }
            self._link_parts = []
        elif tag == "ul" and "quarantine-list" in (attrs.get("class") or ""):
            self._in_quarantine = True
        elif tag == "li" and self._in_quarantine:
            self._start("li")

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._link:
            text = clean_text("".join(self._link_parts))
            self._link["text"] = text
            if self._link["url"] and text:
                self.links.append(self._link)
            self._link = None
            self._link_parts = []
        elif tag == self._capture:
            text = clean_text("".join(self._parts))
            if tag == "h1":
                self.title = text
            elif tag == "dt":
                self.current_label = text
            elif tag == "dd" and self.current_label and text:
                self.fields.setdefault(snake(self.current_label), []).append(text)
            elif tag == "li" and text:
                self.quarantine_countries.append(text)
            self._capture = None
            self._parts = []
        elif tag == "ul" and self._in_quarantine:
            self._in_quarantine = False

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._parts.append(data)
        if self._link:
            self._link_parts.append(data)

    def _start(self, capture: str) -> None:
        self._capture = capture
        self._parts = []


class TableParser(HTMLParser):
    def __init__(self, base_url: str):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.tables: dict[str, dict[str, Any]] = {}
        self._table_id: str | None = None
        self._row: list[dict[str, Any]] | None = None
        self._cell: dict[str, Any] | None = None
        self._capture_cell = False
        self._cell_parts: list[str] = []
        self._link: dict[str, str | None] | None = None
        self._link_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs_list: list[tuple[str, str | None]]) -> None:
        attrs = dict(attrs_list)
        if tag == "table":
            self._table_id = attrs.get("id") or f"table_{len(self.tables) + 1}"
            self.tables[self._table_id] = {"headers": [], "rows": []}
        elif self._table_id and tag == "tr":
            self._row = []
        elif self._table_id and tag in ("th", "td"):
            self._cell = {"header": tag == "th", "class": attrs.get("class"), "text": "", "links": []}
            self._capture_cell = True
            self._cell_parts = []
        elif self._capture_cell and tag == "a":
            target = attrs.get("data-target") or attrs.get("href")
            self._link = {"url": absolutise(self.base_url, target), "text": ""}
            self._link_parts = []

    def handle_endtag(self, tag: str) -> None:
        if self._link and tag == "a":
            self._link["text"] = clean_text("".join(self._link_parts))
            if self._cell is not None:
                self._cell["links"].append(self._link)
            self._link = None
            self._link_parts = []
        elif self._cell is not None and tag in ("th", "td"):
            self._cell["text"] = clean_text("".join(self._cell_parts))
            if self._row is not None:
                self._row.append(self._cell)
            self._cell = None
            self._capture_cell = False
            self._cell_parts = []
        elif self._table_id and tag == "tr":
            if self._row:
                table = self.tables[self._table_id]
                if all(cell["header"] for cell in self._row):
                    table["headers"] = [cell["text"] for cell in self._row]
                else:
                    table["rows"].append(self._row)
            self._row = None
        elif self._table_id and tag == "table":
            self._table_id = None

    def handle_data(self, data: str) -> None:
        if self._link is not None:
            self._link_parts.append(data)
        if self._capture_cell:
            self._cell_parts.append(data)


class AnchorParser(HTMLParser):
    def __init__(self, base_url: str):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.links: list[dict[str, str]] = []
        self._href: str | None = None
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs_list: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            attrs = dict(attrs_list)
            self._href = absolutise(self.base_url, attrs.get("href"))
            self._parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href:
            text = clean_text("".join(self._parts))
            if text:
                self.links.append({"title": text, "url": self._href})
            self._href = None
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self._href:
            self._parts.append(data)


def parse_dl_fields(html_text: str, base_url: str) -> DetailParser:
    parser = DetailParser(base_url)
    parser.feed(html_text)
    return parser


def parse_table_rows(html_text: str, base_url: str, table_id: str) -> list[dict[str, Any]]:
    parser = TableParser(base_url)
    parser.feed(html_text)
    table = parser.tables.get(table_id, {})
    headers = table.get("headers") or []
    rows = []
    for raw_row in table.get("rows", []):
        row: dict[str, Any] = {}
        links: list[dict[str, str | None]] = []
        for index, cell in enumerate(raw_row):
            key = snake(headers[index] if index < len(headers) else (cell.get("class") or f"column_{index + 1}"))
            row[key] = cell["text"]
            if cell.get("links"):
                row[f"{key}_links"] = cell["links"]
                links.extend(cell["links"])
        if links:
            row["links"] = links
        rows.append(row)
    return rows


def parse_pest_detail(html_text: str, source_url: str, pest_id: str) -> dict[str, Any]:
    parser = parse_dl_fields(html_text, source_url)
    fields = {key: values[0] if len(values) == 1 else values for key, values in parser.fields.items()}
    action_url = None
    for link in parser.links:
        if link.get("url") and "action-upon-interception" in str(link["url"]):
            action_url = link["url"]
            break
    skip_link_text = {"skip to content", "share on facebook", "share on twitter", "share on linkedin", "share via email", "status definitions", "legislation", "back to top"}
    useful_links = [
        link
        for link in parser.links
        if link.get("url")
        and str(link.get("text") or "").lower() not in skip_link_text
        and not str(link["url"]).startswith(("mailto:", "https://www.facebook.com", "https://twitter.com", "https://www.linkedin.com"))
        and "#main-content-link" not in str(link["url"])
        and "#banner" not in str(link["url"])
        and (
            "dmsdocument" in str(link["url"])
            or "pest-details" in str(link["url"])
            or "cabi.org" in str(link["url"])
            or "eppo" in str(link["url"])
            or "nzor" in str(link["url"])
            or "mpi.govt.nz/biosecurity" in str(link["url"])
        )
    ]
    return {
        "kind": "pest",
        "status": "ok",
        "source": "Official New Zealand Pest Register",
        "source_url": source_url,
        "pest_id": pest_id,
        "title": parser.title,
        "fields": fields,
        "quarantine_countries": parser.quarantine_countries,
        "action_upon_interception_url": action_url,
        "links": useful_links,
    }


def parse_import_rows(html_text: str, source_url: str) -> list[dict[str, Any]]:
    rows = parse_table_rows(html_text, source_url, "commodityList")
    for row in rows:
        countries_url = None
        for link in row.get("links", []):
            if link.get("url") and "ImportCountriesList" in str(link["url"]):
                countries_url = link["url"]
                break
        row["countries_url"] = countries_url
        if countries_url:
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(countries_url).query)
            row["commodity_id"] = (qs.get("commodityID") or [None])[0]
    return rows


def parse_requirement(html_text: str, source_url: str) -> dict[str, Any]:
    parser = parse_dl_fields(html_text, source_url)
    fields = {key: values[0] if len(values) == 1 else values for key, values in parser.fields.items()}
    docs = [
        link
        for link in parser.links
        if link.get("url")
        and (
            "dmsdocument" in str(link["url"])
            or "onzpr.mpi.govt.nz/pest-register-importing/pest-details" in str(link["url"])
        )
    ]
    return {
        "source_url": source_url,
        "title": parser.title,
        "fields": fields,
        "official_documentation": docs,
    }


def commodity_suggestions(term: str, limit: int) -> list[str]:
    url = f"{PIER_SEARCH_BASE}/import-commodity-names.js?m=1782914077"
    text, _ = fetch_text(url)
    match = re.search(r"commodityNameSuggestions\s*=\s*(\[.*?\]);", text, flags=re.S)
    if not match:
        return []
    names = json.loads(match.group(1))
    needle = term.lower()
    starts = [name for name in names if name.lower().startswith(needle)]
    contains = [name for name in names if needle in name.lower() and name not in starts]
    return (starts + contains)[:limit]


def pier_api(path: str) -> Any:
    url = f"{PIER_SEARCH_BASE}/pier-api.php?{urllib.parse.urlencode({'url': path})}"
    payload, _ = fetch_json(url)
    if isinstance(payload, dict) and payload.get("code"):
        raise SkillError(f"PIER API returned {payload.get('code')}: {payload.get('message')}")
    return payload


def cmd_pest_search(args: argparse.Namespace) -> dict[str, Any]:
    params: dict[str, Any] = {"SearchText": args.query}
    if args.organism_type:
        params["OrganismType"] = args.organism_type
    if args.notifiable:
        params["Notifiable"] = 1
    if args.regulated:
        params["RegulatoryStatus"] = 1
    return onzpr_table(params, limit=args.limit)


def cmd_pest_get(args: argparse.Namespace) -> dict[str, Any]:
    pest_id = str(args.pest_id)
    url = f"{PEST_REGISTER_BASE}/pest-register-importing/pest-details/?{urllib.parse.urlencode({'id': pest_id})}"
    text, final_url = fetch_text(url)
    result = parse_pest_detail(text, final_url, pest_id)
    if not result.get("title"):
        raise SkillError(f"no pest detail content found for pest id {pest_id}")
    return result


def cmd_notifiable(args: argparse.Namespace) -> dict[str, Any]:
    result = onzpr_table({"Notifiable": 1}, limit=args.limit)
    result["kind"] = "notifiable"
    result["description"] = "ONZPR records marked notifiable."
    return result


def cmd_import_requirements(args: argparse.Namespace) -> dict[str, Any]:
    commodity = args.commodity.strip()
    try:
        type_groups = pier_api(
            f"CommodityNames/{urllib.parse.quote(commodity, safe='')}/Types?searchType=import"
        )
    except (SkillError, BlockedSource) as exc:
        if isinstance(exc, BlockedSource):
            return blocked_payload("PIER Search", exc.url, exc.status)
        suggestions = commodity_suggestions(commodity, args.limit)
        return {
            "kind": "import_requirements",
            "status": "not_found",
            "source": "PIER Search",
            "commodity": commodity,
            "message": str(exc),
            "suggestions": suggestions,
        }

    type_choices = []
    for group in type_groups:
        for item in group.get("names", []):
            type_choices.append({"type": group.get("type"), "id": item.get("id"), "name": item.get("name")})
    if not type_choices:
        suggestions = commodity_suggestions(commodity, args.limit)
        return {
            "kind": "import_requirements",
            "status": "not_found",
            "source": "PIER Search",
            "commodity": commodity,
            "message": "PIER did not return any commodity type choices for this query.",
            "type_choices": [],
            "searches": [],
            "country_matches": [],
            "suggestions": suggestions,
        }

    selected = [c for c in type_choices if str(c["id"]) == str(args.commodity_type_id)] if args.commodity_type_id else type_choices
    selected = selected[: max(1, min(args.limit, 10))]
    searches = []
    country_matches = []
    for choice in selected:
        result_url = (
            f"{PIER_SEARCH_BASE}/importing-commodities-to-new-zealand/search-by-commodity-only/"
            f"search-results/?{urllib.parse.urlencode({'commodityName': commodity, 'commodityType': choice['id']})}"
        )
        try:
            text, final_url = fetch_text(result_url)
        except BlockedSource as exc:
            searches.append(blocked_payload("PIER Search", exc.url, exc.status))
            continue
        rows = parse_import_rows(text, final_url)[: args.limit]
        search_result = {"commodity_type": choice, "source_url": final_url, "rows": rows}
        searches.append(search_result)
        if args.country:
            country_matches.extend(find_country_requirements(rows, args.country, args.limit))

    return {
        "kind": "import_requirements",
        "status": "ok",
        "source": "PIER Search",
        "commodity": commodity,
        "country": args.country,
        "type_choices": type_choices,
        "searches": searches,
        "country_matches": country_matches,
    }


def find_country_requirements(rows: list[dict[str, Any]], country: str, limit: int) -> list[dict[str, Any]]:
    matches = []
    needle = country.strip().lower()
    for row in rows:
        countries_url = row.get("countries_url")
        if not countries_url:
            continue
        try:
            text, final_url = fetch_text(countries_url)
        except BlockedSource as exc:
            matches.append(blocked_payload("PIER Search", exc.url, exc.status))
            continue
        countries = parse_table_rows(text, final_url, "countryList")
        for item in countries:
            item_country = str(item.get("country_region") or "").lower()
            if item_country == needle or needle in item_country:
                requirement = None
                for link in item.get("links", []):
                    if link.get("url") and "import-requirements" in str(link["url"]):
                        req_text, req_url = fetch_text(str(link["url"]))
                        requirement = parse_requirement(req_text, req_url)
                        break
                matches.append({"commodity_row": row, "country": item, "requirement": requirement})
                if len(matches) >= limit:
                    return matches
    return matches


def cmd_responses(args: argparse.Namespace) -> dict[str, Any]:
    try:
        text, final_url = fetch_text(ACTIVE_RESPONSES_URL)
    except BlockedSource as exc:
        return blocked_payload("MPI active biosecurity responses", exc.url, exc.status)
    parser = AnchorParser(final_url)
    parser.feed(text)
    base_path = urllib.parse.urlparse(final_url).path.rstrip("/")
    seen: set[str] = set()
    responses = []
    for link in parser.links:
        parsed = urllib.parse.urlparse(link["url"])
        path = parsed.path.rstrip("/")
        title = link["title"]
        if not path.startswith(base_path + "/") or path == base_path:
            continue
        if title.lower() in {"print", "feedback", "contact us"}:
            continue
        if link["url"] in seen:
            continue
        seen.add(link["url"])
        responses.append({"title": title, "url": link["url"]})
    return {
        "kind": "responses",
        "status": "ok",
        "source": "MPI active biosecurity responses",
        "source_url": final_url,
        "responses": responses,
    }


def cmd_sources(args: argparse.Namespace) -> dict[str, Any]:
    packages = []
    errors = []
    for package_id in (ONZPR_PACKAGE, PIER_PACKAGE):
        try:
            packages.append(ckan_package(package_id))
        except (SkillError, BlockedSource) as exc:
            errors.append({"package": package_id, "error": str(exc)})
    return {
        "kind": "sources",
        "status": "ok" if not errors else "partial",
        "packages": packages,
        "errors": errors,
        "endpoints": [
            {
                "name": "ONZPR DataTables search",
                "url": f"{ONZPR_BASE}/pest-api.php?method=GetTableDataAjax",
                "method": "POST",
                "notes": "Form field param contains JSON query parameters.",
            },
            {
                "name": "ONZPR autocomplete",
                "url": f"{ONZPR_BASE}/pest-api.php?method=AutoPopulateFreeSearch&term=fruit",
                "method": "GET",
            },
            {
                "name": "ONZPR pest detail",
                "url": f"{PEST_REGISTER_BASE}/pest-register-importing/pest-details/?id=111",
                "method": "GET",
            },
            {
                "name": "PIER commodity type resolver",
                "url": f"{PIER_SEARCH_BASE}/pier-api.php?url=CommodityNames/Apple/Types?searchType=import",
                "method": "GET",
            },
            {
                "name": "MPI active responses index",
                "url": ACTIVE_RESPONSES_URL,
                "method": "GET",
                "notes": "Often blocked by Imperva/Incapsula from server IPs.",
            },
        ],
    }


def blocked_payload(source: str, url: str, status: int | None = None) -> dict[str, Any]:
    return {
        "status": "blocked",
        "blocked_by": "Imperva/Incapsula",
        "source": source,
        "source_url": url,
        "http_status": status,
        "message": "Direct HTTP access returned an Incapsula challenge page. Use the source URL in a browser-grade/residential context.",
    }


def emit(result: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return
    kind = result.get("kind")
    status = result.get("status")
    if status == "blocked":
        print(f"{result['source']}: blocked by {result['blocked_by']}")
        print(result["source_url"])
    elif kind in ("pest_search", "notifiable"):
        print(f"{result['source']}: {result.get('records_filtered')} matching records")
        for record in result.get("records", []):
            flags = []
            if record.get("regulatory_status"):
                flags.append(record["regulatory_status"])
            if record.get("unwanted") is not None:
                flags.append(f"unwanted={yes_no(record['unwanted'])}")
            if record.get("notifiable") is not None:
                flags.append(f"notifiable={yes_no(record['notifiable'])}")
            print(f"- {record.get('pest_name')} (id {record.get('pest_id')})")
            print(f"  type: {record.get('organism_type') or '-'} | {' | '.join(flags)}")
            if record.get("common_names"):
                print(f"  common: {', '.join(record['common_names'][:5])}")
            print(f"  url: {record.get('detail_url')}")
    elif kind == "pest":
        print(f"{result.get('title')} (ONZPR id {result.get('pest_id')})")
        for key in ("preferred_scientific_name", "organism_type", "regulatory_status", "unwanted", "notifiable", "hsno_status", "country_freedom_status"):
            value = result.get("fields", {}).get(key)
            if value:
                print(f"{key.replace('_', ' ')}: {value}")
        print(result["source_url"])
    elif kind == "import_requirements":
        print(f"PIER import requirements for {result.get('commodity')}")
        if result.get("country"):
            print(f"country: {result['country']}")
        for choice in result.get("type_choices", [])[:10]:
            print(f"- type {choice['id']}: {choice['type']} / {choice['name']}")
        for match in result.get("country_matches", []):
            req = match.get("requirement") or {}
            fields = req.get("fields", {})
            print(f"  match: {fields.get('commodity_name') or match.get('commodity_row', {}).get('commodity_name')} from {fields.get('from_country_region') or match.get('country', {}).get('country_region')}")
            print(f"  status: {fields.get('import_status') or match.get('country', {}).get('import_status')}")
            if req.get("source_url"):
                print(f"  url: {req['source_url']}")
    elif kind == "responses":
        print(f"MPI active biosecurity responses: {len(result.get('responses', []))} links")
        for item in result.get("responses", []):
            print(f"- {item['title']}: {item['url']}")
    elif kind == "sources":
        print("Biosecurity NZ sources")
        for package in result.get("packages", []):
            print(f"- {package.get('title')} ({package.get('name')})")
            print(f"  {package.get('source_url')}")
    else:
        print(json.dumps(result, indent=2, ensure_ascii=False))


def yes_no(value: bool) -> str:
    return "yes" if value else "no"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Query public New Zealand biosecurity sources")
    sub = parser.add_subparsers(dest="command", required=True)

    pest = sub.add_parser("pest", help="Search or fetch ONZPR pest records")
    pest_sub = pest.add_subparsers(dest="pest_command", required=True)
    search = pest_sub.add_parser("search", help="Search ONZPR by name or free text")
    search.add_argument("--query", required=True)
    search.add_argument("--limit", type=int, default=10)
    search.add_argument("--organism-type")
    search.add_argument("--notifiable", action="store_true")
    search.add_argument("--regulated", action="store_true")
    search.add_argument("--json", action="store_true")
    search.set_defaults(func=cmd_pest_search)

    get = pest_sub.add_parser("get", help="Fetch ONZPR pest detail page by pest id")
    get.add_argument("pest_id")
    get.add_argument("--json", action="store_true")
    get.set_defaults(func=cmd_pest_get)

    notifiable = sub.add_parser("notifiable", help="List ONZPR notifiable organisms")
    notifiable.add_argument("--limit", type=int, default=20)
    notifiable.add_argument("--json", action="store_true")
    notifiable.set_defaults(func=cmd_notifiable)

    imports = sub.add_parser("import-requirements", help="Resolve PIER import commodity requirements")
    imports.add_argument("--commodity", required=True)
    imports.add_argument("--country")
    imports.add_argument("--commodity-type-id")
    imports.add_argument("--limit", type=int, default=5)
    imports.add_argument("--json", action="store_true")
    imports.set_defaults(func=cmd_import_requirements)

    responses = sub.add_parser("responses", help="List MPI active biosecurity response pages")
    responses.add_argument("--json", action="store_true")
    responses.set_defaults(func=cmd_responses)

    sources = sub.add_parser("sources", help="Show source datasets and endpoint notes")
    sources.add_argument("--json", action="store_true")
    sources.set_defaults(func=cmd_sources)

    datasets = sub.add_parser("datasets", help="Alias for sources")
    datasets.add_argument("--json", action="store_true")
    datasets.set_defaults(func=cmd_sources)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        result = args.func(args)
        emit(result, getattr(args, "json", False))
    except BlockedSource as exc:
        emit(blocked_payload("requested source", exc.url, exc.status), getattr(args, "json", False))
    except SkillError as exc:
        die(str(exc))


if __name__ == "__main__":
    main()
