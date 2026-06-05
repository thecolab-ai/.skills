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
CACHE_TTL_SECONDS = 600  # reuse browser-obtained Incapsula clearance for 10 minutes
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


def parse_minister_profile(html: str, slug: str) -> dict[str, Any]:
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S)
    name = _strip_tags(h1.group(1)) if h1 else slug
    portfolios: list[dict[str, str]] = []
    seen: set[str] = set()
    for path, text in re.findall(r'<a\s+href="(/portfolio/[^"]+)"[^>]*>(.*?)</a>', html, re.S):
        parts = path.rstrip("/").split("/")
        if len(parts) < 4:  # /portfolio/<government>/<area>
            continue
        area = parts[-1]
        if area in seen:
            continue
        seen.add(area)
        label = _strip_tags(text) or area.replace("-", " ").title()
        portfolios.append({"name": label, "url": BASE + path, "slug": area})
    return {"name": name, "slug": slug, "portfolios": portfolios}


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
    if not base.startswith("hon-"):
        candidates.append("hon-" + base)
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
    last_err: Exception | None = None
    for slug in minister_slug_candidates(value):
        url = f"{BASE}/minister/{slug}"
        try:
            html = fetch_protected(url, allow_browser=allow_browser)
        except ApiError as e:
            last_err = e
            continue
        if re.search(r"<h1[^>]*>", html) and "/minister/" in html:
            return slug, html
        last_err = ApiError(f"no minister page found for {slug!r}")
    if isinstance(last_err, Exception):
        raise last_err
    raise ApiError(f"no minister page found for {value!r}")


def cmd_minister(args: argparse.Namespace) -> int:
    slug, html = _resolve_minister(args.minister, allow_browser=args.browser)
    profile = parse_minister_profile(html, slug)
    articles = parse_minister_articles(html)
    profile["url"] = f"{BASE}/minister/{slug}"
    profile["recent_articles"] = articles[:5]
    profile["article_count_on_page"] = len(articles)
    if args.json:
        print(json.dumps(profile, indent=2, ensure_ascii=False))
    else:
        print(profile["name"])
        print(f"  {profile['url']}")
        if profile["portfolios"]:
            print("  Portfolios: " + ", ".join(p["name"] for p in profile["portfolios"]))
        if profile["recent_articles"]:
            print("  Recent articles:")
            for a in profile["recent_articles"]:
                print(f"    [{a['type']}] {a.get('published_label') or a['published']} — {a['title']}")
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

    p_min = sub.add_parser("minister", help="a minister's profile, portfolios, and recent articles")
    p_min.add_argument("minister", help="minister slug or name, e.g. 'hon-simeon-brown' or 'Simeon Brown'")
    p_min.add_argument("--browser", action="store_true", help="use CloakBrowser to clear beehive bot protection")
    p_min.add_argument("--json", action="store_true", help="emit JSON")
    p_min.set_defaults(func=cmd_minister)

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
