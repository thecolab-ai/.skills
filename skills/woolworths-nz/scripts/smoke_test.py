#!/usr/bin/env python3
import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock

SKILL_DIR = Path(__file__).parent.parent
CLI = SKILL_DIR / "scripts" / "cli.py"


def run(args: list) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CLI)] + args,
        capture_output=True,
        text=True,
        cwd=str(SKILL_DIR),
        timeout=45,
    )


def test(name: str, fn):
    try:
        ok = fn()
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {name}")
        return ok
    except Exception as e:
        print(f"[FAIL] {name}")
        print(f"  error: {e}")
        return False


results = []


def load_cli():
    import importlib.util

    name = f"woolworths_nz_cli_{len(sys.modules)}"
    spec = importlib.util.spec_from_file_location(name, CLI)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_product_fixture():
    module = load_cli()
    record = module.parse_product(
        {
            "sku": "705692",
            "name": "Synthetic Milk",
            "brand": "Example",
            "slug": "synthetic-milk",
            "price": {
                "originalPrice": 4.5,
                "salePrice": 3.9,
                "isSpecial": True,
                "savePrice": 0.6,
            },
            "size": {"volumeSize": "2L", "cupPrice": 0.20, "cupMeasure": "100ml"},
            "breadcrumb": {"department": {"name": "Fresh"}, "aisle": {"name": "Dairy"}},
        }
    )
    assert record["sku"] == "705692"
    assert record["sale_price"] == 3.9
    assert record["is_special"] is True
    assert record["category"] == "Fresh / Dairy"
    print("[PASS] fixture Woolworths product normalisation")
    return True


results.append(test("fixture product parser", test_product_fixture))


def load_graphql_api():
    import importlib.util

    path = SKILL_DIR / "scripts" / "graphql_api.py"
    name = f"woolworths_nz_graphql_{len(sys.modules)}"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_graphql_product_contract():
    module = load_graphql_api()
    fixture = json.loads(
        (SKILL_DIR / "tests" / "fixtures" / "graphql-products.json").read_text()
    )
    request = module.product_search_request(
        mode="keyword", value="milk", page=1, limit=24
    )
    assert request["operationName"] == "ProductSearch"
    assert request["variables"]["searchInput"]["byKeyword"]["pageIndex"] == 0
    parsed = module.parse_product_search(fixture)
    assert parsed["count"] == 1
    assert parsed["total"] == 1
    assert parsed["products"][0]["sku"] == "705692"
    assert parsed["products"][0]["variant_key"] == "705692-EA"
    assert parsed["products"][0]["sale_price"] == 3.9
    assert parsed["products"][0]["category"] == "Fresh / Dairy / Milk"
    return True


results.append(
    test("GraphQL product request and parser", test_graphql_product_contract)
)


def test_specials_overfetch_before_filter():
    cli = load_cli()
    requests = []
    emitted = []
    products = [
        {"sku": f"regular-{index}", "is_special": False} for index in range(3)
    ] + [{"sku": f"special-{index}", "is_special": True} for index in range(3)]
    cli.graphql_json = lambda request: requests.append(request) or {}
    cli.parse_graphql = lambda *_args, **_kwargs: {
        "products": products,
        "total": 6,
        "page": 1,
        "page_size": 24,
        "total_pages": 1,
    }
    cli.emit = lambda data, _as_json: emitted.append(data)
    args = cli.argparse.Namespace(query="cheese", page=1, limit=3, json=True)
    cli.cmd_specials(args)
    search_input = requests[0]["variables"]["searchInput"]["byKeyword"]
    assert search_input["pageSize"] > args.limit
    assert emitted[0]["count"] == 3
    assert all(item["is_special"] for item in emitted[0]["products"])
    return True


results.append(
    test("specials overfetch before filtering", test_specials_overfetch_before_filter)
)


