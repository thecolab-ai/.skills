#!/usr/bin/env python3
"""New World NZ CLI — public catalogue and authenticated account lookup.

Generated after sniffing newworld.co.nz with Hermes+CloakBrowser CDP. Unofficial.
"""
from __future__ import annotations

import argparse
import base64
import http.cookiejar
import json
import math
import os
import sys
import textwrap
import time
import pathlib
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "lib"))
import nzfetch  # noqa: E402

BASE_WEB = "https://www.newworld.co.nz"
BASE_API = "https://api-prod.newworld.co.nz/v1/edge"
CLUBPLUS_WEB = "https://login.clubplus.co.nz"
CLUBPLUS_API = "https://api-prod.clubplus.co.nz/retail-fsl-online-edge"
AUTH_ALLOWED_HOSTS = frozenset(
    {"login.clubplus.co.nz", "api-prod.clubplus.co.nz", "api-prod.newworld.co.nz", "www.newworld.co.nz"}
)
DEFAULT_STORE_ID = os.environ.get("NEWWORLD_STORE_ID", "ef977d89-f3d8-4e8b-8a48-b895ded38646")  # New World Papakura
CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))) / "newworld-cli"
TOKEN_FILE = CACHE_DIR / "guest-token.json"
AUTH_FILE = Path(os.environ.get("NEWWORLD_AUTH_FILE", str(CACHE_DIR / "auth.json"))).expanduser()
UA = os.environ.get(
    "NEWWORLD_USER_AGENT",
    nzfetch.DEFAULT_UA,
)


def account_commands_enabled(env: Any = None) -> bool:
    """Expose personal commands only when the provider credential pair is present."""
    source = os.environ if env is None else env
    username = source.get("NEWWORLD_USERNAME") or source.get("NEWWORLD_EMAIL")
    return bool(username and source.get("NEWWORLD_PASSWORD"))


class AuthHTTPError(Exception):
    def __init__(self, status: int, code: str = "", message: str = ""):
        super().__init__(message or code or f"HTTP {status}")
        self.status = status
        self.code = code
        self.message = message


def die(msg: str, code: int = 1) -> None:
    print(f"newworld: {msg}", file=sys.stderr)
    raise SystemExit(code)


def money(cents: Any) -> str:
    try:
        return f"${int(cents) / 100:.2f}"
    except Exception:
        return "-"


