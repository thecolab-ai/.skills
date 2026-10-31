#!/usr/bin/env python3
"""Bounded Genesis My Account reads, derived from an MIT-licensed Genesis client.

See ../LICENSE and ../references/source-notes.md for attribution and limitations.
No credentials, tokens, cookies, response bodies or account identifiers are logged.
"""
from __future__ import annotations

import http.cookiejar
import json
import re
import socket
import urllib.error
import urllib.request
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit

AUTH = "https://auth.genesisenergy.co.nz/auth.genesisenergy.co.nz"
DATA = "https://web-api.genesisenergy.co.nz/v2/private/electricity/site-usage"
REDIRECT = "https://myaccount.genesisenergy.co.nz/auth/redirect"
# Public Genesis website OAuth application identifier, not a user/API secret.
CLIENT_ID = "8e41676f-7601-4490-9786-85d74f387f47"
POLICY = "B2C_1A_signin"
MAX_BODY = 2 * 1024 * 1024


class GenesisError(Exception):
    """Static, deliberately non-sensitive public failure."""

    def __init__(self, code, message, retry_after=None):
        super().__init__(message)
        self.code, self.retry_after = code, retry_after


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Transport:
    """A private cookie jar, verified TLS, no automatic redirect or proxy."""

    def __init__(self):
        self.cookies = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}), NoRedirect(),
            urllib.request.HTTPCookieProcessor(self.cookies),
        )

    def request(self, method, url, *, form=None, payload=None, headers=None):
        parsed = urlsplit(url)
        auth_origin = (parsed.scheme, parsed.netloc) == ("https", "auth.genesisenergy.co.nz")
        if not (auth_origin or url == DATA):
            raise GenesisError(4, "Unexpected Genesis destination")
        body = None
        request_headers = {"User-Agent": "genesis-energy-nz/1", **(headers or {})}
        if form is not None:
            body = urlencode(form).encode()
            request_headers["Content-Type"] = "application/x-www-form-urlencoded"
        elif payload is not None:
            body = json.dumps(payload).encode()
            request_headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=body, headers=request_headers, method=method)
        try:
            try:
                response = self.opener.open(request, timeout=30)
            except urllib.error.HTTPError as exc:
                response = exc
            with response:
                status = response.code
                if status in (401, 403):
                    raise GenesisError(4, "Genesis access rejected; sign-in may need user interaction")
                if status == 429:
                    retry = response.headers.get("Retry-After", "")
                    # Never echo an arbitrary header; only a short delay in seconds.
                    retry = retry if re.fullmatch(r"[0-9]{1,8}", retry) else None
                    raise GenesisError(4, "Genesis rate limit; retry later", retry)
                if status not in (200, 302, 303, 400):
                    raise GenesisError(5, "Unexpected Genesis HTTP status")
                raw = response.read(MAX_BODY + 1)
                if len(raw) > MAX_BODY:
                    raise GenesisError(6, "Genesis response exceeds the size limit")
                return status, raw.decode("utf-8"), response.headers
        except (urllib.error.URLError, OSError, socket.timeout, UnicodeError, ValueError):
            raise GenesisError(5, "Cannot read Genesis response") from None


def object_json(body):
    try:
        result = json.loads(body)
        if not isinstance(result, dict):
            raise ValueError
        return result
    except (ValueError, TypeError, RecursionError):
        raise GenesisError(6, "Genesis response schema changed") from None


