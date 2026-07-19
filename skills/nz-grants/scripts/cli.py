#!/usr/bin/env python3
"""Read-only CLI for NZ grant opportunities and Class 4 grant distribution history.

Sources:
- DIA / Granted.govt.nz Class 4 grants CSV published through data.govt.nz CKAN.
- CommunityMatters public fund/opportunity pages, parsed from HTML when reachable.

Standard library only. No login, application submission, browser automation, or mutation.
"""
from __future__ import annotations

import argparse
import csv
import html as html_lib
import io
import json
import pathlib
import re
import sys
import textwrap
import urllib.parse
from html.parser import HTMLParser
from typing import Any, Iterable

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "lib"))
import nzfetch  # noqa: E402

CKAN_BASE = "https://catalogue.data.govt.nz"
CKAN_ACTION = CKAN_BASE + "/api/3/action/"
CLASS4_PACKAGE = "class-4-grants-data"
CLASS4_FALLBACK_CSV = (
    CKAN_BASE
    + "/dataset/b6b7f1cc-bfa4-4c7a-81e8-8a03f2983cae/resource/"
    + "06d99ad0-47d6-4591-84c7-8872a4f77da9/download/class-4-grants-dataset-csv.csv"
)
GRANTED_URL = "https://www.granted.govt.nz/"
COMMUNITY_BASE = "https://www.communitymatters.govt.nz"
COMMUNITY_FUNDS_URL = COMMUNITY_BASE + "/funds/"
UA = "nz-grants-skill/1.0 (+https://github.com/thecolab-ai/.skills)"
DEFAULT_TIMEOUT = 20
MAX_LIMIT = 200

MONEY_FIELDS = ("Amount_Requested_Final", "Amount_Granted_Final", "Amount_Refunded_Clean")


class UpstreamUnavailable(RuntimeError):
    pass


def die(message: str, code: int = 1) -> None:
    print(f"nz-grants: {message}", file=sys.stderr)
    raise SystemExit(code)


ACCEPT_HEADER = "text/html,application/json,text/csv,application/csv,*/*;q=0.8"


def fetch_bytes(url: str, timeout: int = DEFAULT_TIMEOUT) -> bytes:
    try:
        body, _content_type, _final_url = nzfetch.fetch_bytes(
            url,
            timeout=timeout,
            accept=ACCEPT_HEADER,
            headers={"Accept-Language": "en-NZ,en;q=0.9"},
        )
        return body
    except nzfetch.Blocked as exc:
        raise UpstreamUnavailable(f"network error fetching {url}: {exc}") from exc
    except nzfetch.FetchError as exc:
        raise UpstreamUnavailable(str(exc)) from exc


def fetch_text(url: str, timeout: int = DEFAULT_TIMEOUT) -> str:
    return fetch_bytes(url, timeout=timeout).decode("utf-8", "replace")


def fetch_json(url: str, timeout: int = DEFAULT_TIMEOUT) -> dict[str, Any]:
    raw = fetch_bytes(url, timeout=timeout).decode("utf-8", "replace")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise UpstreamUnavailable(f"invalid JSON from {url}: {exc}") from exc


def ckan(action: str, params: dict[str, Any], timeout: int = DEFAULT_TIMEOUT) -> dict[str, Any]:
    query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    url = CKAN_ACTION + action + ("?" + query if query else "")
    data = fetch_json(url, timeout=timeout)
    if not data.get("success"):
        raise UpstreamUnavailable(f"CKAN {action} returned success=false: {data.get('error')}")
    return {"source_url": url, "result": data.get("result") or {}}


def class4_csv_url(timeout: int = DEFAULT_TIMEOUT) -> tuple[str, list[dict[str, Any]], str | None]:
    """Return the best current Class 4 CSV resource URL and package resources."""
    package_url = None
    resources: list[dict[str, Any]] = []
    try:
        data = ckan("package_show", {"id": CLASS4_PACKAGE}, timeout=timeout)
        package_url = data["source_url"]
        resources = data["result"].get("resources") or []
        csv_resources = [
            r for r in resources
            if (r.get("format") or "").lower() == "csv" or str(r.get("url") or "").lower().endswith(".csv")
        ]
        if csv_resources:
            csv_resources.sort(key=lambda r: (r.get("last_modified") or r.get("created") or "", r.get("name") or ""), reverse=True)
            return str(csv_resources[0].get("url") or CLASS4_FALLBACK_CSV), resources, package_url
    except UpstreamUnavailable:
        pass
    return CLASS4_FALLBACK_CSV, resources, package_url