def request_json(method: str, url: str, data: Any = None, token: str | None = None, timeout: int = 30) -> Any:
    body = None
    headers = {
        "Origin": BASE_WEB,
        "Referer": BASE_WEB + "/",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"
    try:
        raw_bytes, _ct, _final = nzfetch.fetch_bytes(
            url,
            timeout=timeout,
            accept="application/json, text/plain, */*",
            headers=headers,
            data=body,
            method=method.upper(),
            allowed_hosts=AUTH_ALLOWED_HOSTS,
        )
    except nzfetch.Blocked as e:
        die(f"network error calling {url}: {e}")
    except nzfetch.FetchError as e:
        die(str(e))
    raw = raw_bytes.decode("utf-8", "replace")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        die(f"invalid JSON from {url}: {e}")


def get_guest_token(force: bool = False) -> str:
    if not force and TOKEN_FILE.exists():
        try:
            cached = json.loads(TOKEN_FILE.read_text())
            if cached.get("access_token") and cached.get("expires_epoch", 0) > time.time() + 60:
                return cached["access_token"]
        except Exception:
            pass
    fingerprint_user = os.environ.get("NEWWORLD_FINGERPRINT_USER", "newworld-cli")
    payload = {"fingerprintUser": fingerprint_user, "fingerprintGuest": UA}
    data = request_json("POST", BASE_WEB + "/api/user/get-current-user", payload)
    token = data.get("access_token") if isinstance(data, dict) else None
    if not token:
        die("could not obtain guest access token")
    expires = data.get("expires_time") or ""
    # Tokens are typically 30 minutes. Avoid needing date parsing deps.
    expires_epoch = time.time() + 25 * 60
    write_private_json(
        TOKEN_FILE,
        {"access_token": token, "expires_time": expires, "expires_epoch": expires_epoch},
    )
    return token


def api(method: str, path: str, data: Any = None) -> Any:
    token = get_guest_token()
    return request_json(method, BASE_API + path, data, token=token)


def jwt_payload(token: str) -> dict[str, Any]:
    """Decode unverified JWT claims for expiry/status hints only."""
    try:
        part = token.split(".")[1]
        part += "=" * (-len(part) % 4)
        value = json.loads(base64.urlsafe_b64decode(part).decode("utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def write_private_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        path.parent.chmod(0o700)
    except OSError:
        pass
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2)
            handle.write("\n")
        os.replace(temporary, path)
        path.chmod(0o600)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def read_auth_cache() -> dict[str, Any]:
    try:
        value = json.loads(AUTH_FILE.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_auth_tokens(
    access_token: str,
    refresh_token: str,
    device_id: str | None = None,
    *,
    refresh_kind: str = "newworld",
) -> dict[str, Any]:
    claims = jwt_payload(access_token)
    try:
        access_expires = int(claims.get("exp") or time.time() + 25 * 60)
    except (TypeError, ValueError):
        access_expires = int(time.time() + 25 * 60)
    value = {
        "access_token": access_token,
        "access_expires_epoch": access_expires,
        "refresh_expires_epoch": int(time.time() + 14 * 24 * 60 * 60),
        "device_id": device_id or read_auth_cache().get("device_id") or str(uuid.uuid4()),
    }
    if refresh_kind == "clubplus":
        value["clubplus_refresh_token"] = refresh_token
    else:
        value["refresh_token"] = refresh_token
    write_private_json(AUTH_FILE, value)
    return value


def _validate_auth_url(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").lower()
    if (
        parsed.scheme != "https"
        or host not in AUTH_ALLOWED_HOSTS
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in (None, 443)
    ):
        raise AuthHTTPError(0, "UNSAFE_AUTH_URL", "auth request host is not allowlisted")


class _AuthRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _validate_auth_url(newurl)
        old_host = (urllib.parse.urlparse(req.full_url).hostname or "").lower()
        new_host = (urllib.parse.urlparse(newurl).hostname or "").lower()
        if new_host != old_host:
            raise AuthHTTPError(0, "UNSAFE_AUTH_REDIRECT", "cross-host auth redirect was rejected")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def auth_http(
    method: str,
    url: str,
    data: Any = None,
    *,
    token: str | None = None,
    extra_headers: dict[str, str] | None = None,
    read_body: bool = True,
    opener: Any = None,
) -> tuple[Any, Any]:
    """Credential-bearing request with an exact-host redirect allowlist."""
    _validate_auth_url(url)
    parsed = urllib.parse.urlparse(url)
    is_clubplus = parsed.hostname and parsed.hostname.endswith("clubplus.co.nz")
    origin = CLUBPLUS_WEB if is_clubplus else BASE_WEB
    headers = {
        "User-Agent": UA,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-NZ,en;q=0.8",
        "Origin": origin,
        "Referer": origin + "/",
        "sec-ch-ua": nzfetch.SEC_CH_UA,
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"macOS"',
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if extra_headers:
        headers.update(extra_headers)
    request = urllib.request.Request(url, data=body, headers=headers, method=method.upper())
    opener = opener or urllib.request.build_opener(_AuthRedirectHandler())
    try:
        with opener.open(request, timeout=30) as response:
            raw = response.read() if read_body else b""
            response_headers = response.headers
            response_status = response.status
        if not raw:
            return None, response_headers
        try:
            return json.loads(raw.decode("utf-8", "replace")), response_headers
        except json.JSONDecodeError as exc:
            raise AuthHTTPError(response_status, "INVALID_JSON", "auth service returned invalid JSON") from exc
    except urllib.error.HTTPError as exc:
        raw = exc.read(32_768)
        payload: Any = {}
        try:
            payload = json.loads(raw.decode("utf-8", "replace"))
        except json.JSONDecodeError:
            pass
        error_code = ""
        message = ""
        if isinstance(payload, dict):
            error_code = str(payload.get("code") or payload.get("error") or "")
            message = str(payload.get("message") or payload.get("error_description") or "")
        raise AuthHTTPError(exc.code, error_code, message) from exc
    except urllib.error.URLError as exc:
        raise AuthHTTPError(0, "NETWORK_ERROR", str(exc.reason)) from exc
    except (TimeoutError, OSError) as exc:
        raise AuthHTTPError(0, "NETWORK_ERROR", str(exc)) from exc


def get_apigee_token() -> str:
    data, _headers = auth_http("GET", CLUBPLUS_WEB + "/api/apigee-credentials")
    token = data.get("access_token") if isinstance(data, dict) else None
    if not token:
        die("Club+ credential bootstrap did not return a token")
    return str(token)


def exchange_for_newworld_tokens(access_token: str, refresh_token: str, device_id: str) -> dict[str, Any]:
    secure, _headers = auth_http(
        "POST",
        CLUBPLUS_API + "/user/token/secure",
        {"banner": "MNW", "source": "WEB"},
        token=access_token,
    )
    code = secure.get("secure_token") if isinstance(secure, dict) else None
    if not code:
        die("Club+ did not return a New World secure token")

    cookie_jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(_AuthRedirectHandler(), urllib.request.HTTPCookieProcessor(cookie_jar))
    callback_url = BASE_WEB + "/auth/callback?" + urllib.parse.urlencode({"code": code})
    auth_http("GET", callback_url, read_body=False, opener=opener)
    fingerprint_user = os.environ.get("NEWWORLD_FINGERPRINT_USER") or device_id
    sso_payload = {
        "key": code,
        "forceNewSession": False,
        "fingerprintUser": fingerprint_user,
        "fingerprintGuest": UA,
    }
    sso, _headers = auth_http(
        "POST",
        BASE_WEB + "/api/user/login/sso",
        sso_payload,
        opener=opener,
    )
    if isinstance(sso, dict) and sso.get("statusCode") == 409:
        sso_payload["forceNewSession"] = True
        sso, _headers = auth_http(
            "POST",
            BASE_WEB + "/api/user/login/sso",
            sso_payload,
            opener=opener,
        )
    if isinstance(sso, dict) and sso.get("statusCode") not in (None, 200):
        die(f"New World SSO exchange failed (HTTP {sso.get('statusCode')})")
    edge_access = next(
        (cookie.value for cookie in cookie_jar if cookie.name == "fs-user-token"),
        None,
    )
    claims = jwt_payload(edge_access or "")
    if not edge_access or claims.get("email") == "anonymous":
        die("New World rejected the Club+ token exchange; no authenticated token was issued")
    return save_auth_tokens(
        edge_access,
        refresh_token,
        device_id,
        refresh_kind="clubplus",
    )


def finish_clubplus_login(result: dict[str, Any], device_id: str) -> dict[str, Any]:
    access = result.get("access_token")
    refresh = result.get("refresh_token")
    if not access:
        die("Club+ login response did not include an access token")
    if result.get("isTFARequired"):
        pending = {
            "pending_mfa": True,
            "half_access_token": access,
            "phv_token": result.get("phvToken"),
            "device_id": device_id,
            "pending_expires_epoch": int(time.time() + 10 * 60),
        }
        write_private_json(AUTH_FILE, pending)
        code = os.environ.get("NEWWORLD_MFA_CODE")
        if code:
            return complete_mfa(code)
        die(
            "Club+ requires MFA. Set NEWWORLD_MFA_CODE to the 6-digit code and run `auth mfa`.",
            3,
        )
    if result.get("isEmailVerified") is False:
        die("Club+ requires email verification; complete that once in the New World login page", 3)
    if not refresh:
        die("Club+ login response did not include a refresh token")
    return exchange_for_newworld_tokens(str(access), str(refresh), device_id)


def login_account() -> dict[str, Any]:
    username = os.environ.get("NEWWORLD_USERNAME") or os.environ.get("NEWWORLD_EMAIL")
    password = os.environ.get("NEWWORLD_PASSWORD")
    if not username or not password:
        die("set NEWWORLD_USERNAME and NEWWORLD_PASSWORD to log in", 2)
    cached = read_auth_cache()
    device_id = str(cached.get("device_id") or uuid.uuid4())
    try:
        result, _headers = auth_http(
            "POST",
            CLUBPLUS_API + "/user/login",
            {"email": username, "password": password, "source": "WEB"},
            token=get_apigee_token(),
            extra_headers={"x-device-id": device_id},
        )
    except AuthHTTPError as exc:
        if exc.status == 401 and exc.code == "INVALID_EMAIL_OR_PASSWORD":
            die("Club+ rejected the username or password", 2)
        if exc.status in (403, 429):
            die("Club+ temporarily blocked login after too many attempts; try later", 2)
        die(f"Club+ login failed ({exc.code or 'HTTP ' + str(exc.status)})", 2)
    if not isinstance(result, dict):
        die("Club+ login returned an unexpected response")
    return finish_clubplus_login(result, device_id)


def complete_mfa(code: str | None = None) -> dict[str, Any]:
    cached = read_auth_cache()
    if not cached.get("pending_mfa") or cached.get("pending_expires_epoch", 0) < time.time():
        die("no current MFA login is pending; run `auth login` first", 2)
    code = (code or os.environ.get("NEWWORLD_MFA_CODE") or "").strip()
    if len(code) != 6 or not code.isdigit():
        die("set NEWWORLD_MFA_CODE to the 6-digit Club+ verification code", 2)
    try:
        result, _headers = auth_http(
            "POST",
            CLUBPLUS_API + "/user/tfa/login",
            {"code": code, "phvToken": cached.get("phv_token")},
            token=str(cached.get("half_access_token") or ""),
        )
    except AuthHTTPError as exc:
        if exc.status == 410:
            die("the MFA code is expired or locked; run `auth login` again", 2)
        die("Club+ rejected the MFA code", 2)
    if not isinstance(result, dict):
        die("Club+ MFA returned an unexpected response")
    return finish_clubplus_login(result, str(cached.get("device_id") or uuid.uuid4()))


def refresh_account(refresh_token: str | None = None) -> dict[str, Any]:
    cached = read_auth_cache()
    clubplus_refresh = cached.get("clubplus_refresh_token")
    refresh_token = refresh_token or os.environ.get("NEWWORLD_REFRESH_TOKEN") or cached.get("refresh_token")
    if clubplus_refresh and not refresh_token:
        try:
            result, _headers = auth_http(
                "POST",
                CLUBPLUS_API + "/user/login/refresh",
                {"refreshToken": clubplus_refresh},
                token=get_apigee_token(),
            )
        except AuthHTTPError as exc:
            die(f"Club+ token refresh failed ({exc.code or 'HTTP ' + str(exc.status)}); run `auth login`", 2)
        if not isinstance(result, dict) or not result.get("access_token") or not result.get("refresh_token"):
            die("Club+ token refresh returned an unexpected response")
        return exchange_for_newworld_tokens(
            str(result["access_token"]),
            str(result["refresh_token"]),
            str(cached.get("device_id") or uuid.uuid4()),
        )
    if not refresh_token:
        die("no New World refresh token is available; run `auth login`", 2)
    try:
        result, _headers = auth_http(
            "POST",
            BASE_API + "/user/login/refresh",
            {"sourceApplication": "WEB", "refreshToken": refresh_token, "banner": "MNW"},
        )
    except AuthHTTPError as exc:
        die(f"New World token refresh failed ({exc.code or 'HTTP ' + str(exc.status)}); run `auth login`", 2)
    if not isinstance(result, dict) or not result.get("access_token"):
        die("New World token refresh returned an unexpected response")
    return save_auth_tokens(
        str(result["access_token"]),
        str(result.get("refresh_token") or refresh_token),
        str(cached.get("device_id") or uuid.uuid4()),
    )


def get_account_token(force_refresh: bool = False) -> str:
    env_token = os.environ.get("NEWWORLD_ACCESS_TOKEN")
    if env_token and not force_refresh:
        return env_token
    cached = read_auth_cache()
    token = cached.get("access_token")
    expires = cached.get("access_expires_epoch") or jwt_payload(str(token or "")).get("exp") or 0
    try:
        token_is_fresh = float(expires) > time.time() + 60
    except (TypeError, ValueError):
        token_is_fresh = False
    if token and not force_refresh and token_is_fresh:
        return str(token)
    newworld_refresh = os.environ.get("NEWWORLD_REFRESH_TOKEN") or cached.get("refresh_token")
    if newworld_refresh:
        return str(refresh_account(str(newworld_refresh))["access_token"])
    if cached.get("clubplus_refresh_token"):
        return str(refresh_account()["access_token"])
    if (os.environ.get("NEWWORLD_USERNAME") or os.environ.get("NEWWORLD_EMAIL")) and os.environ.get(
        "NEWWORLD_PASSWORD"
    ):
        return str(login_account()["access_token"])
    die("account authentication required; set New World credentials and run `auth login`", 2)


def account_api(method: str, path: str, data: Any = None) -> Any:
    url = BASE_API + path
    token = get_account_token()
    try:
        result, _headers = auth_http(method, url, data, token=token)
        return result
    except AuthHTTPError as exc:
        if exc.status == 401:
            try:
                result, _headers = auth_http(method, url, data, token=get_account_token(force_refresh=True))
                return result
            except AuthHTTPError as retry_exc:
                exc = retry_exc
        die(f"New World account request failed ({exc.code or 'HTTP ' + str(exc.status)})")


def positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if number < 1 or number > 100:
        raise argparse.ArgumentTypeError("must be between 1 and 100")
    return number


def positive_quantity(value: str) -> int | float:
    try:
        number = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a number") from exc
    if not math.isfinite(number) or number <= 0 or number > 999:
        raise argparse.ArgumentTypeError("must be greater than 0 and no more than 999")
    return int(number) if number.is_integer() else number


def positive_cart_quantity(value: str) -> int | float:
    try:
        number = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a number") from exc
    if not math.isfinite(number) or number <= 0 or number > 999_000:
        raise argparse.ArgumentTypeError("must be greater than 0 and no more than 999000")
    return int(number) if number.is_integer() else number


def nonempty_list_name(value: str) -> str:
    name = value.strip()
    if not name:
        raise argparse.ArgumentTypeError("must not be empty")
    if any(ord(character) < 32 for character in name):
        raise argparse.ArgumentTypeError("must not contain control characters")
    if len(name) > 100:
        raise argparse.ArgumentTypeError("must be no more than 100 characters")
    return name


def print_json(data: Any) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False))


def cmd_token(args: argparse.Namespace) -> None:
    token = get_guest_token(force=args.refresh)
    if args.json:
        print_json({"ok": True, "token_length": len(token), "cached_at": str(TOKEN_FILE)})
    else:
        print(f"guest token ok ({len(token)} chars, cached at {TOKEN_FILE})")


def cmd_stores(args: argparse.Namespace) -> None:
    data = api("GET", "/store")
    stores = data.get("stores", data if isinstance(data, list) else [])
    q = (args.query or "").lower()
    if q:
        stores = [s for s in stores if q in (s.get("name", "") + " " + s.get("address", "")).lower()]
    if args.json:
        print_json(stores[: args.limit])
        return
    for s in stores[: args.limit]:
        flags = []
        if s.get("clickAndCollect"):
            flags.append("collect")
        if s.get("delivery"):
            flags.append("delivery")
        print(f"{s.get('id')}  {s.get('name')}  ({', '.join(flags) or 'store'})")
        print(f"  {s.get('address')}")


def cmd_categories(args: argparse.Namespace) -> None:
    data = api("GET", f"/store/{args.store_id}/categories")
    if args.json:
        print_json(data)
        return
    def walk(nodes: list[dict], depth: int = 0):
        for n in nodes:
            print("  " * depth + "- " + n.get("name", ""))
            if depth < args.depth:
                walk(n.get("children") or [], depth + 1)
    walk(data)


def product_summary(p: dict[str, Any]) -> str:
    pid = p.get("productId") or p.get("productID") or p.get("objectID") or ""
    brand = p.get("brand") or ""
    name = p.get("name") or p.get("displayName") or ""
    display = p.get("displayName") or ""
    price = "-"
    if p.get("singlePrice"):
        price = money(p["singlePrice"].get("price"))
    elif p.get("averagePrice") is not None:
        # Algolia result can be dollars, decorated result is cents.
        try: price = f"${float(p.get('averagePrice')):.2f}"
        except Exception: pass
    promo = ""
    promos = p.get("promotions") or p.get("promotionBadges") or []
    if promos:
        promo_bits = []
        for x in promos[:2]:
            if isinstance(x, dict):
                desc = x.get("description") or x.get("name") or x.get("decalDescription")
                if not desc and x.get("rewardValue"):
                    desc = f"special {money(x.get('rewardValue'))}"
                if x.get("cardDependencyFlag"):
                    desc = (desc or "special") + " with Clubcard"
                promo_bits.append(desc or "special")
            else:
                promo_bits.append(str(x))
        promo = "  promo: " + "; ".join(promo_bits)
    cat = ""
    trees = p.get("categoryTrees") or []
    if trees:
        t = trees[0]
        cat = " / ".join(x for x in [t.get("level0"), t.get("level1"), t.get("level2")] if x)
    elif p.get("category0"):
        cat = " / ".join((p.get("category0") or [])[:1] + (p.get("category1") or [])[:1] + (p.get("category2") or [])[:1])
    line = f"{pid:18} {price:>8}  {brand} {name} {display}".strip()
    if cat:
        line += f"\n  {cat}"
    if promo:
        line += f"\n  {promo}"
    return line


def search_payload(query: str, store_id: str, limit: int, page: int, promo_only: bool = False, category: str | None = None) -> dict[str, Any]:
    filters = [f"stores:{store_id}"]
    if promo_only:
        filters.append(f"onPromotion:{store_id}")
    if category:
        # Useful for exact Algolia category facet values; command keeps it raw intentionally.
        filters.append(category)
    page0 = max(page - 1, 0)
    return {
        "algoliaQuery": {
            "attributesToHighlight": [],
            "attributesToRetrieve": ["productID", "Type", "sponsored", "category0NI", "category1NI", "category2NI"],
            "facets": ["brand", "category1NI", "onPromotion", "productFacets", "tobacco"],
            "filters": " AND ".join(filters),
            "highlightPostTag": "__/ais-highlight__",
            "highlightPreTag": "__ais-highlight__",
            "hitsPerPage": limit,
            "maxValuesPerFacet": 100,
            "page": page0,
            "query": query,
            "analyticsTags": ["fs#WEB:desktop"],
        },
        "algoliaFacetQueries": [],
        "storeId": store_id,
        "hitsPerPage": limit,
        "page": page0,
        "sortOrder": "NI_POPULARITY_ASC",
        "tobaccoQuery": True,
        "precisionMedia": {
            "adDomain": "SEARCH_PAGE" if query else "CATEGORY_PAGE",
            "adPositions": [4, 8, 12],
            "publishImpressionEvent": False,
            "disableAds": False,
        },
    }


def cmd_search(args: argparse.Namespace) -> None:
    data = api("POST", "/search/paginated/products", search_payload(args.query, args.store_id, args.limit, args.page, args.promo))
    products = data.get("products") or []
    if args.json:
        print_json(data)
        return
    print(f"{len(products)} products for {args.query!r} at store {args.store_id}")
    for p in products:
        print(product_summary(p))


def normalize_product_id(pid: str) -> str:
    pid = pid.strip().upper().replace("_", "-")
    if pid.isdigit():
        return f"{pid}-EA-000"
    if "-" not in pid and len(pid) >= 7:
        return pid
    return pid


def normalize_product_id_for_sale(pid: str, sale_type: str) -> str:
    value = pid.strip()
    if value.isdigit():
        suffix = "KGM" if sale_type == "WEIGHT" else "EA"
        return f"{value}-{suffix}-000"
    return normalize_product_id(value)


def cmd_product(args: argparse.Namespace) -> None:
    ids = [normalize_product_id(x) for x in args.product_ids]
    data = api("POST", f"/store/{args.store_id}/decorateProducts", {"productIds": ids})
    products = data.get("products") or []
    if args.json:
        print_json(data)
        return
    for p in products:
        print(product_summary(p))
        if p.get("description"):
            print("  " + str(p.get("description"))[:300])


def cmd_specials(args: argparse.Namespace) -> None:
    args.query = args.query or ""
    args.promo = True
    cmd_search(args)


def records_from(data: Any, *keys: str) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in keys:
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
            if isinstance(value, dict):
                nested = records_from(value, *keys)
                if nested:
                    return nested
    return []


def first_value(item: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = item.get(key)
        if value not in (None, ""):
            return value
    return ""


def cmd_auth_login(args: argparse.Namespace) -> None:
    result = login_account()
    payload = {
        "authenticated": True,
        "access_expires_epoch": result.get("access_expires_epoch"),
        "refresh_expires_epoch": result.get("refresh_expires_epoch"),
        "cached_at": str(AUTH_FILE),
    }
    if args.json:
        print_json(payload)
    else:
        print(f"New World login complete; rotating tokens cached at {AUTH_FILE}")


def cmd_auth_mfa(args: argparse.Namespace) -> None:
    result = complete_mfa()
    payload = {
        "authenticated": True,
        "access_expires_epoch": result.get("access_expires_epoch"),
        "refresh_expires_epoch": result.get("refresh_expires_epoch"),
        "cached_at": str(AUTH_FILE),
    }
    if args.json:
        print_json(payload)
    else:
        print(f"New World MFA login complete; rotating tokens cached at {AUTH_FILE}")


def cmd_auth_refresh(args: argparse.Namespace) -> None:
    result = refresh_account()
    payload = {
        "authenticated": True,
        "access_expires_epoch": result.get("access_expires_epoch"),
        "refresh_expires_epoch": result.get("refresh_expires_epoch"),
        "cached_at": str(AUTH_FILE),
    }
    if args.json:
        print_json(payload)
    else:
        print(f"New World access token refreshed; cache updated at {AUTH_FILE}")


def cmd_auth_status(args: argparse.Namespace) -> None:
    cached = read_auth_cache()
    env_access = bool(os.environ.get("NEWWORLD_ACCESS_TOKEN"))
    token = os.environ.get("NEWWORLD_ACCESS_TOKEN") or cached.get("access_token")
    expires = jwt_payload(str(token or "")).get("exp") or cached.get("access_expires_epoch")
    try:
        access_is_fresh = float(expires or 0) > time.time()
    except (TypeError, ValueError):
        access_is_fresh = False
    status = {
        "authenticated": bool(token and access_is_fresh),
        "pending_mfa": bool(cached.get("pending_mfa")),
        "access_token_from_environment": env_access,
        "refresh_available": bool(
            os.environ.get("NEWWORLD_REFRESH_TOKEN")
            or cached.get("refresh_token")
            or cached.get("clubplus_refresh_token")
        ),
        "access_expires_epoch": expires,
        "cached_at": str(AUTH_FILE),
        "cache_exists": AUTH_FILE.exists(),
    }
    if args.json:
        print_json(status)
        return
    if status["pending_mfa"]:
        print("MFA verification is pending")
    elif status["authenticated"]:
        print(f"authenticated; access token expires at epoch {expires}")
    elif status["refresh_available"]:
        print("access token expired; a refresh token is available")
    else:
        print("not authenticated")


def cmd_auth_logout(args: argparse.Namespace) -> None:
    try:
        AUTH_FILE.unlink()
        removed = True
    except FileNotFoundError:
        removed = False
    if args.json:
        print_json({"authenticated": False, "cache_removed": removed, "cached_at": str(AUTH_FILE)})
    else:
        print("local New World token cache removed" if removed else "no local New World token cache existed")


def cmd_orders(args: argparse.Namespace) -> None:
    query = urllib.parse.urlencode({"page": args.page, "source": args.source, "size": args.limit})
    data = account_api("GET", "/order/paged?" + query)
    if args.json:
        print_json(data)
        return
    orders = records_from(data, "orders", "items", "results", "content")
    print(f"{len(orders)} order(s)")
    for order in orders:
        order_id = first_value(order, "orderId", "id", "orderNumber")
        date = first_value(order, "orderTimestamp", "orderDate", "createdDate", "createdAt", "date")
        status = first_value(order, "status", "orderStatus", "state")
        source = first_value(order, "source", "orderSource", "type")
        print("  ".join(str(value) for value in (order_id, date, status, source) if value not in (None, "")))


def cmd_order(args: argparse.Namespace) -> None:
    order_id = urllib.parse.quote(args.order_id, safe="")
    if args.source == "IN_STORE":
        data = account_api("GET", "/order/instore?" + urllib.parse.urlencode({"orderId": args.order_id}))
    else:
        data = account_api("GET", f"/order/{order_id}")
    print_json(data)


def cmd_previous_purchases(args: argparse.Namespace) -> None:
    data = account_api(
        "POST",
        "/order/previousPurchases",
        {"excludeCart": not args.include_cart, "maximumResults": args.limit},
    )
    if args.json:
        print_json(data)
        return
    products = records_from(data, "products", "items", "results", "previousPurchases")
    print(f"{len(products)} previous purchase(s)")
    for product in products:
        product_id = first_value(product, "productId", "productID", "id")
        name = first_value(product, "name", "displayName", "productName")
        print("  ".join(str(value) for value in (product_id, name) if value not in (None, "")))


def cmd_lists(args: argparse.Namespace) -> None:
    data = account_api("GET", "/list")
    if args.json:
        print_json(data)
        return
    lists = records_from(data, "lists", "items", "results")
    print(f"{len(lists)} list(s)")
    for item in lists:
        list_id = first_value(item, "listId", "id")
        name = first_value(item, "name", "listName", "title")
        count = first_value(item, "itemCount", "productCount", "count")
        print("  ".join(str(value) for value in (list_id, name, count) if value not in (None, "")))


def cmd_list_detail(args: argparse.Namespace) -> None:
    list_id = urllib.parse.quote(args.list_id, safe="")
    data = account_api("GET", f"/list/{list_id}")
    print_json(data)


def list_product_payload(args: argparse.Namespace, *, quantity: int | float | None = None) -> dict[str, Any]:
    return {
        "productId": normalize_product_id_for_sale(args.product_id, args.sale_type),
        "sale_type": args.sale_type,
        "quantity": args.quantity if quantity is None else quantity,
    }


def print_mutation_result(operation: str, data: Any, *, json_output: bool) -> None:
    payload = {"ok": True, "operation": operation}
    if data is not None:
        payload["result"] = data
    if json_output:
        print_json(payload)
    else:
        print(f"{operation} complete")


def cmd_list_create(args: argparse.Namespace) -> None:
    data = account_api("PUT", "/list", {"name": args.name, "products": []})
    print_mutation_result("list-create", data, json_output=args.json)


def cmd_list_rename(args: argparse.Namespace) -> None:
    list_id = urllib.parse.quote(args.list_id, safe="")
    data = account_api("POST", f"/list/{list_id}/rename", {"name": args.name})
    print_mutation_result("list-rename", data, json_output=args.json)


def cmd_list_delete(args: argparse.Namespace) -> None:
    if not args.yes:
        die("list-delete is destructive; repeat with --yes to confirm", 2)
    list_id = urllib.parse.quote(args.list_id, safe="")
    data = account_api("DELETE", f"/list/{list_id}")
    print_mutation_result("list-delete", data, json_output=args.json)


def cmd_list_add(args: argparse.Namespace) -> None:
    list_id = urllib.parse.quote(args.list_id, safe="")
    data = account_api("POST", f"/list/{list_id}/update-product", list_product_payload(args))
    print_mutation_result("list-add", data, json_output=args.json)


def cmd_list_update(args: argparse.Namespace) -> None:
    list_id = urllib.parse.quote(args.list_id, safe="")
    data = account_api("POST", f"/list/{list_id}/update-product", list_product_payload(args))
    print_mutation_result("list-update", data, json_output=args.json)


def cmd_list_remove(args: argparse.Namespace) -> None:
    if not args.yes:
        die("list-remove is destructive; repeat with --yes to confirm", 2)
    list_id = urllib.parse.quote(args.list_id, safe="")
    data = account_api(
        "POST",
        f"/list/{list_id}/update-product",
        list_product_payload(args, quantity=0),
    )
    print_mutation_result("list-remove", data, json_output=args.json)


def cart_product_payload(
    product_id: str,
    sale_type: str,
    quantity: int | float,
) -> dict[str, Any]:
    try:
        numeric_quantity = float(quantity)
    except (TypeError, ValueError):
        die("cart quantity must be numeric", 2)
    if not math.isfinite(numeric_quantity) or numeric_quantity < 0 or numeric_quantity > 999_000:
        die("cart quantity must be between 0 and 999000", 2)
    if sale_type == "UNITS" and (numeric_quantity > 999 or not numeric_quantity.is_integer()):
        die("UNITS quantity must be a whole number no more than 999", 2)
    return {
        "productId": normalize_product_id_for_sale(product_id, sale_type),
        "sale_type": sale_type,
        "quantity": quantity,
    }


def cart_products(data: Any) -> list[dict[str, Any]]:
    return records_from(data, "products", "items", "results")


def cmd_cart(args: argparse.Namespace) -> None:
    data = account_api("GET", "/cart")
    if args.json:
        print_json(data)
        return
    products = cart_products(data)
    print(f"{len(products)} cart product(s)")
    for product in products:
        product_id = first_value(product, "productId", "id")
        name = first_value(product, "displayName", "name", "productName")
        quantity = first_value(product, "quantity", "totalQuantity")
        sale_type = first_value(product, "sale_type", "saleType")
        print(
            "  ".join(
                str(value)
                for value in (product_id, name, quantity, sale_type)
                if value not in (None, "")
            )
        )


def cmd_cart_add(args: argparse.Namespace) -> None:
    current = account_api("GET", "/cart")
    normalized_id = normalize_product_id_for_sale(args.product_id, args.sale_type)
    existing_quantity: int | float = 0
    for product in cart_products(current):
        product_id = str(first_value(product, "productId", "id"))
        sale_type = str(first_value(product, "sale_type", "saleType"))
        if product_id == normalized_id and sale_type == args.sale_type:
            value = first_value(product, "quantity", "totalQuantity")
            try:
                existing_quantity = float(value)
            except (TypeError, ValueError):
                existing_quantity = 0
            break
    target_quantity = existing_quantity + args.quantity
    if isinstance(target_quantity, float) and target_quantity.is_integer():
        target_quantity = int(target_quantity)
    data = account_api(
        "POST",
        "/cart",
        {"products": [cart_product_payload(normalized_id, args.sale_type, target_quantity)]},
    )
    print_mutation_result("cart-add", data, json_output=args.json)


def cmd_cart_update(args: argparse.Namespace) -> None:
    data = account_api(
        "POST",
        "/cart",
        {"products": [cart_product_payload(args.product_id, args.sale_type, args.quantity)]},
    )
    print_mutation_result("cart-update", data, json_output=args.json)


def cmd_cart_remove(args: argparse.Namespace) -> None:
    if not args.yes:
        die("cart-remove is destructive; repeat with --yes to confirm", 2)
    data = account_api(
        "POST",
        "/cart",
        {"products": [cart_product_payload(args.product_id, args.sale_type, 0)]},
    )
    print_mutation_result("cart-remove", data, json_output=args.json)


def build_parser(include_account: bool | None = None) -> argparse.ArgumentParser:
    if include_account is None:
        include_account = account_commands_enabled()
    scope = (
        "public catalogue, account history, lists, and cart management"
        if include_account
        else "public catalogue lookup"
    )
    account_examples = """
          newworld auth login
          newworld orders --limit 20
          newworld lists
          newworld list-create "Weekly shop"
          newworld list-add <list-id> 5201479
          newworld cart
          newworld cart-add 5201479 --quantity 2
    """ if include_account else """

        Optional account features:
          Set NEWWORLD_USERNAME (or NEWWORLD_EMAIL) and NEWWORLD_PASSWORD
          before launching the CLI to enable them.
    """
    p = argparse.ArgumentParser(
        prog="newworld",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=f"Unofficial New World NZ CLI for {scope}.",
        epilog=textwrap.dedent(f"""
        Defaults:
          store id: {DEFAULT_STORE_ID} (override with --store-id or NEWWORLD_STORE_ID)

        Examples:
          newworld stores --query auckland
          newworld search milk --limit 10
          newworld specials --limit 20
          newworld product 5201479
          newworld categories --depth 2
        {account_examples}
        """),
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("token", help="fetch/cache a guest token")
    sp.add_argument("--refresh", action="store_true")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_token)

    sp = sub.add_parser("stores", help="list New World stores")
    sp.add_argument("--query", "-q", default="", help="filter by name/address")
    sp.add_argument("--limit", "-n", type=int, default=20)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_stores)

    sp = sub.add_parser("categories", help="list categories for a store")
    sp.add_argument("--store-id", default=DEFAULT_STORE_ID)
    sp.add_argument("--depth", type=int, default=2)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_categories)

    sp = sub.add_parser("search", help="search products and prices")
    sp.add_argument("query")
    sp.add_argument("--store-id", default=DEFAULT_STORE_ID)
    sp.add_argument("--limit", "-n", type=int, default=20)
    sp.add_argument("--page", type=int, default=1)
    sp.add_argument("--promo", action="store_true", help="only promotional products")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_search)

    sp = sub.add_parser("specials", help="search promotional products")
    sp.add_argument("query", nargs="?", default="")
    sp.add_argument("--store-id", default=DEFAULT_STORE_ID)
    sp.add_argument("--limit", "-n", type=int, default=20)
    sp.add_argument("--page", type=int, default=1)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_specials)

    sp = sub.add_parser("product", help="decorate product IDs with store-specific price/details")
    sp.add_argument("product_ids", nargs="+")
    sp.add_argument("--store-id", default=DEFAULT_STORE_ID)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_product)

    if not include_account:
        return p

    sp = sub.add_parser("auth", help="manage optional Club+ authentication")
    auth_sub = sp.add_subparsers(dest="auth_cmd", required=True)

    auth_sp = auth_sub.add_parser("login", help="log in using NEWWORLD_USERNAME and NEWWORLD_PASSWORD")
    auth_sp.add_argument("--json", action="store_true")
    auth_sp.set_defaults(func=cmd_auth_login)

    auth_sp = auth_sub.add_parser("mfa", help="complete login using NEWWORLD_MFA_CODE")
    auth_sp.add_argument("--json", action="store_true")
    auth_sp.set_defaults(func=cmd_auth_mfa)

    auth_sp = auth_sub.add_parser("refresh", help="rotate the cached access token")
    auth_sp.add_argument("--json", action="store_true")
    auth_sp.set_defaults(func=cmd_auth_refresh)

    auth_sp = auth_sub.add_parser("status", help="show token availability without printing secrets")
    auth_sp.add_argument("--json", action="store_true")
    auth_sp.set_defaults(func=cmd_auth_status)

    auth_sp = auth_sub.add_parser("logout", help="remove only the local token cache")
    auth_sp.add_argument("--json", action="store_true")
    auth_sp.set_defaults(func=cmd_auth_logout)

    sp = sub.add_parser("orders", help="list previous online and in-store orders")
    sp.add_argument("--page", type=positive_int, default=1)
    sp.add_argument("--limit", "-n", type=positive_int, default=20)
    sp.add_argument("--source", choices=("ALL", "ONLINE", "IN_STORE"), default="ALL")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_orders)

    sp = sub.add_parser("order", help="fetch one previous order")
    sp.add_argument("order_id")
    sp.add_argument("--source", choices=("ONLINE", "IN_STORE"), default="ONLINE")
    sp.add_argument("--json", action="store_true", help="accepted for consistency; order output is JSON")
    sp.set_defaults(func=cmd_order)

    sp = sub.add_parser("previous-purchases", help="fetch products from previous purchases")
    sp.add_argument("--limit", "-n", type=positive_int, default=20)
    sp.add_argument("--include-cart", action="store_true")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_previous_purchases)

    sp = sub.add_parser("lists", help="list personal New World shopping lists")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_lists)

    sp = sub.add_parser("list", help="fetch one personal shopping list")
    sp.add_argument("list_id")
    sp.add_argument("--json", action="store_true", help="accepted for consistency; list output is JSON")
    sp.set_defaults(func=cmd_list_detail)

    sp = sub.add_parser("list-create", help="create an empty personal shopping list")
    sp.add_argument("name", type=nonempty_list_name)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_list_create)

    sp = sub.add_parser("list-rename", help="rename a personal shopping list")
    sp.add_argument("list_id")
    sp.add_argument("name", type=nonempty_list_name)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_list_rename)

    sp = sub.add_parser("list-delete", help="permanently delete a personal shopping list")
    sp.add_argument("list_id")
    sp.add_argument("--yes", action="store_true", help="confirm permanent list deletion")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_list_delete)

    for command, help_text, handler in (
        ("list-add", "add a product to a personal shopping list", cmd_list_add),
        ("list-update", "change a product quantity in a personal shopping list", cmd_list_update),
        ("list-remove", "remove a product from a personal shopping list", cmd_list_remove),
    ):
        sp = sub.add_parser(command, help=help_text)
        sp.add_argument("list_id")
        sp.add_argument("product_id")
        sp.add_argument("--sale-type", choices=("UNITS", "WEIGHT"), default="UNITS")
        if command != "list-remove":
            sp.add_argument("--quantity", type=positive_quantity, default=1)
        else:
            sp.set_defaults(quantity=0)
            sp.add_argument("--yes", action="store_true", help="confirm product removal")
        sp.add_argument("--json", action="store_true")
        sp.set_defaults(func=handler)

    sp = sub.add_parser("cart", help="show the current personal shopping cart")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_cart)

    for command, help_text, handler in (
        ("cart-add", "add a quantity of a product to the shopping cart", cmd_cart_add),
        ("cart-update", "set a product quantity in the shopping cart", cmd_cart_update),
        ("cart-remove", "remove a product from the shopping cart", cmd_cart_remove),
    ):
        sp = sub.add_parser(command, help=help_text)
        sp.add_argument("product_id")
        sp.add_argument("--sale-type", choices=("UNITS", "WEIGHT"), default="UNITS")
        if command != "cart-remove":
            sp.add_argument(
                "--quantity",
                type=positive_cart_quantity,
                default=1,
                help="units for UNITS products; grams for WEIGHT products",
            )
        else:
            sp.set_defaults(quantity=0)
            sp.add_argument("--yes", action="store_true", help="confirm product removal")
        sp.add_argument("--json", action="store_true")
        sp.set_defaults(func=handler)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
