#!/usr/bin/env python3
"""Bunnings lightweight public read-only CLI.

Self-contained stdlib wrapper around Bunnings NZ/AU read-only JSON APIs.
No login, cart mutation, browser automation, or third-party dependencies.
"""
from __future__ import annotations

import argparse
import http.cookiejar
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any

COUNTRIES = {
    "nz": {
        "label": "Bunnings NZ",
        "base": "https://www.bunnings.co.nz",
        "auth_base": "https://authorisation.api.bunnings.co.nz",
        "guest_client_id": "budp_guest_user_nz",
        "country_code": "NZ",
        "country_name": "New Zealand",
        "locale": "en_NZ",
        "currency": "NZD",
        "default_store": "9489",
        "default_region": "NI_Zone_9",
    },
    "au": {
        "label": "Bunnings AU",
        "base": "https://www.bunnings.com.au",
        "auth_base": "https://authorisation.api.bunnings.com.au",
        "guest_client_id": "budp_guest_user_au",
        "country_code": "AU",
        "country_name": "Australia",
        "locale": "en_AU",
        "currency": "AUD",
        "default_store": "6400",
        "default_region": "VICMetro",
    },
}

APIGEE_CLIENT_ID = "mHPVWnzuBkrW7rmt56XGwKkb5Gp9BJMk"
GUEST_SCOPE = "chk:exec cm:access ecom:access chk:pub vch:public bsk:pub"
TOKEN_CACHE_SECONDS = int(os.environ.get("BUNNINGS_GUEST_TOKEN_CACHE_SECONDS", "3600"))
TOKEN_REFRESH_SKEW = 300
TOKEN_CACHE: dict[str, dict[str, Any]] = {}

UA = os.environ.get(
    "BUNNINGS_USER_AGENT",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
)


def die(message: str, code: int = 1) -> None:
    print(f"bunnings: {message}", file=sys.stderr)
    raise SystemExit(code)


def country_cfg(country: str) -> dict[str, str]:
    return COUNTRIES.get(country) or COUNTRIES["nz"]


def build_url(cfg: dict[str, str], path_or_url: str) -> str:
    if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
        return path_or_url
    path = path_or_url if path_or_url.startswith("/") else "/" + path_or_url
    return cfg["base"] + path


def request_text(cfg: dict[str, str], path_or_url: str, timeout: int = 30) -> str:
    url = build_url(cfg, path_or_url)
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-NZ,en-AU;q=0.9,en;q=0.8",
        "Referer": cfg["base"] + "/",
        "User-Agent": UA,
    }
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        detail = re.sub(r"\s+", " ", raw[:300]).strip()
        die(f"HTTP {e.code} from {url}: {detail}")
    except urllib.error.URLError as e:
        die(f"network error calling {url}: {e.reason}")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req: urllib.request.Request, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        return None


def token_cache_path(cfg: dict[str, str]) -> str:
    cache_home = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
    return os.path.join(cache_home, "bunnings-skill", f"guest-token-{cfg['country_code'].lower()}.json")


def read_cached_token(cfg: dict[str, str]) -> str | None:
    key = cfg["country_code"].lower()
    cached = TOKEN_CACHE.get(key)
    now = time.time()
    if cached and float(cached.get("cache_expires_at") or 0) > now + TOKEN_REFRESH_SKEW:
        return str(cached.get("token") or "")
    path = token_cache_path(cfg)
    try:
        with open(path, "r", encoding="utf-8") as f:
            cached = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    if float(cached.get("cache_expires_at") or 0) <= now + TOKEN_REFRESH_SKEW:
        return None
    TOKEN_CACHE[key] = cached
    return str(cached.get("token") or "") or None


def write_cached_token(cfg: dict[str, str], token: str, expires_in: int) -> None:
    now = time.time()
    real_expires_at = now + max(0, expires_in)
    cache_expires_at = min(real_expires_at - TOKEN_REFRESH_SKEW, now + max(60, TOKEN_CACHE_SECONDS))
    cached = {
        "token": token,
        "real_expires_at": real_expires_at,
        "cache_expires_at": cache_expires_at,
        "country": cfg["country_code"],
    }
    TOKEN_CACHE[cfg["country_code"].lower()] = cached
    path = token_cache_path(cfg)
    try:
        os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cached, f)
    except OSError:
        pass


def clear_cached_token(cfg: dict[str, str]) -> None:
    TOKEN_CACHE.pop(cfg["country_code"].lower(), None)
    try:
        os.unlink(token_cache_path(cfg))
    except OSError:
        pass


