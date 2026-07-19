#!/usr/bin/env python3
"""Query official Treasury fiscal publications and workbook values."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "lib"))

import nzfetch  # noqa: E402
from result_contract import result_envelope, utc_now  # noqa: E402
from treasury_workbooks import (  # noqa: E402
    ComparisonError,
    compare_key_indicators,
    filter_key_indicators,
    parse_key_indicators,
    parse_publications,
    parse_resources,
    primary_forecast_publications,
    resolve_publication,
    search_appropriations,
    select_charts_workbook,
)

ALLOWED = {"treasury.govt.nz", "www.treasury.govt.nz"}
CATALOGUE = "https://www.treasury.govt.nz/publications/budgets/forecasts"
APPROPS = "https://www.treasury.govt.nz/publications/data/budget-2026-data-estimates-appropriations-2026-27"
BUDGET = "https://www.treasury.govt.nz/publications/budgets/budget-2026"
APPROPS_PUBLICATION = {
    "title": "Budget 2026 Data: Estimates and Appropriations 2026/27",
    "url": APPROPS,
}
WARN = [
    "Do not compare measures whose definitions changed between publications.",
    "Actuals, forecasts, scenarios and assumptions remain distinct.",
    "Values retain publication, workbook, period, status and cell provenance.",
    "Fiscal data retrieval is not financial or investment advice.",
]


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    for name in ("latest", "fiscal-model", "sources"):
        command = commands.add_parser(name)
        command.add_argument("--limit", type=int, default=50)
        command.add_argument("--json", action="store_true")
    for name, positional in (
        ("forecast", "indicator"),
        ("appropriation", "query"),
        ("vote", "name"),
    ):
        command = commands.add_parser(name)
        command.add_argument(positional)
        command.add_argument("--limit", type=int, default=50)
        command.add_argument("--json", action="store_true")
    command = commands.add_parser("compare")
    command.add_argument("--from", dest="from_publication", required=True)
    command.add_argument("--to", dest="to_publication", required=True)
    command.add_argument("--limit", type=int, default=50)
    command.add_argument("--json", action="store_true")
    return root


def get_resources(url, stamp):
    return parse_resources(
        nzfetch.fetch_text(url, timeout=30, allowed_hosts=ALLOWED), url, stamp
    )


def get_publications(stamp):
    rows = parse_publications(
        nzfetch.fetch_text(CATALOGUE, timeout=30, allowed_hosts=ALLOWED),
        CATALOGUE,
        stamp,
    )
    publications = primary_forecast_publications(rows)
    if not publications:
        raise ValueError("Treasury forecasts catalogue contained no primary EFU releases")
    return rows, publications


def publication_sources(publications, stamp, limit):
    output = []
    for publication in publications[:limit]:
        resources = [
            resource
            for resource in get_resources(publication["url"], stamp)
            if resource["format"] in {"xlsx", "xls", "csv", "pdf"}
        ]
        output.append(
            {
                **publication,
                "resources": resources,
            }
        )
    return output


def main():
    args = parser().parse_args()
    stamp = utc_now()
    try:
        if not 1 <= args.limit <= 100:
            raise ValueError("--limit must be between 1 and 100")

        if args.command == "latest":
            _, publications = get_publications(stamp)
            source_url = CATALOGUE
            data = publications[: args.limit]
        elif args.command == "sources":
            _, publications = get_publications(stamp)
            source_url = CATALOGUE
            data = publication_sources(publications, stamp, args.limit)
        elif args.command == "forecast":
            _, publications = get_publications(stamp)
            publication = publications[0]
            workbook_record = select_charts_workbook(
                get_resources(publication["url"], stamp)
            )
            body, _, workbook_url = nzfetch.fetch_bytes(
                workbook_record["url"], timeout=60, allowed_hosts=ALLOWED
            )
            records = parse_key_indicators(
                body, publication, workbook_url, stamp
            )
            data = filter_key_indicators(records, args.indicator, args.limit)
            source_url = publication["url"]
        elif args.command in {"appropriation", "vote"}:
            resources = get_resources(APPROPS, stamp)
            workbooks = [row for row in resources if row["format"] == "xlsx"]
            if not workbooks:
                raise ValueError("Treasury publication exposed no XLSX workbook")
            workbook_record = next(
                (row for row in workbooks if "expenditure" in row["title"].casefold()),
                workbooks[0],
            )
            body, _, workbook_url = nzfetch.fetch_bytes(
                workbook_record["url"], timeout=60, allowed_hosts=ALLOWED
            )
            query = args.query if args.command == "appropriation" else args.name
            data = search_appropriations(
                body,
                query,
                APPROPS_PUBLICATION,
                workbook_url,
                stamp,
                args.limit,
                vote_only=args.command == "vote",
            )
            source_url = APPROPS
        elif args.command == "fiscal-model":
            source_url = BUDGET
            data = [
                row
                for row in get_resources(source_url, stamp)
                if "model" in row["title"].casefold()
            ][: args.limit]
        else:
            source_url = CATALOGUE
            publication_rows, _ = get_publications(stamp)
            before = resolve_publication(publication_rows, args.from_publication)
            after = resolve_publication(publication_rows, args.to_publication)
            if not before or not after:
                print(
                    json.dumps(
                        {
                            "error": "unsupported_operation",
                            "code": 7,
                            "message": "One or both publication vintages did not resolve uniquely to the official Treasury forecasts catalogue.",
                        }
                    ),
                    file=sys.stderr,
                )
                return 7
            before_workbook = select_charts_workbook(
                get_resources(before["url"], stamp)
            )
            after_workbook = select_charts_workbook(
                get_resources(after["url"], stamp)
            )
            before_body, _, before_url = nzfetch.fetch_bytes(
                before_workbook["url"], timeout=60, allowed_hosts=ALLOWED
            )
            after_body, _, after_url = nzfetch.fetch_bytes(
                after_workbook["url"], timeout=60, allowed_hosts=ALLOWED
            )
            before_rows = parse_key_indicators(
                before_body, before, before_url, stamp
            )
            after_rows = parse_key_indicators(after_body, after, after_url, stamp)
            data = compare_key_indicators(before_rows, after_rows, args.limit)

        warnings = list(WARN)
        if args.command == "compare":
            warnings.append(
                "Compare includes only exact shared Table 1 definitions, units, period basis and forecast periods; changed or ambiguous definitions fail closed."
            )
        envelope = result_envelope(
            ok=True,
            source_name="New Zealand Treasury",
            source_url=source_url,
            retrieved_at=stamp,
            freshness="publication-specific",
            query=vars(args),
            data=data,
            warnings=warnings,
            blocked=False,
        )
        print(
            json.dumps(
                envelope if args.json else data, indent=2, ensure_ascii=False
            )
        )
        return 0
    except ComparisonError as error:
        print(
            json.dumps(
                {"error": "unsupported_operation", "code": 7, "message": str(error)}
            ),
            file=sys.stderr,
        )
        return 7
    except ValueError as error:
        print(
            json.dumps(
                {"error": "invalid_input_or_source_schema", "message": str(error)}
            ),
            file=sys.stderr,
        )
        return 2 if str(error).startswith("--") else 6
    except nzfetch.RateLimited as error:
        print(
            json.dumps(
                {
                    "error": "rate_limited",
                    "message": str(error),
                    "retry_after": error.retry_after,
                }
            ),
            file=sys.stderr,
        )
        return 4
    except nzfetch.Blocked as error:
        print(json.dumps({"error": "blocked", "message": str(error)}), file=sys.stderr)
        return 4
    except nzfetch.FetchError as error:
        print(
            json.dumps({"error": "source_unavailable", "message": str(error)}),
            file=sys.stderr,
        )
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
