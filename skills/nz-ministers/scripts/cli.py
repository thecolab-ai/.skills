#!/usr/bin/env python3
"""Query NZ government ministers, their portfolios, and their press releases.

Data source: beehive.govt.nz (the official NZ Government website).

- `latest`    : newest government releases/speeches site-wide. Keyless — reads the
                allowlisted RSS feed, works with no browser.
- `minister`  : a single minister's profile (name, portfolios, recent articles).
- `articles`  : all releases/speeches/features attributed to a given minister.

`minister` and `articles` read minister pages that sit behind Incapsula bot
protection. Pass `--browser` once to clear the challenge with CloakBrowser
(https://github.com/CloakHQ/CloakBrowser); the clearance cookies are cached in a
temp file and reused by plain HTTP for ~10 minutes, so subsequent calls need no
browser. See references/api-notes.md for detail.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import ssl
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any

BASE = "https://www.beehive.govt.nz"
RSS_URL = f"{BASE}/rss.xml"
DEFAULT_UA = os.environ.get(
    "NZ_MINISTERS_USER_AGENT",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
)
CACHE_FILE = os.path.join(tempfile.gettempdir(), "nz-ministers-incap.json")
CACHE_TTL_SECONDS = 300  # reuse browser-obtained Incapsula clearance (sessions are short-lived)
ARTICLE_TYPES = ("release", "speech", "feature")


class ApiError(RuntimeError):
    """Upstream/network failure with a clean human message."""


class ClearanceUnavailable(RuntimeError):
    """Minister pages need Incapsula clearance and none is available."""


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _open(url: str, headers: dict[str, str], timeout: int = 20) -> str:
    req = urllib.request.Request(url, headers=headers, method="GET")
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raise ApiError(f"HTTP {e.code} from {url}") from e
    except urllib.error.URLError as e:
        raise ApiError(f"network error contacting beehive.govt.nz: {e.reason}") from e


def is_incapsula(text: str) -> bool:
    low = text.lower()
    return "incapsula" in low or "_incapsula_resource" in low


def fetch_rss() -> str:
    """The root RSS feed is allowlisted and needs no clearance."""
    text = _open(RSS_URL, {"User-Agent": DEFAULT_UA, "Accept": "application/rss+xml, application/xml, */*"})
    if is_incapsula(text):
        raise ApiError("beehive RSS feed is temporarily blocked; try again shortly")
    return text


# ---------------------------------------------------------------------------
# Incapsula clearance (cookie bootstrap via CloakBrowser, cached for reuse)
# ---------------------------------------------------------------------------

def load_clearance() -> dict[str, str] | None:
    try:
        with open(CACHE_FILE, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not data.get("cookie") or not data.get("ua"):
        return None
    if time.time() - float(data.get("ts", 0)) > CACHE_TTL_SECONDS:
        return None
    return {"ua": data["ua"], "cookie": data["cookie"]}


def save_clearance(ua: str, cookie: str) -> None:
    tmp = CACHE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"ua": ua, "cookie": cookie, "ts": time.time()}, fh)
    os.replace(tmp, CACHE_FILE)


def bootstrap_clearance() -> dict[str, str]:
    """Launch CloakBrowser, clear the Incapsula challenge, cache UA + cookies."""
    try:
        import cloakbrowser  # noqa: F401
    except Exception as exc:  # pragma: no cover - optional host dependency
        raise ClearanceUnavailable(
            "cloakbrowser_not_installed: install CloakBrowser to clear beehive's bot "
            "protection (https://github.com/CloakHQ/CloakBrowser)."
        ) from exc

    from cloakbrowser import launch

    browser = None
    try:
        # CloakBrowser prints a banner to stdout on some versions — keep stdout clean.
        with contextlib.redirect_stdout(sys.stderr):
            browser = launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
                timezone="Pacific/Auckland",
                locale="en-NZ",
            )
            page = browser.new_page()
            page.goto(BASE + "/", wait_until="domcontentloaded", timeout=90000)
            cleared = False
            for _ in range(6):
                page.wait_for_timeout(2500)
                html = page.content()
                if not is_incapsula(html) and len(html) > 5000:
                    cleared = True
                    break
                with contextlib.suppress(Exception):
                    page.reload(wait_until="domcontentloaded", timeout=60000)
            if not cleared:
                raise ClearanceUnavailable(
                    "browser_blocked: CloakBrowser could not clear the beehive bot challenge"
                )
            ua = page.evaluate("() => navigator.userAgent")
            cookie = "; ".join(f'{c["name"]}={c["value"]}' for c in page.context.cookies())
    finally:
        if browser is not None:
            with contextlib.suppress(Exception):
                browser.close()

    if not cookie:
        raise ClearanceUnavailable("browser_blocked: no clearance cookies obtained")
    save_clearance(ua, cookie)
    return {"ua": ua, "cookie": cookie}


def fetch_protected(url: str, *, allow_browser: bool) -> str:
    """Fetch a bot-protected beehive page using cached or fresh Incapsula clearance.

    Tries cached clearance first (pure HTTP, no browser). If that is missing or
    stale, and --browser is allowed, bootstraps fresh clearance via CloakBrowser.
    """
    clearance = load_clearance()
    if clearance is None:
        if not allow_browser:
            raise ClearanceUnavailable(
                "clearance_required: beehive minister pages are behind Incapsula bot "
                "protection. Run this command once with --browser (CloakBrowser) to mint "
                "clearance cookies; they are cached and reused for ~10 minutes."
            )
        clearance = bootstrap_clearance()

    def _get(c: dict[str, str]) -> str:
        return _open(
            url,
            {
                "User-Agent": c["ua"],
                "Cookie": c["cookie"],
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-NZ,en;q=0.9",
                "Referer": BASE + "/",
            },
        )

    html = _get(clearance)
    if is_incapsula(html):
        # Cached cookies went stale mid-flight; re-bootstrap once if allowed.
        if not allow_browser:
            raise ClearanceUnavailable(
                "clearance_expired: cached beehive clearance is stale. Re-run with --browser."
            )
        clearance = bootstrap_clearance()
        html = _get(clearance)
        if is_incapsula(html):
            raise ClearanceUnavailable("browser_blocked: beehive served a challenge after clearance")
    return html


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _strip_tags(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text)).strip()


def article_type_from_path(path: str) -> str:
    seg = path.lstrip("/").split("/", 1)[0]
    return seg if seg in ARTICLE_TYPES else "article"


def parse_rss_items(xml_text: str) -> list[dict[str, Any]]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        raise ApiError(f"could not parse beehive RSS: {e}") from e
    items: list[dict[str, Any]] = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        if not link:
            continue
        path = urllib.parse.urlparse(link).path
        items.append(
            {
                "title": title,
                "url": link,
                "slug": path.rstrip("/").split("/")[-1],
                "type": article_type_from_path(path),
                "published": pub,
            }
        )
    return items


# Each article on a minister page is a <article class="teaser ..."> block.
_TEASER_RE = re.compile(r'<article\b[^>]*class="[^"]*\bteaser\b[^"]*"[^>]*>(.*?)</article>', re.S)
_TYPE_RE = re.compile(r'meta__content-type"[^>]*>(.*?)<', re.S)
_TIME_RE = re.compile(r'<time[^>]*datetime="([^"]+)"[^>]*>(.*?)</time>', re.S)
_TITLE_RE = re.compile(
    r'field--name-node-title.*?<a\s+href="(/[^"#?]+)"[^>]*>(.*?)</a>', re.S
)


def parse_minister_articles(html: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for block in _TEASER_RE.findall(html):
        tm = _TITLE_RE.search(block)
        if not tm:
            continue
        path, title = tm.group(1), _strip_tags(tm.group(2))
        ctype = _TYPE_RE.search(block)
        time_m = _TIME_RE.search(block)
        out.append(
            {
                "title": title,
                "url": BASE + path,
                "slug": path.rstrip("/").split("/")[-1],
                "type": (_strip_tags(ctype.group(1)).lower() if ctype else article_type_from_path(path)),
                "published": time_m.group(1) if time_m else "",
                "published_label": _strip_tags(time_m.group(2)) if time_m else "",
            }
        )
    return out


# The appointments view lists each role as one row:
#   <span class="views-field views-field-field-portfolio"><a href="/portfolio/..">Health</a></span>
#   - <span class="views-field views-field-field-position">Minister</span>
#   <span class="views-field views-field-field-archived"><span class="field-content">..</span></span>
_APPT_VIEW_RE = re.compile(r'view-appointments\b.*?<div class="view-content">(.*?)</div>\s*</div>', re.S)
_APPT_ROW_RE = re.compile(
    r'views-field-field-portfolio"><a\s+href="([^"]+)"[^>]*>(.*?)</a>.*?'
    r'views-field-field-position">(.*?)</span>.*?'
    r'views-field-field-archived"><span class="field-content">(.*?)</span>',
    re.S,
)


def parse_minister_roles(html: str) -> list[dict[str, Any]]:
    """Roles & responsibilities: each portfolio the minister holds + their position."""
    view = _APPT_VIEW_RE.search(html)
    block = view.group(1) if view else html
    roles: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for url, portfolio, position, archived in _APPT_ROW_RE.findall(block):
        name = _strip_tags(portfolio)
        pos = _strip_tags(position)
        key = (name, pos)
        if not name or key in seen:
            continue
        seen.add(key)
        position = pos or "Minister"
        roles.append(
            {
                "portfolio": name,
                "position": position,
                # Mirror beehive's own "Health - Minister" phrasing rather than
                # forcing "of"/"for", which varies by portfolio.
                "title": f"{name} — {position}",
                "url": BASE + url if url.startswith("/") else url,
                "archived": bool(_strip_tags(archived)),
            }
        )
    return [r for r in roles if not r["archived"]]


def parse_biography_url(html: str) -> str | None:
    m = re.search(r'href="(/minister/biography/[^"#?]+)"', html)
    return BASE + m.group(1) if m else None


def parse_minister_id(html: str) -> str | None:
    m = re.search(r"ministers(?:%3A|:)(\d+)", html)
    return m.group(1) if m else None


def parse_latest_diary(html: str) -> dict[str, Any] | None:
    """The most recent ministerial diary (the minister's published calendar)."""
    view = re.search(r"view-ministerial-diaries\b.*?(?=</aside>)", html, re.S)
    if not view:
        return None
    block = view.group(0)
    title = re.search(r'views-field-title">\s*<strong[^>]*>(.*?)</strong>', block, re.S)
    when = re.search(r'<time[^>]*datetime="([^"]+)"[^>]*>(.*?)</time>', block, re.S)
    pdf = re.search(r'href="([^"]+\.pdf[^"]*)"', block)
    if not (title or pdf):
        return None
    return {
        "title": _strip_tags(title.group(1)) if title else "",
        "published": when.group(1) if when else "",
        "published_label": _strip_tags(when.group(2)) if when else "",
        "pdf_url": pdf.group(1) if pdf else None,
    }


def diary_archive_url(html: str) -> str | None:
    m = re.search(r'href="(/search\?[^"]*ministerial_diary[^"]*)"', html)
    return BASE + m.group(1).replace("&amp;", "&") if m else None


def parse_minister_profile(html: str, slug: str) -> dict[str, Any]:
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S)
    name = _strip_tags(h1.group(1)) if h1 else slug
    return {
        "name": name,
        "slug": slug,
        "url": f"{BASE}/minister/{slug}",
        "roles": parse_minister_roles(html),
        "biography_url": parse_biography_url(html),
        "latest_diary": parse_latest_diary(html),
        "diary_archive_url": diary_archive_url(html),
    }


