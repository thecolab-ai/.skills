#!/usr/bin/env python3
"""find-experts-nz — discover NZ experts across public sources.

Read-only, keyless queries across scholarly graphs (OpenAlex, Crossref),
Wikidata, ORCID, and university "Find an Expert" directories. Produces
EPHEMERAL candidate shortlists for a human steward — discovery is not consent;
never treat output as a contact list. Python stdlib only.
"""

from __future__ import annotations

import argparse
import html
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


def fetch_json(url: str, **kw):
    try:
        return nzfetch.fetch_json(url, **kw)
    except nzfetch.Blocked as e:
        die(f"network error: upstream_blocked: {e}", 2)
    except nzfetch.FetchError as e:
        die(f"network error: upstream_unavailable: {e}", 2)


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
        "fields": [],
        "profile_url": None,
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


WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"
_WD_STOP = {"care", "study", "studies", "research", "zealand", "health", "with",
            "from", "that", "this", "using", "based", "into", "over"}


def wikidata_experts(args) -> dict:
    """NZ-linked academics from Wikidata whose field-of-work matches the topic.

    Notable-only (people with a Wikidata item), but uniform across every
    institution — useful where a portal has no API. NZ-only (P27 or NZ employer).
    """
    if (args.country or "NZ").upper() != "NZ":
        print("Note: Wikidata source is NZ-only; skipping.", file=sys.stderr)
        return {}
    toks = [t for t in re.findall(r"[a-z]{5,}", (args.topic or "").lower())
            if t not in _WD_STOP]
    if not toks:
        toks = [t for t in re.findall(r"[a-z]{4,}", (args.topic or "").lower())
                if t not in _WD_STOP]
    if not toks:
        return {}
    toks = toks[:4]
    filt = " || ".join(f'CONTAINS(LCASE(?fl),"{t}")' for t in toks)
    query = f"""
SELECT DISTINCT ?person ?personLabel ?fieldLabel ?employerLabel ?article WHERE {{
  ?person wdt:P106 ?occ . VALUES ?occ {{ wd:Q1650915 wd:Q3400985 wd:Q1622272 wd:Q901 }}
  {{ ?person wdt:P27 wd:Q664 }} UNION {{ ?person wdt:P108 ?emp . ?emp wdt:P17 wd:Q664 }}
  ?person wdt:P101 ?field . ?field rdfs:label ?fl . FILTER(LANG(?fl)="en" && ({filt}))
  OPTIONAL {{ ?person wdt:P108 ?employer . ?employer wdt:P17 wd:Q664 }}
  OPTIONAL {{ ?article schema:about ?person ; schema:isPartOf <https://en.wikipedia.org/> }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}} LIMIT {min(args.sample, 50)}"""
    url = f"{WIKIDATA_SPARQL}?{urllib.parse.urlencode({'query': query, 'format': 'json'})}"
    try:
        # Soft-fail: WDQS rate-limits aggressively, and a Wikidata block must not
        # abort a multi-source (--source all) run. nzfetch owns the User-Agent /
        # fingerprint; we pass only the semantic Accept header.
        data = nzfetch.fetch_json(
            url, headers={"accept": "application/sparql-results+json"})
    except nzfetch.FetchError as e:
        print(f"Note: Wikidata unavailable (skipped): {e}", file=sys.stderr)
        return {}
    experts: dict[str, dict] = {}
    for b in (data.get("results") or {}).get("bindings", []):
        name = (b.get("personLabel") or {}).get("value")
        if not name or name.startswith("Q"):
            continue
        e = experts.setdefault(name_key(name), new_expert(name))
        if "wikidata" not in e["sources"]:
            e["sources"].append("wikidata")
        e["matching_works"] += 1
        emp = (b.get("employerLabel") or {}).get("value")
        if emp and emp not in e["institutions"]:
            e["institutions"].append(emp)
        fld = (b.get("fieldLabel") or {}).get("value")
        if fld and fld not in e["fields"]:
            e["fields"].append(fld)
        art = (b.get("article") or {}).get("value")
        if art and not e["profile_url"]:
            e["profile_url"] = art
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
            t["profile_url"] = t["profile_url"] or e.get("profile_url")
            t["matching_works"] += e["matching_works"]
            t["latest_year"] = max(t["latest_year"], e["latest_year"])
            for nm in e["institutions"]:
                if nm not in t["institutions"]:
                    t["institutions"].append(nm)
            for f in e.get("fields", []):
                if f not in t["fields"]:
                    t["fields"].append(f)
            for s in e["sources"]:
                if s not in t["sources"]:
                    t["sources"].append(s)
            for w in e["sample_works"]:
                if len(t["sample_works"]) < 3:
                    t["sample_works"].append(w)
    return merged