def test_trolley_unit_resolution():
    graph = load_graphql_api()
    cli = load_cli()
    detail_request = graph.product_detail_request("424242")
    assert (
        "... on GroceryVariant {\n          key sku richDescription name"
        in detail_request["query"]
    )
    fixture = json.loads(
        (SKILL_DIR / "tests" / "fixtures" / "graphql-product-detail.json").read_text()
    )
    product = graph.parse_product_detail(fixture)
    assert product["variants"] == [
        {
            "variant_key": "424242-EA",
            "variant_sku": "424242-EA",
            "unit": "EA",
            "name": "Synthetic Produce Each",
        },
        {
            "variant_key": "424242-KG",
            "variant_sku": "424242-KG",
            "unit": "KG",
            "name": "Synthetic Produce By Weight",
        },
    ]
    detail_requests = []

    def fixture_detail(request):
        detail_requests.append(request)
        return fixture

    cli.graphql_json = fixture_detail
    empty = {"items": []}
    assert cli.resolve_variant_key("424242", empty, "Each") == "424242-EA"
    assert cli.resolve_variant_key("424242", empty, "Kg") == "424242-KG"
    existing_each = {
        "items": [
            {
                "sku": "424242",
                "variant_key": "424242-EA",
                "unit": "EA",
            }
        ]
    }
    assert cli.resolve_variant_key("424242", existing_each, "Kg") == "424242-KG"
    ambiguous = {
        "items": [
            {"sku": "424242", "variant_key": "424242-EA", "unit": "EA"},
            {"sku": "424242", "variant_key": "424242-KG", "unit": "KG"},
        ]
    }
    try:
        cli.resolve_variant_key("424242", ambiguous)
    except SystemExit:
        pass
    else:
        raise AssertionError("ambiguous trolley SKU must require an exact variant key")
    return True


results.append(
    test("trolley unit resolves exact variant", test_trolley_unit_resolution)
)


def test_graphql_cart_contract():
    module = load_graphql_api()
    cart_request = module.customer_cart_request()
    assert "product {\n        name\n        slug" in cart_request["query"]
    fixture = json.loads(
        (SKILL_DIR / "tests" / "fixtures" / "graphql-cart.json").read_text()
    )
    parsed = module.parse_customer_cart(fixture)
    assert parsed["cart_key"] == "synthetic-cart"
    assert parsed["item_count"] == 2
    assert parsed["items"][0]["variant_key"] == "705692-EA"
    assert parsed["items"][0]["unit"] == "EA"
    assert parsed["items"][0]["quantity"] == 2
    update = module.cart_quantity_request("705692-EA", 3)
    assert update["operationName"] == "SetCartLineItemQuantity"
    assert update["variables"]["input"]["cartLineItemQuantityUpdates"] == [
        {"variantKey": "705692-EA", "quantity": 3}
    ]
    clear = module.clear_cart_request()
    assert clear["operationName"] == "ClearCart"
    return True


results.append(test("GraphQL trolley request and parser", test_graphql_cart_contract))


def test_graphql_errors_fail_closed():
    module = load_graphql_api()
    try:
        module.parse_customer_cart(
            {"data": {"customerCart": {}}, "errors": [{"message": "fixture error"}]}
        )
    except module.GraphQLContractError as exc:
        assert "fixture error" in str(exc)
    else:
        raise AssertionError("GraphQL errors must fail closed")
    return True


results.append(test("GraphQL errors fail closed", test_graphql_errors_fail_closed))


def test_account_command_gating():
    module = load_cli()
    public_help = module.build_parser(include_account=False).format_help()
    account_help = module.build_parser(include_account=True).format_help()
    assert "cart-add" not in public_help and "invoice-items" not in public_help
    assert "cart-add" in account_help and "invoice-items" in account_help
    assert module.account_commands_enabled({}) is False
    assert (
        module.account_commands_enabled(
            {
                "WOOLWORTHS_EMAIL": "fixture@example.test",
                "WOOLWORTHS_PASSWORD": "fixture",
            }
        )
        is True
    )
    return True


results.append(
    test("account commands are credential-gated", test_account_command_gating)
)