# ---------------------------------------------------------------------------
# Slug handling
# ---------------------------------------------------------------------------

def slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.strip().lower()).strip("-")
    return s


def minister_slug_candidates(value: str) -> list[str]:
    raw = value.strip()
    base = slugify(raw)
    candidates = []
    # If the caller already passed a slug, honour it first.
    if "/" not in raw and " " not in raw and base == raw.lower():
        candidates.append(raw.lower())
    candidates.append(base)
    # Ministers carry honorifics in their slug: "hon-", and "rt-hon-" for the
    # Prime Minister / senior ministers. Try the bare name with each prefix.
    bare = re.sub(r"^(rt-)?hon-", "", base)
    for prefix in ("hon-", "rt-hon-"):
        candidates.append(prefix + bare)
    # de-dup preserving order
    out: list[str] = []
    for c in candidates:
        if c and c not in out:
            out.append(c)
    return out


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_latest(args: argparse.Namespace) -> int:
    items = parse_rss_items(fetch_rss())
    if args.type:
        items = [i for i in items if i["type"] == args.type]
    items = items[: args.limit]
    payload = {"source": RSS_URL, "count": len(items), "results": items}
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"Latest NZ government releases ({len(items)})")
        for i in items:
            print(f"  [{i['type']}] {i['published']}")
            print(f"    {i['title']}")
            print(f"    {i['url']}")
    return 0


