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

nzfetch owns the browser fingerprint. Every request carries a consistent current
Chrome header set by default (User-Agent + matching sec-ch-ua / Sec-Fetch-* /
Accept-Language / Priority). A skill should NOT pass its own fingerprint headers:
a skill User-Agent or sec-ch-ua that disagrees with the rest of the set is itself
a bot signal. Pass ``headers={...}`` only for SEMANTIC headers a source needs (an
API key, Authorization, Referer, Content-Type, X-Requested-With) — those merge
over the defaults and win. nzfetch stays fully capable of overrides: set
``NZFETCH_UA`` for the User-Agent, pass any header in ``headers=`` (it wins), or
use ``browser_headers=False`` for a lean set — but default to nzfetch's headers
wherever they already work.

Environment (all optional):
    FETCH_PROXY / HTTPS_PROXY   rotating proxy URL, e.g. http://user:pass@host:port
                               — a SECRET. Never hard-code it, never print it, never
                               commit it. nzfetch reads it from the env only.
    PROXY_RETRIES              retries through the proxy on a block or a truncated
                               read (default 3). A rotating pool gets a fresh IP each
                               retry; a single-IP proxy just re-attempts (which still
                               clears transient truncations). Raise it for a stubborn
                               wall or a proxy that often truncates large responses.
    NZFETCH_UA                 override the User-Agent if a source needs a specific one.