def cmd_search(args) -> None:
    if args.source == "both":
        sources = ["openalex", "crossref"]
    elif args.source == "all":
        sources = ["openalex", "crossref", "wikidata"]
    else:
        sources = [args.source]
    if args.topic_id and "crossref" in sources and args.source != "openalex":
        print("Note: --topic-id is OpenAlex-only; Crossref uses free-text topic.",
              file=sys.stderr)
    inst_filter = args.institution or args.org_type
    if inst_filter:
        dropped = [s for s in ("crossref", "wikidata") if s in sources]
        if dropped:
            sources = [s for s in sources if s not in dropped]
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
    if "wikidata" in sources:
        if not args.topic:
            print("Note: Wikidata needs a free-text topic; skipping Wikidata.",
                  file=sys.stderr)
        else:
            maps.append(wikidata_experts(args))
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
        if e.get("fields"):
            print(f"    Fields: {', '.join(e['fields'][:6])}")
        for w in e["sample_works"][:2]:
            print(f"      - {w['title']} ({w['year']})")
        if e.get("profile_url"):
            print(f"    {e['profile_url']}")
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


# ---------------------------------------------------------------- directories


AUCKLAND_BASE = "https://profiles.auckland.ac.nz"
MASSEY_BASE = "https://www.massey.ac.nz"
MASSEY_API = (MASSEY_BASE + "/massey/app_templates/_pagetemplates/pagelets/search/"
              "people/profile_solr_native/profiles_solr_native.cfc")


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
                           "department": r.get("department") or r.get("college")}],
            "expertise": html_to_lines(r.get("interests")),
            "profile_url": (MASSEY_BASE + path) if path.startswith("/") else (path or None),
            "university": "Massey University",
        })  # note: email/phone/extension fields intentionally NOT collected
    total = (((data.get("response") or {}).get("numFound")) or len(docs))
    return experts, total


DIRECTORIES = {
    "auckland": {"name": "University of Auckland", "method": "api",
                 "portal": AUCKLAND_BASE, "search": auckland_search},
    "massey": {"name": "Massey University", "method": "api",
               "portal": MASSEY_BASE + "/massey/expertise/profile.cfm",
               "search": massey_search},
    # Roadmap — each needs its portal's public JSON search endpoint identified
    # (see references/guide.md, "adding a university"):
    "otago": {"name": "University of Otago", "method": "todo",
              "portal": "https://www.otago.ac.nz/profiles"},
    "vuw": {"name": "Te Herenga Waka — Victoria University of Wellington",
            "method": "todo", "portal": "https://people.wgtn.ac.nz"},
    "canterbury": {"name": "University of Canterbury", "method": "todo",
                   "portal": "https://researchprofiles.canterbury.ac.nz"},
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
        for s, a in DIRECTORIES.items()
    ]
    if args.json:
        print(json.dumps({"kind": "universities", "count": len(rows),
                          "universities": rows}, indent=2))
        return
    for r in rows:
        ready = "api" if r["method"] == "api" else r["method"]
        print(f"{r['slug']:12} [{ready:5}] {r['name']}")
    print("\nOnly 'api' portals are searchable now; others are roadmap "
          "(references/guide.md).")