def _resolve_minister(value: str, *, allow_browser: bool) -> tuple[str, str]:
    """Return (slug, html) for the first candidate slug that resolves to a page."""
    saw_404 = False
    clearance_err: ClearanceUnavailable | None = None
    for slug in minister_slug_candidates(value):
        url = f"{BASE}/minister/{slug}"
        try:
            html = fetch_protected(url, allow_browser=allow_browser)
        except ClearanceUnavailable as e:
            clearance_err = e  # bot-wall, not a name problem — report it, don't keep trying
            break
        except ApiError as e:
            if "HTTP 404" in str(e):
                saw_404 = True
                continue
            raise  # genuine network/upstream error
        if re.search(r"<h1[^>]*>", html) and "/minister/" in html:
            return slug, html
        saw_404 = True
    if clearance_err is not None:
        raise clearance_err
    if saw_404:
        raise ApiError(
            f"no minister found for {value!r} — try the exact beehive slug, e.g. 'hon-simeon-brown'"
        )
    raise ApiError(f"could not resolve minister {value!r}")


def cmd_minister(args: argparse.Namespace) -> int:
    slug, html = _resolve_minister(args.minister, allow_browser=args.browser)
    profile = parse_minister_profile(html, slug)
    articles = parse_minister_articles(html)
    profile["recent_articles"] = articles[:5]
    profile["article_count_on_page"] = len(articles)
    if args.json:
        print(json.dumps(profile, indent=2, ensure_ascii=False))
    else:
        print(profile["name"])
        print(f"  {profile['url']}")
        if profile["roles"]:
            print("  Roles & responsibilities:")
            for r in profile["roles"]:
                print(f"    {r['title']}")
        if profile.get("biography_url"):
            print(f"  Biography: {profile['biography_url']}")
        diary = profile.get("latest_diary")
        if diary:
            label = diary.get("published_label") or diary.get("published") or ""
            print(f"  Latest diary: {diary.get('title') or 'Ministerial diary'} ({label})")
            if diary.get("pdf_url"):
                print(f"    {diary['pdf_url']}")
        if profile["recent_articles"]:
            print("  Recent articles:")
            for a in profile["recent_articles"]:
                print(f"    [{a['type']}] {a.get('published_label') or a['published']} — {a['title']}")
    return 0


