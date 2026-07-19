"""Read the public Hinekōrako drinking-water register."""

from __future__ import annotations

import base64
import http.cookiejar
import html
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

import nzfetch

HOST = "hinekorako.taumataarowai.govt.nz"
BASE = f"https://{HOST}"
LIST_URL = f"{BASE}/publicregister/supplies/"
GRID_URL = f"{BASE}/_services/entity-grid-data.json/d78574f9-20c3-4dcc-8d8d-85cf5b7ac141"
TOKEN_URL = f"{BASE}/_layout/tokenhtml"


class PortalSession:
    def __init__(self) -> None:
        handlers: list[Any] = [
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
            nzfetch._AllowlistRedirectHandler(frozenset({HOST})),
        ]
        proxy = nzfetch.proxy_url()
        if proxy:
            handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
        self.opener = urllib.request.build_opener(*handlers)

    def request(self, url: str, *, data: bytes | None = None, headers: dict[str, str] | None = None) -> bytes:
        request_headers = nzfetch._browser_headers(url, "application/json,*/*" if data else "text/html,*/*")
        if headers:
            request_headers.update(headers)
        request = urllib.request.Request(url, data=data, headers=request_headers, method="POST" if data else "GET")
        try:
            with self.opener.open(request, timeout=25) as response:
                return nzfetch._decompress(response.read(), response.headers.get("Content-Encoding"))
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                raise nzfetch.RateLimited(
                    "Hinekōrako public register rate-limited the request (HTTP 429)",
                    retry_after=exc.headers.get("Retry-After"),
                ) from exc
            if exc.code in {403, 406, 451}:
                raise nzfetch.Blocked(f"Hinekōrako public register blocked the request (HTTP {exc.code})") from exc
            raise nzfetch.FetchError(f"HTTP {exc.code} from Hinekōrako public register") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise nzfetch.FetchError(f"Hinekōrako public register network error: {exc}") from exc


def _layout(page_html: str) -> dict[str, Any]:
    match = re.search(r"data-view-layouts=(?:'([^']+)'|\"([^\"]+)\")", page_html)
    if not match:
        raise ValueError("Hinekōrako register page is missing its grid configuration")
    encoded = html.unescape(match.group(1) or match.group(2))
    try:
        layouts = json.loads(base64.b64decode(encoded).decode("utf-8"))
        return layouts[0]
    except (ValueError, IndexError, KeyError, json.JSONDecodeError) as exc:
        raise ValueError("Hinekōrako grid configuration schema changed") from exc


def region_filters(page_html: str) -> dict[str, str]:
    select = re.search(r'<select[^>]+name="0"[^>]*>(.*?)</select>', page_html, re.S)
    if not select:
        raise ValueError("Hinekōrako register region filter is missing")
    return {
        html.unescape(label).strip(): html.unescape(value)
        for value, label in re.findall(r'<option value="([^"]*)" label="([^"]*)"', select.group(1))
        if value and label.strip()
    }


def fetch_supplies(
    *, search: str | None = None, region: str | None = None, limit: int = 50
) -> tuple[list[dict[str, Any]], str]:
    session = PortalSession()
    page_html = session.request(LIST_URL).decode("utf-8", "replace")
    layout = _layout(page_html)
    configuration = layout["Configuration"]
    meta_filter = None
    if region:
        choices = region_filters(page_html)
        match = next((value for label, value in choices.items() if label.casefold() == region.casefold()), None)
        if not match:
            raise LookupError(f"unknown official region: {region}")
        meta_filter = urllib.parse.urlencode({"0": match})
    token_html = session.request(TOKEN_URL).decode("utf-8", "replace")
    token_match = re.search(r'name="__RequestVerificationToken"[^>]+value="([^"]+)"', token_html)
    if not token_match:
        raise ValueError("Hinekōrako register did not return a request verification token")
    payload = {
        "base64SecureConfiguration": layout["Base64SecureConfiguration"],
        "sortExpression": layout.get("SortExpression") or "ta_supplyname ASC",
        "search": search,
        "page": 1,
        "pageSize": max(1, min(limit, 50)),
        "pagingCookie": "",
        "filter": None,
        "metaFilter": meta_filter,
        "nlSearchFilter": None,
        "timezoneOffset": -720,
        "customParameters": [],
        "entityName": None,
        "entityId": None,
    }
    raw = session.request(
        GRID_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "__RequestVerificationToken": token_match.group(1),
            "X-Requested-With": "XMLHttpRequest",
            "Referer": LIST_URL,
        },
    )
    return parse_grid_response(raw), page_html


