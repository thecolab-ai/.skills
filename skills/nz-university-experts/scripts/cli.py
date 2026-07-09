#!/usr/bin/env python3
"""nz-university-experts — search NZ university "Find an Expert" directories.

Read-only, keyless queries against university expert-directory JSON APIs.
Returns EPHEMERAL candidate shortlists (name, title, department, expertise,
public profile URL) for a human steward — discovery is not consent, and the
output is never a contact list. Python stdlib only.

Each portal exposes a public JSON search API (e.g. University of Auckland's
/api/users) which we call directly. Universities not yet wired up are listed by
`unis` as `todo`; see references/guide.md for how to add one.
"""

from __future__ import annotations

import argparse
import html
import json
import pathlib
import re
import sys
import urllib.parse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "lib"))
import nzfetch  # noqa: E402

_TAG_RE = re.compile(r"<[^>]+>")


def html_to_lines(raw):
    """Turn an HTML snippet of <p>/<li> items into a clean list of strings."""
    if not raw:
        return []
    parts = re.split(r"</?(?:p|li|br|div)[^>]*>", raw, flags=re.IGNORECASE)
    out = []
    for p in parts:
        text = html.unescape(_TAG_RE.sub("", p)).strip()
        if text and text not in out:
            out.append(text)
    return out


def die(msg: str, code: int = 1) -> None:
    print(json.dumps({"error": msg}), file=sys.stderr)
    sys.exit(code)


def fetch_json(url, **kw):
    try:
        return nzfetch.fetch_json(url, **kw)
    except nzfetch.Blocked as e:
        die(f"network error: upstream_blocked: {e}", 2)
    except nzfetch.FetchError as e:
        die(f"network error: upstream_unavailable: {e}", 2)


# ---------------------------------------------------------------- Auckland


AUCKLAND_BASE = "https://profiles.auckland.ac.nz"


def auckland_search(query: str, limit: int) -> tuple[list, int]:
    """University of Auckland — public /api/users JSON search."""
    per_page = 25
    experts: list[dict] = []
    total = 0
    start = 0
    while len(experts) < limit:
        payload = json.dumps({
            "params": {"by": "text", "category": "user", "text": query,
                       "startFrom": start, "perPage": per_page},
            "filters": [
                {"name": n, "matchDocsWithMissingValues": True, "useValuesToFilter": False}
                for n in ("customFilterOne", "department", "tags",
                          "customFilterTwo", "customFilterThree")
            ],
        }).encode()
        data = fetch_json(
            f"{AUCKLAND_BASE}/api/users",
            data=payload, method="POST",
            headers={"content-type": "application/json", "accept": "application/json",
                     "origin": AUCKLAND_BASE,
                     "referer": f"{AUCKLAND_BASE}/search?by=text&type=user"},
        )
        page = data.get("resource") or []
        total = ((data.get("pagination") or {}).get("total")) or total
        if not page:
            break
        for r in page:
            positions = [
                {"role": p.get("position"), "department": p.get("department")}
                for p in (r.get("positions") or [])
            ]
            expertise = [
                t.get("value") for t in ((r.get("tags") or {}).get("explicit") or [])
                if t.get("value")
            ]
            slug = r.get("discoveryUrlId")
            experts.append({
                "name": r.get("firstNameLastName")
                or " ".join(filter(None, [r.get("firstName"), r.get("lastName")])),
                "title": r.get("title"),
                "positions": positions,
                "expertise": expertise,
                "profile_url": f"{AUCKLAND_BASE}/{slug}" if slug else None,
                "university": "University of Auckland",
            })
            if len(experts) >= limit:
                break
        start += per_page
        if start >= total:
            break
    return experts, total


# ---------------------------------------------------------------- Massey


MASSEY_BASE = "https://www.massey.ac.nz"
MASSEY_API = (MASSEY_BASE + "/massey/app_templates/_pagetemplates/pagelets/search/"
              "people/profile_solr_native/profiles_solr_native.cfc")


def massey_search(query: str, limit: int) -> tuple[list, int]:
    """Massey University — public Solr-backed expert search (keyword mode).

    The API returns contact details (email/phone); we deliberately drop them —
    this skill emits expertise, not a contact list.
    """
    body = urllib.parse.urlencode({
        "experts_keywords_auto_selected": "none", "experts_keywords": query,
        "experts_position_auto_selected": "none", "experts_position": "",
        "experts_college": "", "experts_department": "", "solrHost": "tur-solr1",
        "method": "getExpertsFromSolr", "radioSelect": "keywords",
    }).encode()
    data = fetch_json(
        MASSEY_API, data=body, method="POST",
        headers={"accept": "application/json, text/javascript, */*; q=0.01",
                 "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
                 "x-requested-with": "XMLHttpRequest",
                 "referer": f"{MASSEY_BASE}/massey/expertise/profile.cfm"},
    )
    docs = ((data.get("response") or {}).get("docs")) or []
    experts = []
    for r in docs[:limit]:
        path = r.get("url") or ""
        experts.append({
            "name": r.get("known_as") or r.get("last_name"),
            "title": r.get("position"),
            "positions": [{"role": r.get("position"),
                           "department": r.get("department")
                           or r.get("college")}],
            "expertise": html_to_lines(r.get("interests")),
            "profile_url": (MASSEY_BASE + path) if path.startswith("/") else (path or None),
            "university": "Massey University",
        })  # note: email/phone/extension fields intentionally NOT collected
    total = (((data.get("response") or {}).get("numFound")) or len(docs))
    return experts, total