def cmd_roles(args: argparse.Namespace) -> int:
    slug, html = _resolve_minister(args.minister, allow_browser=args.browser)
    roles = parse_minister_roles(html)
    name_m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S)
    payload = {
        "minister": slug,
        "name": _strip_tags(name_m.group(1)) if name_m else slug,
        "url": f"{BASE}/minister/{slug}",
        "count": len(roles),
        "roles": roles,
    }
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"{payload['name']} — roles & responsibilities ({len(roles)})")
        for r in roles:
            print(f"  {r['title']}")
            print(f"    {r['url']}")
    return 0


def cmd_diary(args: argparse.Namespace) -> int:
    slug, html = _resolve_minister(args.minister, allow_browser=args.browser)
    diary = parse_latest_diary(html)
    payload = {
        "minister": slug,
        "url": f"{BASE}/minister/{slug}",
        "latest_diary": diary,
        "archive_url": diary_archive_url(html),
        "note": "Beehive publishes the latest ministerial diary on the minister page. "
        "The full diary archive is behind a JavaScript search at archive_url.",
    }
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        if diary:
            label = diary.get("published_label") or diary.get("published") or ""
            print(f"Latest ministerial diary for {slug}: {diary.get('title') or ''} ({label})")
            if diary.get("pdf_url"):
                print(f"  PDF: {diary['pdf_url']}")
        else:
            print(f"No published ministerial diary found for {slug}.")
        if payload["archive_url"]:
            print(f"  Full diary archive: {payload['archive_url']}")
    return 0


