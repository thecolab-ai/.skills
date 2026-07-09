#!/usr/bin/env python3
"""IRD Working for Families / FamilyBoost rates helper.

Stdlib-only, read-only CLI exposing source-backed Working for Families tax
credit rates, abatement thresholds, and FamilyBoost parameters from public IRD
pages. The numeric schedule is versioned in this file; commands can also probe
IRD source pages to report reachability/last-updated snippets without relying
on scraped data for correctness.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import pathlib
import sys
import textwrap
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "lib"))
import nzfetch  # noqa: E402

UA = "ird-wff-rates-nz-skill/1.0 (+https://github.com/thecolab-ai/.skills)"
DEFAULT_TIMEOUT = 10
DISCLAIMER = (
    "General information only, not tax advice or an entitlement decision. "
    "IRD may change rates/rules; check the cited source URL before relying on this."
)

BASE = "https://www.ird.govt.nz"
SOURCES = {
    "working-for-families": f"{BASE}/working-for-families",
    "family-tax-credit": f"{BASE}/working-for-families/types/family-tax-credit",
    "in-work": f"{BASE}/working-for-families/types/in-work-tax-credit",
    "best-start": f"{BASE}/working-for-families/types/best-start",
    "mftc": f"{BASE}/working-for-families/types/minimum-family-tax-credit",
    "familyboost": f"{BASE}/familyboost/how-much-familyboost-can-you-claim",
    "familyboost-eligibility": f"{BASE}/familyboost/can-you-get-familyboost",
}

# Tax year is the year ending 31 March (for example, 2027 is 1 Apr 2026-31 Mar 2027).
DATA: dict[int, dict[str, Any]] = {
    2026: {
        "tax_year": 2026,
        "period": "1 Apr 2025 to 31 Mar 2026",
        "status": "historical_current_source_context",
        "thresholds": {
            "wff_family_income_abatement_threshold": {"amount": 44900, "unit": "annual NZD"},
            "wff_abatement_rate": {"rate": 0.275, "description": "27.5 cents per dollar over threshold"},
            "best_start_income_threshold": {"amount": 79000, "unit": "annual NZD", "applies": "years 2 and 3; first year not income-tested for children born before 1 Apr 2026"},
            "best_start_abatement_rate": {"rate": 0.21, "description": "21 cents per dollar over threshold"},
        },
        "credits": {
            "family-tax-credit": {
                "name": "Family tax credit",
                "amounts": [
                    {"family_situation": "eldest dependent child", "annual": 7921, "weekly": 152},
                    {"family_situation": "each other dependent child", "annual": 6454, "weekly": 124},
                ],
                "eligibility_summary": "For families with dependent children; full amount when family income is at or below the WFF threshold, then abated.",
                "source": SOURCES["family-tax-credit"],
            },
            "in-work": {
                "name": "In-work tax credit",
                "amounts": [
                    {"family_situation": "1 to 3 children", "annual": 5070, "weekly": 97},
                    {"family_situation": "each child after first 3", "annual": 780, "weekly": 15},
                ],
                "eligibility_summary": "For families normally receiving income from paid work and not receiving an income-tested benefit or student's allowance; abatement may apply after family tax credit.",
                "source": SOURCES["in-work"],
            },
            "best-start": {
                "name": "Best Start tax credit",
                "amounts": [{"family_situation": "eligible child", "annual": 3838, "weekly": 73}],
                "eligibility_summary": "For eligible children in the first 3 years. For children born before 1 Apr 2026 the first year is not income-tested; later years are abated over the Best Start threshold.",
                "source": SOURCES["best-start"],
            },
            "mftc": {
                "name": "Minimum family tax credit",
                "amounts": [{"family_situation": "minimum after-tax family income", "annual": 36604, "weekly": 703}],
                "eligibility_summary": "Tops up qualifying working families to a minimum after-tax income. Requires minimum weekly work hours and net family income below the limit.",
                "source": SOURCES["mftc"],
            },
        },
    },
    2027: {
        "tax_year": 2027,
        "period": "1 Apr 2026 to 31 Mar 2027",
        "status": "current_from_ird_pages_seen_2026",
        "thresholds": {
            "wff_family_income_abatement_threshold": {"amount": 44900, "unit": "annual NZD"},
            "wff_abatement_rate": {"rate": 0.275, "description": "27.5 cents per dollar over threshold"},
            "best_start_income_threshold": {"amount": 79000, "unit": "annual NZD"},
            "best_start_abatement_rate": {"rate": 0.21, "description": "21 cents per dollar over threshold"},
        },
        "credits": {
            "family-tax-credit": {
                "name": "Family tax credit",
                "amounts": [
                    {"family_situation": "eldest dependent child", "annual": 7921, "weekly": 152},
                    {"family_situation": "each other dependent child", "annual": 6454, "weekly": 124},
                ],
                "eligibility_summary": "For families with dependent children; full amount when family income is at or below $44,900, then abated at 27.5%.",
                "source": SOURCES["family-tax-credit"],
            },
            "in-work": {
                "name": "In-work tax credit",
                "amounts": [
                    {"family_situation": "1 to 3 children", "annual": 7670, "weekly": 147, "note": "Temporary increase from 1 Apr 2026; IRD says it may reduce if petrol drops below $3/litre and returns after 31 Mar 2027."},
                    {"family_situation": "each child after first 3", "annual": 780, "weekly": 15},
                ],
                "eligibility_summary": "For families receiving income from paid work. Passive income only does not qualify; abatement may apply after family tax credit.",
                "source": SOURCES["in-work"],
            },
            "best-start": {
                "name": "Best Start tax credit",
                "amounts": [{"family_situation": "eligible child", "annual": 4041, "weekly": 77}],
                "eligibility_summary": "For children born on or after 1 Apr 2026, the weekly payment is reduced when family income exceeds $79,000. For children born before 1 Apr 2026, the first year remains not income-tested.",
                "source": SOURCES["best-start"],
            },
            "mftc": {
                "name": "Minimum family tax credit",
                "amounts": [{"family_situation": "minimum after-tax family income", "annual": 36604, "weekly": 703}],
                "eligibility_summary": "Tops up qualifying working families to $36,604 a year ($703 a week) after tax. Requires minimum weekly work hours and net family income below the limit.",
                "source": SOURCES["mftc"],
            },
        },
    },
}

FAMILYBOOST = {
    "programme": "FamilyBoost",
    "source": SOURCES["familyboost"],
    "eligibility_source": SOURCES["familyboost-eligibility"],
    "periods": [
        {
            "applies": "quarters ending before 1 Jul 2025",
            "household_income_full_rate_threshold_quarterly": 35000,
            "household_income_cap_quarterly": 45000,
            "reimbursement_rate": 0.25,
            "maximum_payment_quarterly": 975,
            "abatement_rate_over_threshold": 0.0975,
        },
        {
            "applies": "quarters ending on or after 1 Jul 2025",
            "household_income_full_rate_threshold_quarterly": 35000,
            "household_income_cap_quarterly": 57286,
            "reimbursement_rate": 0.40,
            "maximum_payment_quarterly": 1560,
            "abatement_rate_over_threshold": 0.07,
        },
    ],
    "eligibility_summary": [
        "Caregiver of a child or children aged 5 and under.",
        "Household income below the quarterly cap for the claim period.",
        "Costs from a licensed early childhood education (ECE) provider.",
        "Caregiver is a New Zealand tax resident.",
        "Only claim required childcare fees; exclude donations and subsidies such as MSD Childcare Subsidy.",
    ],
    "claim_quarters": ["1 Jul-30 Sep", "1 Oct-31 Dec", "1 Jan-31 Mar", "1 Apr-30 Jun"],
}

ALIASES = {
    "family-tax-credit": "family-tax-credit", "ftc": "family-tax-credit", "family": "family-tax-credit",
    "in-work": "in-work", "in-work-tax-credit": "in-work", "iwtc": "in-work",
    "best-start": "best-start", "bstc": "best-start",
    "mftc": "mftc", "minimum-family-tax-credit": "mftc",
}


def fetch_text(url: str, timeout: int) -> str:
    return nzfetch.fetch_text(url, timeout=timeout, accept="text/html,application/xhtml+xml")


def page_probe(url: str, timeout: int) -> dict[str, Any]:
    try:
        raw = fetch_text(url, timeout)
    except (nzfetch.FetchError, TimeoutError, OSError) as e:
        return {"url": url, "available": False, "error": "upstream_unavailable", "detail": str(e)[:160]}
    txt = html.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"<(script|style)[\s\S]*?</\1>", " ", raw, flags=re.I)))
    txt = re.sub(r"\s+", " ", txt).strip()
    m = re.search(r"Last updated:\s*([^J]+?)(?:Jump back|Print|$)", txt, flags=re.I)
    return {"url": url, "available": True, "last_updated": m.group(1).strip() if m else None, "text_sample": txt[:240]}


def envelope(data: Any, *, sources: list[str] | None = None, timeout: int = DEFAULT_TIMEOUT, probe: bool = False) -> dict[str, Any]:
    out = {"ok": True, "disclaimer": DISCLAIMER, "data": data}
    if sources:
        out["sources"] = sources
        if probe:
            out["source_checks"] = [page_probe(u, timeout) for u in sources]
    return out


def emit(obj: Any, as_json: bool) -> None:
    if as_json:
        print(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print_human(obj)


def print_human(obj: Any) -> None:
    if isinstance(obj, dict) and "data" in obj:
        print(DISCLAIMER)
        print()
        data = obj["data"]
        if isinstance(data, dict):
            title = data.get("programme") or data.get("name") or f"Tax year {data.get('tax_year')}"
            print(title)
            print("-" * len(str(title)))
            if "period" in data:
                print(f"Period: {data['period']}")
            if "thresholds" in data:
                print("Thresholds:")
                for k, v in data["thresholds"].items():
                    print(f"  {k}: {v}")
            credits = data.get("credits")
            if credits:
                print("Credits:")
                for slug, credit in credits.items():
                    print(f"  {slug}: {credit['name']}")
                    for amt in credit.get("amounts", []):
                        print(f"    - {amt}")
            if "amounts" in data:
                for amt in data["amounts"]:
                    print(f"- {amt}")
                print(textwrap.fill(data.get("eligibility_summary", ""), width=88))
            if data.get("periods"):
                for p in data["periods"]:
                    print(f"- {p}")
                print("Eligibility: " + "; ".join(data.get("eligibility_summary", [])))
        if obj.get("sources"):
            print("\nSources:")
            for s in obj["sources"]:
                print(f"- {s}")
    else:
        print(obj)


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="IRD WFF / Best Start / FamilyBoost rates and thresholds")
    p.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="network timeout for optional source probes")
    sub = p.add_subparsers(dest="cmd", required=True)

    rates = sub.add_parser("rates", help="all WFF credit amounts and thresholds for a tax year")
    rates.add_argument("--year", type=int, default=max(DATA), help="tax year ending 31 March, e.g. 2027")
    rates.add_argument("--probe", action="store_true", help="probe cited IRD pages for availability/last-updated snippets")
    rates.add_argument("--json", action="store_true")

    thresholds = sub.add_parser("thresholds", help="abatement thresholds and rates for a tax year")
    thresholds.add_argument("--year", type=int, default=max(DATA))
    thresholds.add_argument("--probe", action="store_true")
    thresholds.add_argument("--json", action="store_true")

    credit = sub.add_parser("credit", help="inspect one WFF credit")
    csub = credit.add_subparsers(dest="credit_cmd", required=True)
    get = csub.add_parser("get", help="get credit by slug")
    get.add_argument("slug", choices=sorted(ALIASES))
    get.add_argument("--year", type=int, default=max(DATA))
    get.add_argument("--probe", action="store_true")
    get.add_argument("--json", action="store_true")

    fb = sub.add_parser("familyboost", help="FamilyBoost rates, caps, abatement, and eligibility")
    fb.add_argument("--probe", action="store_true")
    fb.add_argument("--json", action="store_true")
    return p.parse_args(argv)


def get_year(year: int) -> dict[str, Any]:
    if year not in DATA:
        raise KeyError(f"No built-in schedule for tax year {year}. Available: {', '.join(map(str, sorted(DATA)))}")
    return DATA[year]


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        if args.cmd == "rates":
            data = get_year(args.year)
            sources = sorted({c["source"] for c in data["credits"].values()})
            emit(envelope(data, sources=sources, timeout=args.timeout, probe=args.probe), args.json)
        elif args.cmd == "thresholds":
            data = get_year(args.year)
            payload = {"tax_year": data["tax_year"], "period": data["period"], "thresholds": data["thresholds"]}
            emit(envelope(payload, sources=[SOURCES["family-tax-credit"], SOURCES["best-start"]], timeout=args.timeout, probe=args.probe), args.json)
        elif args.cmd == "credit" and args.credit_cmd == "get":
            data = get_year(args.year)
            slug = ALIASES[args.slug]
            credit = dict(data["credits"][slug])
            credit.update({"slug": slug, "tax_year": args.year, "thresholds": data["thresholds"]})
            emit(envelope(credit, sources=[credit["source"]], timeout=args.timeout, probe=args.probe), args.json)
        elif args.cmd == "familyboost":
            emit(envelope(FAMILYBOOST, sources=[FAMILYBOOST["source"], FAMILYBOOST["eligibility_source"]], timeout=args.timeout, probe=args.probe), args.json)
        return 0
    except KeyError as e:
        err = {"ok": False, "error": "not_found", "message": str(e).strip("'")}
        print(json.dumps(err, ensure_ascii=False, indent=2) if getattr(args, "json", False) else err["message"], file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
