#!/usr/bin/env python3
"""Browser-assisted Woolworths login with a private reusable cookie cache.

Woolworths' Auth0 prompt currently uses a browser challenge, so authentication
cannot be reproduced safely with raw form POSTs. Camoufox is imported lazily:
public catalogue commands and authenticated API calls with a valid cache remain
stdlib-only.
"""
from __future__ import annotations

import asyncio
import json
import os
import pathlib
from typing import Any

BASE_WEB = "https://www.woolworths.co.nz"
SESSION_COOKIE_DOMAINS = {"woolworths.co.nz", ".woolworths.co.nz", "www.woolworths.co.nz"}
LOGIN_URL = (
    BASE_WEB
    + "/api/v1/bff/initiate-oidc-signin?redirectUrl="
    + "https%3A%2F%2Fwww.woolworths.co.nz%2Faccount%2Forders"
)


def _cookie_for_browser(item: dict[str, Any]) -> dict[str, Any] | None:
    if (
        not item.get("name")
        or str(item.get("domain", "")).lower() not in SESSION_COOKIE_DOMAINS
    ):
        return None
    cookie: dict[str, Any] = {
        "name": str(item["name"]),
        "value": str(item.get("value", "")),
        "domain": str(item.get("domain") or ".woolworths.co.nz"),
        "path": str(item.get("path") or "/"),
        "secure": bool(item.get("secure", True)),
        "httpOnly": bool(item.get("httpOnly", False)),
    }
    expires = item.get("expires")
    if isinstance(expires, (int, float)) and expires > 0:
        cookie["expires"] = expires
    same_site = item.get("sameSite")
    if same_site in {"Strict", "Lax", "None"}:
        cookie["sameSite"] = same_site
    return cookie


async def _load_cookies(context: Any, path: pathlib.Path) -> None:
    if not path.exists():
        return
    try:
        payload = json.loads(path.read_text())
        cookies = [_cookie_for_browser(item) for item in payload if isinstance(item, dict)]
        clean = [item for item in cookies if item]
        if clean:
            await context.add_cookies(clean)
    except Exception:
        # A bad/expired cache should fall through to a clean login.
        return


def _save_cookies(path: pathlib.Path, cookies: list[dict[str, Any]]) -> None:
    clean = [
        item
        for item in cookies
        if isinstance(item, dict)
        and item.get("name")
        and str(item.get("domain", "")).lower() in SESSION_COOKIE_DOMAINS
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(clean, indent=2))
    temporary.chmod(0o600)
    temporary.replace(path)
    path.chmod(0o600)


async def _session_is_valid(page: Any) -> bool:
    try:
        response = await page.request.get(BASE_WEB + "/api/v1/bff/get-user")
        if response.status != 200:
            return False
        payload = await response.json()
        if not isinstance(payload, dict):
            return False
        return bool(
            payload.get("isAuthenticated")
            or payload.get("isLoggedIn")
            or payload.get("isShopper")
            or payload.get("shopper")
        )
    except Exception:
        return False


async def _perform_login(
    username: str,
    password: str,
    path: pathlib.Path,
    *,
    headed: bool,
) -> dict[str, Any]:
    try:
        from camoufox.async_api import AsyncCamoufox
    except ImportError as exc:
        raise RuntimeError(
            "Woolworths login requires the optional Camoufox browser dependency. "
            "Install it with `python3 -m pip install camoufox`, then download its "
            "browser once with `python3 -m camoufox fetch`."
        ) from exc

    proxy_url = os.environ.get("WOOLWORTHS_PROXY")
    proxy = {"server": proxy_url} if proxy_url else None
    try:
        manager = AsyncCamoufox(headless=not headed, proxy=proxy)
        async with manager as browser:
            context = browser.contexts[0] if browser.contexts else await browser.new_context()
            await _load_cookies(context, path)
            page = await context.new_page()

            if not await _session_is_valid(page):
                await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60_000)
                email = page.locator('input[type="email"], input[name="username"]').first
                await email.wait_for(state="visible", timeout=45_000)
                await email.fill(username)
                await email.press("Enter")

                password_input = page.locator('input[type="password"]:visible').first
                await password_input.wait_for(state="visible", timeout=45_000)
                await password_input.fill(password)
                await password_input.press("Enter")
                try:
                    await page.wait_for_url(
                        lambda url: url.startswith(BASE_WEB),
                        timeout=60_000,
                    )
                except Exception:
                    # Validation below provides the useful error.
                    pass
                await page.wait_for_timeout(2_000)

            if not await _session_is_valid(page):
                raise RuntimeError(
                    "Woolworths login did not produce an authenticated session. "
                    "Retry with `auth login --headed` to complete any visible challenge."
                )
            cookies = await context.cookies([BASE_WEB])
            _save_cookies(path, cookies)
            return {"session_file": str(path), "cookie_count": len(cookies)}
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(
            f"Woolworths browser login failed: {exc}. "
            "Retry with `auth login --headed` if the sign-in challenge needs attention."
        ) from exc


def login_and_save(
    username: str,
    password: str,
    path: pathlib.Path,
    *,
    headed: bool = False,
) -> dict[str, Any]:
    """Authenticate and save only cookies; credentials remain in the environment."""
    return asyncio.run(_perform_login(username, password, path, headed=headed))
