#!/usr/bin/env python3
"""DataForSEO CLI.

Read-only stdlib wrapper around DataForSEO v3 — SERP rank checks, keyword
research + discovery, competitor/domain analytics, backlinks, and App Store /
Play data — through a CLI that is easy for agents to script and humans to scan.
Most commands hit synchronous `live` endpoints; the App Store `appsearch` and
`appreviews` commands use async task_post/task_get and poll for a few seconds.

Auth: HTTP Basic with DATAFORSEO_LOGIN + DATAFORSEO_PASSWORD (your API
credentials from the DataForSEO dashboard, NOT your website login). Credentials
are only read inside commands that hit the API, so `--help` works without them.

Cost: every API call spends DataForSEO credits. `--limit` caps result rows.
See references/endpoints.md for approximate per-call costs.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections import Counter

BASE_URL = "https://api.dataforseo.com"
USER_AGENT = "thecolab-skills-dataforseo/1.0"
DEFAULT_TIMEOUT = 60  # Labs/backlinks live calls can be slow

# Friendly location aliases -> DataForSEO location_code.
# Full list: https://api.dataforseo.com/v3/serp/google/locations
LOCATIONS = {
    "nz": 2554,
    "us": 2840,
    "uk": 2826,
    "gb": 2826,
    "au": 2036,
    "ca": 2124,
    "ie": 2372,
    "za": 2710,
    "in": 2356,
}


def die(message, code=1):
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(code)


def env_required(name):
    value = os.environ.get(name)
    if not value:
        die(
            f"missing {name}; export DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD "
            f"(your API credentials from https://app.dataforseo.com/api-access) "
            f"before running this authenticated CLI"
        )
    return value


def env_login(primary):
    """Resolve the API login, accepting DATAFORSEO_USERNAME as an alias so a
    single set of env vars powers both this skill and the DataForSEO MCP."""
    for name in (primary, "DATAFORSEO_USERNAME"):
        value = os.environ.get(name)
        if value:
            return value
    die(
        f"missing {primary} (or DATAFORSEO_USERNAME); export your API login and "
        f"DATAFORSEO_PASSWORD (from https://app.dataforseo.com/api-access) "
        f"before running this authenticated CLI"
    )


def dig(obj, path, default=None):
    """Safely walk a dotted path through nested dicts."""
    cur = obj
    for key in path.split("."):
        if isinstance(cur, dict) and key in cur:
            cur = cur[key]
        else:
            return default
    return cur


def strip_www(domain):
    """Drop a leading 'www.' prefix. NOT str.lstrip, which strips a char set
    (e.g. 'wise.com'.lstrip('www.') -> 'ise.com')."""
    text = (domain or "").lower()
    return text[4:] if text.startswith("www.") else text


def resolve_location(value):
    text = str(value).strip().lower()
    if text.isdigit():
        return int(text)
    if text in LOCATIONS:
        return LOCATIONS[text]
    known = ", ".join(sorted(LOCATIONS))
    die(f"unknown --location '{value}'; use a numeric location_code or one of: {known}")


class DataForSEOClient:
    def __init__(self, login, password):
        token = base64.b64encode(f"{login}:{password}".encode("utf-8")).decode("ascii")
        self.auth_header = f"Basic {token}"

    def _send(self, method, path, payload=None):
        """Core HTTP call. Returns the parsed JSON envelope (unvalidated)."""
        url = f"{BASE_URL}/{path.lstrip('/')}"
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {
            "Authorization": self.auth_header,
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        }
        if body is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:500]
            if exc.code in (401, 403):
                die(
                    f"DataForSEO auth failed (HTTP {exc.code}). Check your API credentials "
                    f"(DATAFORSEO_USERNAME/LOGIN + DATAFORSEO_PASSWORD), not your website login."
                )
            die(f"DataForSEO HTTP {exc.code} for {path}: {detail}")
        except urllib.error.URLError as exc:
            die(f"DataForSEO request failed for {path}: {exc.reason}")
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            die(f"DataForSEO returned non-JSON for {path}: {exc}")

    def post(self, path, payload):
        """POST a live endpoint; validate envelope + first task; return its result list."""
        return self._first_task_result(self._send("POST", path, payload), path)

    def post_raw(self, path, payload):
        """POST and return the raw envelope (used by task_post to read the task id)."""
        return self._send("POST", path, payload)

    def get(self, path):
        """GET a task_get endpoint; return the raw envelope."""
        return self._send("GET", path)

    def _first_task_result(self, data, path):
        """Validate envelope + first task, return that task's `result` list."""
        status = data.get("status_code")
        if status != 20000:
            die(f"DataForSEO error {status} for {path}: {data.get('status_message')}")
        tasks = data.get("tasks") or []
        if not tasks:
            die(f"DataForSEO returned no tasks for {path}")
        task = tasks[0]
        tstatus = task.get("status_code")
        if tstatus != 20000:
            die(f"DataForSEO task error {tstatus} for {path}: {task.get('status_message')}")
        return task.get("result") or []