def test_session_cache_is_bound_to_account():
    module = load_cli()
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "cookies.json"
        module.session_file = lambda: path
        matching_env = {
            "WOOLWORTHS_EMAIL": "first.fixture@example.test",
            "WOOLWORTHS_PASSWORD": "fixture",
        }
        with mock.patch.dict(os.environ, matching_env, clear=False):
            account_hash = module.account_cache_key()
            path.write_text(
                json.dumps(
                    {
                        "schema_version": "1",
                        "account_hash": account_hash,
                        "cookies": [
                            {
                                "name": "session",
                                "value": "fixture",
                                "domain": ".woolworths.co.nz",
                            }
                        ],
                    }
                )
            )
            assert len(module.load_session_cookies()) == 1
            with mock.patch.dict(
                os.environ,
                {"WOOLWORTHS_EMAIL": "second.fixture@example.test"},
                clear=False,
            ):
                assert module.load_session_cookies() == []

            # Legacy unbound list caches are intentionally invalidated.
            path.write_text(
                json.dumps(
                    [
                        {
                            "name": "session",
                            "value": "fixture",
                            "domain": ".woolworths.co.nz",
                        }
                    ]
                )
            )
            assert module.load_session_cookies() == []
    return True


results.append(
    test(
        "session cache is bound to supplied account",
        test_session_cache_is_bound_to_account,
    )
)


def test_cookie_cache_is_created_private():
    module = load_cli()
    sys.path.insert(0, str(CLI.parent))
    import browser_auth

    with tempfile.TemporaryDirectory() as directory:
        parent = Path(directory) / "woolworths-nz"
        path = parent / "cookies.json"
        browser_auth._save_cookies(
            path,
            [
                {
                    "name": "session",
                    "value": "fixture",
                    "domain": ".woolworths.co.nz",
                }
            ],
            "fixture@example.test",
        )
        payload = json.loads(path.read_text())
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert stat.S_IMODE(parent.stat().st_mode) == 0o700
        assert payload["account_hash"] == module.account_cache_key(
            "fixture@example.test"
        )
        assert "fixture@example.test" not in path.read_text()
        assert not list(parent.glob("*.tmp"))
    return True


results.append(
    test("cookie cache is atomically private", test_cookie_cache_is_created_private)
)


def test_custom_cache_parent_permissions_are_preserved():
    sys.path.insert(0, str(CLI.parent))
    import browser_auth

    with tempfile.TemporaryDirectory() as directory:
        parent = Path(directory) / "woolworths-nz"
        parent.mkdir(mode=0o755)
        parent.chmod(0o755)
        path = parent / "cookies.json"
        browser_auth._save_cookies(
            path,
            [
                {
                    "name": "session",
                    "value": "fixture",
                    "domain": ".woolworths.co.nz",
                }
            ],
            "fixture@example.test",
        )
        assert stat.S_IMODE(parent.stat().st_mode) == 0o755
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    return True


results.append(
    test(
        "custom cache parent permissions are preserved",
        test_custom_cache_parent_permissions_are_preserved,
    )
)


def test_response_cookie_merge_is_domain_scoped():
    module = load_cli()

    class FakeHeaders:
        def get_all(self, name):
            if name.lower() != "set-cookie":
                return []
            return [
                "ak_bmsc=fresh; Domain=.woolworths.co.nz; Path=/; Secure; HttpOnly",
                "foreign=blocked; Domain=.example.test; Path=/; Secure",
            ]

    original = [
        {
            "name": "ak_bmsc",
            "value": "stale",
            "domain": ".woolworths.co.nz",
            "path": "/",
        },
        {
            "name": "session",
            "value": "fixture",
            "domain": ".woolworths.co.nz",
            "path": "/",
        },
    ]
    merged, changed = module.merge_response_cookies(original, FakeHeaders())
    by_name = {item["name"]: item for item in merged}
    assert changed is True
    assert by_name["ak_bmsc"]["value"] == "fresh"
    assert by_name["session"]["value"] == "fixture"
    assert "foreign" not in by_name
    assert original[0]["value"] == "stale"
    return True


results.append(
    test(
        "response cookie refresh stays domain-scoped",
        test_response_cookie_merge_is_domain_scoped,
    )
)


