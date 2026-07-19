#!/usr/bin/env python3
"""Query the official public Hinekōrako drinking-water register."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "lib"))

import nzfetch  # noqa: E402
from hinekorako_register import (  # noqa: E402
    LIST_URL,
    document_result,
    exact_supply_match,
    fetch_supplies,
    parse_supply_detail,
    supplier_relationships,
)
from result_contract import result_envelope, utc_now  # noqa: E402

HOSTS = {"hinekorako.taumataarowai.govt.nz"}
WARNINGS = [
    "Registration is not proof of current potability or compliance.",
    "Missing public documents do not prove non-compliance.",
    "Some supplies need not register until 2028 and withheld information is preserved.",
]


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    for command, positional in (("supplier", "query"), ("supply", "id_or_name"), ("region", "name"), ("documents", "id")):
        child = commands.add_parser(command)
        child.add_argument(positional)
        child.add_argument("--limit", type=int, default=20)
        child.add_argument("--json", action="store_true")
    near = commands.add_parser("near")
    near.add_argument("--lat", type=float, required=True)
    near.add_argument("--lon", type=float, required=True)
    near.add_argument("--limit", type=int, default=20)
    near.add_argument("--json", action="store_true")
    return root


def main() -> int:
    args = parser().parse_args()
    if not 1 <= args.limit <= 100:
        print(json.dumps({"error": "invalid_input", "message": "--limit must be between 1 and 100"}), file=sys.stderr)
        return 2
    if args.command == "near":
        print(
            json.dumps(
                {
                    "error": "unsupported_operation",
                    "message": "The public register does not expose official coordinates or service-area geometry for a reliable nearby lookup.",
                }
            ),
            file=sys.stderr,
        )
        return 7
    retrieved_at = utc_now()
    try:
        if args.command == "region":
            data, _ = fetch_supplies(region=args.name, limit=args.limit)
            query = args.name
        else:
            query = args.query if args.command == "supplier" else args.id_or_name if args.command == "supply" else args.id
            search_limit = 50 if args.command in {"supply", "documents"} else args.limit
            data, _ = fetch_supplies(search=query, limit=search_limit)
        if args.command == "supplier":
            candidates = data
            if not candidates:
                candidates, _ = fetch_supplies(limit=min(50, max(20, args.limit * 4)))
            suppliers: dict[tuple[str, str], dict] = {}
            for row in candidates[: min(50, max(20, args.limit * 4))]:
                detail_html = nzfetch.fetch_text(row["source_url"], timeout=25, allowed_hosts=HOSTS)
                detail = parse_supply_detail(detail_html, row["source_url"], retrieved_at)
                for relationship in supplier_relationships(detail):
                    if query.casefold() not in relationship["name"].casefold():
                        continue
                    key = (relationship["relationship"], relationship["name"].casefold())
                    supplier = suppliers.setdefault(key, {
                        "name": relationship["name"],
                        "relationship": relationship["relationship"],
                        "related_supplies": [],
                        "source_url": row["source_url"],
                        "retrieved_at": retrieved_at,
                    })
                    supplier["related_supplies"].append({"id": detail["supply_id"], "name": detail["supply_name"], "source_url": row["source_url"]})
            if not suppliers:
                raise RuntimeError("The bounded public-register records did not publish a matching supplier/owner/operator relationship")
            data = list(suppliers.values())[:args.limit]
        if args.command in {"supply", "documents"}:
            exact = exact_supply_match(data, query)
            if exact is None:
                data = []
            else:
                detail_html = nzfetch.fetch_text(exact["source_url"], timeout=25, allowed_hosts=HOSTS)
                detail = parse_supply_detail(detail_html, exact["source_url"], retrieved_at)
                data = [document_result(detail)] if args.command == "documents" else [detail]
        for row in data:
            row.setdefault("retrieved_at", retrieved_at)
            row.setdefault("what_this_does_not_prove", WARNINGS[:2])
        warnings = list(WARNINGS)
        if args.command == "supplier":
            warnings.append("Supplier results include only owner/operator relationships explicitly published on linked supply detail records.")
        envelope = result_envelope(
            ok=True,
            source_name="Taumata Arowai Hinekōrako public register",
            source_url=LIST_URL,
            retrieved_at=retrieved_at,
            freshness="source-managed",
            query=vars(args),
            data=data,
            warnings=warnings,
            blocked=False,
        )
        print(json.dumps(envelope if args.json else data, indent=2, ensure_ascii=False))
        return 0
    except LookupError as exc:
        print(json.dumps({"error": "invalid_input", "message": str(exc)}), file=sys.stderr)
        return 2
    except RuntimeError as exc:
        print(json.dumps({"error": "unsupported_source_surface", "message": str(exc)}), file=sys.stderr)
        return 7
    except nzfetch.RateLimited as exc:
        print(json.dumps({"error": "rate_limited", "retry_after": exc.retry_after, "message": str(exc)}), file=sys.stderr)
        return 4
    except nzfetch.Blocked as exc:
        print(json.dumps({"error": "blocked", "message": str(exc)}), file=sys.stderr)
        return 4
    except nzfetch.FetchError as exc:
        print(json.dumps({"error": "source_unavailable", "message": str(exc)}), file=sys.stderr)
        return 5
    except (ValueError, KeyError) as exc:
        print(json.dumps({"error": "source_schema_failure", "message": str(exc)}), file=sys.stderr)
        return 6


if __name__ == "__main__":
    raise SystemExit(main())