# DataForSEO task-status codes that mean "still working, keep polling".
_TASK_PENDING = {20100, 40100, 40601, 40602}


def run_task(client, base, payload, timeout=180, interval=6):
    """Submit an async App Data task (task_post) and poll task_get until ready.

    `base` is the endpoint stem, e.g. 'v3/app_data/apple/app_searches'.
    Returns the first task's `result` list, or dies on error / timeout.
    """
    posted = client.post_raw(f"{base}/task_post", payload)
    if posted.get("status_code") != 20000:
        die(f"DataForSEO error for {base}/task_post: {posted.get('status_message')}")
    tasks = posted.get("tasks") or []
    if not tasks:
        die(f"DataForSEO returned no task for {base}/task_post")
    task = tasks[0]
    if task.get("status_code") not in (20000, 20100):
        die(f"DataForSEO task error {task.get('status_code')} for {base}/task_post: "
            f"{task.get('status_message')}")
    task_id = task.get("id")
    if not task_id:
        die(f"DataForSEO returned no task id for {base}/task_post")

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        time.sleep(interval)
        got = client.get(f"{base}/task_get/advanced/{task_id}")
        t = (got.get("tasks") or [{}])[0]
        code = t.get("status_code")
        if code == 20000 and t.get("result"):
            return t.get("result") or []
        if code not in _TASK_PENDING and code != 20000:
            die(f"DataForSEO task {task_id} failed ({code}): {t.get('status_message')}")
    die(f"DataForSEO task {task_id} not ready after {timeout}s; try a higher --timeout")


def get_client(args):
    return DataForSEOClient(
        login=env_login(args.login_env),
        password=env_required(args.password_env),
    )


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def emit(args, human_lines, json_payload):
    if getattr(args, "json", False):
        print(json.dumps(json_payload, indent=2, ensure_ascii=False))
    else:
        print("\n".join(human_lines) if human_lines else "(no results)")


def fmt_table(rows, headers):
    """Render a list of tuples as an aligned text table."""
    if not rows:
        return ["(no rows)"]
    cols = list(zip(*([headers] + [tuple(str(c) for c in r) for r in rows])))
    widths = [max(len(c) for c in col) for col in cols]
    out = []
    out.append("  ".join(h.ljust(w) for h, w in zip(headers, widths)))
    out.append("  ".join("-" * w for w in widths))
    for r in rows:
        out.append("  ".join(str(c).ljust(w) for c, w in zip(r, widths)))
    return out


def truncate(text, n):
    text = "" if text is None else str(text)
    return text if len(text) <= n else text[: n - 1] + "…"


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_serp(args):
    loc = resolve_location(args.location)
    depth = max(args.limit, 1)
    payload = [{
        "keyword": args.keyword,
        "location_code": loc,
        "language_code": args.language,
        "depth": depth,
    }]
    result = get_client(args).post("v3/serp/google/organic/live/advanced", payload)
    items = (dig(result[0], "items", []) if result else []) or []
    organic = [i for i in items if i.get("type") == "organic"]

    if args.domain:
        target = strip_www(args.domain)
        hit = None
        for i in organic:
            dom = strip_www(i.get("domain"))
            if dom == target or dom.endswith("." + target) or target.endswith("." + dom):
                hit = i
                break
        payload_out = {
            "keyword": args.keyword,
            "domain": args.domain,
            "found": hit is not None,
            "rank_absolute": hit.get("rank_absolute") if hit else None,
            "rank_group": hit.get("rank_group") if hit else None,
            "url": hit.get("url") if hit else None,
            "checked_depth": depth,
        }
        if hit:
            lines = [
                f"{args.domain} ranks #{hit.get('rank_absolute')} (group #{hit.get('rank_group')}) "
                f"for '{args.keyword}' [{args.location}]",
                f"  {hit.get('url')}",
            ]
        else:
            lines = [f"{args.domain} not found in top {depth} for '{args.keyword}' [{args.location}]"]
        emit(args, lines, payload_out)
        return

    rows = [
        (i.get("rank_absolute"), truncate(i.get("domain"), 30), truncate(i.get("title"), 50))
        for i in organic[: args.limit]
    ]
    lines = [f"Top {len(rows)} organic results for '{args.keyword}' [{args.location}]:", ""]
    lines += fmt_table(rows, ["#", "domain", "title"])
    emit(args, lines, {"keyword": args.keyword, "items": organic[: args.limit]})


