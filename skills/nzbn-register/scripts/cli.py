#!/usr/bin/env python3
"""NZBN Register lightweight public lookup CLI.

Self-contained stdlib wrapper around read-only public NZBN Register website
proxy endpoints. No API key, login, cookies, writes, or private data access.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import pathlib
import urllib.parse
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "lib"))
import nzfetch  # noqa: E402

BASE_WEB = "https://www.nzbn.govt.nz"
PROXY = BASE_WEB + "/api/business/nzbn"


def die(message: str, code: int = 1) -> None:
    print(f"nzbn-register: {message}", file=sys.stderr)
    raise SystemExit(code)


def nzbn_path(uri: str, timeout: int = 25) -> Any:
    """GET an NZBN API URI through the public website proxy."""
    url = PROXY + "?" + urllib.parse.urlencode({"u": uri})
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Referer": BASE_WEB + "/mynzbn/search/",
    }
    try:
        body, _ct, _final = nzfetch.fetch_bytes(
            url, timeout=timeout, headers=headers, accept="application/json, text/plain, */*"
        )
    except nzfetch.Blocked as e:
        die(f"network error: {e}")
    except nzfetch.FetchError as e:
        die(str(e))
    raw = body.decode("utf-8", "replace")
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        die(f"invalid JSON from {url}: {e}")
    # The proxy commonly returns upstream errors as JSON with HTTP 200.
    if isinstance(payload, dict):
        status = str(payload.get("status") or payload.get("statusCode") or "")
        if status and not status.startswith("2"):
            msg = payload.get("errorDescription") or payload.get("message") or payload.get("error") or raw[:300]
            die(f"upstream error for {uri}: {status} {msg}")
    return payload


def nzbn_url(nzbn: Any) -> str | None:
    s = str(nzbn or "").strip()
    if not s:
        return None
    return f"{BASE_WEB}/mynzbn/nzbndetails/{urllib.parse.quote(s)}/"


def compact_address(addr: dict[str, Any]) -> str:
    parts = [addr.get("careOf"), addr.get("address1"), addr.get("address2"), addr.get("address3"), addr.get("address4"), addr.get("postCode"), addr.get("countryCode")]
    return ", ".join(str(p) for p in parts if p)


def simplify_entity(entity: dict[str, Any], *, detail: bool = False) -> dict[str, Any]:
    out: dict[str, Any] = {
        "nzbn": entity.get("nzbn"),
        "entity_name": entity.get("entityName"),
        "entity_status": entity.get("entityStatusDescription"),
        "entity_status_code": entity.get("entityStatusCode"),
        "entity_type": entity.get("entityTypeDescription"),
        "entity_type_code": entity.get("entityTypeCode"),
        "registration_date": entity.get("registrationDate"),
        "source_register": entity.get("sourceRegister"),
        "source_register_unique_id": entity.get("sourceRegisterUniqueIdentifier") or entity.get("sourceRegisterUniqueId"),
        "last_updated_date": entity.get("lastUpdatedDate"),
        "previous_entity_names": entity.get("previousEntityNames") or [],
        "trading_names": [x.get("name") for x in entity.get("tradingNames") or [] if isinstance(x, dict) and x.get("name") and x.get("name") != "No trading name"],
        "url": nzbn_url(entity.get("nzbn")),
    }
    if detail:
        addresses = (entity.get("addresses") or {}).get("addressList") if isinstance(entity.get("addresses"), dict) else entity.get("addresses")
        if isinstance(addresses, list):
            out["addresses"] = [
                {
                    "type": a.get("addressType"),
                    "address": compact_address(a),
                    "start_date": a.get("startDate"),
                    "end_date": a.get("endDate"),
                }
                for a in addresses
                if isinstance(a, dict)
            ]
        out["websites"] = [x.get("url") for x in entity.get("websites") or [] if isinstance(x, dict) and x.get("url")]
        out["email_addresses"] = [x.get("emailAddress") for x in entity.get("emailAddresses") or [] if isinstance(x, dict) and x.get("emailAddress")]
        out["phone_numbers"] = [x for x in entity.get("phoneNumbers") or [] if isinstance(x, dict)]
        out["industry_classifications"] = [x for x in entity.get("industryClassifications") or entity.get("classifications") or [] if isinstance(x, dict)]
        out["gst_numbers"] = entity.get("gstNumbers") or []
        out["australian_business_number"] = entity.get("australianBusinessNumber")
    return out


def emit(data: Any, as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False))
        return
    if isinstance(data, dict) and "entities" in data:
        print(f"NZBN search: {data.get('total_items')} total, showing {len(data.get('entities') or [])} ({data.get('elapsed_ms')} ms)")
        print()
        for item in data.get("entities") or []:
            print(f"{item.get('nzbn')}  {item.get('entity_name')}")
            bits = [item.get("entity_status"), item.get("entity_type"), item.get("registration_date")]
            print("  " + " | ".join(str(x) for x in bits if x))
            if item.get("trading_names"):
                print("  trading: " + "; ".join(item["trading_names"]))
            if item.get("url"):
                print(f"  {item.get('url')}")
            print()
    elif isinstance(data, dict) and "entity" in data:
        e = data["entity"]
        print(f"{e.get('nzbn')}  {e.get('entity_name')}")
        bits = [e.get("entity_status"), e.get("entity_type"), e.get("source_register"), e.get("registration_date")]
        print("  " + " | ".join(str(x) for x in bits if x))
        if e.get("previous_entity_names"):
            print("  previous names: " + "; ".join(e["previous_entity_names"][:8]))
        if e.get("trading_names"):
            print("  trading: " + "; ".join(e["trading_names"][:8]))
        for addr in e.get("addresses") or []:
            print(f"  {addr.get('type')}: {addr.get('address')}")
        if e.get("websites"):
            print("  websites: " + "; ".join(e["websites"]))
        if e.get("email_addresses"):
            print("  emails: " + "; ".join(e["email_addresses"]))
        if e.get("url"):
            print(f"  {e.get('url')}")
        print(f"  fetched in {data.get('elapsed_ms')} ms")
    else:
        print(data)


def cmd_search(args: argparse.Namespace) -> None:
    if not args.query.strip():
        die("search query is required")
    page_size = min(max(1, args.limit), 100)
    page = max(0, args.page)
    params = {
        "search-term": args.query,
        "page-size": page_size,
        "page": page,
    }
    uri = "entities?" + urllib.parse.urlencode({k: v for k, v in params.items() if v not in (None, "")})
    started = time.perf_counter()
    payload = nzbn_path(uri)
    elapsed_ms = round((time.perf_counter() - started) * 1000)
    items = payload.get("items") if isinstance(payload, dict) else []
    data = {
        "query": args.query,
        "page": payload.get("page") if isinstance(payload, dict) else page,
        "page_size": payload.get("pageSize") if isinstance(payload, dict) else page_size,
        "total_items": payload.get("totalItems") if isinstance(payload, dict) else None,
        "elapsed_ms": elapsed_ms,
        "entities": [simplify_entity(x) for x in items or [] if isinstance(x, dict)],
    }
    emit(data, args.json)


def cmd_lookup(args: argparse.Namespace) -> None:
    nzbn = re.sub(r"\D", "", args.nzbn)
    if len(nzbn) != 13:
        die("NZBN must be 13 digits")
    started = time.perf_counter()
    payload = nzbn_path(f"entities/{nzbn}")
    elapsed_ms = round((time.perf_counter() - started) * 1000)
    if not isinstance(payload, dict):
        die("unexpected lookup response")
    data = {
        "elapsed_ms": elapsed_ms,
        "entity": simplify_entity(payload, detail=True),
        "raw": payload if args.raw else None,
    }
    emit(data, args.json)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Search and lookup public NZBN Register entities")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("search", help="search businesses/entities by name or NZBN text")
    s.add_argument("query", help="business/entity name or NZBN search text")
    s.add_argument("--limit", type=int, default=10, help="results per page, 1-100 (default: 10)")
    s.add_argument("--page", type=int, default=0, help="zero-based page number (default: 0)")
    s.add_argument("--json", action="store_true", help="emit JSON")
    s.set_defaults(func=cmd_search)

    l = sub.add_parser("lookup", help="lookup exact 13-digit NZBN")
    l.add_argument("nzbn", help="13-digit NZBN")
    l.add_argument("--json", action="store_true", help="emit JSON")
    l.add_argument("--raw", action="store_true", help="include raw upstream payload in JSON")
    l.set_defaults(func=cmd_lookup)
    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