def open_no_redirect(opener: urllib.request.OpenerDirector, url: str, headers: dict[str, str], timeout: int) -> Any:
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        return opener.open(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        if e.code in (301, 302, 303, 307, 308):
            return e
        raise


def mint_guest_token(cfg: dict[str, str], timeout: int = 30) -> tuple[str, int]:
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar), NoRedirect)
    params = {
        "response_type": "token",
        "scope": GUEST_SCOPE,
        "client_id": cfg["guest_client_id"],
        "redirect_uri": cfg["base"] + "/static/guest.html",
        "nonce": uuid.uuid4().hex[:18],
        "acr_values": "adtid:" + str(uuid.uuid1()),
    }
    current = cfg["auth_base"] + "/connect/authorize?" + urllib.parse.urlencode(params)
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-NZ,en-AU;q=0.9,en;q=0.8",
        "Referer": cfg["base"] + "/",
        "User-Agent": UA,
    }
    last_body = ""
    location = ""
    try:
        for _ in range(12):
            resp = open_no_redirect(opener, current, headers, timeout)
            location = resp.headers.get("Location", "")
            if not location:
                last_body = resp.read().decode("utf-8", "replace")[:300]
                break
            current = urllib.parse.urljoin(current, location)
            if urllib.parse.urlparse(current).fragment:
                location = current
                break
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        die(f"guest token bootstrap failed with HTTP {e.code}: {detail}")
    except urllib.error.URLError as e:
        die(f"guest token bootstrap network error: {e.reason}")
    fragment = urllib.parse.parse_qs(urllib.parse.urlparse(location).fragment)
    token = (fragment.get("access_token") or fragment.get("id_token") or [""])[0]
    expires_in = int((fragment.get("expires_in") or ["0"])[0] or 0)
    if not token:
        detail = re.sub(r"\s+", " ", last_body).strip()
        die(f"guest token bootstrap did not return a token{': ' + detail if detail else ''}")
    return token, expires_in


def guest_token(cfg: dict[str, str]) -> str:
    cached = read_cached_token(cfg)
    if cached:
        return cached
    token, expires_in = mint_guest_token(cfg)
    write_cached_token(cfg, token, expires_in)
    return token


def api_headers(cfg: dict[str, str], referer_path: str = "/", token: str | None = None, json_body: bool = False) -> dict[str, str]:
    token = token or guest_token(cfg)
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-NZ,en-AU;q=0.9,en;q=0.8",
        "Authorization": "Bearer " + token,
        "Cookie": "GuestAuthentication=" + token,
        "Referer": build_url(cfg, referer_path),
        "User-Agent": UA,
        "clientId": APIGEE_CLIENT_ID,
        "correlationid": str(uuid.uuid1()),
        "country": cfg["country_code"],
        "currency": cfg["currency"],
        "locale": cfg["locale"],
        "locationCode": cfg["default_store"],
        "sessionid": str(uuid.uuid1()),
        "stream": "RETAIL",
        "userId": "anonymous",
        "X-region": cfg["default_region"],
    }
    if json_body:
        headers["Content-Type"] = "application/json"
    return headers


def api_json(
    cfg: dict[str, str],
    path: str,
    method: str = "GET",
    body: dict[str, Any] | None = None,
    referer_path: str = "/",
    retry_auth: bool = True,
) -> Any:
    url = build_url(cfg, path)
    token = guest_token(cfg)
    data = json.dumps(body, separators=(",", ":")).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=api_headers(cfg, referer_path, token, body is not None), method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        if e.code in (401, 403) and retry_auth:
            clear_cached_token(cfg)
            return api_json(cfg, path, method, body, referer_path, retry_auth=False)
        detail = api_error_detail(raw) or re.sub(r"\s+", " ", raw[:300]).strip()
        die(f"HTTP {e.code} from {url}: {detail}")
    except urllib.error.URLError as e:
        die(f"network error calling {url}: {e.reason}")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        die(f"invalid JSON from {url}: {e}")
    status = payload.get("statusDetails") if isinstance(payload, dict) else None
    if isinstance(status, dict) and status.get("state") == "FAILURE":
        die(f"{status.get('errorCode') or 'API'} from {url}: {status.get('description') or 'request failed'}")
    if isinstance(payload, dict) and "data" in payload and isinstance(status, dict):
        return payload["data"]
    return payload


def api_error_detail(raw: str) -> str:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return ""
    if not isinstance(payload, dict):
        return ""
    status = payload.get("statusDetails")
    if isinstance(status, dict):
        return str(status.get("description") or status.get("errorCode") or "")
    return str(payload.get("message") or payload.get("detail") or payload.get("title") or "")


def next_data_from_text(text: str, url: str) -> dict[str, Any]:
    stripped = text.lstrip()
    if stripped.startswith("{"):
        try:
            return json.loads(stripped)
        except json.JSONDecodeError as e:
            die(f"invalid JSON from {url}: {e}")
    match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', text)
    if not match:
        if "<title>Page Not Found" in text or "/404" in text[:5000]:
            die(f"page not found: {url}")
        die(f"could not find Next.js data in {url}")
    try:
        return json.loads(html.unescape(match.group(1)))
    except json.JSONDecodeError as e:
        die(f"invalid Next.js data in {url}: {e}")


def fetch_next_data(cfg: dict[str, str], path_or_url: str) -> dict[str, Any]:
    url = build_url(cfg, path_or_url)
    return next_data_from_text(request_text(cfg, url), url)


def page_props(data: dict[str, Any]) -> dict[str, Any]:
    return ((data.get("props") or {}).get("pageProps") or data.get("pageProps") or {})