def test_account_request_contract():
    module = load_cli()
    captured = {"requests": [], "saved": []}

    class FakeResponse:
        def __init__(self, payload, headers=None):
            self.payload = payload
            self.headers = headers

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps(self.payload).encode()

    class FakeHeaders:
        def __init__(self, values):
            self.values = values

        def get_all(self, name):
            return self.values if name.lower() == "set-cookie" else []

    module.ensure_account_session = lambda **_kwargs: [
        {
            "name": "XSRF-TOKEN",
            "value": "fixture%20token",
            "domain": ".woolworths.co.nz",
        },
        {"name": "session", "value": "fixture", "domain": ".woolworths.co.nz"},
        {"name": "ak_bmsc", "value": "stale", "domain": ".woolworths.co.nz"},
    ]
    module.save_session_cookies = lambda cookies: captured["saved"].append(cookies)

    def fake_urlopen(request, timeout):
        captured["requests"].append((request, timeout))
        if request.method == "GET":
            return FakeResponse(
                {"isAuthenticated": True},
                FakeHeaders(
                    [
                        "ak_bmsc=fresh; Domain=.woolworths.co.nz; "
                        "Path=/; Secure; HttpOnly"
                    ]
                ),
            )
        return FakeResponse({"ok": True})

    module.urllib.request.urlopen = fake_urlopen
    result = module.account_api(
        "POST",
        "/trolleys/my/items",
        {"sku": "705692", "quantity": 2, "pricingUnit": "Each"},
    )
    assert len(captured["requests"]) == 2
    refresh_request = captured["requests"][0][0]
    request = captured["requests"][1][0]
    headers = {key.lower(): value for key, value in request.header_items()}
    assert result == {"ok": True}
    assert refresh_request.method == "GET"
    assert (
        refresh_request.full_url == "https://www.woolworths.co.nz/api/v1/bff/get-user"
    )
    assert request.method == "POST"
    assert request.full_url == "https://www.woolworths.co.nz/api/v1/trolleys/my/items"
    assert headers["x-xsrf-token"] == "fixture token"
    assert headers["x-requested-with"] == "OnlineShopping.WebApp"
    assert headers["cache-control"] == "no-cache"
    assert "ak_bmsc=fresh" in headers["cookie"]
    assert "ak_bmsc=stale" not in headers["cookie"]
    assert captured["saved"]
    assert json.loads(request.data) == {
        "sku": "705692",
        "quantity": 2,
        "pricingUnit": "Each",
    }
    return True


results.append(
    test("authenticated request headers and payload", test_account_request_contract)
)


def test_account_graphql_contract():
    module = load_cli()
    graph = load_graphql_api()
    captured = []
    cookies = [
        {"name": "XSRF-TOKEN", "value": "fixture-token", "domain": ".woolworths.co.nz"},
        {"name": "session", "value": "fixture", "domain": ".woolworths.co.nz"},
    ]

    class FakeResponse:
        headers = None

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"data":{"customerCart":{"lineItems":[]}}}'

    module.ensure_account_session = lambda **_kwargs: cookies
    module.refresh_account_cookies = lambda value, **_kwargs: value
    module.update_session_from_response = lambda *_args, **_kwargs: None

    def fake_urlopen(request, timeout):
        captured.append((request, timeout))
        return FakeResponse()

    module.urllib.request.urlopen = fake_urlopen
    module.account_graphql(graph.customer_cart_request())
    module.account_graphql(graph.cart_quantity_request("705692-EA", 2), mutation=True)
    assert len(captured) == 2
    assert captured[0][0].get_header("Wnzx-operation-name") == "CustomerCart"
    assert captured[1][0].get_header("Wnzx-operation-name") == "SetCartLineItemQuantity"
    assert captured[1][0].get_header("X-xsrf-token") == "fixture-token"
    request_payload = json.loads(captured[1][0].data)
    assert request_payload["variables"]["input"]["cartLineItemQuantityUpdates"] == [
        {"variantKey": "705692-EA", "quantity": 2}
    ]
    try:
        module.account_graphql(
            {"operationName": "PlaceOrder", "query": "mutation PlaceOrder { x }"},
            mutation=True,
        )
    except SystemExit:
        pass
    else:
        raise AssertionError("unapproved account mutations must be blocked")
    return True