def parse_grid_response(raw: bytes | str) -> list[dict[str, Any]]:
    try:
        response = json.loads(raw)
        records = response["Records"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError("Hinekōrako grid response schema changed") from exc
    if not isinstance(records, list):
        raise ValueError("Hinekōrako grid response Records field is not a list")
    rows: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("Hinekōrako grid response contains a non-object record")
        raw_attributes = record.get("Attributes")
        if not isinstance(raw_attributes, list):
            raise ValueError("Hinekōrako grid record Attributes field is not a list")
        if any(not isinstance(attribute, dict) for attribute in raw_attributes):
            raise ValueError("Hinekōrako grid record contains a non-object attribute")
        if any(not isinstance(attribute.get("Name"), str) for attribute in raw_attributes):
            raise ValueError("Hinekōrako grid record contains an attribute without a valid Name")
        attributes = {attribute["Name"]: attribute for attribute in raw_attributes}
        def display(name: str) -> Any:
            value = attributes.get(name, {})
            return value.get("DisplayValue") if value else None
        record_id = record.get("Id")
        rows.append(
            {
                "id": display("ta_supplyid"),
                "supply_name": display("ta_supplyname"),
                "supply_type": display("ta_supplytype"),
                "community": display("ta_community"),
                "record_id": record_id,
                "source_url": f"{LIST_URL}view/?id={record_id}",
            }
        )
    return rows


def _clean(value: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", html.unescape(value)).split())


def parse_supply_detail(page_html: str, source_url: str, retrieved_at: str) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for cell in re.findall(r"<td\b.*?</td>", page_html, re.S | re.I):
        label_match = re.search(r'<label\b[^>]*class="[^"]*field-label[^"]*"[^>]*>(.*?)</label>', cell, re.S | re.I)
        if not label_match:
            continue
        label = re.sub(r"[^a-z0-9]+", "_", _clean(label_match.group(1)).lower()).strip("_")
        input_match = re.search(r'<input\b[^>]*\bvalue="([^"]*)"[^>]*(?:readonly|disabled)', cell, re.S | re.I)
        status_match = re.search(r'<span\b[^>]*class="[^"]*status[^"]*"[^>]*>(.*?)</span>', cell, re.S | re.I)
        if status_match:
            fields[label] = _clean(status_match.group(1))
        elif input_match:
            fields[label] = _clean(input_match.group(1))
        elif re.search(r'<input\b[^>]*type="checkbox"[^>]*checked', cell, re.I):
            fields[label] = True
        elif "checkbox-cell" in cell:
            fields[label] = False
    if not fields.get("supply_id") or not fields.get("supply_name"):
        raise ValueError("Hinekōrako supply detail is missing required public fields")
    documents = []
    for href, title in re.findall(r'<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>', page_html, re.S | re.I):
        absolute = urllib.parse.urljoin(source_url, html.unescape(href))
        if re.search(r"\.(?:pdf|docx?|xlsx?)(?:\?|$)", absolute, re.I):
            documents.append({"title": _clean(title), "url": absolute})
    fields.update(
        {
            "documents": documents,
            "information_withheld": "Some information about this supply has been withheld" in page_html,
            "what_this_does_not_prove": [
                "current potability",
                "current compliance",
                "non-compliance from missing documents",
            ],
            "source_url": source_url,
            "retrieved_at": retrieved_at,
        }
    )
    return fields


def supplier_relationships(detail: dict[str, Any]) -> list[dict[str, Any]]:
    """Return only supplier/owner/operator relationships explicitly published."""
    rows: list[dict[str, Any]] = []
    ignored = {"source_url", "retrieved_at", "documents", "what_this_does_not_prove"}
    for field, value in detail.items():
        if field in ignored or not isinstance(value, str) or not value.strip():
            continue
        if any(marker in field for marker in ("supplier", "owner", "operator", "registration_holder")):
            rows.append({"relationship": field, "name": value.strip()})
    return rows


def exact_supply_match(rows: list[dict[str, Any]], query: str) -> dict[str, Any] | None:
    """Resolve only an exact case-insensitive public supply ID or name."""

    normal_query = query.strip().casefold()
    if not normal_query:
        return None
    matches = [
        row
        for row in rows
        if str(row.get("id") or "").strip().casefold() == normal_query
        or str(row.get("supply_name") or "").strip().casefold() == normal_query
    ]
    return matches[0] if len(matches) == 1 else None


def document_result(detail: dict[str, Any]) -> dict[str, Any]:
    """Return the stable documents-command shape without a raw supply summary."""

    return {
        "supply_id": detail["supply_id"],
        "supply_name": detail["supply_name"],
        "documents": list(detail.get("documents") or []),
        "information_withheld": bool(detail.get("information_withheld")),
        "what_this_does_not_prove": list(detail.get("what_this_does_not_prove") or []),
        "source_url": detail["source_url"],
        "retrieved_at": detail["retrieved_at"],
    }
