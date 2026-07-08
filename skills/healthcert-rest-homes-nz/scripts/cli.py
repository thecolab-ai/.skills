#!/usr/bin/env python3
"""Ministry of Health certified aged-care rest-home CLI."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import html
import io
import json
import re
import ssl
import sys
import urllib.parse
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))
import nzfetch  # noqa: E402

CSV_URL = "https://www.health.govt.nz/system/files/LegalEntitySummaryAgedCare.csv"
REST_HOME_LISTING = "https://www.health.govt.nz/regulation-legislation/certification-of-health-care-services/certified-providers/rest-homes"
FACILITY_BASE = REST_HOME_LISTING + "/"
DEFAULT_TIMEOUT = 10
REQUIRED_CSV_HEADERS = {
    "Premises Name",
    "Certification Service Type",
    "Service Types",
    "Total Beds",
    "Certificate Name",
    "Certification Period (Months)",
    "Certificate/License End Date",
    "Current Auditor",
    "Legal Name",
}


class SkillError(RuntimeError):
    def __init__(self, message: str, *, code: str = "error", source_url: str | None = None):
        super().__init__(message)
        self.code = code
        self.source_url = source_url


class UpstreamBlocked(SkillError):
    pass


def fetched_at() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def clean_text(value: Any) -> str:
    text = html.unescape(str(value or "")).replace("\xa0", " ")
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def key_text(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", clean_text(value).lower()).strip()


def slugify(value: str) -> str:
    text = clean_text(value).lower()
    text = re.sub(r"&", " and ", text)
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return re.sub(r"-+", "-", text).strip("-")


def parse_date(value: str) -> str | None:
    text = clean_text(value)
    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%d %B %Y"):
        try:
            return dt.datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return text or None


def fetch_bytes(url: str, timeout: int = DEFAULT_TIMEOUT) -> tuple[bytes, str, str]:
    try:
        body, content_type, final_url = nzfetch.fetch_bytes(
            url,
            timeout=timeout,
            headers={"Referer": "https://www.health.govt.nz/"},
            context=ssl.create_default_context(),
        )
    except nzfetch.Blocked as exc:
        raise UpstreamBlocked(
            f"Ministry of Health blocked this HTTP request; the source is public but this network may be bot-blocked. {exc}",
            code="blocked",
            source_url=url,
        ) from exc
    except nzfetch.FetchError as exc:
        raise SkillError(str(exc), code="upstream_http", source_url=url) from exc
    head = body[:5000].lower()
    if b"cf-chl-" in head or b"cloudflare" in head or b"request unsuccessful" in head:
        raise UpstreamBlocked("Ministry of Health returned a bot-protection page instead of source data.", code="blocked", source_url=final_url)
    return body, final_url, content_type


def fetch_text(url: str, timeout: int = DEFAULT_TIMEOUT) -> tuple[str, str, str]:
    body, final_url, content_type = fetch_bytes(url, timeout)
    return body.decode("utf-8-sig", "replace"), final_url, content_type


def normalise_row(row: dict[str, str]) -> dict[str, Any]:
    get = lambda name: clean_text(row.get(name, ""))
    total_beds = get("Total Beds")
    period = get("Certification Period (Months)")
    premise_name = get("Premises Name")
    return {
        "premises_name": premise_name,
        "slug": slugify(premise_name),
        "facility_url": FACILITY_BASE + slugify(premise_name) if premise_name else None,
        "certification_service_type": get("Certification Service Type"),
        "service_types": [part.strip() for part in get("Service Types").split(",") if part.strip()],
        "total_beds": int(total_beds) if total_beds.isdigit() else None,
        "premises_website": get("Premises Website") or None,
        "premises_address": {
            "other": get("Premises Address Other") or None,
            "street": get(" Premises Address"),
            "suburb_or_road": get(" Premises Address Suburb/Road"),
            "town_city": get(" Premises Address Town/City"),
            "post_code": get(" Premises Address Post Code"),
        },
        "district_health_board": get(" DHB Name") or None,
        "certificate_name": get("Certificate Name"),
        "certification_period_months": int(period) if period.isdigit() else None,
        "certificate_end_date": parse_date(get("Certificate/License End Date")),
        "current_auditor": get("Current Auditor") or None,
        "legal_name": get("Legal Name"),
        "legal_entity_address": {
            "other": get("Legal Entity Address Other") or None,
            "street": get(" Legal Entity Address"),
            "suburb_or_road": get(" Legal Entity Address Suburb/Road"),
            "town_city": get(" Legal Entity Address Town/City"),
            "post_code": get(" Legal Entity Address Post Code"),
        },
        "legal_entity_postal_address": {
            "street": get(" Legal Entity Postal Address"),
            "suburb_or_road": get(" Legal Entity Postal Address Suburb/Road"),
            "town_city": get(" Legal Entity Postal Address Town/City"),
            "post_code": get(" Legal Entity Postal Address Post Code"),
        },
        "legal_entity_website": get(" Legal Entity Website") or None,
    }


def csv_rows(timeout: int = DEFAULT_TIMEOUT) -> tuple[list[dict[str, Any]], str]:
    text, final_url, _content_type = fetch_text(CSV_URL, timeout)
    if text.lstrip().startswith("<"):
        raise UpstreamBlocked("Ministry of Health returned HTML instead of the certified-provider CSV.", code="blocked", source_url=final_url)
    reader = csv.DictReader(io.StringIO(text))
    headers = set(reader.fieldnames or [])
    missing = sorted(REQUIRED_CSV_HEADERS - headers)
    if missing:
        raise SkillError(f"certified-provider CSV schema changed; missing required headers: {', '.join(missing)}", code="upstream_schema", source_url=final_url)
    rows = [normalise_row(row) for row in reader]
    if not rows:
        raise SkillError("certified-provider CSV contained no rows", code="upstream_schema", source_url=final_url)
    return rows, final_url


def find_csv_row(name_or_slug: str, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    needle_slug = slugify(name_or_slug)
    needle_key = key_text(name_or_slug)
    for row in rows:
        if row["slug"] == needle_slug or key_text(row["premises_name"]) == needle_key:
            return row
    for row in rows:
        if needle_key and needle_key in key_text(row["premises_name"]):
            return row
    return None


def apply_filters(rows: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    filtered = rows
    if getattr(args, "query", None):
        needle = key_text(args.query)
        filtered = [row for row in filtered if needle in key_text(json.dumps(row, sort_keys=True))]
    if getattr(args, "city", None):
        city = key_text(args.city)
        filtered = [row for row in filtered if city in key_text(row["premises_address"]["town_city"])]
    if getattr(args, "provider", None):
        provider = key_text(args.provider)
        filtered = [row for row in filtered if provider in key_text(row["legal_name"])]
    return filtered


class FacilityParser(HTMLParser):
    def __init__(self, source_url: str) -> None:
        super().__init__()
        self.source_url = source_url
        self.title = ""
        self.sections: dict[str, dict[str, str]] = {}
        self.reports: list[dict[str, Any]] = []
        self.corrective_action_note: dict[str, str] | None = None
        self._capture_heading: str | None = None
        self._heading_text: list[str] = []
        self._current_section: str | None = None
        self._text: list[str] = []
        self._href: str | None = None
        self._link_text: list[str] = []
        self._last_audit_date: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {name: value or "" for name, value in attrs}
        if tag in {"h1", "h2", "h3", "h4"}:
            self._capture_heading = tag
            self._heading_text = []
        elif tag == "a":
            self._href = attrs_dict.get("href")
            self._link_text = []

    def handle_data(self, data: str) -> None:
        if data:
            self._text.append(data)
        if self._capture_heading:
            self._heading_text.append(data)
        if self._href:
            self._link_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == self._capture_heading:
            heading = clean_text(" ".join(self._heading_text))
            lower = heading.lower()
            if tag == "h1" and heading:
                self.title = heading
            if lower in {"premise details", "certification/licence details", "provider details"}:
                self._current_section = lower
            elif lower.startswith("audit date:"):
                self._last_audit_date = parse_date(heading.split(":", 1)[1])
            elif lower.startswith("corrective"):
                self._current_section = "corrective actions"
            self._capture_heading = None
            self._heading_text = []
        elif tag == "a" and self._href:
            label = clean_text(" ".join(self._link_text))
            url = urllib.parse.urljoin(self.source_url, self._href)
            if any(ext in url.lower() for ext in (".pdf", ".doc", ".docx")) or "download" in label.lower():
                self.reports.append(
                    {
                        "label": label,
                        "url": url,
                        "format": (re.search(r"\.(pdf|docx?|rtf)(?:$|[?#])", url, re.I).group(1).lower() if re.search(r"\.(pdf|docx?|rtf)(?:$|[?#])", url, re.I) else None),
                        "audit_date": self._last_audit_date,
                        "audit_type": None,
                    }
                )
            self._href = None
            self._link_text = []

    def close(self) -> None:
        super().close()
        text = clean_text(" ".join(self._text))
        self.sections = {
            "premise_details": section_fields(text, "Premise details", ["Address", "Total beds", "Service types"], "Certification/licence details"),
            "certification_licence_details": section_fields(
                text,
                "Certification/licence details",
                ["Certification/licence name", "Current auditor", "End date of current certificate/licence", "Certification period"],
                "Provider details",
            ),
            "provider_details": section_fields(text, "Provider details", ["Provider name", "Street address", "Postal address"], "Audit reports"),
        }
        if "corrective action" in text.lower():
            self.corrective_action_note = {
                "status": "not_parsed",
                "note": "Facility page text mentions corrective actions, but this CLI does not parse row-level action status; inspect the public page or audit documents before citing corrective-action details.",
            }


def section_fields(text: str, start: str, labels: list[str], end: str) -> dict[str, str]:
    start_idx = text.lower().find(start.lower())
    if start_idx < 0:
        return {}
    end_idx = text.lower().find(end.lower(), start_idx + len(start))
    section = text[start_idx : end_idx if end_idx > start_idx else len(text)]
    result: dict[str, str] = {}
    for idx, label in enumerate(labels):
        next_labels = [re.escape(item) for item in labels[idx + 1 :]]
        stop = "|".join(next_labels + [re.escape(end)])
        pattern = re.compile(re.escape(label) + r"\s+(.*?)(?=\s+(?:" + stop + r")\s+|$)", re.I)
        match = pattern.search(section)
        if match:
            result[key_text(label).replace(" ", "_")] = clean_text(match.group(1))
    return result


def facility_page_url(name_or_slug: str, fallback: dict[str, Any] | None = None) -> str:
    slug = fallback.get("slug") if fallback else slugify(name_or_slug)
    return FACILITY_BASE + slug


def parse_facility_page(url: str, timeout: int) -> dict[str, Any]:
    text, final_url, _content_type = fetch_text(url, timeout)
    parser = FacilityParser(final_url)
    parser.feed(text)
    parser.close()
    return {
        "status": "ok",
        "kind": "facility",
        "source_url": final_url,
        "fetched_at": fetched_at(),
        "title": parser.title,
        "details": parser.sections,
        "latest_audit": {
            "audit_date": parser.reports[0].get("audit_date") if parser.reports else None,
            "audit_type": None,
        },
        "reports": parser.reports,
        "corrective_actions": [],
        "corrective_action_note": parser.corrective_action_note,
    }


def blocked_payload(exc: UpstreamBlocked, *, kind: str, fallback: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": "blocked",
        "kind": kind,
        "code": exc.code,
        "source_url": exc.source_url,
        "message": str(exc),
        "note": "The source is public but blocked this HTTP client; use the source_url in a browser or retry from another network.",
    }
    if fallback:
        payload["csv_fallback"] = fallback
    return payload


def output(payload: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    print(f"{payload.get('kind')}: {payload.get('status')}")
    if payload.get("source_url"):
        print(f"Source: {payload['source_url']}")
    if payload.get("facilities"):
        for row in payload["facilities"][:10]:
            print(f"- {row['premises_name']} ({row['premises_address']['town_city']}): {row.get('total_beds')} beds")
    elif payload.get("reports"):
        for row in payload["reports"]:
            print(f"- {row.get('audit_date') or 'unknown date'} {row.get('label')}: {row.get('url')}")
    elif payload.get("message"):
        print(payload["message"])


def cmd_list(args: argparse.Namespace) -> None:
    rows, final_url = csv_rows(args.timeout)
    filtered = apply_filters(rows, args)
    payload = {
        "status": "ok",
        "kind": "facilities",
        "source_url": final_url,
        "fetched_at": fetched_at(),
        "count": len(filtered),
        "returned": min(len(filtered), args.limit),
        "facilities": filtered[: args.limit],
    }
    output(payload, args.json)


def cmd_sample(args: argparse.Namespace) -> None:
    rows, final_url = csv_rows(args.timeout)
    provider_key = key_text(args.provider)
    matches = [row for row in rows if provider_key in key_text(row["legal_name"])]
    payload = {
        "status": "ok",
        "kind": "provider_sample",
        "source_url": final_url,
        "fetched_at": fetched_at(),
        "provider_query": args.provider,
        "facility_count": len(matches),
        "total_beds": sum(row.get("total_beds") or 0 for row in matches),
        "sample": matches[: args.limit],
    }
    output(payload, args.json)


def cmd_facility(args: argparse.Namespace) -> None:
    rows, csv_url = csv_rows(args.timeout)
    fallback = find_csv_row(args.name, rows)
    url = facility_page_url(args.name, fallback)
    try:
        payload = parse_facility_page(url, args.timeout)
        payload["csv_source_url"] = csv_url
        if fallback:
            payload["csv_fallback"] = fallback
    except UpstreamBlocked as exc:
        payload = blocked_payload(exc, kind="facility", fallback=fallback)
        payload["csv_source_url"] = csv_url
    output(payload, args.json)


def cmd_reports(args: argparse.Namespace) -> None:
    rows, csv_url = csv_rows(args.timeout)
    fallback = find_csv_row(args.name, rows)
    url = facility_page_url(args.name, fallback)
    try:
        facility = parse_facility_page(url, args.timeout)
        payload = {
            "status": "ok",
            "kind": "reports",
            "source_url": facility["source_url"],
            "csv_source_url": csv_url,
            "fetched_at": facility["fetched_at"],
            "facility": facility.get("title") or (fallback or {}).get("premises_name"),
            "reports": facility["reports"],
            "count": len(facility["reports"]),
            "csv_fallback": fallback,
        }
    except UpstreamBlocked as exc:
        payload = blocked_payload(exc, kind="reports", fallback=fallback)
        payload["csv_source_url"] = csv_url
    output(payload, args.json)


def add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="network timeout in seconds")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Query Ministry of Health certified aged-care rest-home data")
    sub = parser.add_subparsers(dest="command", required=True)

    cmd = sub.add_parser("list", help="list certified aged-care rest homes from the official CSV")
    add_common(cmd)
    cmd.add_argument("--query", help="case-insensitive text filter")
    cmd.add_argument("--city", help="town/city filter")
    cmd.add_argument("--provider", help="legal provider-name filter")
    cmd.add_argument("--limit", type=int, default=20)
    cmd.set_defaults(func=cmd_list)

    cmd = sub.add_parser("facility", help="fetch one public facility page by slug or premises name")
    add_common(cmd)
    cmd.add_argument("name", help="facility slug or premises name")
    cmd.set_defaults(func=cmd_facility)

    cmd = sub.add_parser("reports", help="list audit report links for one facility page")
    add_common(cmd)
    cmd.add_argument("name", help="facility slug or premises name")
    cmd.set_defaults(func=cmd_reports)

    cmd = sub.add_parser("sample", help="return a small provider-level sample from the official CSV")
    add_common(cmd)
    cmd.add_argument("--provider", required=True, help="legal provider name or fragment")
    cmd.add_argument("--limit", type=int, default=10)
    cmd.set_defaults(func=cmd_sample)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
        return 0
    except SkillError as exc:
        payload = {"status": "error", "code": exc.code, "message": str(exc), "source_url": exc.source_url}
        if getattr(args, "json", False):
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 2
        print(f"healthcert-rest-homes-nz: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