def cmd_articles(args: argparse.Namespace) -> int:
    slug, html = _resolve_minister(args.minister, allow_browser=args.browser)
    articles = parse_minister_articles(html)
    if args.type:
        articles = [a for a in articles if a["type"] == args.type]
    articles = articles[: args.limit]
    payload = {
        "minister": slug,
        "url": f"{BASE}/minister/{slug}",
        "count": len(articles),
        "results": articles,
    }
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"Articles by {slug} ({len(articles)})")
        for a in articles:
            print(f"  [{a['type']}] {a.get('published_label') or a['published']}")
            print(f"    {a['title']}")
            print(f"    {a['url']}")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Query NZ government ministers, portfolios, and press releases (beehive.govt.nz)."
    )
    sub = ap.add_subparsers(dest="command", required=True)

    p_latest = sub.add_parser("latest", help="latest government releases/speeches (keyless RSS)")
    p_latest.add_argument("--limit", type=int, default=20, help="max items (default 20)")
    p_latest.add_argument("--type", choices=ARTICLE_TYPES, help="filter by content type")
    p_latest.add_argument("--json", action="store_true", help="emit JSON")
    p_latest.set_defaults(func=cmd_latest)

    p_min = sub.add_parser("minister", help="a minister's profile: roles, biography, diary, recent articles")
    p_min.add_argument("minister", help="minister slug or name, e.g. 'hon-simeon-brown' or 'Simeon Brown'")
    p_min.add_argument("--browser", action="store_true", help="use CloakBrowser to clear beehive bot protection")
    p_min.add_argument("--json", action="store_true", help="emit JSON")
    p_min.set_defaults(func=cmd_minister)

    p_roles = sub.add_parser("roles", help="a minister's roles & responsibilities (portfolios + position)")
    p_roles.add_argument("minister", help="minister slug or name, e.g. 'hon-simeon-brown'")
    p_roles.add_argument("--browser", action="store_true", help="use CloakBrowser to clear beehive bot protection")
    p_roles.add_argument("--json", action="store_true", help="emit JSON")
    p_roles.set_defaults(func=cmd_roles)

    p_diary = sub.add_parser("diary", help="a minister's latest published diary (calendar) + archive link")
    p_diary.add_argument("minister", help="minister slug or name, e.g. 'hon-simeon-brown'")
    p_diary.add_argument("--browser", action="store_true", help="use CloakBrowser to clear beehive bot protection")
    p_diary.add_argument("--json", action="store_true", help="emit JSON")
    p_diary.set_defaults(func=cmd_diary)

    p_art = sub.add_parser("articles", help="releases/speeches attributed to a minister")
    p_art.add_argument("minister", help="minister slug or name, e.g. 'hon-simeon-brown'")
    p_art.add_argument("--limit", type=int, default=20, help="max items (default 20)")
    p_art.add_argument("--type", choices=ARTICLE_TYPES, help="filter by content type")
    p_art.add_argument("--browser", action="store_true", help="use CloakBrowser to clear beehive bot protection")
    p_art.add_argument("--json", action="store_true", help="emit JSON")
    p_art.set_defaults(func=cmd_articles)

    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except ClearanceUnavailable as e:
        msg = str(e)
        code = msg.split(":", 1)[0]
        if getattr(args, "json", False):
            print(
                json.dumps(
                    {
                        "error": code,
                        "message": msg,
                        "recommendation": "Run once with --browser (requires CloakBrowser) to mint "
                        "beehive clearance cookies, or use `latest` which needs no browser.",
                    },
                    indent=2,
                ),
                file=sys.stderr,
            )
        else:
            print(f"nz-ministers: {msg}", file=sys.stderr)
        return 2
    except ApiError as e:
        if getattr(args, "json", False):
            print(json.dumps({"error": "upstream_error", "message": str(e)}, indent=2), file=sys.stderr)
        else:
            print(f"nz-ministers: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
