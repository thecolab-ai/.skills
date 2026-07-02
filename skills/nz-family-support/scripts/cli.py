#!/usr/bin/env python3
"""Official-source mapper for New Zealand family support entitlements.

This is deliberately not an entitlement calculator. It maps a public question or
high-level situation to the official IRD/MSD/WINZ pages and checkers that should
be consulted next, without collecting names, IRD numbers, income, addresses, or
other private data.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from typing import Any

UA = "nz-family-support-skill/1.0 (+https://github.com/thecolab-ai/.skills)"

DISCLAIMER = (
    "Official-source map only. This skill does not calculate entitlements, make "
    "eligibility decisions, collect private data, or submit applications. Use the "
    "linked IRD/MSD/WINZ pages and official checkers for current rules and rates."
)

SOURCES: list[dict[str, Any]] = [
    {
        "id": "ird-support-for-families",
        "title": "IRD support for families",
        "agency": "Inland Revenue Department (IRD)",
        "url": "https://www.ird.govt.nz/support-for-families",
        "category": "overview",
        "use_for": [
            "starting point for IRD-administered family payments",
            "finding official IRD family-support topics",
            "checking where family tax credits, Best Start, paid parental leave, or child support sit",
        ],
        "keywords": ["ird", "support", "families", "family", "overview", "tax credits", "child support"],
        "handoff": "Use this as the IRD landing page, then follow the specific programme page for rules.",
    },
    {
        "id": "ird-working-for-families",
        "title": "Working for Families Tax Credits",
        "agency": "Inland Revenue Department (IRD)",
        "url": "https://www.ird.govt.nz/working-for-families",
        "category": "tax-credit",
        "use_for": [
            "Working for Families Tax Credits (WFFTC)",
            "family tax credit, in-work tax credit, minimum family tax credit, or Best Start context",
            "IRD online application/update pathways for WFF",
        ],
        "keywords": ["working for families", "wff", "wfftc", "tax credit", "family tax credit", "in-work", "minimum family tax credit"],
        "handoff": "IRD is the primary source for WFF tax-credit rules and payments unless the person is receiving some MSD assistance.",
    },
    {
        "id": "ird-wff-msd-handoff",
        "title": "Working for Families — when MSD is involved",
        "agency": "Inland Revenue Department (IRD) / Ministry of Social Development (MSD)",
        "url": "https://www.ird.govt.nz/working-for-families/all-about-working-for-families/msd",
        "category": "handoff",
        "use_for": [
            "deciding whether IRD or MSD should be contacted about WFF",
            "families receiving a benefit or other MSD assistance",
            "questions about WFF payment responsibility between agencies",
        ],
        "keywords": ["msd", "winz", "benefit", "handoff", "who pays", "work and income", "working for families"],
        "handoff": "Consult this before advising on agency responsibility; it is the official IRD handoff page for MSD cases.",
    },
    {
        "id": "ird-best-start",
        "title": "Best Start tax credit",
        "agency": "Inland Revenue Department (IRD)",
        "url": "https://www.ird.govt.nz/working-for-families/types/best-start",
        "category": "tax-credit",
        "use_for": [
            "Best Start for a newborn or young child",
            "birth/adoption family-support questions",
            "checking official Best Start eligibility period and income-test notes",
        ],
        "keywords": ["best start", "new baby", "newborn", "birth", "baby", "young child", "tax credit"],
        "handoff": "Map Best Start questions here first; do not infer eligibility from age or income supplied in chat.",
    },
    {
        "id": "ird-familyboost",
        "title": "FamilyBoost childcare payment",
        "agency": "Inland Revenue Department (IRD)",
        "url": "https://www.ird.govt.nz/familyboost",
        "category": "childcare",
        "use_for": [
            "FamilyBoost claims for early childhood education fees",
            "childcare-cost reimbursement questions",
            "distinguishing IRD FamilyBoost from MSD Childcare Subsidy",
        ],
        "keywords": ["familyboost", "family boost", "ece", "early childhood", "childcare", "daycare", "kindy", "fees"],
        "handoff": "Use for IRD FamilyBoost claims; compare with MSD Childcare Subsidy when the user asks generally about childcare help.",
    },
    {
        "id": "msd-checker",
        "title": "Check what you might get",
        "agency": "Ministry of Social Development (MSD)",
        "url": "https://check.msd.govt.nz/",
        "category": "checker",
        "use_for": [
            "official MSD eligibility pre-check across benefits and payments",
            "broad 'what can I get?' questions",
            "directing users to a private official checker instead of collecting details in chat",
        ],
        "keywords": ["checker", "what can i get", "eligibility", "msd", "winz", "benefit", "payment", "entitlement"],
        "handoff": "Send users to the official checker for personal circumstances; do not ask them to disclose private details to the agent.",
    },
    {
        "id": "msd-accommodation-supplement-checker",
        "title": "Accommodation Supplement checker",
        "agency": "Ministry of Social Development (MSD)",
        "url": "https://check.msd.govt.nz/services/accommodation-supplement",
        "category": "checker",
        "use_for": [
            "quick official check for Accommodation Supplement",
            "rent, board, or home-ownership housing-cost help questions",
            "routing housing-cost eligibility questions away from chat-based calculation",
        ],
        "keywords": ["accommodation supplement checker", "rent", "housing", "board", "mortgage", "accommodation", "supplement"],
        "handoff": "Use this checker for personal Accommodation Supplement estimates; pair with the WINZ information page for rules.",
    },
    {
        "id": "winz-accommodation-supplement",
        "title": "Accommodation Supplement",
        "agency": "Work and Income (WINZ/MSD)",
        "url": "https://www.workandincome.govt.nz/products/a-z-benefits/accommodation-supplement.html",
        "category": "housing",
        "use_for": [
            "official Accommodation Supplement rules and application pathway",
            "help with rent, board, or home-ownership costs",
            "checking documents/process after using the MSD checker",
        ],
        "keywords": ["accommodation supplement", "rent", "board", "housing costs", "winz", "work and income", "mortgage"],
        "handoff": "Use for the programme page; use the MSD checker for personalised pre-checks.",
    },
    {
        "id": "winz-childcare-subsidy",
        "title": "Childcare Subsidy",
        "agency": "Work and Income (WINZ/MSD)",
        "url": "https://www.workandincome.govt.nz/products/a-z-benefits/childcare-subsidy.html",
        "category": "childcare",
        "use_for": [
            "MSD Childcare Subsidy rules and application pathway",
            "help paying for pre-school childcare",
            "distinguishing MSD subsidy from IRD FamilyBoost",
        ],
        "keywords": ["childcare subsidy", "childcare", "preschool", "pre-school", "daycare", "winz", "msd", "familyboost"],
        "handoff": "Use with IRD FamilyBoost when a user asks generally about childcare support; they are different programmes.",
    },
    {
        "id": "winz-working-for-families",
        "title": "Working for Families payments through Work and Income",
        "agency": "Work and Income (WINZ/MSD)",
        "url": "https://www.workandincome.govt.nz/products/a-z-benefits/working-for-families.html",
        "category": "tax-credit",
        "use_for": [
            "WINZ/MSD-facing Working for Families information",
            "families receiving a benefit who ask about WFF",
            "checking Work and Income process alongside the IRD MSD handoff page",
        ],
        "keywords": ["working for families", "wff", "winz", "work and income", "msd", "benefit", "family tax credit"],
        "handoff": "Use alongside the IRD MSD handoff page where benefits/MSD involvement affect the route.",
    },
]

PATHWAYS: dict[str, dict[str, Any]] = {
    "starting-point": {
        "title": "I need to know what family support might exist",
        "summary": "Start with official overviews and private checkers, not an agent-run calculator.",
        "source_ids": ["ird-support-for-families", "msd-checker", "ird-working-for-families"],
    },
    "working-for-families": {
        "title": "Working for Families / family tax credits",
        "summary": "Use IRD for WFF rules, then check the IRD/MSD handoff if benefits or Work and Income are involved.",
        "source_ids": ["ird-working-for-families", "ird-wff-msd-handoff", "winz-working-for-families"],
    },
    "new-baby": {
        "title": "New baby / Best Start",
        "summary": "Map Best Start questions to IRD and avoid estimating entitlement from chat details.",
        "source_ids": ["ird-best-start", "ird-working-for-families", "ird-support-for-families"],
    },
    "childcare": {
        "title": "Childcare or early childhood education costs",
        "summary": "Compare the IRD FamilyBoost page with the MSD Childcare Subsidy page; they are separate programmes.",
        "source_ids": ["ird-familyboost", "winz-childcare-subsidy", "msd-checker"],
    },
    "housing": {
        "title": "Rent, board, mortgage, or accommodation costs",
        "summary": "Use the MSD Accommodation Supplement checker for a private pre-check, plus the WINZ programme page for rules.",
        "source_ids": ["msd-accommodation-supplement-checker", "winz-accommodation-supplement", "msd-checker"],
    },
    "on-benefit": {
        "title": "Family is receiving a benefit or already dealing with MSD/WINZ",
        "summary": "Check the IRD/MSD handoff before deciding whether IRD or MSD is the right source for WFF questions.",
        "source_ids": ["ird-wff-msd-handoff", "winz-working-for-families", "msd-checker"],
    },
}


def by_id() -> dict[str, dict[str, Any]]:
    return {source["id"]: source for source in SOURCES}


def public_source(source: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": source["id"],
        "title": source["title"],
        "agency": source["agency"],
        "category": source["category"],
        "url": source["url"],
        "use_for": source["use_for"],
        "handoff": source["handoff"],
    }


def score_source(source: dict[str, Any], query: str) -> int:
    q = query.lower()
    query_words = {
        word
        for word in q.replace("/", " ").replace("-", " ").split()
        if len(word) > 2
        and word
        not in {
            "and",
            "for",
            "get",
            "help",
            "how",
            "the",
            "with",
            "what",
            "where",
        }
    }
    terms = [source["id"], source["title"], source["agency"], source["category"]]
    terms.extend(source.get("keywords", []))
    terms.extend(source.get("use_for", []))
    score = 0
    for term in terms:
        t = str(term).lower()
        if t and t in q:
            score += 5
        for word in t.replace("/", " ").replace("-", " ").split():
            if len(word) > 2 and word in query_words:
                score += 1
    return score


def emit(payload: dict[str, Any], as_json: bool) -> None:
    payload = {"disclaimer": DISCLAIMER, **payload}
    if as_json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    print(payload.get("title", "NZ family support source map"))
    if payload.get("summary"):
        print(payload["summary"])
    print(f"\nNote: {DISCLAIMER}")
    sources = payload.get("sources") or payload.get("results") or []
    if sources:
        print("\nOfficial sources:")
        for item in sources:
            print(f"- {item['title']} ({item['agency']})")
            print(f"  {item['url']}")
            print(f"  Use for: {'; '.join(item['use_for'][:2])}")
            print(f"  Handoff: {item['handoff']}")
    if payload.get("pathways"):
        print("\nPathways:")
        for key, item in payload["pathways"].items():
            print(f"- {key}: {item['title']}")


def cmd_sources(args: argparse.Namespace) -> int:
    items = [public_source(s) for s in SOURCES]
    if args.category:
        items = [s for s in items if s["category"] == args.category]
    emit({"title": "NZ family support official sources", "count": len(items), "sources": items}, args.json)
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    ranked = []
    for source in SOURCES:
        score = score_source(source, args.query)
        if score:
            item = public_source(source)
            item["score"] = score
            ranked.append(item)
    ranked.sort(key=lambda item: (-item["score"], item["title"]))
    ranked = ranked[: args.limit]
    emit(
        {
            "title": f"Official source matches for: {args.query}",
            "query": args.query,
            "count": len(ranked),
            "results": ranked,
            "safe_prompt": "Ask only high-level routing questions; send personal details to official checkers/pages.",
        },
        args.json,
    )
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    lookup = by_id()
    source = lookup.get(args.source_id)
    if not source:
        raise ValueError(f"unknown source id: {args.source_id}")
    emit({"title": source["title"], "sources": [public_source(source)]}, args.json)
    return 0


def cmd_pathway(args: argparse.Namespace) -> int:
    pathway = PATHWAYS.get(args.topic)
    if not pathway:
        raise ValueError(f"unknown pathway: {args.topic}")
    lookup = by_id()
    sources = [public_source(lookup[source_id]) for source_id in pathway["source_ids"]]
    emit({"title": pathway["title"], "summary": pathway["summary"], "topic": args.topic, "sources": sources}, args.json)
    return 0


def cmd_pathways(args: argparse.Namespace) -> int:
    payload = {
        key: {"title": value["title"], "summary": value["summary"], "source_ids": value["source_ids"]}
        for key, value in PATHWAYS.items()
    }
    emit({"title": "NZ family support routing pathways", "pathways": payload}, args.json)
    return 0


def check_url(url: str, timeout: int) -> dict[str, Any]:
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return {"url": url, "ok": 200 <= resp.status < 400, "status": resp.status}
    except urllib.error.HTTPError as e:
        return {"url": url, "ok": 200 <= e.code < 400, "status": e.code}
    except Exception as e:  # noqa: BLE001 - clean CLI error object for smoke tolerance
        return {"url": url, "ok": False, "error": type(e).__name__, "message": str(e)}


def cmd_verify(args: argparse.Namespace) -> int:
    targets = SOURCES if args.all else SOURCES[: args.limit]
    checks = [check_url(source["url"], args.timeout) | {"id": source["id"]} for source in targets]
    ok = all(item.get("ok") for item in checks)
    payload = {"title": "Official source URL checks", "count": len(checks), "ok": ok, "results": checks}
    if args.json:
        print(json.dumps({"disclaimer": DISCLAIMER, **payload}, indent=2, ensure_ascii=False))
    else:
        print("Official source URL checks")
        for item in checks:
            status = item.get("status", item.get("error", "unknown"))
            print(f"- {'OK' if item.get('ok') else 'WARN'} {item['id']}: {status} {item['url']}")
    return 0 if ok else 2


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Map NZ family-support questions to official IRD/MSD/WINZ sources.")
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("sources", help="list official sources")
    p.add_argument("--category", choices=sorted({s["category"] for s in SOURCES}), help="filter by category")
    p.add_argument("--json", action="store_true", help="emit JSON")
    p.set_defaults(func=cmd_sources)

    p = sub.add_parser("search", help="search high-level wording against source map")
    p.add_argument("query", help="high-level support topic, not private personal details")
    p.add_argument("--limit", type=int, default=5, help="max matches (default 5)")
    p.add_argument("--json", action="store_true", help="emit JSON")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("show", help="show one source by id")
    p.add_argument("source_id", help="source id from sources/search")
    p.add_argument("--json", action="store_true", help="emit JSON")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("pathways", help="list routing pathways")
    p.add_argument("--json", action="store_true", help="emit JSON")
    p.set_defaults(func=cmd_pathways)

    p = sub.add_parser("pathway", help="show official sources for one routing pathway")
    p.add_argument("topic", choices=sorted(PATHWAYS), help="routing topic")
    p.add_argument("--json", action="store_true", help="emit JSON")
    p.set_defaults(func=cmd_pathway)

    p = sub.add_parser("verify", help="check official source URLs with HEAD requests")
    p.add_argument("--all", action="store_true", help="check every source URL instead of the first few")
    p.add_argument("--limit", type=int, default=3, help="number to check without --all (default 3)")
    p.add_argument("--timeout", type=int, default=10, help="network timeout seconds (default 10)")
    p.add_argument("--json", action="store_true", help="emit JSON")
    p.set_defaults(func=cmd_verify)

    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except ValueError as e:
        if getattr(args, "json", False):
            print(json.dumps({"error": "invalid_input", "message": str(e)}, indent=2), file=sys.stderr)
        else:
            print(f"nz-family-support: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