def query_states(data: dict[str, Any]) -> list[dict[str, Any]]:
    queries = ((page_props(data).get("dehydratedState") or {}).get("queries") or [])
    return [q for q in queries if isinstance(q, dict)]


def query_data(data: dict[str, Any], key_name: str) -> Any:
    for q in query_states(data):
        key = q.get("queryKey") or []
        if isinstance(key, list) and key and key[0] == key_name:
            return ((q.get("state") or {}).get("data"))
    return None


def search_payload(data: dict[str, Any]) -> dict[str, Any]:
    for q in query_states(data):
        payload = ((q.get("state") or {}).get("data"))
        if isinstance(payload, dict) and isinstance(payload.get("results"), list):
            return payload
    return {}


def walk(value: Any) -> list[Any]:
    out = [value]
    if isinstance(value, dict):
        for child in value.values():
            out.extend(walk(child))
    elif isinstance(value, list):
        for child in value:
            out.extend(walk(child))
    return out


def money(value: Any, currency: str | None = None) -> str:
    if value is None:
        return "-"
    try:
        prefix = "$"
        return f"{prefix}{float(value):.2f}" + (f" {currency}" if currency else "")
    except Exception:
        return str(value)


def slugify_query(value: str) -> str:
    return urllib.parse.quote(value.strip())


def product_url(cfg: dict[str, str], route: str | None) -> str | None:
    if not route:
        return None
    return build_url(cfg, route)


def category_label(raw: dict[str, Any]) -> str:
    parts = []
    categories = raw.get("supercategories") or []
    if isinstance(categories, list):
        for value in categories:
            if isinstance(value, str) and "--" in value:
                parts.append(value.split("--", 1)[0])
    return " / ".join(parts)


def parse_raw_product(raw: dict[str, Any], cfg: dict[str, str]) -> dict[str, Any]:
    route = raw.get("productroutingurl") or raw.get("productRoutingUrl")
    offers = raw.get("productoffers")
    store = cfg["default_store"]
    region = cfg["default_region"].lower()
    ranges = (
        raw.get("productranges")
        or raw.get("productRanges")
        or raw.get(f"productRanges_{store}")
        or raw.get(f"productranges_{store}")
        or raw.get(f"productRanges_{region}")
        or raw.get(f"productranges_{region}")
    )
    price = raw.get("price")
    if price is None:
        price = raw.get(f"price_{store}")
    if isinstance(offers, str):
        offers = [offers]
    if isinstance(ranges, str):
        ranges = [ranges]
    return {
        "sku": str(raw.get("code") or raw.get("itemnumber") or raw.get("itemNumber") or ""),
        "name": raw.get("name") or raw.get("title") or "",
        "brand": raw.get("brandname") or "",
        "price": price,
        "currency": raw.get("currency") or cfg.get("currency"),
        "unit": raw.get("unitofprice"),
        "rating": raw.get("rating"),
        "rating_count": raw.get("ratingcount"),
        "category": category_label(raw),
        "product_ranges": ranges or [],
        "product_offers": offers or [],
        "promotional_campaign": raw.get("promotionalcampaign"),
        "is_new_arrival": str(raw.get("newarrival", "")).lower() == "true",
        "is_best_seller": str(raw.get("bestseller", "")).lower() == "true",
        "image": raw.get("imageurl") or raw.get("thumbnailimageurl"),
        "source_url": product_url(cfg, route),
    }


def products_from_search_payload(payload: dict[str, Any], cfg: dict[str, str], limit: int) -> list[dict[str, Any]]:
    products = []
    for item in payload.get("results") or []:
        raw = item.get("raw") if isinstance(item, dict) else None
        if isinstance(raw, dict) and (raw.get("code") or raw.get("itemnumber")):
            products.append(parse_raw_product(raw, cfg))
    return products[: max(1, limit)]


def search_fields(cfg: dict[str, str]) -> list[str]:
    store = cfg["default_store"]
    region = cfg["default_region"].lower()
    return [
        "source",
        "thumbnailimageurl",
        "supercategoriescode",
        "supercategoriesurl",
        "supercategories",
        "ratingcount",
        "brandiconurl",
        "title",
        "objecttype",
        "currency",
        "colorcount",
        f"price_{store}",
        "price",
        "rating",
        "stockstatus",
        "forhire",
        "orderingid",
        "bestseller",
        "productroutingurl",
        "brandcode",
        "categories",
        "brandname",
        "name",
        "itemnumber",
        "url",
        "newarrival",
        "imageurl",
        "availability",
        "code",
        "basicbundle",
        f"productRanges_{store}",
        f"productRanges_{region}",
        "productranges",
        "stockindicator",
        "familycolourname",
        "unitofprice",
        f"storeattributes_{store}",
        "isactive",
        "keysellingpoints",
        "agerestricted",
        "sellername",
        f"cprice_{store}",
        "comparisonunit",
        "comparisonunitofmeasure",
        "comparisonunitofmeasurecode",
        "promotionalcampaign",
        "promotionalcampaignstart",
        "promotionalcampaignend",
        "defaultofferid",
        "productoffers",
    ]