def cmd_volume(args):
    loc = resolve_location(args.location)
    payload = [{
        "keywords": args.keywords,
        "location_code": loc,
        "language_code": args.language,
    }]
    result = get_client(args).post("v3/keywords_data/google_ads/search_volume/live", payload)
    rows = [
        (
            truncate(i.get("keyword"), 40),
            i.get("search_volume") if i.get("search_volume") is not None else "-",
            f"{i.get('cpc'):.2f}" if isinstance(i.get("cpc"), (int, float)) else "-",
            i.get("competition") or "-",
        )
        for i in result
    ]
    rows.sort(key=lambda r: (r[1] if isinstance(r[1], int) else -1), reverse=True)
    lines = [f"Search volume [{args.location}]:", ""]
    lines += fmt_table(rows, ["keyword", "volume", "cpc", "competition"])
    emit(args, lines, {"items": result})


def cmd_suggestions(args):
    loc = resolve_location(args.location)
    payload = [{
        "keyword": args.seed,
        "location_code": loc,
        "language_code": args.language,
        "limit": args.limit,
    }]
    result = get_client(args).post("v3/dataforseo_labs/google/keyword_suggestions/live", payload)
    items = (dig(result[0], "items", []) if result else []) or []
    rows = []
    for i in items:
        # keyword_suggestions items are flat (keyword_info.*), unlike ranked_keywords
        # which nests under keyword_data.*; accept either for robustness.
        kw = i.get("keyword") or dig(i, "keyword_data.keyword")
        vol = dig(i, "keyword_info.search_volume") or dig(i, "keyword_data.keyword_info.search_volume")
        cpc = dig(i, "keyword_info.cpc")
        if cpc is None:
            cpc = dig(i, "keyword_data.keyword_info.cpc")
        rows.append((
            truncate(kw, 45),
            vol if vol is not None else "-",
            f"{cpc:.2f}" if isinstance(cpc, (int, float)) else "-",
        ))
    lines = [f"Keyword suggestions for '{args.seed}' [{args.location}]:", ""]
    lines += fmt_table(rows, ["keyword", "volume", "cpc"])
    emit(args, lines, {"seed": args.seed, "items": items})


def cmd_ranked(args):
    loc = resolve_location(args.location)
    payload = [{
        "target": args.domain,
        "location_code": loc,
        "language_code": args.language,
        "limit": args.limit,
    }]
    result = get_client(args).post("v3/dataforseo_labs/google/ranked_keywords/live", payload)
    items = (dig(result[0], "items", []) if result else []) or []
    rows = []
    for i in items:
        kw = dig(i, "keyword_data.keyword")
        vol = dig(i, "keyword_data.keyword_info.search_volume")
        rank = dig(i, "ranked_serp_element.serp_item.rank_absolute")
        url = dig(i, "ranked_serp_element.serp_item.url")
        rows.append((truncate(kw, 35), vol if vol is not None else "-", rank if rank is not None else "-", truncate(url, 40)))
    total = dig(result[0], "total_count") if result else None
    lines = [f"Keywords {args.domain} ranks for [{args.location}] (showing {len(rows)} of {total}):", ""]
    lines += fmt_table(rows, ["keyword", "volume", "rank", "url"])
    emit(args, lines, {"target": args.domain, "total_count": total, "items": items})


def cmd_competitors(args):
    loc = resolve_location(args.location)
    payload = [{
        "target": args.domain,
        "location_code": loc,
        "language_code": args.language,
        "limit": args.limit,
    }]
    result = get_client(args).post("v3/dataforseo_labs/google/competitors_domain/live", payload)
    items = (dig(result[0], "items", []) if result else []) or []
    rows = []
    for i in items:
        dom = i.get("domain")
        inter = i.get("intersections")
        count = dig(i, "full_domain_metrics.organic.count") or dig(i, "metrics.organic.count")
        etv = dig(i, "full_domain_metrics.organic.etv") or dig(i, "metrics.organic.etv")
        rows.append((
            truncate(dom, 35),
            inter if inter is not None else "-",
            count if count is not None else "-",
            f"{etv:.0f}" if isinstance(etv, (int, float)) else "-",
        ))
    lines = [f"Competitors of {args.domain} [{args.location}]:", "", "(intersections = shared ranking keywords, etv = est. traffic value)"]
    lines += fmt_table(rows, ["domain", "shared_kw", "organic_kw", "etv"])
    emit(args, lines, {"target": args.domain, "items": items})


