#!/usr/bin/env python3
import json
import subprocess
import sys
from pathlib import Path

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
            "price": {"originalPrice": 4.5, "salePrice": 3.9, "isSpecial": True, "savePrice": 0.6},
            "size": {"volumeSize": "2L", "cupPrice": 0.20, "cupMeasure": "100ml"},
            "quantity": {"min": 1, "max": 12, "increment": 1},
            "availabilityStatus": "In Stock",
            "breadcrumb": {"department": {"name": "Fresh"}, "aisle": {"name": "Dairy"}},
        }
    )
    assert record["sku"] == "705692"
    assert record["sale_price"] == 3.9
    assert record["is_special"] is True and record["in_stock"] is True
    assert record["category"] == "Fresh / Dairy"
    print("[PASS] fixture Woolworths product normalisation")
    return True


results.append(test("fixture product parser", test_product_fixture))


def test_account_command_gating():
    module = load_cli()
    public_help = module.build_parser(include_account=False).format_help()
    account_help = module.build_parser(include_account=True).format_help()
    assert "cart-add" not in public_help and "invoice-items" not in public_help
    assert "cart-add" in account_help and "invoice-items" in account_help
    assert module.account_commands_enabled({}) is False
    assert (
        module.account_commands_enabled(
            {"WOOLWORTHS_EMAIL": "fixture@example.test", "WOOLWORTHS_PASSWORD": "fixture"}
        )
        is True
    )
    return True


results.append(test("account commands are credential-gated", test_account_command_gating))


def test_account_request_contract():
    module = load_cli()
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"ok":true}'

    module.ensure_account_session = lambda **_kwargs: [
        {
            "name": "XSRF-TOKEN",
            "value": "fixture%20token",
            "domain": ".woolworths.co.nz",
        },
        {"name": "session", "value": "fixture", "domain": ".woolworths.co.nz"},
    ]

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeResponse()

    module.urllib.request.urlopen = fake_urlopen
    result = module.account_api(
        "POST",
        "/trolleys/my/items",
        {"sku": "705692", "quantity": 2, "pricingUnit": "Each"},
    )
    request = captured["request"]
    headers = {key.lower(): value for key, value in request.header_items()}
    assert result == {"ok": True}
    assert request.method == "POST"
    assert request.full_url == "https://www.woolworths.co.nz/api/v1/trolleys/my/items"
    assert headers["x-xsrf-token"] == "fixture token"
    assert headers["x-requested-with"] == "OnlineShopping.WebApp"
    assert json.loads(request.data) == {
        "sku": "705692",
        "quantity": 2,
        "pricingUnit": "Each",
    }
    return True


results.append(test("authenticated request headers and payload", test_account_request_contract))


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
            raise module.urllib.error.HTTPError(request.full_url, 401, "expired", {}, None)
        return FakeResponse()

    module.ensure_account_session = fake_session
    module.urllib.request.urlopen = fake_urlopen
    assert module.account_api("GET", "/shoppers/my/saved-lists") == {"ok": True}
    assert len(request_calls) == 2
    assert any(call.get("force") is True for call in session_calls)
    return True


results.append(test("401 refreshes and retries once", test_account_request_refresh_retry))


def test_past_order_item_pagination():
    module = load_cli()
    calls = []

    def fake_account_api(method, path, data=None, *, params=None, retry_auth=True):
        calls.append((method, path, params))
        page = params["page"]
        items = (
            [{"sku": "111111"}, {"sku": "222222"}]
            if page == 1
            else [{"sku": "333333"}]
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


results.append(test("past-order items paginate for large invoices", test_past_order_item_pagination))


def test_list_and_cart_payloads():
    module = load_cli()
    list_args = module.argparse.Namespace(sku="705692", quantity=3)
    assert module.list_item_payload(list_args) == {
        "itemsToAdd": [{"sku": "705692", "quantity": 3}]
    }
    assert module.cart_payload("705692", 2, "Each") == {
        "sku": "705692",
        "quantity": 2,
        "pricingUnit": "Each",
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
        "addFromListSource": "Unspecified",
    }
    return True


results.append(test("saved-list and trolley payload contracts", test_list_and_cart_payloads))


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


results.append(test("invoice rows join deterministically to SKUs", test_invoice_row_parser_and_sku_join))


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
