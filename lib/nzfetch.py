"""nzfetch — shared HTTP helper for For Good skills (Python stdlib only).

Gets past the IP-reputation bot walls (Incapsula / Cloudflare) that guard a lot
of official NZ sources — data.govt.nz (CKAN), councils, some government portals.
It sends a browser-shaped User-Agent and, on a block, RETRIES through a rotating
proxy when one is configured: a fresh IP per attempt clears IP-reputation walls
probabilistically (some rotated IPs are clean).

Import it from a skill's `scripts/cli.py` (it lives at the repo's `lib/`, three
parents up from the skill's scripts dir):

    import pathlib, sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "lib"))
    import nzfetch

    data = nzfetch.fetch_json("https://catalogue.data.govt.nz/api/3/action/...")

Handle the two typed errors so a transient block SKIPS rather than hard-fails:

    try:
        data = nzfetch.fetch_json(url)
    except nzfetch.Blocked as e:
        die(f"network error: {e}")        # smoke tests treat 'network error' as SKIP
    except nzfetch.FetchError as e:
        die(str(e))

Environment (all optional):
    FETCH_PROXY / HTTPS_PROXY   rotating proxy URL, e.g. http://user:pass@host:port
                               — a SECRET. Never hard-code it, never print it, never
                               commit it. nzfetch reads it from the env only.
    PROXY_RETRIES              retries through the proxy on a block (default 4).
    NZFETCH_UA                 override the User-Agent if a source needs a specific one.

No proxy set → nzfetch just does the single direct request (same as before), so a
skill that imports it keeps working unchanged when no proxy is configured.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)


class FetchError(Exception):
    """A non-recoverable fetch failure (a real HTTP error, bad URL, bad body)."""


class Blocked(FetchError):
    """Every attempt hit a bot wall (HTTP 403/429 or an HTML challenge). This is a
    TRANSIENT block (tooling / IP reputation), NOT a dead source — callers should
    skip / soft-fail, never treat it as a citation defect."""


def proxy_url() -> str:
    """The configured rotating-proxy URL, or "" for direct. A SECRET — read from
    the env only, never returned to logs by callers."""
    return (
        os.environ.get("FETCH_PROXY")
        or os.environ.get("HTTPS_PROXY")
        or os.environ.get("https_proxy")
        or ""
    )


def _looks_like_challenge(body: str, content_type: str) -> bool:
    """True if the response is a bot-wall interstitial rather than the real page.
    A source behind Incapsula/Cloudflare answers an API request with an HTML
    challenge (often HTTP 200), so this is what tells a block from real content."""
    if "text/html" in content_type:
        return True
    head = body.lstrip()[:800].lower()
    return (
        head.startswith("<")
        or "<!doctype html" in head
        or "incapsula" in body[:4000].lower()
        or "_incapsula_resource" in body[:4000].lower()
        or "request unsuccessful" in head
        or "checking your browser" in head
        or "cf-browser-verification" in head
        or "attention required" in head
    )


def fetch_bytes(url: str, *, timeout: int = 30, accept: str = "*/*") -> tuple[bytes, str, str]:
    """GET *url* → (body, content_type, final_url).

    Tries a DIRECT request first; on a bot-block (HTTP 403/429 or an HTML
    challenge) retries through the rotating proxy when one is configured, a fresh
    IP per attempt. Raises `Blocked` if every attempt is blocked, `FetchError`
    for other HTTP/URL failures."""
    ua = os.environ.get("NZFETCH_UA") or DEFAULT_UA
    proxy = proxy_url()
    openers: list = [None]  # attempt 1 = direct
    if proxy:
        handler = urllib.request.ProxyHandler({"http": proxy, "https": proxy})
        retries = max(1, int(os.environ.get("PROXY_RETRIES", "4")))
        openers += [urllib.request.build_opener(handler)] * retries
    last = "no attempt made"
    for opener in openers:
        req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": accept})
        try:
            resp = opener.open(req, timeout=timeout) if opener else urllib.request.urlopen(req, timeout=timeout)
            body = resp.read()
            content_type = (resp.headers.get("Content-Type") or "").lower()
            final_url = resp.geturl()
        except urllib.error.HTTPError as e:
            if e.code in (403, 429):  # bot-block — rotate to a fresh IP and retry
                last = f"HTTP {e.code}"
                continue
            raise FetchError(f"HTTP {e.code} from {url}") from e
        except urllib.error.URLError as e:
            last = f"network error: {e.reason}"
            continue
        if _looks_like_challenge(body.decode("utf-8", "replace"), content_type):
            last = "bot-challenge interstitial"
            continue  # rotate and retry
        return body, content_type, final_url
    raise Blocked(
        f"{url} blocked after {len(openers)} attempt(s) ({last}). The public source is "
        f"bot-blocking this network; set a rotating FETCH_PROXY to clear it."
    )


def fetch_text(url: str, *, timeout: int = 30, accept: str = "*/*", encoding: str = "utf-8") -> str:
    body, _ct, _final = fetch_bytes(url, timeout=timeout, accept=accept)
    return body.decode(encoding, "replace")


def fetch_json(url: str, *, timeout: int = 30):
    body, content_type, _final = fetch_bytes(url, timeout=timeout, accept="application/json,*/*")
    raw = body.decode("utf-8", "replace")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        # A challenge that returned HTTP 200 + real-looking length can slip past
        # fetch_bytes; catch it here so it reads as a block, not malformed JSON.
        if _looks_like_challenge(raw, content_type):
            raise Blocked(f"{url} returned a non-JSON bot-challenge (blocked, not a dead source).") from e
        raise FetchError(f"invalid JSON from {url}: {e}") from e