results.append(test("current GraphQL trolley transport", test_account_graphql_contract))


def test_account_graphql_refresh_retry():
    module = load_cli()
    graph = load_graphql_api()
    cookies = [
        {
            "name": "XSRF-TOKEN",
            "value": "fixture-token",
            "domain": ".woolworths.co.nz",
        }
    ]
    session_calls = []
    request_calls = []

    def fake_session(**kwargs):
        session_calls.append(kwargs)
        return cookies

    class FakeResponse:
        headers = None

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"data":{"setCartLineItemQuantity":{"lineItems":[]}}}'

    def fake_urlopen(request, timeout):
        request_calls.append((request, timeout))
        if len(request_calls) == 1:
            raise module.urllib.error.HTTPError(
                request.full_url, 401, "Unauthorized", {}, None
            )
        return FakeResponse()

    module.ensure_account_session = fake_session
    module.refresh_account_cookies = lambda value, **_kwargs: value
    module.update_session_from_response = lambda *_args, **_kwargs: None
    module.urllib.request.urlopen = fake_urlopen
    result = module.account_graphql(
        graph.cart_quantity_request("705692-EA", 2), mutation=True
    )
    assert result["data"]["setCartLineItemQuantity"]["lineItems"] == []
    assert len(request_calls) == 2
    assert sum(call.get("force") is True for call in session_calls) == 1
    return True


results.append(
    test("GraphQL 401 refreshes and retries once", test_account_graphql_refresh_retry)
)


def test_account_graphql_xsrf_refresh():
    module = load_cli()
    graph = load_graphql_api()
    state = {"fresh": False}
    requests = []
    stale = [{"name": "session", "value": "stale", "domain": ".woolworths.co.nz"}]
    fresh = [
        {
            "name": "XSRF-TOKEN",
            "value": "fresh-token",
            "domain": ".woolworths.co.nz",
        }
    ]

    def fake_session(**kwargs):
        if kwargs.get("force"):
            state["fresh"] = True
        return fresh if state["fresh"] else stale

    class FakeResponse:
        headers = None

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"data":{"clearCart":{"lineItems":[]}}}'

    def fake_urlopen(request, timeout):
        requests.append((request, timeout))
        return FakeResponse()

    module.ensure_account_session = fake_session
    module.refresh_account_cookies = lambda value, **_kwargs: value
    module.update_session_from_response = lambda *_args, **_kwargs: None
    module.urllib.request.urlopen = fake_urlopen
    module.account_graphql(graph.clear_cart_request(), mutation=True)
    assert len(requests) == 1
    assert requests[0][0].get_header("X-xsrf-token") == "fresh-token"
    return True


results.append(
    test(
        "GraphQL refreshes missing XSRF before send", test_account_graphql_xsrf_refresh
    )
)


def test_account_request_refresh_retry():
    module = load_cli()
    session_calls = []
    request_calls = []
    cookies = [
        {"name": "XSRF-TOKEN", "value": "fixture", "domain": ".woolworths.co.nz"},
        {"name": "session", "value": "fixture", "domain": ".woolworths.co.nz"},
    ]

    def fake_session(**kwargs):
        session_calls.append(kwargs)
        return cookies

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"ok":true}'

    def fake_urlopen(request, timeout):
        request_calls.append((request, timeout))
        if len(request_calls) == 1:
            raise module.urllib.error.HTTPError(
                request.full_url, 401, "expired", {}, None
            )
        return FakeResponse()

    module.ensure_account_session = fake_session
    module.urllib.request.urlopen = fake_urlopen
    assert module.account_api("GET", "/shoppers/my/saved-lists") == {"ok": True}
    assert len(request_calls) == 2
    assert any(call.get("force") is True for call in session_calls)
    return True


results.append(
    test("401 refreshes and retries once", test_account_request_refresh_retry)
)