def cmd_directory(args) -> None:
    adapter = DIRECTORIES.get(args.uni)
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
    print(f"Experts for {args.query!r} — {adapter['name']} ({len(experts)} of {total}):\n")
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


# ---------------------------------------------------------------- registers
#
# Professional / practitioner registers — the tier scholarly sources miss.
# Every adapter returns records shaped {name, role, organisation, expertise[],
# status, location, profile_url, register} and NEVER emits contact details
# (email/phone/address are dropped even where the source exposes them).


def _strip_html(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(_TAG_RE.sub("", s or ""))).strip()


def register_record(**kw) -> dict:
    base = {"name": None, "role": None, "organisation": None, "expertise": [],
            "status": None, "location": None, "profile_url": None, "register": None}
    base.update(kw)
    return base


def pgdb_search(query: str, limit: int) -> tuple[list, int]:
    """Plumbers, Gasfitters & Drainlayers Board — public register (by name)."""
    data = fetch_json(
        f"https://pgdb-api.pgdb.co.nz/v1/Search/PublicRegister?name={urllib.parse.quote(query)}",
        headers={"accept": "application/json"})
    contacts = data.get("publicRegisterContacts") or []
    out = []
    for r in contacts[:limit]:
        regs = r.get("registrations") or []
        types = [g.get("registrationTypeName") for g in regs if g.get("registrationTypeName")]
        active = [g for g in regs if g.get("registrationStatusCode") == "ACTV"]
        out.append(register_record(
            name=r.get("fullName"),
            role="; ".join(dict.fromkeys(types)) or "Plumber/Gasfitter/Drainlayer",
            organisation=None,
            expertise=list(dict.fromkeys(types)),
            status="Active" if active else (regs[0].get("registrationStatusName") if regs else None),
            location=r.get("businessCity") or r.get("businessSuburbTown"),
            profile_url=r.get("url") or "https://www2.pgdb.co.nz/public-register",
            register="PGDB (Plumbers, Gasfitters & Drainlayers Board)",
        ))  # publicPhone/publicEmail/address intentionally dropped
    return out, len(contacts)


def legalaid_search(query: str, limit: int) -> tuple[list, int]:
    """Ministry of Justice legal-aid lawyers — one JSON roster, filtered here."""
    data = fetch_json(
        "https://www.justice.govt.nz/courts/going-to-court/legal-aid/get-legal-aid/"
        "legal-aid-lawyer-finder/roster/",
        headers={"accept": "application/json", "x-requested-with": "XMLHttpRequest"})
    lawyers = data.get("lawyers") or []
    # lawyer.matterTypes reference the taxonomy by hash — resolve to readable names.
    hashmap = {m.get("hash"): (m.get("mappedColumn") or m.get("matterType"))
               for m in (data.get("matterTypes") or []) if m.get("hash")}
    q = query.lower().strip()
    out = []
    matched = 0
    for r in lawyers:
        matters = [hashmap.get(h, h) for h in (r.get("matterTypes") or [])]
        hay = " ".join([r.get("name") or "", r.get("firmName") or "",
                        " ".join(matters), " ".join(r.get("languages") or [])]).lower()
        if q and q not in hay:
            continue
        matched += 1
        if len(out) >= limit:
            continue
        loc = (r.get("locations") or [{}])[0]
        out.append(register_record(
            name=r.get("name"),
            role=f"Legal-aid lawyer ({r.get('providerType')})" if r.get("providerType") else "Legal-aid lawyer",
            organisation=r.get("firmName"),
            expertise=matters,
            status="Legal aid provider",
            location="; ".join(filter(None, [loc.get("city"), loc.get("region")])) or None,
            profile_url=None,
            register="MoJ Legal Aid Lawyer Finder",
        ))  # locations[].phoneNumber intentionally dropped
    return out, matched