def coveo_payload(cfg: dict[str, str], query: str, limit: int, category_code: str | None = None, category_path: str | None = None) -> dict[str, Any]:
    store = cfg["default_store"]
    region = cfg["default_region"].lower()
    country = cfg["country_code"]
    clauses = [
        f"@availableinregions==({region})",
        f"@price_{store} > 0",
        "@isactive==true",
        f"@batchcountry==({country})",
        "@origin==(OPERATOR)",
    ]
    if category_code:
        clauses.insert(0, f"@supercategoriescode==({category_code})")
    visitor = str(uuid.uuid4())
    body: dict[str, Any] = {
        "debug": False,
        "enableDidYouMean": True,
        "enableDuplicateFiltering": False,
        "enableQuerySyntax": False,
        "facetOptions": {"freezeFacetOrder": True},
        "filterField": "@baseid",
        "filterFieldRange": 10,
        "lowerCaseOperators": True,
        "partialMatch": True,
        "partialMatchKeywords": 2,
        "partialMatchThreshold": "30%",
        "questionMark": True,
        "enableWordCompletion": True,
        "firstResult": 0,
        "isGuestUser": True,
        "numberOfResults": min(max(limit, 1), 36),
        "sortCriteria": "relevancy",
        "q": query,
        "aq": " AND ".join(clauses),
        "cq": f"@source==(PRODUCT_STREAM_{country})",
        "searchHub": "PRODUCT_LISTING" if category_code else "PRODUCT_SEARCH",
        "visitorId": visitor,
        "context": {
            "store": store,
            "country": cfg["country_name"],
            "platform": "Web",
            "role": "retail",
            "website": country,
        },
        "context_website": country,
        "cu": cfg["currency"],
        "de": "UTF-8",
        "analytics": {
            "clientId": visitor,
            "trackingId": country,
            "actionCause": "interfaceLoad" if category_code else "searchboxSubmit",
            "capture": True,
        },
        "extendedSearchOptions": {"includes": ["Banner", "SponsoredProducts", "Facets"]},
        "pipeline": "Variant_Product",
        "fieldsToInclude": search_fields(cfg),
    }
    if category_path:
        body["tab"] = category_path.strip("/")
    return body


def search_products(cfg: dict[str, str], query: str, limit: int = 10) -> dict[str, Any]:
    started = time.perf_counter()
    referer = "/search/products?" + urllib.parse.urlencode({"q": query})
    payload = api_json(cfg, "/_apis/v1/coveo/search", method="POST", body=coveo_payload(cfg, query, limit), referer_path=referer)
    products = products_from_search_payload(payload, cfg, min(max(limit, 1), 36))
    return {
        "country": cfg["label"],
        "query": query,
        "count": len(products),
        "total_count": payload.get("totalCount"),
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "products": products,
    }


def normalize_product_path(value: str) -> str:
    if value.startswith("http://") or value.startswith("https://"):
        path = urllib.parse.urlparse(value).path
    else:
        path = value
    if not path.startswith("/"):
        path = "/" + path
    return path


def sku_from_value(value: str) -> str | None:
    match = re.search(r"_p([A-Za-z0-9]+)", value)
    if match:
        return match.group(1)
    if re.fullmatch(r"[A-Za-z0-9-]+", value):
        return value
    return None


def find_product_route(cfg: dict[str, str], sku_or_route: str) -> tuple[str, str]:
    if "_p" in sku_or_route or "/" in sku_or_route:
        path = normalize_product_path(sku_or_route)
        sku = sku_from_value(path) or sku_or_route
        return sku, path
    sku = sku_or_route
    data = search_products(cfg, sku, limit=10)
    exact = None
    for product in data["products"]:
        if product.get("sku") == sku:
            exact = product
            break
    exact = exact or (data["products"][0] if data["products"] else None)
    if not exact or not exact.get("source_url"):
        die(f"could not resolve product route for SKU {sku}")
    return str(exact.get("sku") or sku), normalize_product_path(str(exact["source_url"]))


def primary_image(product: dict[str, Any]) -> str | None:
    images = product.get("images") or []
    if isinstance(images, list):
        for item in images:
            if isinstance(item, dict) and item.get("imageType") == "PRIMARY":
                return item.get("url") or item.get("thumbnailUrl")
        for item in images:
            if isinstance(item, dict) and (item.get("url") or item.get("thumbnailUrl")):
                return item.get("url") or item.get("thumbnailUrl")
    return None


def feature_values(product: dict[str, Any]) -> dict[str, str]:
    out = {}
    for group in product.get("classifications") or []:
        if not isinstance(group, dict):
            continue
        for feature in group.get("features") or []:
            if not isinstance(feature, dict):
                continue
            vals = feature.get("featureValues") or []
            value = vals[0].get("value") if vals and isinstance(vals[0], dict) else None
            name = feature.get("name")
            if name and value is not None:
                out[str(name)] = str(value)
    return out


def category_from_detail(product: dict[str, Any]) -> str:
    categories = product.get("allCategories") or []
    names = [c.get("displayName") for c in categories if isinstance(c, dict) and c.get("displayName")]
    return " / ".join(str(x) for x in names)