def test_non_json_mutation_is_never_replayed():
    module = load_cli()
    request_calls = []
    session_calls = []
    cookies = [
        {"name": "XSRF-TOKEN", "value": "fixture", "domain": ".woolworths.co.nz"},
        {"name": "session", "value": "fixture", "domain": ".woolworths.co.nz"},
    ]

    def fake_session(**kwargs):
        session_calls.append(kwargs)
        return cookies

    class HtmlResponse:
        headers = None

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b"<html>uncertain response</html>"

    class AuthResponse:
        headers = None

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"isAuthenticated":true}'

    def fake_urlopen(request, timeout):
        request_calls.append((request, timeout))
        if request.method == "GET":
            return AuthResponse()
        return HtmlResponse()

    module.ensure_account_session = fake_session
    module.urllib.request.urlopen = fake_urlopen
    try:
        module.account_api(
            "POST",
            "/trolleys/my/items",
            {"sku": "705692", "quantity": 2, "pricingUnit": "Each"},
        )
    except SystemExit as exc:
        assert exc.code == 1
    else:
        raise AssertionError("non-JSON mutation should fail as uncertain")
    assert len(request_calls) == 2
    assert [request.method for request, _timeout in request_calls] == ["GET", "POST"]
    assert not any(call.get("force") is True for call in session_calls)
    return True


results.append(
    test(
        "non-JSON mutations are never replayed",
        test_non_json_mutation_is_never_replayed,
    )
)


def test_text_auth_status_rejects_anonymous_response():
    module = load_cli()
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "cookies.json"
        path.write_text("{}")
        module.session_file = lambda: path
        module.account_api = lambda *_args, **_kwargs: {
            "isAuthenticated": False,
            "isLoggedIn": False,
        }
        try:
            module.cmd_auth_status(module.argparse.Namespace(json=False))
        except SystemExit as exc:
            assert exc.code == 1
        else:
            raise AssertionError("anonymous status must not report a valid session")
    return True


results.append(
    test(
        "text auth status rejects anonymous response",
        test_text_auth_status_rejects_anonymous_response,
    )
)


def test_past_order_item_pagination():
    module = load_cli()
    calls = []

    def fake_account_api(method, path, data=None, *, params=None, retry_auth=True):
        calls.append((method, path, params))
        page = params["page"]
        items = (
            [{"sku": "111111"}, {"sku": "222222"}] if page == 1 else [{"sku": "333333"}]
        )
        return {"products": {"items": items, "totalItems": 3}}

    module.account_api = fake_account_api
    result = module.fetch_past_order_items("fixture-order", page_size=2)
    assert [item["sku"] for item in result["products"]["items"]] == [
        "111111",
        "222222",
        "333333",
    ]
    assert [call[2]["page"] for call in calls] == [1, 2]
    return True


results.append(
    test(
        "past-order items paginate for large invoices", test_past_order_item_pagination
    )
)