def irpnz_search(query: str, limit: int) -> tuple[list, int]:
    """Institute of Rural Professionals — 'find a member' (paginated, filtered here)."""
    base = "https://www.irpnz.co.nz/DataFilter?Action=AjaxList&DataFilter_id=145"
    q = query.lower().strip()
    out, scanned = [], 0
    first = fetch_json(f"{base}&Page=1", headers={"accept": "application/json"})
    total_pages = first.get("TotalPages") or 1
    total_items = first.get("TotalItems") or 0
    page, data = 1, first
    while True:
        for r in data.get("Items") or []:
            scanned += 1
            hay = " ".join([r.get("PersonProfile_title") or "", r.get("Person_jobtitle") or "",
                            r.get("Company_name") or "", r.get("PersonProfile_subtitle") or ""]).lower()
            if q and q not in hay:
                continue
            view = r.get("PersonProfile_urlview") or ""
            out.append(register_record(
                name=r.get("PersonProfile_title"),
                role=r.get("Person_jobtitle"),
                organisation=r.get("Company_name"),
                expertise=[x for x in [r.get("Person_jobtitle"), r.get("PersonProfile_subtitle")] if x],
                status="IRPNZ member",
                location=None,
                profile_url=f"https://www.irpnz.co.nz/{view}" if view else None,
                register="Institute of Rural Professionals (IRPNZ)",
            ))  # Person_mail / phone intentionally dropped
            if len(out) >= limit:
                return out, total_items
        page += 1
        if page > total_pages:
            break
        data = fetch_json(f"{base}&Page={page}", headers={"accept": "application/json"})
    return out, total_items


_MCNZ_TILE = re.compile(r'<a href="([^"]+)"[^>]*title-link[^>]*>(.*?)</a>', re.S)
_MCNZ_FIELD = re.compile(r'b-doctor-detail__content-(\w+)">(.*?)</li>', re.S)


def mcnz_search(query: str, limit: int) -> tuple[list, int]:
    """Medical Council of NZ — register of doctors (HTML-in-JSON, paginated)."""
    base = ("https://www.mcnz.org.nz/registration/register-of-doctors/"
            f"?keyword={urllib.parse.quote(query)}&location=&area=&status=")
    out, start, total = [], 0, 0
    while len(out) < limit:
        data = fetch_json(f"{base}&start={start}",
                          headers={"accept": "application/json", "x-requested-with": "XMLHttpRequest"})
        upd = (data.get("content") or {}).get("update") or {}
        summ = _strip_html(upd.get("#search-results-summary") or "")
        m = re.search(r"([\d,]+)\s+doctor", summ)
        if m:
            total = int(m.group(1).replace(",", ""))
        wrap = upd.get("#search-results-wrap") or ""
        tiles = wrap.split("b-search-register-tile b-grid-list__list-item")[1:]
        if not tiles:
            break
        for tile in tiles:
            am = _MCNZ_TILE.search(tile)
            if not am:
                continue
            fields = {k: _strip_html(v) for k, v in _MCNZ_FIELD.findall(tile)}
            href = am.group(1)
            out.append(register_record(
                name=_strip_html(am.group(2)),
                role="Doctor",
                organisation=None,
                expertise=[fields["speciality"]] if fields.get("speciality") else [],
                status=fields.get("status"),
                location=fields.get("location"),
                profile_url=("https://www.mcnz.org.nz" + href) if href.startswith("/") else href,
                register="Medical Council of NZ — Register of Doctors",
            ))
            if len(out) >= limit:
                break
        start += 20
        if start >= (total or 0):
            break
    return out, total


REGISTERS = {
    "pgdb": {"name": "PGDB — plumbers, gasfitters, drainlayers", "reaches": "practitioners",
             "query": "name", "search": pgdb_search},
    "legalaid": {"name": "MoJ Legal Aid lawyers", "reaches": "practitioners",
                 "query": "name / practice area", "search": legalaid_search},
    "irpnz": {"name": "IRPNZ — rural professionals / farm advisers", "reaches": "practitioners",
              "query": "name / role / firm", "search": irpnz_search},
    "mcnz": {"name": "MCNZ — register of doctors", "reaches": "practitioners",
             "query": "name", "search": mcnz_search},
}