def parse_product_detail(data: dict[str, Any], cfg: dict[str, str], sku: str, path: str) -> dict[str, Any]:
    product = query_data(data, "retail-product") or {}
    price = query_data(data, "product-retail-price") or {}
    fulfilment = query_data(data, "product-fulfilment") or {}
    aisle_data = query_data(data, "product-aisle-item-location") or []
    if not isinstance(product, dict) or not product.get("code"):
        die(f"could not find product detail data for {sku}")
    brand = product.get("brand") or {}
    feature = product.get("feature") or {}
    in_store = fulfilment.get("inStorePickUpData") if isinstance(fulfilment, dict) else {}
    click_collect = fulfilment.get("clickNCollectData") if isinstance(fulfilment, dict) else {}
    delivery = fulfilment.get("deliveryData") if isinstance(fulfilment, dict) else {}
    aisle_locations = []
    if isinstance(aisle_data, list):
        for group in aisle_data:
            if not isinstance(group, dict):
                continue
            for loc in group.get("inStoreLocations") or []:
                if isinstance(loc, dict):
                    aisle_locations.append(
                        {
                            "aisle": loc.get("aisle"),
                            "bay": loc.get("bay"),
                            "sequence": loc.get("sequence"),
                        }
                    )
    return {
        "sku": str(product.get("code") or sku),
        "item_number": product.get("itemNumber"),
        "name": product.get("name"),
        "brand": brand.get("name") if isinstance(brand, dict) else None,
        "price": price.get("value") if isinstance(price, dict) else None,
        "price_display": price.get("formattedValue") if isinstance(price, dict) else None,
        "currency": price.get("currencyIso") if isinstance(price, dict) else cfg.get("currency"),
        "rating": product.get("averageRating"),
        "rating_count": product.get("numberOfReviews"),
        "category": category_from_detail(product),
        "key_selling_points": feature.get("pointers") if isinstance(feature, dict) else [],
        "description": feature.get("description") if isinstance(feature, dict) else None,
        "features": feature_values(product),
        "product_ranges": [
            "Click & Collect" if click_collect and click_collect.get("isClicknCollectAvailable") else None,
            "In-Store" if in_store and in_store.get("inStorePickUpAvailable") else None,
            "Delivery" if delivery and delivery.get("isDeliveryAvailable") else None,
        ],
        "stock": {
            "store": in_store.get("storeName") if isinstance(in_store, dict) else None,
            "in_store_text": in_store.get("inStoreStockTxt") if isinstance(in_store, dict) else None,
            "in_store_stock": in_store.get("stock") if isinstance(in_store, dict) else None,
            "click_collect_text": click_collect.get("clickNCollectStockTxt") if isinstance(click_collect, dict) else None,
            "click_collect_stock": click_collect.get("stock") if isinstance(click_collect, dict) else None,
        },
        "aisle_locations": aisle_locations,
        "image": primary_image(product),
        "source_url": build_url(cfg, path),
    }


def product_route_from_api(product: dict[str, Any], sku: str) -> str | None:
    route = product.get("url") or product.get("productUrl") or product.get("productRoutingUrl")
    if isinstance(route, str) and route and "BaseSite/products" not in route:
        return normalize_product_path(route)
    slug = product.get("slug")
    if isinstance(slug, str) and slug:
        return normalize_product_path(slug)
    name = product.get("name")
    if isinstance(name, str) and name:
        return f"/{slugify_path(name)}_p{sku}"
    return None


def parse_api_product_detail(
    product: dict[str, Any],
    price: dict[str, Any],
    fulfilment: dict[str, Any],
    aisle_data: Any,
    cfg: dict[str, str],
    sku: str,
) -> dict[str, Any]:
    if not isinstance(product, dict) or not product.get("code"):
        die(f"could not find product detail data for {sku}")
    brand = product.get("brand") or {}
    feature = product.get("feature") or {}
    in_store = fulfilment.get("inStorePickUpData") if isinstance(fulfilment, dict) else {}
    click_collect = fulfilment.get("clickNCollectData") if isinstance(fulfilment, dict) else {}
    delivery = fulfilment.get("deliveryData") if isinstance(fulfilment, dict) else {}
    aisle_locations = []
    if isinstance(aisle_data, list):
        for group in aisle_data:
            if not isinstance(group, dict):
                continue
            for loc in group.get("inStoreLocations") or []:
                if isinstance(loc, dict):
                    aisle_locations.append(
                        {
                            "aisle": loc.get("aisle"),
                            "bay": loc.get("bay"),
                            "sequence": loc.get("sequence"),
                        }
                    )
    route = product_route_from_api(product, str(product.get("code") or sku))
    return {
        "sku": str(product.get("code") or sku),
        "item_number": product.get("itemNumber"),
        "name": product.get("name"),
        "brand": brand.get("name") if isinstance(brand, dict) else product.get("brandName"),
        "price": price.get("value") if isinstance(price, dict) else None,
        "price_display": price.get("formattedValue") if isinstance(price, dict) else None,
        "currency": price.get("currencyIso") if isinstance(price, dict) else cfg.get("currency"),
        "rating": product.get("averageRating"),
        "rating_count": product.get("numberOfReviews"),
        "category": category_from_detail(product),
        "key_selling_points": feature.get("pointers") if isinstance(feature, dict) else [],
        "description": feature.get("description") if isinstance(feature, dict) else None,
        "features": feature_values(product),
        "product_ranges": [
            "Click & Collect" if click_collect and click_collect.get("isClicknCollectAvailable") else None,
            "In-Store" if in_store and in_store.get("inStorePickUpAvailable") else None,
            "Delivery" if delivery and delivery.get("isDeliveryAvailable") else None,
        ],
        "stock": {
            "store": in_store.get("storeName") if isinstance(in_store, dict) else None,
            "in_store_text": in_store.get("inStoreStockTxt") if isinstance(in_store, dict) else None,
            "in_store_stock": in_store.get("stock") if isinstance(in_store, dict) else None,
            "click_collect_text": click_collect.get("clickNCollectStockTxt") if isinstance(click_collect, dict) else None,
            "click_collect_stock": click_collect.get("stock") if isinstance(click_collect, dict) else None,
        },
        "aisle_locations": aisle_locations,
        "image": primary_image(product),
        "source_url": build_url(cfg, route) if route else None,
    }