# ---------------------------------------------------------------- registry


ADAPTERS = {
    "auckland": {
        "name": "University of Auckland",
        "method": "api",
        "portal": AUCKLAND_BASE,
        "search": auckland_search,
    },
    # Documented in references/guide.md, not yet wired up (each needs its portal's
    # public JSON search endpoint identified — see the guide's "adding a university"):
    "otago": {"name": "University of Otago", "method": "todo",
              "portal": "https://www.otago.ac.nz/profiles"},
    "vuw": {"name": "Te Herenga Waka — Victoria University of Wellington",
            "method": "todo", "portal": "https://people.wgtn.ac.nz"},
    "canterbury": {"name": "University of Canterbury", "method": "todo",
                   "portal": "https://researchprofiles.canterbury.ac.nz"},
    "massey": {"name": "Massey University", "method": "api",
               "portal": MASSEY_BASE + "/massey/expertise/profile.cfm",
               "search": massey_search},
    "aut": {"name": "Auckland University of Technology", "method": "todo",
            "portal": "https://academics.aut.ac.nz"},
    "waikato": {"name": "University of Waikato", "method": "todo",
                "portal": "https://www.waikato.ac.nz/staff-profiles"},
    "lincoln": {"name": "Lincoln University", "method": "todo",
                "portal": "https://researchers.lincoln.ac.nz"},
}


def cmd_unis(args) -> None:
    rows = [
        {"slug": s, "name": a["name"], "method": a["method"], "portal": a["portal"]}
        for s, a in ADAPTERS.items()
    ]
    if args.json:
        print(json.dumps({"kind": "universities", "count": len(rows),
                          "universities": rows}, indent=2))
        return
    for r in rows:
        ready = "✅ api" if r["method"] == "api" else f"… {r['method']}"
        print(f"{r['slug']:12} {ready:14} {r['name']}")
    print("\nOnly 'api' portals are searchable now; others are documented roadmap "
          "(references/guide.md).")


def cmd_search(args) -> None:
    adapter = ADAPTERS.get(args.uni)
    if not adapter:
        die(f"unknown university '{args.uni}'. Run `unis` to list supported slugs.")
    if adapter["method"] != "api" or "search" not in adapter:
        die(f"'{args.uni}' ({adapter['name']}) is not wired up yet "
            f"(method={adapter['method']}). Run `unis`; see references/guide.md.")
    experts, total = adapter["search"](args.query, args.limit)
    out = {
        "kind": "university-experts",
        "note": "Ephemeral candidate shortlist from a public directory. "
        "Discovery is not consent — do not store or bulk-contact.",
        "university": adapter["name"],
        "query": args.query,
        "total_available": total,
        "count": len(experts),
        "experts": experts,
    }
    if args.json:
        print(json.dumps(out, indent=2))
        return
    if not experts:
        print(f"No matches for {args.query!r} at {adapter['name']}.")
        return
    print(f"Experts for {args.query!r} — {adapter['name']} "
          f"({len(experts)} of {total}):\n")
    for i, e in enumerate(experts, 1):
        pos = "; ".join(
            f"{p['role']}, {p['department']}" if p.get("department") else (p.get("role") or "")
            for p in e["positions"]
        ) or "(no listed position)"
        print(f"{i:2}. {e['name']} — {e['title'] or ''}")
        print(f"    {pos}")
        if e["expertise"]:
            print(f"    Expertise: {', '.join(e['expertise'][:8])}")
        if e["profile_url"]:
            print(f"    {e['profile_url']}")
    print("\nNote: ephemeral shortlist from public data — discovery is not consent.")


def main() -> None:
    p = argparse.ArgumentParser(
        prog="nz-university-experts",
        description="Search NZ university expert directories (public, keyless). "
        "Ephemeral shortlists only — discovery is not consent.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("search", help="search a university's expert directory")
    s.add_argument("query", help="free-text topic / expertise / name")
    s.add_argument("--uni", default="auckland",
                   help="university slug (default auckland; run `unis` to list)")
    s.add_argument("--limit", type=int, default=10, help="experts to return")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_search)

    u = sub.add_parser("unis", help="list supported universities and their status")
    u.add_argument("--json", action="store_true")
    u.set_defaults(func=cmd_unis)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