def csv_rows(timeout: int = 90) -> Iterable[dict[str, str]]:
    url, _, _ = class4_csv_url(timeout=min(timeout, DEFAULT_TIMEOUT))
    try:
        body, _content_type, _final_url = nzfetch.fetch_bytes(
            url,
            timeout=timeout,
            accept=ACCEPT_HEADER,
            headers={"Accept-Language": "en-NZ,en;q=0.9"},
        )
    except nzfetch.Blocked as exc:
        raise UpstreamUnavailable(f"network error downloading Class 4 CSV: {exc}") from exc
    except nzfetch.FetchError as exc:
        raise UpstreamUnavailable(f"error downloading Class 4 CSV: {exc}") from exc
    text = io.StringIO(body.decode("utf-8-sig", "replace"))
    try:
        reader = csv.DictReader(text)
        for row in reader:
            yield row
    except csv.Error as exc:
        raise UpstreamUnavailable(f"invalid Class 4 CSV: {exc}") from exc


def norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).lower()


def money(value: Any) -> float:
    text = str(value or "").strip().replace("$", "").replace(",", "")
    if not text or text.lower() in {"n/a", "na", "-", ".."}:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def parse_date(value: Any) -> tuple[int | None, int | None]:
    text = str(value or "").strip()
    # Handles YYYY-MM-DD, DD/MM/YYYY, DD-MM-YYYY and similar source variants.
    m = re.search(r"(20\d{2})[-/](\d{1,2})[-/](\d{1,2})", text)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r"(\d{1,2})[-/](\d{1,2})[-/](20\d{2})", text)
    if m:
        return int(m.group(3)), int(m.group(2))
    return None, None


def period_matches(row: dict[str, str], period: str | None) -> bool:
    if not period:
        return True
    m = re.fullmatch(r"(20\d{2})-H([12])", period.strip(), flags=re.I)
    if not m:
        raise ValueError("--period must look like 2024-H1 or 2024-H2")
    want_year = int(m.group(1))
    want_half = int(m.group(2))
    year, month = parse_date(row.get("Date_of_Accept/Decline"))
    if year is None:
        year_text = row.get("Year_of_Accept/Decline") or row.get("Year") or ""
        if str(want_year) != str(year_text).strip():
            return False
        return True  # old rows without dates cannot be split further; include matching year rows.
    half = 1 if (month or 1) <= 6 else 2
    return year == want_year and half == want_half


def clean_class4_row(row: dict[str, str]) -> dict[str, Any]:
    out: dict[str, Any] = dict(row)
    for field in MONEY_FIELDS:
        out[field + "_Number"] = money(row.get(field))
    year, month = parse_date(row.get("Date_of_Accept/Decline"))
    if year and month:
        out["Period"] = f"{year}-H{1 if month <= 6 else 2}"
    return out


def class4_match(row: dict[str, str], args: argparse.Namespace) -> bool:
    if not period_matches(row, args.period):
        return False
    if args.recipient and norm(args.recipient) not in norm(row.get("Final_Organisation_Name") or row.get("Organisation_Name")):
        return False
    if args.tla and norm(args.tla) not in norm(row.get("Territorial_Local_Authority")):
        return False
    if args.funder and norm(args.funder) not in norm(row.get("Society_Name")):
        return False
    if args.status and norm(args.status) != norm(row.get("Status")):
        return False
    if args.query and norm(args.query) not in norm(" ".join(str(v) for v in row.values())):
        return False
    return True


def command_class4(args: argparse.Namespace) -> dict[str, Any]:
    csv_url, resources, package_url = class4_csv_url(timeout=args.timeout)
    records: list[dict[str, Any]] = []
    scanned = matched = accepted = declined = 0
    total_requested = total_granted = total_refunded = 0.0
    for row in csv_rows(timeout=max(args.timeout, 60)):
        scanned += 1
        if not class4_match(row, args):
            continue
        matched += 1
        status = norm(row.get("Status"))
        if status == "accepted":
            accepted += 1
        elif status == "declined":
            declined += 1
        total_requested += money(row.get("Amount_Requested_Final"))
        total_granted += money(row.get("Amount_Granted_Final"))
        total_refunded += money(row.get("Amount_Refunded_Clean"))
        if len(records) < args.limit:
            records.append(clean_class4_row(row))
    return {
        "kind": "class4_grants",
        "source": "DIA / Granted.govt.nz Class 4 grants CSV via data.govt.nz",
        "source_url": csv_url,
        "package_url": package_url,
        "granted_url": GRANTED_URL,
        "filters": {k: getattr(args, k) for k in ("period", "recipient", "tla", "funder", "status", "query") if getattr(args, k, None)},
        "scanned": scanned,
        "matched": matched,
        "returned": len(records),
        "accepted": accepted,
        "declined": declined,
        "totals": {
            "requested": round(total_requested, 2),
            "granted": round(total_granted, 2),
            "refunded": round(total_refunded, 2),
        },
        "resources": [resource_summary(r) for r in resources],
        "records": records,
    }