def product_detail(cfg: dict[str, str], sku_or_route: str) -> dict[str, Any]:
    started = time.perf_counter()
    sku = sku_from_value(sku_or_route)
    if not sku:
        die(f"invalid product SKU or product URL: {sku_or_route}")
    referer = "/search/products?" + urllib.parse.urlencode({"q": sku})
    product_data = api_json(cfg, f"/_apis/v1/products/{urllib.parse.quote(sku)}?fields=FULL", referer_path=referer)
    price = api_json(cfg, f"/_apis/v2/products/{urllib.parse.quote(sku)}/priceInfo", referer_path=referer)
    fulfilment = api_json(
        cfg,
        f"/_apis/v2/products/{urllib.parse.quote(sku)}/fulfillment",
        method="POST",
        body={"includeVariantStock": False, "locationCode": cfg["default_store"], "storeRadius": "200000"},
        referer_path=referer,
    )
    aisle = api_json(
        cfg,
        "/_apis/v1/item-api/locations?"
        + urllib.parse.urlencode({"locationCode": cfg["default_store"], "productCode": sku}),
        referer_path=referer,
    )
    product = parse_api_product_detail(product_data, price, fulfilment, aisle, cfg, sku)
    return {
        "country": cfg["label"],
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "product": product,
    }


def browse_category(cfg: dict[str, str], category: str, limit: int = 10) -> dict[str, Any]:
    started = time.perf_counter()
    path = normalize_product_path(category)
    if not path.startswith("/products/"):
        path = "/products/" + path.lstrip("/")
    category_code = path.rstrip("/").split("/")[-1]
    payload = api_json(
        cfg,
        "/_apis/v1/coveo/search",
        method="POST",
        body=coveo_payload(cfg, "", limit, category_code=category_code, category_path=path.replace("/products/", "", 1)),
        referer_path=path,
    )
    children = []
    products = products_from_search_payload(payload, cfg, min(max(limit, 1), 36))
    return {
        "country": cfg["label"],
        "category": path,
        "count": len(products),
        "total_count": payload.get("totalCount"),
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "child_categories": children,
        "products": products,
    }


def store_links(cfg: dict[str, str]) -> list[str]:
    text = request_text(cfg, "/stores")
    paths = []
    for match in re.finditer(r'["\'](/stores/[A-Za-z0-9/-]+)["\']', text):
        path = match.group(1).rstrip("/")
        parts = [p for p in path.split("/") if p]
        if len(parts) == 3 and parts[1] not in {"checkActiveStore", "products", "defaultStore"}:
            paths.append(path)
    seen = set()
    out = []
    for path in paths:
        if path not in seen:
            seen.add(path)
            out.append(path)
    return out


def parse_hours(store: dict[str, Any]) -> list[dict[str, Any]]:
    hours = ((store.get("openingHours") or {}).get("weekDayOpeningList") or [])
    out = []
    for item in hours:
        if not isinstance(item, dict):
            continue
        out.append(
            {
                "day": item.get("weekDay"),
                "closed": bool(item.get("closed")),
                "open": ((item.get("openingTime") or {}).get("formattedHour")),
                "close": ((item.get("closingTime") or {}).get("formattedHour")),
            }
        )
    return out


def parse_store_detail(data: dict[str, Any], cfg: dict[str, str], path: str) -> dict[str, Any] | None:
    state = page_props(data).get("initialState") or {}
    store = ((state.get("store") or {}).get("data") or {})
    if not isinstance(store, dict) or not store.get("name"):
        return None
    address = store.get("address") or {}
    geo = store.get("geoPoint") or {}
    return {
        "code": store.get("name"),
        "name": store.get("displayName") or store.get("description"),
        "region": store.get("urlRegion") or path.split("/")[2],
        "store_region": store.get("storeRegion"),
        "pricing_region": store.get("pricingRegion"),
        "address": address.get("formattedAddress"),
        "line1": address.get("line1"),
        "suburb": address.get("line2") or address.get("suburb"),
        "town": address.get("town"),
        "state": address.get("state"),
        "postal_code": address.get("postalCode"),
        "phone": address.get("phone"),
        "email": address.get("email"),
        "latitude": geo.get("latitude"),
        "longitude": geo.get("longitude"),
        "has_click_and_collect": bool(store.get("hasClickAndCollect")),
        "has_delivery": bool(store.get("hasDelivery")),
        "services": store.get("storeServices") or [],
        "hours": parse_hours(store),
        "map_url": store.get("mapUrl"),
        "source_url": build_url(cfg, path),
    }