def cmd_domain(args):
    loc = resolve_location(args.location)
    payload = [{
        "target": args.domain,
        "location_code": loc,
        "language_code": args.language,
    }]
    result = get_client(args).post("v3/dataforseo_labs/google/domain_rank_overview/live", payload)
    items = (dig(result[0], "items", []) if result else []) or []
    metrics = dig(items[0], "metrics", {}) if items else {}
    organic = metrics.get("organic") or {}
    paid = metrics.get("paid") or {}
    payload_out = {"target": args.domain, "metrics": metrics}
    lines = [
        f"Domain overview for {args.domain} [{args.location}]:",
        "",
        f"  Organic keywords : {organic.get('count', '-')}",
        f"  Est. traffic (ETV): {organic.get('etv', '-')}",
        f"  Pos 1            : {organic.get('pos_1', '-')}",
        f"  Pos 2-3          : {organic.get('pos_2_3', '-')}",
        f"  Pos 4-10         : {organic.get('pos_4_10', '-')}",
        f"  Paid keywords    : {paid.get('count', '-')}",
    ]
    emit(args, lines, payload_out)


def cmd_backlinks(args):
    payload = [{"target": args.domain}]
    result = get_client(args).post("v3/backlinks/summary/live", payload)
    summary = result[0] if result else {}
    payload_out = {"target": args.domain, "summary": summary}
    lines = [
        f"Backlink summary for {args.domain}:",
        "",
        f"  Backlinks              : {summary.get('backlinks', '-')}",
        f"  Referring domains      : {summary.get('referring_domains', '-')}",
        f"  Referring main domains : {summary.get('referring_main_domains', '-')}",
        f"  Referring pages        : {summary.get('referring_pages', '-')}",
        f"  Broken backlinks       : {summary.get('broken_backlinks', '-')}",
        f"  Domain rank            : {summary.get('rank', '-')}",
    ]
    emit(args, lines, payload_out)


def cmd_refdomains(args):
    payload = [{
        "target": args.domain,
        "limit": args.limit,
        "order_by": ["rank,desc"],
    }]
    result = get_client(args).post("v3/backlinks/referring_domains/live", payload)
    items = (dig(result[0], "items", []) if result else []) or []
    rows = [
        (truncate(i.get("domain"), 40), i.get("backlinks", "-"), i.get("rank", "-"))
        for i in items
    ]
    lines = [f"Referring domains for {args.domain} (top {len(rows)} by rank):", ""]
    lines += fmt_table(rows, ["domain", "backlinks", "rank"])
    emit(args, lines, {"target": args.domain, "items": items})


# ---------------------------------------------------------------------------
# Discovery commands (surface demand you didn't seed — counter confirmation bias)
# ---------------------------------------------------------------------------

def cmd_ideas(args):
    """Semantically related keywords that need NOT contain the seed."""
    loc = resolve_location(args.location)
    payload = [{
        "keywords": args.seeds,
        "location_code": loc,
        "language_code": args.language,
        "limit": args.limit,
    }]
    result = get_client(args).post("v3/dataforseo_labs/google/keyword_ideas/live", payload)
    items = (dig(result[0], "items", []) if result else []) or []
    rows = []
    for i in items:
        kw = i.get("keyword") or dig(i, "keyword_data.keyword")
        vol = dig(i, "keyword_info.search_volume")
        cpc = dig(i, "keyword_info.cpc")
        intent = dig(i, "search_intent_info.main_intent")
        rows.append((
            truncate(kw, 40),
            vol if vol is not None else "-",
            f"{cpc:.2f}" if isinstance(cpc, (int, float)) else "-",
            intent or "-",
        ))
    rows.sort(key=lambda r: (r[1] if isinstance(r[1], int) else -1), reverse=True)
    lines = [f"Keyword ideas related to {args.seeds} [{args.location}] (semantic, not seed-matched):", ""]
    lines += fmt_table(rows, ["keyword", "volume", "cpc", "intent"])
    emit(args, lines, {"seeds": args.seeds, "items": items})


def cmd_related(args):
    """'Searches related to' depth expansion — walk laterally from a seed."""
    loc = resolve_location(args.location)
    payload = [{
        "keyword": args.seed,
        "location_code": loc,
        "language_code": args.language,
        "depth": args.depth,
        "limit": args.limit,
    }]
    result = get_client(args).post("v3/dataforseo_labs/google/related_keywords/live", payload)
    items = (dig(result[0], "items", []) if result else []) or []
    rows = []
    for i in items:
        kw = dig(i, "keyword_data.keyword")
        vol = dig(i, "keyword_data.keyword_info.search_volume")
        cpc = dig(i, "keyword_data.keyword_info.cpc")
        rows.append((
            truncate(kw, 45),
            vol if vol is not None else "-",
            f"{cpc:.2f}" if isinstance(cpc, (int, float)) else "-",
        ))
    rows.sort(key=lambda r: (r[1] if isinstance(r[1], int) else -1), reverse=True)
    lines = [f"Searches related to '{args.seed}' [{args.location}] (depth {args.depth}):", ""]
    lines += fmt_table(rows, ["keyword", "volume", "cpc"])
    emit(args, lines, {"seed": args.seed, "depth": args.depth, "items": items})