No proxy set → nzfetch just does the single direct request (same as before), so a
skill that imports it keeps working unchanged when no proxy is configured.
"""
from __future__ import annotations

import gzip
import http.client
import json
import os
import urllib.error
import urllib.parse
import urllib.request
import zlib

# Keep the UA version and the sec-ch-ua brand list in sync — a real Chrome sends a
# UA and Client-Hints that agree, and a mismatch is itself a bot signal. Bump this
# one constant to track current stable Chrome. Values below mirror a real Chrome
# request captured from DevTools (macOS, Chrome 149).
CHROME_VERSION = "149"
DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    f"(KHTML, like Gecko) Chrome/{CHROME_VERSION}.0.0.0 Safari/537.36"
)
# The GREASE-style brand list Chrome 149 emits (order + the "Not)A;Brand" token
# match the real header exactly).
SEC_CH_UA = f'"Google Chrome";v="{CHROME_VERSION}", "Chromium";v="{CHROME_VERSION}", "Not)A;Brand";v="24"'


def _browser_headers(url: str, accept: str) -> dict:
    """A realistic current-Chrome request header set. Beyond the User-Agent it
    sends the language, encoding, cache, and Client-Hint / Sec-Fetch-* headers a
    real browser does, and a same-origin Referer — which clears a lot of
    fingerprint-based bot walls at the HTTP layer. Sec-Fetch-* + Accept adapt to
    a document navigation vs an API/asset request.

    NOTE: this cannot change urllib's TLS ClientHello fingerprint (a Python
    signature some advanced WAFs still detect) — for those, the stealth browser
    (fetch.mjs's cloak rung) remains the strongest bypass. Browser-shaped headers
    plus a rotating IP clear the common cases."""
    ua = os.environ.get("NZFETCH_UA") or DEFAULT_UA
    try:
        p = urllib.parse.urlparse(url)
        origin = f"{p.scheme}://{p.netloc}" if p.scheme and p.netloc else ""
    except Exception:
        origin = ""
    is_doc = "text/html" in accept or accept in ("*/*", "")
    h = {
        "User-Agent": ua,
        "Accept": accept if accept else "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate",  # only what we can decode in stdlib
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "sec-ch-ua": SEC_CH_UA,
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"macOS"',
        # Chrome's Fetch Priority hint: u=0 (highest) for a document navigation,
        # u=1 for an API/subresource fetch. Matches a real request exactly.
        "Priority": "u=0, i" if is_doc else "u=1, i",
        "Sec-Fetch-Dest": "document" if is_doc else "empty",
        "Sec-Fetch-Mode": "navigate" if is_doc else "cors",
        "Sec-Fetch-Site": "same-origin",
    }
    if is_doc:
        h["Upgrade-Insecure-Requests"] = "1"
    if origin:
        h["Referer"] = origin + "/"
    return h


def _minimal_headers(accept: str) -> dict:
    """A LEAN header set — just a browser-ish User-Agent, Accept, language and
    encoding, like a plain urllib request. Some hosts return a clean 200 to a bare
    request but trip a fingerprint bot-wall on the full Client-Hint / Sec-Fetch-*
    set in `_browser_headers` (observed on Interislander / Bluebridge / Eventfinda
    / Auckland Leisure). For those, pass ``browser_headers=False`` so the fetch
    still gets nzfetch's rotating-proxy fallback WITHOUT the headers that make it
    strictly worse than plain urllib."""
    ua = os.environ.get("NZFETCH_UA") or DEFAULT_UA
    return {
        "User-Agent": ua,
        "Accept": accept if accept else "*/*",
        "Accept-Language": "en-NZ,en;q=0.8",
        "Accept-Encoding": "gzip, deflate",
    }


def _decompress(body: bytes, content_encoding: str | None) -> bytes:
    """Decode gzip/deflate we asked for in Accept-Encoding. On any decode error,
    return the bytes unchanged (challenge detection still works on raw bytes)."""
    enc = (content_encoding or "").lower()
    try:
        if "gzip" in enc:
            return gzip.decompress(body)
        if "deflate" in enc:
            try:
                return zlib.decompress(body)
            except zlib.error:
                return zlib.decompress(body, -zlib.MAX_WBITS)  # raw deflate stream
    except Exception:
        return body
    return body


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


# Reliable bot-wall fingerprints — a real page NEVER contains these, so they flag
# a challenge regardless of content type (safe for HTML/XML sources).
_CHALLENGE_MARKERS = (
    "incapsula",
    "_incapsula_resource",
    "request unsuccessful",
    "checking your browser",
    "cf-browser-verification",
    "cf-chl-",
    "cf_chl_",
    "attention required",
    "just a moment",
    "verifying you are human",
    "verify you are human",
    "enable javascript and cookies to continue",
    "performing security verification",
    "ddos protection by",
    "unusual traffic from your",
    # AWS WAF challenge / CAPTCHA shell (served at HTTP 200, so status alone
    # misses it; without these an AWS-WAF-walled API reads as an empty success —
    # the ADR-0006 mirror risk. Seen on eventfinda.co.nz and some *.govt.nz).
    "token.awswaf.com",
    "awswaf",
    "gokuprops",
)


def _looks_like_challenge(body: str, content_type: str, *, expected_json: bool = False) -> bool:
    """True if the response is a bot-wall interstitial rather than the real page.

    Two signals: (1) a reliable challenge fingerprint anywhere in the body — a
    real page never contains these; (2) ONLY when the caller expected JSON, an
    HTML body / markup (an API answering with an interstitial instead of data).
    Plain HTML or XML on its own is NOT flagged — legitimate HTML-scraper and
    OData/RSS/XML skills fetch exactly that."""
    low = body[:6000].lower()
    if any(m in low for m in _CHALLENGE_MARKERS):
        return True
    if expected_json:
        head = body.lstrip()[:1]
        # Actual JSON despite a mislabelled text/html Content-Type (several NZ
        # govt APIs do this) is NOT a challenge.
        if head in ("{", "["):
            return False
        # An API that answers with markup instead of data is a challenge.
        if head == "<" or "text/html" in content_type:
            return True
    return False


def fetch_bytes(
    url: str,
    *,
    timeout: int = 30,
    accept: str = "*/*",
    headers: dict | None = None,
    data: bytes | None = None,
    method: str | None = None,
    context=None,
    expect_json: bool | None = None,
    browser_headers: bool = True,
) -> tuple[bytes, str, str]:
    """Fetch *url* → (body, content_type, final_url). GET by default; pass
    ``data`` (bytes) for a POST. A full drop-in for a skill's own
    ``urllib.request`` call:

    - ``headers`` — extra request headers (e.g. an API key / Authorization),
      merged OVER the default browser User-Agent + Accept (so callers can
      override either). Auth headers are preserved through the proxy.
    - ``data`` / ``method`` — request body / HTTP method for non-GET calls.
    - ``context`` — a custom ``ssl.SSLContext`` if a source needs one.
    - ``expect_json`` — whether an HTML/markup body should count as a bot-wall
      interstitial (an API answering a challenge instead of data). ``None``
      (default) infers it from the ``accept`` string (``"json"`` present). The
      typed entrypoints set it EXPLICITLY: ``fetch_text`` passes ``False`` so a
      real HTML/XML page is never mis-flagged no matter what ``accept`` it sends,
      and ``fetch_json`` passes ``True``. This removes the footgun where an HTML
      fetch that left ``application/json`` in ``accept`` got its real page flagged.
    - ``browser_headers`` — ``True`` (default) sends the full Chrome header set;
      ``False`` sends only a lean UA + Accept + language + encoding. Use ``False``
      for the few hosts that 200 on a bare request but bot-wall the full
      Client-Hint / Sec-Fetch-* set — the fetch still gets the rotating-proxy
      fallback without the headers that make it worse than plain urllib.

    Tries a DIRECT request first; on a bot-block (HTTP 403/429 or an HTML
    challenge) retries through the rotating proxy when one is configured, a fresh
    IP per attempt. Raises ``Blocked`` if every attempt is blocked, ``FetchError``
    for other HTTP/URL failures."""
    hdrs = _browser_headers(url, accept) if browser_headers else _minimal_headers(accept)
    if headers:
        hdrs.update(headers)  # caller headers (API key, auth, custom UA/Accept) win
    # Whether an HTML body counts as a challenge. Explicit from the entrypoint
    # (fetch_text=False, fetch_json=True) when given; else inferred from accept.
    expects_json = expect_json if expect_json is not None else ("json" in (accept or "").lower())
    proxy = proxy_url()
    openers: list = [None]  # attempt 1 = direct (urlopen, which accepts context=)
    if proxy:
        handler = urllib.request.ProxyHandler({"http": proxy, "https": proxy})
        # A custom SSL context must be baked into an HTTPSHandler on the opener —
        # OpenerDirector.open() does NOT accept a context= kwarg (passing it raises
        # TypeError), so it can't be forwarded per-call like urlopen's.
        extra = [urllib.request.HTTPSHandler(context=context)] if context is not None else []
        retries = max(1, int(os.environ.get("PROXY_RETRIES", "3")))
        openers += [urllib.request.build_opener(handler, *extra)] * retries
    # context= only goes to the direct urlopen; the proxy openers carry it in their handler.
    direct_kw = {"timeout": timeout}
    if context is not None:
        direct_kw["context"] = context
    last = "no attempt made"
    for opener in openers:
        req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
        try:
            resp = opener.open(req, timeout=timeout) if opener else urllib.request.urlopen(req, **direct_kw)
            body = _decompress(resp.read(), resp.headers.get("Content-Encoding"))
            content_type = (resp.headers.get("Content-Type") or "").lower()
            final_url = resp.geturl()
        except urllib.error.HTTPError as e:
            # WAF bot-walls: 403/429 classic, 406 is Akamai's "Not Acceptable"
            # bot block (seen on aucklandcouncil.govt.nz — a bare curl gets it
            # too), 451 some edge WAFs. Rotate to a fresh IP and retry; if every
            # attempt hits it, it surfaces as Blocked (SKIP-able / not a defect).
            if e.code in (403, 406, 429, 451):
                last = f"HTTP {e.code}"
                continue
            raise FetchError(f"HTTP {e.code} from {url}") from e
        except urllib.error.URLError as e:
            last = f"network error: {e.reason}"
            continue
        except (TimeoutError, OSError) as e:  # bare socket timeout / connection reset
            last = f"network error: {e}"
            continue
        except http.client.HTTPException as e:
            # A truncated / malformed response body — most often
            # http.client.IncompleteRead when a chunked response is cut off
            # mid-stream (common through a proxy on a large body). Transient:
            # retry (a fresh connection / IP usually completes it).
            last = f"network error: incomplete read ({type(e).__name__})"
            continue
        if _looks_like_challenge(body.decode("utf-8", "replace"), content_type, expected_json=expects_json):
            last = "bot-challenge interstitial"
            continue  # rotate and retry
        return body, content_type, final_url
    raise Blocked(
        f"{url} blocked after {len(openers)} attempt(s) ({last}). The public source is "
        f"bot-blocking this network; set a rotating FETCH_PROXY to clear it."
    )


def fetch_text(url: str, *, encoding: str = "utf-8", **kw) -> str:
    # Text/HTML/XML callers never want their real page read as a JSON challenge.
    kw.setdefault("expect_json", False)
    body, _ct, _final = fetch_bytes(url, **kw)
    return body.decode(encoding, "replace")


def fetch_json(url: str, **kw):
    kw.setdefault("accept", "application/json,*/*")
    kw.setdefault("expect_json", True)  # an HTML answer here IS a challenge
    body, content_type, _final = fetch_bytes(url, **kw)
    raw = body.decode("utf-8", "replace")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        # A challenge that returned HTTP 200 + real-looking length can slip past
        # fetch_bytes; catch it here so it reads as a block, not malformed JSON.
        if _looks_like_challenge(raw, content_type, expected_json=True):
            raise Blocked(f"{url} returned a non-JSON bot-challenge (blocked, not a dead source).") from e
        raise FetchError(f"invalid JSON from {url}: {e}") from e