def cmd_registers(args) -> None:
    rows = [{"slug": s, "name": a["name"], "reaches": a["reaches"], "query": a["query"]}
            for s, a in REGISTERS.items()]
    if args.json:
        print(json.dumps({"kind": "registers", "count": len(rows), "registers": rows}, indent=2))
        return
    for r in rows:
        print(f"{r['slug']:10} {r['name']}  (query: {r['query']})")
    print("\nProfessional registers reach practitioners scholarly sources miss. "
          "Contact details are never collected.")


def cmd_register(args) -> None:
    reg = REGISTERS.get(args.which)
    if not reg:
        die(f"unknown register '{args.which}'. Run `registers` to list slugs.")
    experts, total = reg["search"](args.query, args.limit)
    out = {
        "kind": "register-experts",
        "note": "Ephemeral candidate shortlist from a public register. Discovery is "
        "not consent — do not store or bulk-contact. Contact details not collected.",
        "register": reg["name"],
        "query": args.query,
        "total_available": total,
        "count": len(experts),
        "experts": experts,
    }
    if args.json:
        print(json.dumps(out, indent=2))
        return
    if not experts:
        print(f"No matches for {args.query!r} in {reg['name']}.")
        return
    print(f"{reg['name']} — {args.query!r} ({len(experts)} of {total}):\n")
    for i, e in enumerate(experts, 1):
        org = f" — {e['organisation']}" if e["organisation"] else ""
        print(f"{i:2}. {e['name']}{org}")
        line = "; ".join(filter(None, [e["role"], e["location"], e["status"]]))
        if line:
            print(f"    {line}")
        if e["expertise"]:
            print(f"    Expertise: {', '.join(e['expertise'][:8])}")
        if e["profile_url"]:
            print(f"    {e['profile_url']}")
    print("\nNote: ephemeral shortlist from a public register — discovery is not consent.")


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
        description="Discover NZ experts across public sources — scholarly graphs "
        "(OpenAlex + Crossref + Wikidata + ORCID) and university directories. "
        "Ephemeral shortlists only; discovery is not consent.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("search", help="ranked NZ-affiliated authors for a topic")
    s.add_argument("topic", nargs="?", default=None, help="free-text topic query")
    s.add_argument("--source",
                   choices=["openalex", "crossref", "wikidata", "both", "all"],
                   default="both",
                   help="source(s): both=openalex+crossref (default), "
                   "all=+wikidata (notable NZ experts, any institution)")
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

    d = sub.add_parser("directory",
                       help="search a university 'Find an Expert' directory")
    d.add_argument("query", help="free-text topic / expertise / name")
    d.add_argument("--uni", default="auckland",
                   help="university slug (default auckland; run `unis` to list)")
    d.add_argument("--limit", type=int, default=10, help="experts to return")
    d.add_argument("--json", action="store_true")
    d.set_defaults(func=cmd_directory)

    u = sub.add_parser("unis", help="list supported university directories")
    u.add_argument("--json", action="store_true")
    u.set_defaults(func=cmd_unis)

    rg = sub.add_parser("register",
                        help="search a professional register (practitioners)")
    rg.add_argument("query", help="name / practice area / role")
    rg.add_argument("--which", default="pgdb",
                    help="register slug (run `registers` to list): pgdb, legalaid, irpnz, mcnz")
    rg.add_argument("--limit", type=int, default=10, help="people to return")
    rg.add_argument("--json", action="store_true")
    rg.set_defaults(func=cmd_register)

    rgs = sub.add_parser("registers", help="list supported professional registers")
    rgs.add_argument("--json", action="store_true")
    rgs.set_defaults(func=cmd_registers)

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