def resource_summary(resource: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": resource.get("id"),
        "name": resource.get("name"),
        "format": resource.get("format"),
        "url": resource.get("url"),
        "last_modified": resource.get("last_modified") or resource.get("created"),
    }


class LinkTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[dict[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []
        self.title: str | None = None
        self._in_title = False
        self._skip = 0
        self.text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = dict(attrs)
        if tag in {"script", "style", "svg", "noscript"}:
            self._skip += 1
        if tag == "title":
            self._in_title = True
        if tag == "a":
            self._href = attr.get("href")
            self._text = []
        if tag in {"p", "li", "h1", "h2", "h3", "br"} and not self._skip:
            self.text_parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "svg", "noscript"} and self._skip:
            self._skip -= 1
        if tag == "title":
            self._in_title = False
        if tag == "a" and self._href:
            label = " ".join(" ".join(self._text).split())
            if label:
                self.links.append({"href": self._href, "text": html_lib.unescape(label)})
            self._href = None
            self._text = []
        if tag in {"p", "li", "h1", "h2", "h3"} and not self._skip:
            self.text_parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._in_title:
            text = " ".join(data.split())
            if text:
                self.title = html_lib.unescape(text)
        if self._href is not None:
            self._text.append(data)
        if not self._skip:
            text = " ".join(data.split())
            if text:
                self.text_parts.append(html_lib.unescape(text) + " ")

    def readable_text(self) -> str:
        lines = [" ".join(line.split()) for line in "".join(self.text_parts).splitlines()]
        return "\n".join(line for line in lines if line)


def slug_from_url(url: str) -> str:
    path = urllib.parse.urlparse(url).path.strip("/")
    if not path:
        return ""
    return path.split("/")[-1]


def looks_like_fund_link(item: dict[str, str]) -> bool:
    href = item.get("href") or ""
    text = item.get("text") or ""
    url = urllib.parse.urljoin(COMMUNITY_FUNDS_URL, href)
    path = urllib.parse.urlparse(url).path.lower()
    if any(skip in path for skip in ("wp-content", "privacy", "contact", "accessibility")):
        return False
    hay = (path + " " + text).lower()
    return ("fund" in hay or "grant" in hay or "scholarship" in hay or "fellowship" in hay) and url.startswith(COMMUNITY_BASE)


def normalise_fund_link(item: dict[str, str]) -> dict[str, Any]:
    url = urllib.parse.urljoin(COMMUNITY_FUNDS_URL, item["href"])
    return {
        "title": item["text"],
        "slug": slug_from_url(url),
        "source_url": url,
        "provider": "CommunityMatters / Department of Internal Affairs",
    }


def extract_meta(html: str, name: str) -> str | None:
    m = re.search(rf'<meta[^>]+(?:name|property)=["\']{re.escape(name)}["\'][^>]+content=["\']([^"\']*)', html, flags=re.I)
    if not m:
        m = re.search(rf'<meta[^>]+content=["\']([^"\']*)["\'][^>]+(?:name|property)=["\']{re.escape(name)}["\']', html, flags=re.I)
    return html_lib.unescape(m.group(1)) if m else None


def command_funds(args: argparse.Namespace) -> dict[str, Any]:
    page = fetch_text(COMMUNITY_FUNDS_URL, timeout=args.timeout)
    parser = LinkTextParser()
    parser.feed(page)
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for link in parser.links:
        if not looks_like_fund_link(link):
            continue
        item = normalise_fund_link(link)
        key = item["source_url"].rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        records.append(item)
        if len(records) >= args.limit:
            break
    return {
        "kind": "fund_opportunities",
        "source": "CommunityMatters public funds page",
        "source_url": COMMUNITY_FUNDS_URL,
        "count": len(records),
        "records": records,
    }


def command_fund_get(args: argparse.Namespace) -> dict[str, Any]:
    slug = args.slug_or_url.strip()
    if slug.startswith("http://") or slug.startswith("https://"):
        url = slug
    else:
        slug = slug.strip("/")
        if slug.startswith("funds/"):
            path = slug
        else:
            path = "funds/" + slug
        url = urllib.parse.urljoin(COMMUNITY_BASE + "/", path + "/")
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or (parsed.hostname or "").lower() != "www.communitymatters.govt.nz":
        raise ValueError("fund URL must use the declared Community Matters HTTPS host")
    page = fetch_text(url, timeout=args.timeout)
    parser = LinkTextParser()
    parser.feed(page)
    title = extract_meta(page, "og:title") or parser.title
    description = extract_meta(page, "description") or extract_meta(page, "og:description")
    text = parser.readable_text()
    if args.max_chars and len(text) > args.max_chars:
        text = text[: args.max_chars].rsplit("\n", 1)[0] + "\n…"
    application_links = []
    for link in parser.links:
        hay = (link.get("text", "") + " " + link.get("href", "")).lower()
        if any(word in hay for word in ("apply", "application", "guidelines", "criteria", "form")):
            application_links.append({"text": link["text"], "url": urllib.parse.urljoin(url, link["href"])})
    return {
        "kind": "fund_opportunity",
        "source": "CommunityMatters public fund page",
        "source_url": url,
        "slug": slug_from_url(url),
        "title": title,
        "description": description,
        "application_links": application_links[:20],
        "text": text,
    }


def print_class4(data: dict[str, Any]) -> None:
    totals = data["totals"]
    print(
        f"Class 4 grants: {data['matched']:,} matched from {data['scanned']:,} rows; "
        f"granted ${totals['granted']:,.2f}"
    )
    for row in data.get("records", []):
        print(
            "- "
            + f"{row.get('Period') or row.get('Year_of_Accept/Decline')} | {row.get('Status')} | "
            + f"{row.get('Society_Name')} -> {row.get('Final_Organisation_Name') or row.get('Organisation_Name')} | "
            + f"{row.get('Amount_Granted_Final')} | {row.get('Territorial_Local_Authority')}, {row.get('Region')}"
        )


def print_funds(data: dict[str, Any]) -> None:
    print(f"CommunityMatters funds: {data['count']} shown")
    for item in data.get("records", []):
        print(f"- {item['title']} ({item['slug']}): {item['source_url']}")


def print_fund(data: dict[str, Any]) -> None:
    print(data.get("title") or data["source_url"])
    if data.get("description"):
        print("\n" + textwrap.fill(data["description"], width=100))
    print(f"\nSource: {data['source_url']}")
    if data.get("application_links"):
        print("\nApplication/guidance links:")
        for link in data["application_links"]:
            print(f"- {link['text']}: {link['url']}")
    print("\n" + (data.get("text") or "No readable text found."))


def emit(data: dict[str, Any], json_flag: bool, human) -> None:
    if json_flag:
        print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        human(data)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Query NZ grant opportunities and Class 4 grant distribution history.")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="network timeout seconds (default: 20)")
    sub = parser.add_subparsers(dest="command", required=True)

    class4 = sub.add_parser("class4", help="filter DIA / Granted.govt.nz Class 4 grant distribution rows")
    class4.add_argument("--period", help="half-year period such as 2024-H1 or 2024-H2")
    class4.add_argument("--recipient", help="recipient/final organisation contains")
    class4.add_argument("--tla", help="territorial local authority contains")
    class4.add_argument("--funder", help="Class 4 society/funder contains")
    class4.add_argument("--status", choices=["Accepted", "Declined"], help="application status")
    class4.add_argument("--query", help="case-insensitive text search across source row fields")
    class4.add_argument("--limit", type=int, default=20, help="max records returned, up to 200")
    class4.add_argument("--json", action="store_true", help="print machine-readable JSON")
    class4.set_defaults(func=command_class4, human=print_class4)

    funds = sub.add_parser("funds", help="list CommunityMatters public fund/opportunity pages")
    funds.add_argument("--limit", type=int, default=50, help="max opportunities returned, up to 200")
    funds.add_argument("--json", action="store_true", help="print machine-readable JSON")
    funds.set_defaults(func=command_funds, human=print_funds)

    fund = sub.add_parser("fund", help="inspect one CommunityMatters public fund/opportunity page")
    fund_sub = fund.add_subparsers(dest="fund_command", required=True)
    get = fund_sub.add_parser("get", help="fetch a fund page by slug or URL")
    get.add_argument("slug_or_url", help="fund slug, funds/<slug>, or full CommunityMatters URL")
    get.add_argument("--max-chars", type=int, default=6000, help="maximum readable page text characters")
    get.add_argument("--json", action="store_true", help="print machine-readable JSON")
    get.set_defaults(func=command_fund_get, human=print_fund)

    args = parser.parse_args(argv)
    if getattr(args, "limit", 1) < 1:
        die("--limit must be >= 1")
    if getattr(args, "limit", 1) > MAX_LIMIT:
        args.limit = MAX_LIMIT
    if args.timeout < 1:
        die("--timeout must be >= 1")
    try:
        data = args.func(args)
        emit(data, getattr(args, "json", False), args.human)
        return 0
    except ValueError as exc:
        print(f"nz-grants: {exc}", file=sys.stderr)
        return 1
    except UpstreamUnavailable as exc:
        payload = {"error": "upstream_unavailable", "message": str(exc)}
        if getattr(args, "json", False):
            print(json.dumps(payload, ensure_ascii=False, indent=2), file=sys.stderr)
        else:
            print(f"Upstream unavailable: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