def test_list_and_cart_payloads():
    module = load_cli()
    parser = module.build_parser(include_account=True)
    assert (
        parser.parse_args(["list-add", "fixture-list", "705692"]).func
        is module.cmd_list_add
    )
    assert (
        parser.parse_args(
            ["list-update", "fixture-list", "705692", "--quantity", "3"]
        ).func
        is module.cmd_list_update
    )
    list_args = module.argparse.Namespace(sku="705692", quantity=3)
    assert module.list_item_payload(list_args) == {
        "itemsToAdd": [{"sku": "705692", "quantity": 3}]
    }
    calls = []
    module.account_api = lambda method, path, payload=None: (
        calls.append((method, path, payload)) or {"ok": True}
    )
    module.emit_json_or_summary = lambda *_args, **_kwargs: None
    module.cmd_list_update(
        module.argparse.Namespace(
            list_id="fixture-list", sku="705692", quantity=3, json=True
        )
    )
    assert calls == [
        (
            "POST",
            "/shoppers/my/saved-lists/fixture-list/items/705692",
            {"itemsToAdd": [{"sku": "705692", "quantity": 3}]},
        )
    ]
    trolley_request = module.cart_payload("705692-EA", 2, "Each")
    assert trolley_request["operationName"] == "SetCartLineItemQuantity"
    assert trolley_request["variables"]["input"] == {
        "cartLineItemQuantityUpdates": [{"variantKey": "705692-EA", "quantity": 2}]
    }
    cart = {
        "items": [
            {
                "products": [
                    {"sku": "705692", "name": "Fixture Milk", "quantity": {"value": 2}}
                ]
            }
        ]
    }
    products = module.cart_products(cart)
    assert len(products) == 1
    assert module.cart_item_quantity(products[0]) == 2

    create_payload = module.list_create_payload(
        module.argparse.Namespace(
            name="Fixture list",
            source="empty",
            source_id=None,
        )
    )
    assert create_payload == {
        "listName": "Fixture list",
        "addFromListSource": "Trolley",
    }
    calls = []

    def empty_trolley_account_api(method, path, data=None, **_kwargs):
        calls.append((method, path, data))
        return {"ok": True}

    module.read_cart = lambda: {"items": []}
    module.account_api = empty_trolley_account_api
    module.cmd_list_create(
        module.argparse.Namespace(
            name="Fixture list",
            source="empty",
            source_id=None,
            json=True,
        )
    )
    assert calls == [
        (
            "POST",
            "/shoppers/my/saved-lists",
            {"listName": "Fixture list", "addFromListSource": "Trolley"},
        ),
    ]

    module.read_cart = lambda: {
        "items": [{"sku": "705692", "variant_key": "705692-EA", "quantity": 1}]
    }
    try:
        module.cmd_list_create(
            module.argparse.Namespace(
                name="Fixture list",
                source="empty",
                source_id=None,
                json=True,
            )
        )
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("empty-list creation must refuse a non-empty trolley")
    try:
        module.positive_quantity("nan")
    except module.argparse.ArgumentTypeError:
        pass
    else:
        raise AssertionError("NaN must not be accepted as a quantity")
    try:
        module.cart_payload("705692", float("nan"), "Kg")
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("NaN must not reach a trolley payload")
    return True


results.append(
    test("saved-list and trolley payload contracts", test_list_and_cart_payloads)
)


def test_invoice_mismatch_fails_before_account_fetch():
    module = load_cli()
    sys.path.insert(0, str(CLI.parent))
    import invoice_parser

    events = []

    def fake_parse(_path):
        events.append("parse")
        return {"page_count": 1, "order_number": "invoice-order", "items": []}

    def fake_fetch(_order_id):
        events.append("fetch")
        return {"products": {"items": [], "totalItems": 0}}

    module.fetch_past_order_items = fake_fetch
    args = module.argparse.Namespace(
        order_id="different-order",
        invoice_pdf="fixture.pdf",
        min_confidence=0.72,
        json=True,
    )
    with mock.patch.object(invoice_parser, "parse_invoice_pdf", fake_parse):
        try:
            module.cmd_invoice_items(args)
        except SystemExit as exc:
            assert exc.code == 2
        else:
            raise AssertionError("a mismatched invoice must be rejected")
    assert events == ["parse"]
    return True


results.append(
    test(
        "invoice mismatch fails before account fetch",
        test_invoice_mismatch_fails_before_account_fetch,
    )
)