def slugify_path(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def parse_store_api(store: dict[str, Any], cfg: dict[str, str]) -> dict[str, Any] | None:
    if not isinstance(store, dict) or not store.get("name"):
        return None
    address = store.get("address") or {}
    geo = store.get("geoPoint") or {}
    region = store.get("urlRegion") or ""
    store_slug = slugify_path(str(store.get("displayName") or store.get("description") or store.get("name") or ""))
    path = f"/stores/{region}/{store_slug}" if region and store_slug else "/stores"
    return {
        "code": store.get("name"),
        "name": store.get("displayName") or store.get("description"),
        "region": region,
        "store_region": store.get("storeRegion"),
        "pricing_region": store.get("pricingRegion"),
        "address": address.get("formattedAddress"),
        "line1": address.get("line1"),
        "suburb": address.get("line2") or address.get("suburb"),
        "town": address.get("town"),
        "state": address.get("state"),
        "postal_code": address.get("postalCode"),
        "phone": address.get("phone"),
        "email": address.get("email"),
        "latitude": geo.get("latitude"),
        "longitude": geo.get("longitude"),
        "has_click_and_collect": bool(store.get("hasClickAndCollect")),
        "has_delivery": bool(store.get("hasDelivery")),
        "services": store.get("storeServices") or [],
        "hours": parse_hours(store),
        "map_url": store.get("mapUrl") or ((store.get("mapIcon") or {}).get("url") if isinstance(store.get("mapIcon"), dict) else None),
        "source_url": build_url(cfg, path),
    }


def store_matches(store: dict[str, Any], region: str | None) -> bool:
    if not region:
        return True
    needle = region.lower().replace(" ", "")
    hay = " ".join(str(v or "") for v in store.values() if not isinstance(v, (list, dict))).lower().replace(" ", "")
    return needle in hay


def stores(cfg: dict[str, str], region: str | None = None, limit: int = 20) -> dict[str, Any]:
    started = time.perf_counter()
    payload = api_json(cfg, f"/_apis/v1/stores/country/{cfg['country_code']}?fields=FULL", referer_path="/stores")
    all_stores = payload.get("pointOfServices") if isinstance(payload, dict) else []
    rows = []
    for raw in all_stores or []:
        if len(rows) >= max(1, limit):
            break
        store = parse_store_api(raw, cfg)
        if store and store_matches(store, region):
            rows.append(store)
    return {
        "country": cfg["label"],
        "region": region,
        "count": len(rows),
        "available_store_links": len(all_stores or []),
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "stores": rows,
    }


def promotional_products(cfg: dict[str, str], query: str | None = None, limit: int = 10) -> dict[str, Any]:
    started = time.perf_counter()
    data = fetch_next_data(cfg, "/campaign/redemption-offers")
    products = []
    seen = set()
    for item in walk(page_props(data).get("initialState") or {}):
        if not isinstance(item, dict):
            continue
        raw = item.get("raw") if isinstance(item.get("raw"), dict) else item
        if not isinstance(raw, dict):
            continue
        offers = raw.get("productoffers") or []
        if isinstance(offers, str):
            offers = [offers]
        is_promo = "Redemption Offer" in offers or bool(raw.get("promotionalcampaign"))
        code = str(raw.get("code") or raw.get("itemnumber") or "")
        if not is_promo or not code or code in seen:
            continue
        product = parse_raw_product(raw, cfg)
        text = " ".join(str(product.get(k) or "") for k in ("sku", "name", "brand", "category")).lower()
        if query and query.lower() not in text:
            continue
        seen.add(code)
        products.append(product)
        if len(products) >= max(1, limit):
            break
    return {
        "country": cfg["label"],
        "query": query,
        "count": len(products),
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "products": products,
        "source_url": build_url(cfg, "/campaign/redemption-offers"),
    }


def price_label(product: dict[str, Any]) -> str:
    display = product.get("price_display")
    if display:
        return str(display)
    return money(product.get("price"), product.get("currency"))


def print_products(data: dict[str, Any], label: str) -> None:
    query = data.get("query") or data.get("category") or label
    total = data.get("total_count")
    total_text = f" of {total}" if total is not None else ""
    print(f"{data.get('country')}: {query}: {data.get('count', 0)}{total_text} products ({data.get('elapsed_ms')} ms)")
    children = data.get("child_categories") or []
    if children:
        print("Child categories: " + ", ".join(str(c.get("name")) for c in children[:8] if c.get("name")))
    print()
    for p in data.get("products") or []:
        bits = [price_label(p)]
        ranges = [x for x in p.get("product_ranges") or [] if x]
        offers = [x for x in p.get("product_offers") or [] if x]
        if ranges:
            bits.append(", ".join(str(x) for x in ranges))
        if offers:
            bits.append(", ".join(str(x) for x in offers))
        rating = p.get("rating")
        if rating:
            bits.append(f"rating {rating}")
        print(f"{p.get('sku'):>8}  {' '.join(x for x in [p.get('brand'), p.get('name')] if x)}")
        print("          " + " | ".join(str(x) for x in bits if x))
        if p.get("category"):
            print(f"          category: {p.get('category')}")
        if p.get("source_url"):
            print(f"          {p.get('source_url')}")
        print()


def print_product_detail(data: dict[str, Any]) -> None:
    p = data["product"]
    print(f"{data.get('country')}: {p.get('sku')}  {' '.join(x for x in [p.get('brand'), p.get('name')] if x)}")
    print(f"Price: {price_label(p)}")
    ranges = [x for x in p.get("product_ranges") or [] if x]
    if ranges:
        print("Fulfilment: " + ", ".join(str(x) for x in ranges))
    stock = p.get("stock") or {}
    stock_bits = []
    if stock.get("store"):
        stock_bits.append(str(stock["store"]))
    if stock.get("in_store_text"):
        stock_bits.append(str(stock["in_store_text"]))
    if stock.get("in_store_stock") is not None:
        stock_bits.append(f"{stock.get('in_store_stock')} in store")
    if stock_bits:
        print("Stock: " + " | ".join(stock_bits))
    locations = p.get("aisle_locations") or []
    if locations:
        loc = locations[0]
        print(f"Location: aisle {loc.get('aisle')}, bay {loc.get('bay')}")
    if p.get("category"):
        print(f"Category: {p.get('category')}")
    if p.get("rating"):
        print(f"Rating: {p.get('rating')} ({p.get('rating_count') or 0} reviews)")
    if p.get("source_url"):
        print(p["source_url"])


def compact_hours(hours: list[dict[str, Any]]) -> str:
    out = []
    for item in hours[:7]:
        if item.get("closed"):
            out.append(f"{item.get('day')}: closed")
        elif item.get("open") and item.get("close"):
            out.append(f"{item.get('day')}: {item.get('open')}-{item.get('close')}")
    return "; ".join(out)


def print_stores(data: dict[str, Any]) -> None:
    region = f" {data.get('region')}" if data.get("region") else ""
    print(f"{data.get('country')} stores{region}: {data.get('count')} stores ({data.get('elapsed_ms')} ms)")
    print()
    for s in data.get("stores") or []:
        print(f"{s.get('code'):>5}  {s.get('name')}")
        bits = [s.get("address"), s.get("phone"), s.get("email")]
        print("       " + " | ".join(str(x) for x in bits if x))
        hours = compact_hours(s.get("hours") or [])
        if hours:
            print(f"       {hours}")
        if s.get("source_url"):
            print(f"       {s.get('source_url')}")
        print()


def emit(data: dict[str, Any], as_json: bool, kind: str) -> None:
    if as_json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    elif kind == "product":
        print_product_detail(data)
    elif kind == "stores":
        print_stores(data)
    else:
        print_products(data, kind)


def cmd_search(args: argparse.Namespace) -> None:
    emit(search_products(country_cfg(args.country), args.query, args.limit), args.json, "search")


def cmd_product(args: argparse.Namespace) -> None:
    emit(product_detail(country_cfg(args.country), args.sku), args.json, "product")


def cmd_browse(args: argparse.Namespace) -> None:
    emit(browse_category(country_cfg(args.country), args.category, args.limit), args.json, "browse")


def cmd_stores(args: argparse.Namespace) -> None:
    emit(stores(country_cfg(args.country), args.region, args.limit), args.json, "stores")


def cmd_specials(args: argparse.Namespace) -> None:
    emit(promotional_products(country_cfg(args.country), args.query, args.limit), args.json, "specials")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Lightweight Bunnings NZ/AU public read-only product and store lookup CLI.")
    ap.add_argument("--country", choices=sorted(COUNTRIES), default=os.environ.get("BUNNINGS_COUNTRY", "nz").lower(), help="site country, default nz")
    sub = ap.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("search", help="search products")
    sp.add_argument("query")
    sp.add_argument("--limit", type=int, default=10)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_search)

    sp = sub.add_parser("product", help="fetch product details by SKU or product URL")
    sp.add_argument("sku")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_product)

    sp = sub.add_parser("browse", help="browse a product category path")
    sp.add_argument("category", help="category path, e.g. tools/power-tools/drills")
    sp.add_argument("--limit", type=int, default=10)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_browse)

    sp = sub.add_parser("stores", help="list stores")
    sp.add_argument("--region", help="region/path/name filter, e.g. uppernorthisland, lowernorthisland, nsw")
    sp.add_argument("--limit", type=int, default=20)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_stores)

    sp = sub.add_parser("specials", help="list redemption/promotion products, optionally filtered by query")
    sp.add_argument("query", nargs="?")
    sp.add_argument("--limit", type=int, default=10)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_specials)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