class Client:
    """One invocation, one login, and a fixed electricity read endpoint."""

    def __init__(self, transport=None):
        self.transport = transport if transport is not None else Transport()
        self.token = None

    def request(self, method, url, **kwargs):
        return self.transport.request(method, url, **kwargs)

    def navigate(self, url):
        for _ in range(5):
            status, body, headers = self.request("GET", url)
            if status == 200:
                return body
            if status not in (302, 303):
                raise GenesisError(4, "Genesis sign-in needs user interaction")
            url = urljoin(url, headers.get("Location", ""))
            parsed = urlsplit(url)
            if (parsed.scheme, parsed.netloc) != ("https", "auth.genesisenergy.co.nz"):
                raise GenesisError(4, "Unexpected Genesis login redirect")
        raise GenesisError(4, "Too many Genesis login redirects")

    def assertion(self, params, csrf, form):
        status, body, _ = self.request(
            "POST", f"{AUTH}/{POLICY}/SelfAsserted?{urlencode(params)}",
            headers={"X-CSRF-TOKEN": csrf}, form=form,
        )
        if status not in (200, 400) or str(object_json(body).get("status")) != "200":
            raise GenesisError(4, "Genesis sign-in rejected or requires user interaction")

    def authenticate(self, email, password):
        scope = f"openid offline_access {CLIENT_ID}"
        body = self.navigate(f"{AUTH}/oauth2/v2.0/authorize?" + urlencode({
            "p": POLICY, "client_id": CLIENT_ID, "response_type": "code",
            "response_mode": "query", "scope": scope, "redirect_uri": REDIRECT,
        }))
        try:
            match = re.search(r"var\s+SETTINGS\s*=\s*", body)
            if not match:
                raise ValueError
            settings, _ = json.JSONDecoder().raw_decode(body[match.end():])
            tx, csrf = settings["transId"], settings["csrf"]
            if not all(isinstance(value, str) and value for value in (tx, csrf)):
                raise ValueError
        except (ValueError, KeyError, TypeError, RecursionError):
            raise GenesisError(6, "Genesis login page changed or requires user interaction") from None
        params = {"tx": tx, "p": POLICY}
        self.assertion(params, csrf, {"request_type": "RESPONSE", "email": email})
        self.navigate(f"{AUTH}/{POLICY}/api/SelfAsserted/confirmed?" + urlencode({
            **params, "csrf_token": csrf,
        }))
        # The password page rotates CSRF. Match a cookie applicable to AUTH,
        # rather than accepting an unrelated cookie with the same name.
        cookie_request = urllib.request.Request(f"{AUTH}/{POLICY}/SelfAsserted")
        self.transport.cookies.add_cookie_header(cookie_request)
        from http.cookies import SimpleCookie
        cookies = SimpleCookie(cookie_request.get_header("Cookie", ""))
        cookie = cookies.get("x-ms-cpim-csrf")
        if cookie is None or not cookie.value:
            raise GenesisError(6, "Genesis login cookie missing")
        csrf = cookie.value
        self.assertion(params, csrf, {
            "request_type": "RESPONSE", "signInName": email, "password": password,
        })
        status, _, headers = self.request(
            "GET", f"{AUTH}/{POLICY}/api/CombinedSigninAndSignup/confirmed?" + urlencode({
                "rememberMe": "false", "csrf_token": csrf, **params,
            }),
        )
        location = urlsplit(headers.get("Location", ""))
        target = urlsplit(REDIRECT)
        if status not in (302, 303) or (location.scheme, location.netloc, location.path) != (
            target.scheme, target.netloc, target.path,
        ):
            raise GenesisError(4, "Unexpected Genesis authorization redirect")
        query = parse_qs(location.query)
        codes = query.get("code", [])
        if query.get("error") or len(codes) != 1 or not codes[0]:
            raise GenesisError(4, "Genesis authorization rejected")
        status, body, _ = self.request("POST", f"{AUTH}/{POLICY}/oauth2/v2.0/token", form={
            "p": POLICY, "grant_type": "authorization_code", "client_id": CLIENT_ID,
            "scope": scope, "redirect_uri": REDIRECT, "code": codes[0],
        })
        result = object_json(body)
        if status != 200 or result.get("error"):
            raise GenesisError(4, "Genesis token exchange rejected")
        token = result.get("access_token")
        if not isinstance(token, str) or not token or any(c.isspace() for c in token):
            raise GenesisError(6, "Genesis token response changed")
        self.token = token
        # Refresh tokens are deliberately not retained or persisted.

    def electricity(self, start, end):
        if not self.token:
            raise GenesisError(3, "Genesis sign-in required")
        status, body, _ = self.request("POST", DATA, payload={
            "startDate": start.isoformat(), "endDate": end.isoformat(), "intervalType": "HOURLY",
        }, headers={"Authorization": f"Bearer {self.token}"})
        if status != 200:
            raise GenesisError(5, "Genesis electricity request failed")
        return object_json(body)