def test_invoice_row_parser_and_sku_join():
    module = load_cli()
    sys.path.insert(0, str(CLI.parent))
    import invoice_parser

    def words(text, x0, top, fontname="Fixture-Regular"):
        result = []
        cursor = x0
        for token in text.split():
            width = max(4, len(token) * 4)
            result.append(
                {
                    "text": token,
                    "x0": cursor,
                    "x1": cursor + width,
                    "top": top,
                    "fontname": fontname,
                    "size": 9,
                }
            )
            cursor += width + 3
        return result

    boundaries = [0, 40, 300, 360, 420, 500, 580]
    fixture_words = []
    fixture_words += words(
        "Order Confirmation/Invoice Number fixture-order-123",
        370,
        2,
    )
    fixture_words += words("1", 10, 30)
    fixture_words += words("Fixture Tea Bags", 50, 30)
    fixture_words += words("2 ea", 310, 30)
    fixture_words += words("2 ea", 370, 30)
    fixture_words += words("$3.50/ea", 430, 30)
    fixture_words += words("$7.00", 510, 30)
    fixture_words += words("40 pack", 50, 42)
    fixture_words += words("2", 10, 60)
    fixture_words += words("Synthetic Biscuits 200 g", 50, 60)
    fixture_words += words("1 ea", 310, 60)
    fixture_words += words("1 ea", 370, 60)
    fixture_words += words("$4.20/ea", 430, 60)
    fixture_words += words("$4.20", 510, 60)

    rows = invoice_parser.parse_invoice_word_rows(
        fixture_words,
        boundaries,
        page_number=1,
        header_top=10,
    )
    assert len(rows) == 2
    assert rows[0]["invoice_description"] == "Fixture Tea Bags 40 pack"
    assert rows[0]["supplied_quantity"] == 2
    assert rows[1]["unit_price"] == 4.2
    invoice_order_number = invoice_parser.extract_invoice_order_number(fixture_words)
    assert invoice_order_number == "fixture-order-123"
    invoice_parser.validate_invoice_order_number(
        invoice_order_number,
        "FIXTUREORDER123",
    )
    try:
        invoice_parser.validate_invoice_order_number(
            invoice_order_number,
            "different-order",
        )
    except invoice_parser.InvoiceParseError:
        pass
    else:
        raise AssertionError("mismatched invoice/order identifiers must be rejected")

    products = [
        {
            "sku": "111111",
            "brand": "Example",
            "name": "Fixture Tea Bags",
            "variety": "",
            "size": {"volumeSize": "40 pack"},
        },
        {
            "sku": "222222",
            "brand": "Example",
            "name": "Synthetic Biscuits",
            "variety": "",
            "size": {"volumeSize": "200g"},
        },
    ]
    joined = invoice_parser.match_invoice_items(rows, products)
    assert joined["summary"]["matched"] == 2
    assert joined["summary"]["ambiguous"] == 0
    assert [item["sku"] for item in joined["items"]] == ["111111", "222222"]
    assert module.confidence("0.8") == 0.8
    return True


results.append(
    test(
        "invoice rows join deterministically to SKUs",
        test_invoice_row_parser_and_sku_join,
    )
)


def test_help():
    result = run(["--help"])
    return result.returncode == 0


results.append(test("--help exits 0", test_help))

_search_sku = "705692"


def test_search():
    global _search_sku
    result = run(["search", "milk", "--limit", "3", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    search = json.loads(result.stdout)
    if not isinstance(search.get("products"), list) or len(search["products"]) < 1:
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected Woolworths search JSON to include products[]")
        return False
    sku = search["products"][0].get("sku")
    if sku:
        _search_sku = str(sku)
    return True


results.append(test("search milk returns products[]", test_search))


_category_key = ""


def test_categories_and_browse():
    global _category_key
    result = run(["categories", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    categories = json.loads(result.stdout)
    children = categories.get("children") or []
    if not children or not children[0].get("key"):
        print("  Expected Woolworths categories JSON to include children[].key")
        return False
    _category_key = str(children[0]["key"])
    result = run(["browse", _category_key, "--limit", "2", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    browse = json.loads(result.stdout)
    return isinstance(browse.get("products"), list) and bool(browse["products"])


results.append(test("categories feed browse keys", test_categories_and_browse))


def test_product():
    result = run(["product", _search_sku, "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    product = json.loads(result.stdout)
    if not isinstance(product.get("products"), list) or len(product["products"]) < 1:
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected Woolworths product JSON to include a SKU product")
        return False
    if not product["products"][0].get("sku"):
        print("  Expected Woolworths product JSON to include a SKU product")
        return False
    return True


results.append(test("product <sku> returns products[].sku", test_product))


def test_specials():
    result = run(["specials", "cheese", "--limit", "3", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    specials = json.loads(result.stdout)
    if not isinstance(specials.get("products"), list):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected Woolworths specials JSON to include products[]")
        return False
    return True


results.append(test("specials cheese returns products[]", test_specials))

if all(results):
    print("[PASS] live smoke assertions completed")
    sys.exit(0)
else:
    print(f"{results.count(False)} test(s) failed.")
    sys.exit(1)