def cmd_intent(args):
    """Classify keywords as informational / navigational / commercial / transactional."""
    payload = [{"keywords": args.keywords, "language_code": args.language}]
    result = get_client(args).post("v3/dataforseo_labs/google/search_intent/live", payload)
    items = (dig(result[0], "items", []) if result else []) or []
    rows = []
    for i in items:
        kw = i.get("keyword")
        label = dig(i, "keyword_intent.label")
        prob = dig(i, "keyword_intent.probability")
        rows.append((
            truncate(kw, 45),
            label or "-",
            f"{prob:.0%}" if isinstance(prob, (int, float)) else "-",
        ))
    lines = ["Search intent:", ""]
    lines += fmt_table(rows, ["keyword", "intent", "confidence"])
    emit(args, lines, {"items": items})


# ---------------------------------------------------------------------------
# App Store data (async task_post/task_get) — competition + pain-point signal.
# NOTE: DataForSEO does NOT provide in-store search VOLUME; you get which apps
# rank, their ratings/review counts, and review text.
# ---------------------------------------------------------------------------

def _store_base(args, endpoint):
    store = args.store.lower()
    if store not in ("apple", "google"):
        die("--store must be 'apple' or 'google'")
    return f"v3/app_data/{store}/{endpoint}"


def cmd_appsearch(args):
    """Which apps rank in the store for a query (async)."""
    loc = resolve_location(args.location)
    payload = [{
        "keyword": args.keyword,
        "location_code": loc,
        "language_code": args.language,
        "depth": max(args.limit, 10),
    }]
    base = _store_base(args, "app_searches")
    result = run_task(get_client(args), base, payload, timeout=args.timeout)
    items = (dig(result[0], "items", []) if result else []) or []
    apps = [i for i in items if i.get("type", "app") != "check_url"][: args.limit]
    rows = []
    for i in apps:
        rating = dig(i, "rating.value")
        votes = dig(i, "rating.votes_count")
        rows.append((
            i.get("rank_absolute", "-"),
            truncate(i.get("title"), 34),
            f"{rating:.1f}" if isinstance(rating, (int, float)) else "-",
            votes if votes is not None else i.get("reviews_count", "-"),
            truncate(i.get("app_id") or i.get("id") or i.get("bundle_id"), 24),
        ))
    lines = [f"Apps ranking for '{args.keyword}' in the {args.store} store [{args.location}]:", ""]
    lines += fmt_table(rows, ["#", "app", "rating", "ratings#", "app_id"])
    emit(args, lines, {"keyword": args.keyword, "store": args.store, "items": apps})


def _review_rating(r):
    rating = r.get("rating", {})
    rv = rating.get("value") if isinstance(rating, dict) else rating
    return rv if isinstance(rv, (int, float)) else None


def cmd_appreviews(args):
    """Mine an app's reviews for pain points (async). app_id from `appsearch`.

    Apple sort_by: most_recent | most_helpful. Google sort_by: most_relevant | newest.
    `--worst` sorts the returned reviews by rating ascending (complaints first) — the
    store-agnostic way to surface pain points regardless of what the API sort supports.
    """
    loc = resolve_location(args.location)
    task = {
        "app_id": args.app_id,
        "location_code": loc,
        "language_code": args.language,
        "depth": args.limit,
    }
    if args.sort:
        task["sort_by"] = args.sort
    base = _store_base(args, "app_reviews")
    result = run_task(get_client(args), base, [task], timeout=args.timeout)
    items = (dig(result[0], "items", []) if result else []) or []
    reviews = items[: args.limit]
    if args.worst:
        reviews = sorted(reviews, key=lambda r: (_review_rating(r) is None, _review_rating(r) or 0))
    if args.json:
        emit(args, [], {"app_id": args.app_id, "store": args.store, "items": reviews})
        return
    order = "worst-rated first" if args.worst else (args.sort or "default order")
    lines = [f"Reviews for app {args.app_id} ({args.store}, {order}):", ""]
    for r in reviews:
        rv = _review_rating(r)
        stars = ("★" * int(rv) + "☆" * (5 - int(rv))) if rv is not None else "?"
        title = r.get("title") or ""
        text = (r.get("review_text") or r.get("text") or "").strip().replace("\n", " ")
        lines.append(f"{stars}  {truncate(title, 60)}")
        if text:
            lines.append(f"     {truncate(text, 160)}")
    emit(args, lines, {"app_id": args.app_id, "store": args.store, "items": reviews})


# ---------------------------------------------------------------------------
# validate — one-shot market validation (discovery + demand + intent +
# competition), scored. Runs ~5 calls (one async), so it spends more than a
# single command. Deliberately does NOT auto-mine reviews (slow/pricey) — it
# prints the top app_id + a ready `appreviews` command to run next.
# ---------------------------------------------------------------------------

