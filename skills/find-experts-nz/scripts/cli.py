#!/usr/bin/env python3
"""find-experts-nz — discover NZ-affiliated researchers/experts by topic.

Read-only, keyless queries against the OpenAlex and ORCID public APIs.
Produces EPHEMERAL candidate shortlists for a human steward — discovery is
not consent; never treat output as a contact list. Python stdlib only.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys
import urllib.parse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "lib"))
import nzfetch  # noqa: E402

OPENALEX = "https://api.openalex.org"
CROSSREF = "https://api.crossref.org"
ORCID_API = "https://pub.orcid.org/v3.0"
ORCID_RE = re.compile(r"(\d{4}-\d{4}-\d{4}-\d{3}[0-9X])", re.IGNORECASE)

MAILTO = os.environ.get("OPENALEX_MAILTO", "")

# Country code -> substrings that identify the country in a free-text
# affiliation string (Crossref has no country code, only affiliation names).
COUNTRY_NAMES = {
    "NZ": ["new zealand", "aotearoa"],
    "AU": ["australia"],
    "GB": ["united kingdom", "england", "scotland", "wales"],
    "US": ["united states", "usa", " u.s.a", " u.s."],
}


def die(msg: str, code: int = 1) -> None:
    print(json.dumps({"error": msg}), file=sys.stderr)
    sys.exit(code)


def fetch_json(url: str, headers: dict | None = None):
    try:
        return nzfetch.fetch_json(url, headers=headers)
    except nzfetch.Blocked as e:
        die(f"network error: upstream_blocked: {e}", 2)
    except nzfetch.FetchError as e:
        die(f"network error: upstream_unavailable: {e}", 2)


def openalex_url(path: str, params: dict) -> str:
    if MAILTO:
        params = {**params, "mailto": MAILTO}
    return f"{OPENALEX}{path}?{urllib.parse.urlencode(params)}"


def norm_orcid(raw: str) -> str:
    m = ORCID_RE.search(raw)
    if not m:
        die(f"not a valid ORCID iD: {raw}")
    return m.group(1).upper()


def author_ref(raw: str) -> str:
    """Accept an OpenAlex author id (A123..., or full URL) or an ORCID iD."""
    raw = raw.strip()
    m = ORCID_RE.search(raw)
    if m and "openalex" not in raw.lower():
        return f"orcid:{m.group(1).upper()}"
    tail = raw.rstrip("/").rsplit("/", 1)[-1]
    if re.fullmatch(r"[Aa]\d+", tail):
        return tail.upper()
    die(f"not an OpenAlex author id or ORCID iD: {raw}")
    return ""  # unreachable


# ---------------------------------------------------------------- search


def authorship_is_country(auth: dict, country: str) -> bool:
    for inst in auth.get("institutions") or []:
        if (inst.get("country_code") or "").upper() == country:
            return True
    return country in [c.upper() for c in (auth.get("countries") or [])]


def name_key(name: str) -> str:
    """Dedup key across sources: first + last multi-letter token, lowercased.

    Merges "Philip J. Lester" and "Philip Lester" -> ("philip","lester").
    Best-effort — initials-only or reordered names may not merge.
    """
    toks = [t for t in re.sub(r"[.\-]", " ", (name or "").lower()).split() if len(t) > 1]
    if not toks:
        return (name or "").lower().strip()
    return f"{toks[0]} {toks[-1]}" if len(toks) > 1 else toks[0]


def new_expert(name: str) -> dict:
    return {
        "openalex_id": None,
        "name": name,
        "orcid": None,
        "institutions": [],
        "matching_works": 0,
        "latest_year": 0,
        "sample_works": [],
        "sources": [],
    }


def add_work(e: dict, title, year, doi, insts, source):
    e["matching_works"] += 1
    if source not in e["sources"]:
        e["sources"].append(source)
    e["latest_year"] = max(e["latest_year"], year or 0)
    for nm in insts:
        if nm and nm not in e["institutions"]:
            e["institutions"].append(nm)
    if len(e["sample_works"]) < 3 and title:
        e["sample_works"].append({"title": title, "year": year, "doi": doi})


def openalex_experts(args) -> dict:
    filters = [f"authorships.institutions.country_code:{args.country}"]
    if args.since:
        filters.append(f"from_publication_date:{args.since}-01-01")
    if args.topic_id:
        filters.append(f"primary_topic.id:{args.topic_id}")
    if getattr(args, "institution", None):
        ids = "|".join(i.rstrip("/").rsplit("/", 1)[-1].upper() for i in args.institution.split(","))
        filters.append(f"authorships.institutions.id:{ids}")
    if getattr(args, "org_type", None):
        filters.append(f"authorships.institutions.type:{args.org_type}")
    params = {
        "filter": ",".join(filters),
        "per-page": str(min(max(args.sample, 1), 200)),
        "select": "id,display_name,publication_year,doi,relevance_score,authorships",
    }
    if args.topic:
        params["search"] = args.topic
        params["sort"] = "relevance_score:desc"
    else:
        params["sort"] = "publication_date:desc"
    works = fetch_json(openalex_url("/works", params)).get("results", [])
    experts: dict[str, dict] = {}
    for work in works:
        for auth in work.get("authorships", []):
            if not authorship_is_country(auth, args.country):
                continue
            a = auth.get("author") or {}
            if not a.get("display_name"):
                continue
            e = experts.setdefault(name_key(a["display_name"]), new_expert(a["display_name"]))
            e["openalex_id"] = e["openalex_id"] or a.get("id")
            e["orcid"] = e["orcid"] or a.get("orcid")
            insts = [i.get("display_name") for i in (auth.get("institutions") or [])]
            add_work(e, work.get("display_name"), work.get("publication_year"),
                     work.get("doi"), insts, "openalex")
    return experts


def crossref_experts(args) -> dict:
    # Crossref has no country code; filter authors by affiliation string.
    markers = COUNTRY_NAMES.get(args.country.upper(), [args.country.lower()])
    params = {
        "rows": str(min(max(args.sample, 1), 200)),
        "select": "title,author,DOI,published",
        "sort": "relevance" if args.topic else "published",
        "order": "desc",
    }
    if args.topic:
        params["query.bibliographic"] = args.topic
    if args.since:
        params["filter"] = f"from-pub-date:{args.since}-01-01"
    if MAILTO:
        params["mailto"] = MAILTO
    url = f"{CROSSREF}/works?{urllib.parse.urlencode(params)}"
    items = (fetch_json(url).get("message") or {}).get("items", [])
    experts: dict[str, dict] = {}
    for work in items:
        title = (work.get("title") or [None])[0]
        year = None
        parts = ((work.get("published") or {}).get("date-parts") or [[None]])
        if parts and parts[0]:
            year = parts[0][0]
        for a in work.get("author") or []:
            affs = [x.get("name", "") for x in (a.get("affiliation") or [])]
            aff_blob = " ; ".join(affs).lower()
            if not any(m in aff_blob for m in markers):
                continue
            full = " ".join(filter(None, [a.get("given"), a.get("family")])).strip()
            if not full:
                continue
            e = experts.setdefault(name_key(full), new_expert(full))
            oid = a.get("ORCID")
            if oid and not e["orcid"]:
                e["orcid"] = oid
            add_work(e, title, year, work.get("DOI"), affs, "crossref")
    return experts


def merge_experts(*maps) -> dict:
    merged: dict[str, dict] = {}
    for m in maps:
        for key, e in m.items():
            if key not in merged:
                merged[key] = e
                continue
            t = merged[key]
            t["openalex_id"] = t["openalex_id"] or e["openalex_id"]
            t["orcid"] = t["orcid"] or e["orcid"]
            t["matching_works"] += e["matching_works"]
            t["latest_year"] = max(t["latest_year"], e["latest_year"])
            for nm in e["institutions"]:
                if nm not in t["institutions"]:
                    t["institutions"].append(nm)
            for s in e["sources"]:
                if s not in t["sources"]:
                    t["sources"].append(s)
            for w in e["sample_works"]:
                if len(t["sample_works"]) < 3:
                    t["sample_works"].append(w)
    return merged


def cmd_search(args) -> None:
    sources = ["openalex", "crossref"] if args.source == "both" else [args.source]
    if args.topic_id and "crossref" in sources and args.source != "openalex":
        print("Note: --topic-id is OpenAlex-only; Crossref uses free-text topic.",
              file=sys.stderr)
    inst_filter = args.institution or args.org_type
    if inst_filter and "crossref" in sources:
        sources = [s for s in sources if s != "crossref"]
        print("Note: --institution/--org-type are OpenAlex-only; using OpenAlex.",
              file=sys.stderr)
    maps = []
    if "openalex" in sources:
        maps.append(openalex_experts(args))
    if "crossref" in sources:
        if not args.topic:
            print("Note: Crossref needs a free-text topic; skipping Crossref.",
                  file=sys.stderr)
        else:
            maps.append(crossref_experts(args))
    experts = merge_experts(*maps)

    ranked = sorted(
        experts.values(),
        key=lambda e: (len(e["sources"]), e["matching_works"], e["latest_year"]),
        reverse=True,
    )[: args.limit]

    out = {
        "kind": "expert-search",
        "note": "Ephemeral candidate shortlist from public scholarly data. "
        "Discovery is not consent — do not store or bulk-contact.",
        "topic": args.topic,
        "topic_id": args.topic_id,
        "country": args.country,
        "since": args.since,
        "sources_used": sources,
        "count": len(ranked),
        "experts": ranked,
    }
    if args.json:
        print(json.dumps(out, indent=2))
        return
    if not ranked:
        print("No matching authors found. Try a broader topic or `topics` to refine.")
        return
    print(f"Candidate experts for {args.topic or args.topic_id!r} "
          f"({args.country}, since {args.since}, sources: {'+'.join(sources)}):\n")
    for i, e in enumerate(ranked, 1):
        insts = "; ".join(e["institutions"]) or "(no listed institution)"
        orcid = f"  ORCID {e['orcid'].rsplit('/', 1)[-1]}" if e["orcid"] else ""
        src = "+".join(e["sources"])
        oid = f"  {e['openalex_id']}" if e["openalex_id"] else ""
        print(f"{i:2}. {e['name']} — {insts}")
        print(f"    {e['matching_works']} matching works, latest {e['latest_year']}"
              f"  [{src}]{oid}{orcid}")
        for w in e["sample_works"][:2]:
            print(f"      - {w['title']} ({w['year']})")
    print("\nNote: ephemeral shortlist from public data — discovery is not consent.")


# ---------------------------------------------------------------- author


def cmd_author(args) -> None:
    ref = author_ref(args.id)
    data = fetch_json(openalex_url(f"/authors/{ref}", {}))
    out = {
        "kind": "author",
        "openalex_id": data.get("id"),
        "name": data.get("display_name"),
        "orcid": data.get("orcid"),
        "works_count": data.get("works_count"),
        "cited_by_count": data.get("cited_by_count"),
        "h_index": (data.get("summary_stats") or {}).get("h_index"),
        "affiliations": [
            {
                "institution": (a.get("institution") or {}).get("display_name"),
                "country": (a.get("institution") or {}).get("country_code"),
                "years": a.get("years", [])[:1] + a.get("years", [])[-1:],
            }
            for a in (data.get("affiliations") or [])[:5]
        ],
        "topics": [
            {"name": t.get("display_name"), "count": t.get("count")}
            for t in (data.get("topics") or [])[:8]
        ],
    }
    if args.works:
        aid = (data.get("id") or "").rstrip("/").rsplit("/", 1)[-1]
        wdata = fetch_json(
            openalex_url(
                "/works",
                {
                    "filter": f"author.id:{aid}",
                    "sort": "publication_date:desc",
                    "per-page": str(min(args.works, 25)),
                    "select": "display_name,publication_year,doi,primary_topic",
                },
            )
        )
        out["recent_works"] = [
            {
                "title": w.get("display_name"),
                "year": w.get("publication_year"),
                "doi": w.get("doi"),
                "topic": (w.get("primary_topic") or {}).get("display_name"),
            }
            for w in wdata.get("results", [])
        ]
    if args.json:
        print(json.dumps(out, indent=2))
        return
    print(f"{out['name']}  ({out['openalex_id']})")
    if out["orcid"]:
        print(f"ORCID: {out['orcid']}")
    print(f"Works: {out['works_count']}  Citations: {out['cited_by_count']}  "
          f"h-index: {out['h_index']}")
    for a in out["affiliations"]:
        yrs = "–".join(str(y) for y in a["years"]) if a["years"] else ""
        print(f"  Affiliation: {a['institution']} ({a['country']}) {yrs}")
    if out["topics"]:
        print("  Topics: " + ", ".join(t["name"] for t in out["topics"] if t["name"]))
    for w in out.get("recent_works", []):
        print(f"  - {w['title']} ({w['year']})")


# ---------------------------------------------------------------- orcid


def _org(summary: dict) -> dict:
    org = summary.get("organization") or {}
    start = summary.get("start-date") or {}
    end = summary.get("end-date") or {}

    def year(d):
        return ((d or {}).get("year") or {}).get("value")

    return {
        "role": summary.get("role-title"),
        "organisation": org.get("name"),
        "city": (org.get("address") or {}).get("city"),
        "country": (org.get("address") or {}).get("country"),
        "start": year(start),
        "end": year(end),
    }


def cmd_orcid(args) -> None:
    oid = norm_orcid(args.id)
    data = fetch_json(f"{ORCID_API}/{oid}/record", headers={"Accept": "application/json"})
    person = data.get("person") or {}
    name = person.get("name") or {}
    acts = data.get("activities-summary") or {}
    employments = []
    for group in ((acts.get("employments") or {}).get("affiliation-group") or []):
        for s in group.get("summaries") or []:
            emp = s.get("employment-summary")
            if emp:
                employments.append(_org(emp))
    keywords = [
        k.get("content")
        for k in ((person.get("keywords") or {}).get("keyword") or [])
        if k.get("content")
    ]
    out = {
        "kind": "orcid-record",
        "orcid": oid,
        "name": " ".join(
            filter(
                None,
                [
                    ((name.get("given-names") or {}).get("value")),
                    ((name.get("family-name") or {}).get("value")),
                ],
            )
        )
        or None,
        "biography": ((person.get("biography") or {}).get("content")),
        "keywords": keywords,
        "employments": employments[:6],
    }
    if args.json:
        print(json.dumps(out, indent=2))
        return
    print(f"{out['name'] or '(name not public)'}  ORCID {oid}")
    if out["biography"]:
        print(f"  Bio: {out['biography'][:300]}")
    if keywords:
        print("  Keywords: " + ", ".join(keywords))
    for e in out["employments"]:
        span = f"{e['start'] or '?'}–{e['end'] or 'present'}"
        print(f"  {e['role'] or 'Role n/a'} — {e['organisation']} ({e['country']}) {span}")


# ---------------------------------------------------------------- institutions


def cmd_institutions(args) -> None:
    filters = [f"country_code:{args.country}"]
    if args.type:
        filters.append(f"type:{args.type}")
    params = {
        "search": args.query,
        "filter": ",".join(filters),
        "per-page": str(args.limit),
        "select": "id,display_name,type,works_count,homepage_url",
    }
    data = fetch_json(openalex_url("/institutions", params))
    results = [
        {
            "id": r.get("id", "").rstrip("/").rsplit("/", 1)[-1],
            "name": r.get("display_name"),
            "type": r.get("type"),
            "works_count": r.get("works_count"),
            "homepage": r.get("homepage_url"),
        }
        for r in data.get("results", [])
    ]
    out = {
        "kind": "institutions",
        "query": args.query,
        "country": args.country,
        "count": len(results),
        "institutions": results,
    }
    if args.json:
        print(json.dumps(out, indent=2))
        return
    if not results:
        print("No matching institutions found.")
        return
    for r in results:
        print(f"{r['id']}  [{r['type']}]  {r['name']}  ({r['works_count']} works)")
    print("\nPass an id to `search --institution <id>` to find its experts on a topic.")


# ---------------------------------------------------------------- topics


def cmd_topics(args) -> None:
    data = fetch_json(
        openalex_url("/topics", {"search": args.query, "per-page": str(args.limit)})
    )
    results = [
        {
            "id": t.get("id", "").rstrip("/").rsplit("/", 1)[-1],
            "name": t.get("display_name"),
            "subfield": (t.get("subfield") or {}).get("display_name"),
            "field": (t.get("field") or {}).get("display_name"),
            "works_count": t.get("works_count"),
        }
        for t in data.get("results", [])
    ]
    out = {"kind": "topics", "query": args.query, "count": len(results), "topics": results}
    if args.json:
        print(json.dumps(out, indent=2))
        return
    for t in results:
        print(f"{t['id']}  {t['name']}  [{t['subfield']} / {t['field']}]  "
              f"{t['works_count']} works")


# ---------------------------------------------------------------- main


def main() -> None:
    p = argparse.ArgumentParser(
        prog="find-experts-nz",
        description="Discover NZ-affiliated researchers/experts by topic "
        "(OpenAlex + Crossref + ORCID, public data, ephemeral shortlists only).",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("search", help="ranked NZ-affiliated authors for a topic")
    s.add_argument("topic", nargs="?", default=None, help="free-text topic query")
    s.add_argument("--source", choices=["openalex", "crossref", "both"], default="both",
                   help="scholarly source(s) to search (default both)")
    s.add_argument("--topic-id", help="OpenAlex topic id (from `topics`), e.g. T10662")
    s.add_argument("--institution", help="restrict to OpenAlex institution id(s), "
                   "comma-separated (from `institutions`). OpenAlex-only.")
    s.add_argument("--org-type", choices=["education", "company", "government",
                   "facility", "nonprofit", "healthcare", "other"],
                   help="restrict to institutions of this type, e.g. company. OpenAlex-only.")
    s.add_argument("--country", default="NZ", help="ISO country code (default NZ)")
    s.add_argument("--since", type=int, default=2016, help="earliest publication year")
    s.add_argument("--sample", type=int, default=100, help="works to sample (max 200)")
    s.add_argument("--limit", type=int, default=10, help="experts to return")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_search)

    ins = sub.add_parser("institutions",
                         help="resolve NZ universities/CRIs/companies to OpenAlex ids")
    ins.add_argument("query")
    ins.add_argument("--country", default="NZ", help="ISO country code (default NZ)")
    ins.add_argument("--type", choices=["education", "company", "government",
                     "facility", "nonprofit", "healthcare", "other"],
                     help="filter by institution type, e.g. company")
    ins.add_argument("--limit", type=int, default=10)
    ins.add_argument("--json", action="store_true")
    ins.set_defaults(func=cmd_institutions)

    a = sub.add_parser("author", help="author profile by OpenAlex id or ORCID")
    a.add_argument("id", help="OpenAlex author id (A…) or ORCID iD")
    a.add_argument("--works", type=int, default=0, help="include N recent works")
    a.add_argument("--json", action="store_true")
    a.set_defaults(func=cmd_author)

    o = sub.add_parser("orcid", help="public ORCID record (employment, keywords)")
    o.add_argument("id", help="ORCID iD or URL")
    o.add_argument("--json", action="store_true")
    o.set_defaults(func=cmd_orcid)

    t = sub.add_parser("topics", help="resolve a fuzzy topic to OpenAlex topic ids")
    t.add_argument("query")
    t.add_argument("--limit", type=int, default=10)
    t.add_argument("--json", action="store_true")
    t.set_defaults(func=cmd_topics)

    args = p.parse_args()
    if args.cmd == "search" and not args.topic and not args.topic_id:
        p.error("search needs a topic or --topic-id")
    args.func(args)


if __name__ == "__main__":
    main()