def _bucket(value, table, default):
    """table: list of (min_inclusive, label) high→low. Returns first match."""
    if value is not None:
        for lo, label in table:
            if value >= lo:
                return label
    return default


def cmd_validate(args):
    seed = args.seed
    loc = resolve_location(args.location)
    client = get_client(args)

    # 1. Discovery — semantic ideas (carry intent) + related expansion.
    ideas = client.post(
        "v3/dataforseo_labs/google/keyword_ideas/live",
        [{"keywords": [seed], "location_code": loc, "language_code": args.language, "limit": args.limit}],
    )
    idea_items = (dig(ideas[0], "items", []) if ideas else []) or []
    related = client.post(
        "v3/dataforseo_labs/google/related_keywords/live",
        [{"keyword": seed, "location_code": loc, "language_code": args.language, "depth": 2, "limit": args.limit}],
    )
    rel_items = (dig(related[0], "items", []) if related else []) or []

    cand = {}
    for i in idea_items:
        kw = i.get("keyword")
        if not kw:
            continue
        c = cand.setdefault(kw, {})
        c["volume"] = dig(i, "keyword_info.search_volume")
        c["cpc"] = dig(i, "keyword_info.cpc")
        c["intent"] = dig(i, "search_intent_info.main_intent")
    for i in rel_items:
        kw = dig(i, "keyword_data.keyword")
        if not kw:
            continue
        c = cand.setdefault(kw, {})
        c.setdefault("volume", dig(i, "keyword_data.keyword_info.search_volume"))
        c.setdefault("cpc", dig(i, "keyword_data.keyword_info.cpc"))

    ranked = sorted(cand.items(), key=lambda kv: (kv[1].get("volume") or 0), reverse=True)
    top = ranked[:15]

    # 2. Clean intent classification — anchor on the seed plus top discovered terms.
    top_kws = list(dict.fromkeys([seed] + [k for k, _ in top[:9]]))
    intents = {}
    if top_kws:
        ir = client.post(
            "v3/dataforseo_labs/google/search_intent/live",
            [{"keywords": top_kws, "language_code": args.language}],
        )
        for it in ((dig(ir[0], "items", []) if ir else []) or []):
            intents[it.get("keyword")] = dig(it, "keyword_intent.label")

    # 3. Anchor demand on the seed itself — discovered terms drift off-target.
    sv = client.post(
        "v3/keywords_data/google_ads/search_volume/live",
        [{"keywords": [seed], "location_code": loc, "language_code": args.language}],
    )
    seed_item = (sv[0] if sv else {}) or {}
    seed_vol = seed_item.get("search_volume")
    seed_cpc = seed_item.get("cpc")

    # 4. SERP on the seed — is the actual query owned by content or apps?
    serp = client.post(
        "v3/serp/google/organic/live/advanced",
        [{"keyword": seed, "location_code": loc, "language_code": args.language, "depth": 10}],
    )
    serp_organic = [x for x in ((dig(serp[0], "items", []) if serp else []) or []) if x.get("type") == "organic"]
    app_hosts = {"play.google.com", "apps.apple.com", "itunes.apple.com"}
    serp_apps = sum(1 for x in serp_organic if (x.get("domain") or "") in app_hosts)

    # 4. App-store competition (async).
    appbase = _store_base(args, "app_searches")
    apps = run_task(
        client, appbase,
        [{"keyword": seed, "location_code": loc, "language_code": args.language, "depth": max(args.limit, 10)}],
        timeout=args.timeout,
    )
    app_items = (dig(apps[0], "items", []) if apps else []) or []
    top_apps = [a for a in app_items if a.get("title")][:10]

    def app_votes(a):
        v = dig(a, "rating.votes_count")
        return v if isinstance(v, (int, float)) else (a.get("reviews_count") or 0)

    max_votes = max((app_votes(a) for a in top_apps), default=0)

    # ---- scoring (transparent heuristics) ----
    vols = [c.get("volume") or 0 for _, c in top]
    max_vol = max(vols, default=0)
    sum_vol = sum(vols)
    cpcs = [c["cpc"] for _, c in top if isinstance(c.get("cpc"), (int, float)) and c["cpc"] > 0]
    median_cpc = sorted(cpcs)[len(cpcs) // 2] if cpcs else 0.0
    labels = [lbl for lbl in intents.values() if lbl]
    dom_intent = Counter(labels).most_common(1)[0][0] if labels else None

    demand = _bucket(seed_vol, [(5000, "high"), (1000, "moderate"), (100, "low")], "negligible")
    anchor_cpc = seed_cpc if isinstance(seed_cpc, (int, float)) and seed_cpc > 0 else median_cpc
    commercial = _bucket(anchor_cpc, [(2.0, "high"), (0.75, "moderate")], "low")
    appcomp = _bucket(max_votes, [(100000, "entrenched"), (10000, "strong"), (1000, "moderate")], "open (white space)")
    serp_type = "content-dominated (SEO-winnable)" if serp_apps <= 1 else (
        "app-competitive" if serp_apps >= 3 else "mixed")

    flags = []
    if demand in ("negligible", "low"):
        flags.append(f"'{seed}' itself gets {seed_vol or 0:,}/mo — category search won't get you found.")
    elif demand == "high":
        flags.append(f"'{seed}' gets {seed_vol:,}/mo — real direct demand.")
    if serp_type.startswith("content"):
        flags.append(f"'{truncate(seed, 30)}' SERP is content-dominated — an SEO/content channel is winnable.")
    if appcomp.startswith("open"):
        flags.append("No entrenched app in this exact niche — genuine white space.")
    elif appcomp in ("entrenched", "strong"):
        flags.append(f"Strong app incumbent — up to {max_votes:,} ratings. Needs a sharp wedge.")
    if commercial == "high":
        flags.append("High CPC — willingness to pay is real.")
    elif commercial == "low" and dom_intent == "informational":
        flags.append("Low CPC + informational — free-answer seekers, not buyers.")
    if dom_intent:
        note = {"informational": " (content, not conversion)", "commercial": " (buyers)",
                "transactional": " (buyers)"}.get(dom_intent, "")
        flags.append(f"Dominant intent: {dom_intent}{note}.")

    suggestion = None
    if top_apps:
        aid = top_apps[0].get("app_id") or top_apps[0].get("id")
        if aid:
            suggestion = (f"dataforseo appreviews {aid} --store {args.store} --worst --limit 30"
                          f"   # mine '{truncate(top_apps[0].get('title'), 30)}' for the wedge")

    payload_out = {
        "seed": seed, "location": args.location, "store": args.store,
        "scores": {"demand": demand, "commercial": commercial, "app_competition": appcomp,
                   "serp_type": serp_type, "dominant_intent": dom_intent},
        "signals": {"seed_volume": seed_vol, "seed_cpc": seed_cpc, "cluster_ceiling_volume": max_vol,
                    "sum_top_volume": sum_vol, "median_cpc": round(median_cpc, 2),
                    "serp_apps_in_top10": serp_apps, "max_app_ratings": max_votes},
        "top_keywords": [{"keyword": k, **v, "intent": intents.get(k, v.get("intent"))} for k, v in top],
        "top_apps": top_apps,
        "next": suggestion,
    }
    if args.json:
        emit(args, [], payload_out)
        return

    lines = [
        f"═══ Idea validation: '{seed}'  [{args.location}, {args.store} store] ═══",
        "",
        f"  Seed demand     : {demand}   ('{truncate(seed, 28)}' = {seed_vol or 0:,}/mo)",
        f"  Discovery       : {len([v for v in vols if v])} related terms, ceiling {max_vol:,}/mo (breadth; may drift off-target)",
        f"  Commercial      : {commercial}   (CPC ${anchor_cpc:.2f})",
        f"  Dominant intent : {dom_intent or '-'}",
        f"  SERP (the seed) : {serp_type}   ({serp_apps}/10 results are apps)",
        f"  App competition : {appcomp}   (strongest incumbent {max_votes:,} ratings)",
        "",
        "  Read:",
    ]
    lines += [f"   • {f}" for f in flags]
    lines += ["", "  Top demand (discovered — review for off-target semantic matches):", ""]
    krows = [(truncate(k, 40), v.get("volume") if v.get("volume") is not None else "-",
              f"{v['cpc']:.2f}" if isinstance(v.get("cpc"), (int, float)) else "-",
              intents.get(k) or v.get("intent") or "-") for k, v in top]
    lines += fmt_table(krows, ["keyword", "volume", "cpc", "intent"])
    if top_apps:
        lines += ["", "  Incumbent apps:", ""]
        arows = [(a.get("rank_absolute", "-"), truncate(a.get("title"), 34),
                  f"{dig(a, 'rating.value'):.1f}" if isinstance(dig(a, "rating.value"), (int, float)) else "-",
                  app_votes(a)) for a in top_apps]
        lines += fmt_table(arows, ["#", "app", "rating", "ratings#"])
    if suggestion:
        lines += ["", f"  Next — mine the incumbent's pain points:", f"   $ {suggestion}"]
    emit(args, lines, payload_out)


# ---------------------------------------------------------------------------
# Arg parsing
# ---------------------------------------------------------------------------

def add_common(p, *, location=True, limit_default=10):
    if location:
        p.add_argument("--location", default="nz", help="location alias (nz, us, uk, au, ...) or numeric location_code (default: nz)")
        p.add_argument("--language", default="en", help="language_code (default: en)")
    p.add_argument("--limit", type=int, default=limit_default, help=f"max rows (default: {limit_default})")
    p.add_argument("--json", action="store_true", help="emit raw JSON instead of a table")
    p.add_argument("--login-env", default="DATAFORSEO_LOGIN", help="env var holding the API login")
    p.add_argument("--password-env", default="DATAFORSEO_PASSWORD", help="env var holding the API password")


def build_parser():
    parser = argparse.ArgumentParser(
        prog="dataforseo",
        description="Query DataForSEO: SERP, keyword research + discovery, domain/competitor "
                    "analytics, backlinks, and App Store / Play data.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("serp", help="Google organic results for a keyword; --domain to get a site's rank")
    p.add_argument("keyword")
    p.add_argument("--domain", help="report this domain's rank position instead of listing results")
    add_common(p)
    p.set_defaults(func=cmd_serp)

    p = sub.add_parser("volume", help="search volume, CPC, competition for one or more keywords")
    p.add_argument("keywords", nargs="+")
    add_common(p)
    p.set_defaults(func=cmd_volume)

    p = sub.add_parser("suggestions", help="long-tail keyword ideas containing a seed term")
    p.add_argument("seed")
    add_common(p)
    p.set_defaults(func=cmd_suggestions)

    p = sub.add_parser("ranked", help="keywords a domain already ranks for")
    p.add_argument("domain")
    add_common(p)
    p.set_defaults(func=cmd_ranked)

    p = sub.add_parser("competitors", help="domains competing for the same keywords")
    p.add_argument("domain")
    add_common(p)
    p.set_defaults(func=cmd_competitors)

    p = sub.add_parser("domain", help="organic/paid rank overview for a domain")
    p.add_argument("domain")
    add_common(p)
    p.set_defaults(func=cmd_domain)

    p = sub.add_parser("backlinks", help="backlink summary for a domain")
    p.add_argument("domain")
    add_common(p, location=False)
    p.set_defaults(func=cmd_backlinks)

    p = sub.add_parser("refdomains", help="referring domains for a domain")
    p.add_argument("domain")
    add_common(p, location=False)
    p.set_defaults(func=cmd_refdomains)

    # --- Discovery (counter confirmation bias: surface terms you didn't seed) ---
    p = sub.add_parser("ideas", help="semantically related keywords (NOT just seed-matched)")
    p.add_argument("seeds", nargs="+", help="one or more seed keywords")
    add_common(p, limit_default=25)
    p.set_defaults(func=cmd_ideas)

    p = sub.add_parser("related", help="'searches related to' depth expansion from a seed")
    p.add_argument("seed")
    p.add_argument("--depth", type=int, default=2, help="expansion depth 0-4 (default 2; higher=wider, pricier)")
    add_common(p, limit_default=25)
    p.set_defaults(func=cmd_related)

    p = sub.add_parser("intent", help="classify keywords: informational/commercial/transactional")
    p.add_argument("keywords", nargs="+")
    add_common(p)
    p.set_defaults(func=cmd_intent)

    # --- App Store / Play data (async; no in-store search volume exists) ---
    p = sub.add_parser("appsearch", help="which apps rank in a store for a query")
    p.add_argument("keyword")
    p.add_argument("--store", default="apple", help="apple | google (default: apple)")
    p.add_argument("--timeout", type=int, default=180, help="max seconds to poll (default: 180)")
    add_common(p, limit_default=20)
    p.set_defaults(func=cmd_appsearch)

    # --- One-shot idea validation (orchestrates ~5 calls, one async) ---
    p = sub.add_parser("validate", help="score an app/business idea: demand + intent + competition in one pass")
    p.add_argument("seed", help="the idea as a keyword phrase, e.g. \"fruit tree care app\"")
    p.add_argument("--store", default="apple", help="app store for competition check: apple | google (default: apple)")
    p.add_argument("--timeout", type=int, default=200, help="max seconds to poll the app search (default: 200)")
    add_common(p, limit_default=25)
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("appreviews", help="mine an app's reviews for pain points (app_id from appsearch)")
    p.add_argument("app_id")
    p.add_argument("--store", default="apple", help="apple | google (default: apple)")
    p.add_argument("--worst", action="store_true", help="sort returned reviews worst-rated first (pain points)")
    p.add_argument("--sort", help="API sort_by — apple: most_recent|most_helpful; google: most_relevant|newest")
    p.add_argument("--timeout", type=int, default=180, help="max seconds to poll (default: 180)")
    add_common(p, limit_default=50)
    p.set_defaults(func=cmd_appreviews)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
