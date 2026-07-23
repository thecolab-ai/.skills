#!/usr/bin/env python3
import json
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent
CLI = SKILL_DIR / "scripts" / "cli.py"


def run(args: list) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CLI)] + args,
        capture_output=True,
        text=True,
        cwd=str(SKILL_DIR),
        timeout=30,
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


def test_search_payload_fixture():
    import importlib.util

    spec = importlib.util.spec_from_file_location("paknsave_nz_cli", CLI)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    assert module.BANNER_CODE == "PNS"
    payload = module.search_payload("milk", "PAK-001", 12, 2, True)
    params = payload["algoliaQuery"]
    assert params["query"] == "milk"
    assert params["hitsPerPage"] == 12
    assert params["page"] == 1
    assert "onPromotion:PAK-001" in params["filters"]
    assert module.normalize_product_id("12345") == "12345-EA-000"
    print("[PASS] fixture PAK'nSAVE search payload normalisation")
    return True


results.append(test("fixture search payload builder", test_search_payload_fixture))


def test_auth_helpers_fixture():
    import base64
    import importlib.util

    spec = importlib.util.spec_from_file_location("paknsave_nz_auth_cli", CLI)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    def encoded(value: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(value).encode()).decode().rstrip("=")

    synthetic_token = f"{encoded({'alg': 'none'})}.{encoded({'exp': 4102444800, 'email': 'synthetic@example.invalid'})}.fixture"
    with tempfile.TemporaryDirectory() as directory:
        original_auth_file = module.AUTH_FILE
        original_auth_http = module.auth_http
        try:
            module.AUTH_FILE = Path(directory) / "auth.json"
            cached = module.save_auth_tokens(synthetic_token, "synthetic-refresh", "synthetic-device")
            assert cached["access_expires_epoch"] == 4102444800
            assert stat.S_IMODE(module.AUTH_FILE.stat().st_mode) == 0o600
            stored = json.loads(module.AUTH_FILE.read_text())
            assert "password" not in stored and "username" not in stored
            clubplus_cached = module.save_auth_tokens(
                synthetic_token,
                "synthetic-clubplus-refresh",
                "synthetic-device",
                refresh_kind="clubplus",
            )
            assert clubplus_cached["clubplus_refresh_token"] == "synthetic-clubplus-refresh"
            assert "refresh_token" not in clubplus_cached
            module.save_auth_tokens(synthetic_token, "synthetic-refresh", "synthetic-device")

            def fake_auth_http(method, url, data=None, **kwargs):
                assert method == "POST"
                assert url.endswith("/user/login/refresh")
                assert data["refreshToken"] == "synthetic-refresh"
                assert data["banner"] == "PNS"
                return {"access_token": synthetic_token, "refresh_token": "rotated-synthetic-refresh"}, {}

            module.auth_http = fake_auth_http
            refreshed = module.refresh_account()
            assert refreshed["refresh_token"] == "rotated-synthetic-refresh"
        finally:
            module.AUTH_FILE = original_auth_file
            module.auth_http = original_auth_http

    parser = module.build_parser(include_account=True)
    assert parser.parse_args(["orders", "--source", "IN_STORE"]).cmd == "orders"
    assert parser.parse_args(["auth", "mfa"]).auth_cmd == "mfa"
    assert parser.parse_args(["store-select", "--store-id", "synthetic-store"]).store_id == "synthetic-store"
    assert parser.parse_args(["list", "synthetic-list"]).list_id == "synthetic-list"
    assert parser.parse_args(["list-add", "synthetic-list", "12345"]).quantity == 1
    assert parser.parse_args(
        ["list-update", "synthetic-list", "12345", "--quantity", "1.5", "--sale-type", "WEIGHT"]
    ).quantity == 1.5
    assert parser.parse_args(["cart-add", "12345", "--quantity", "2"]).quantity == 2
    assert parser.parse_args(
        ["cart-update", "12345-KGM-000", "--quantity", "1250", "--sale-type", "WEIGHT"]
    ).quantity == 1250
    for invalid_quantity in ("0", "-1", "nan", "inf"):
        try:
            module.positive_quantity(invalid_quantity)
        except module.argparse.ArgumentTypeError:
            pass
        else:
            raise AssertionError(f"invalid quantity {invalid_quantity!r} was accepted")
    print("[PASS] fixture auth cache, refresh rotation, and command parsing")
    return True


results.append(test("fixture authenticated-personal helpers", test_auth_helpers_fixture))


def test_account_store_selection_contract():
    import importlib.util

    spec = importlib.util.spec_from_file_location("paknsave_nz_store_cli", CLI)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    calls = []

    def fake_auth_http(method, url, data=None, **kwargs):
        calls.append((method, url, data, kwargs.get("token")))
        if len(calls) == 1:
            raise module.AuthHTTPError(412, "PreconditionFailed", "Store is not set")
        if len(calls) == 2:
            return None, {}
        return {"fixture": True}, {}

    original_auth_http = module.auth_http
    original_get_account_token = module.get_account_token
    module.auth_http = fake_auth_http
    module.get_account_token = lambda force_refresh=False: "synthetic-access-token"
    try:
        result = module.account_api("PUT", "/list", {"name": "Fixture list", "products": []})
    finally:
        module.auth_http = original_auth_http
        module.get_account_token = original_get_account_token

    assert result == {"fixture": True}
    assert calls == [
        (
            "PUT",
            module.BASE_API + "/list",
            {"name": "Fixture list", "products": []},
            "synthetic-access-token",
        ),
        (
            "POST",
            module.BASE_API + f"/cart/store/{module.DEFAULT_STORE_ID}",
            None,
            "synthetic-access-token",
        ),
        (
            "PUT",
            module.BASE_API + "/list",
            {"name": "Fixture list", "products": []},
            "synthetic-access-token",
        ),
    ]
    print("[PASS] fixture first authenticated write selects a default store and retries")
    return True


results.append(test("fixture authenticated store selection", test_account_store_selection_contract))


def test_list_mutation_contract():
    import importlib.util

    spec = importlib.util.spec_from_file_location("paknsave_nz_list_cli", CLI)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    parser = module.build_parser(include_account=True)
    calls = []

    def fake_account_api(method, path, data=None):
        calls.append((method, path, data))
        return {"fixture": True}

    original_account_api = module.account_api
    module.account_api = fake_account_api
    try:
        for argv in (
            ["list-create", "Fixture list", "--json"],
            ["list-rename", "fixture-list", "Renamed fixture", "--json"],
            ["list-add", "fixture-list", "12345", "--quantity", "2", "--json"],
            [
                "list-update",
                "fixture-list",
                "12345",
                "--quantity",
                "1.5",
                "--sale-type",
                "WEIGHT",
                "--json",
            ],
            ["list-remove", "fixture-list", "12345", "--yes", "--json"],
            ["list-delete", "fixture-list", "--yes", "--json"],
        ):
            args = parser.parse_args(argv)
            args.func(args)
    finally:
        module.account_api = original_account_api

    assert calls == [
        ("PUT", "/list", {"name": "Fixture list", "products": []}),
        ("POST", "/list/fixture-list/rename", {"name": "Renamed fixture"}),
        (
            "POST",
            "/list/fixture-list/update-product",
            {"productId": "12345-EA-000", "sale_type": "UNITS", "quantity": 2},
        ),
        (
            "POST",
            "/list/fixture-list/update-product",
            {"productId": "12345-KGM-000", "sale_type": "WEIGHT", "quantity": 1.5},
        ),
        (
            "POST",
            "/list/fixture-list/update-product",
            {"productId": "12345-EA-000", "sale_type": "UNITS", "quantity": 0},
        ),
        ("DELETE", "/list/fixture-list", None),
    ]

    calls.clear()
    for argv in (
        ["list-remove", "fixture-list", "12345"],
        ["list-delete", "fixture-list"],
    ):
        args = parser.parse_args(argv)
        try:
            args.func(args)
        except SystemExit as exc:
            assert exc.code == 2
        else:
            raise AssertionError(f"{argv[0]} should require --yes")
    assert calls == []
    print("[PASS] fixture list mutation request shapes and destructive guards")
    return True


results.append(test("fixture list mutation contract", test_list_mutation_contract))


def test_cart_mutation_contract():
    import importlib.util

    spec = importlib.util.spec_from_file_location("paknsave_nz_cart_cli", CLI)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    parser = module.build_parser(include_account=True)
    calls = []

    def fake_account_api(method, path, data=None):
        calls.append((method, path, data))
        if method == "GET" and path == "/cart":
            return {
                "products": [
                    {
                        "productId": "12345-EA-000",
                        "quantity": 2,
                        "sale_type": "UNITS",
                    }
                ]
            }
        return {"products": [], "fixture": True}

    original_account_api = module.account_api
    module.account_api = fake_account_api
    try:
        for argv in (
            ["cart-add", "12345", "--quantity", "3", "--json"],
            [
                "cart-update",
                "54321-KGM-000",
                "--quantity",
                "1250",
                "--sale-type",
                "WEIGHT",
                "--json",
            ],
            ["cart-remove", "12345", "--yes", "--json"],
        ):
            args = parser.parse_args(argv)
            args.func(args)
    finally:
        module.account_api = original_account_api

    assert calls == [
        ("GET", "/cart", None),
        (
            "POST",
            "/cart",
            {
                "products": [
                    {
                        "productId": "12345-EA-000",
                        "sale_type": "UNITS",
                        "quantity": 5,
                    }
                ]
            },
        ),
        (
            "POST",
            "/cart",
            {
                "products": [
                    {
                        "productId": "54321-KGM-000",
                        "sale_type": "WEIGHT",
                        "quantity": 1250,
                    }
                ]
            },
        ),
        (
            "POST",
            "/cart",
            {
                "products": [
                    {
                        "productId": "12345-EA-000",
                        "sale_type": "UNITS",
                        "quantity": 0,
                    }
                ]
            },
        ),
    ]

    calls.clear()
    args = parser.parse_args(["cart-remove", "12345"])
    try:
        args.func(args)
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("cart-remove should require --yes")
    assert calls == []
    print("[PASS] fixture cart read/update request shapes and destructive guard")
    return True


results.append(test("fixture cart mutation contract", test_cart_mutation_contract))


def test_account_command_gate():
    import importlib.util

    spec = importlib.util.spec_from_file_location("paknsave_nz_command_gate_cli", CLI)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    assert not module.account_commands_enabled({})
    assert not module.account_commands_enabled({"PAKNSAVE_USERNAME": "member@example.invalid"})
    assert module.account_commands_enabled(
        {
            "PAKNSAVE_EMAIL": "member@example.invalid",
            "PAKNSAVE_PASSWORD": "synthetic-password",
        }
    )

    guest_parser = module.build_parser(include_account=False)
    guest_help = guest_parser.format_help()
    for hidden_command in ("auth", "orders", "store-select", "list-create", "cart-add"):
        assert hidden_command not in guest_help

    account_parser = module.build_parser(include_account=True)
    account_help = account_parser.format_help()
    for visible_command in ("auth", "orders", "store-select", "list-create", "cart-add"):
        assert visible_command in account_help
    print("[PASS] account commands are hidden until provider credentials are present")
    return True


results.append(test("fixture account command environment gate", test_account_command_gate))


def test_help():
    result = run(["--help"])
    if result.returncode != 0:
        return False
    return all(command not in result.stdout for command in ("orders", "list-create", "cart-add"))


results.append(test("--help exits 0", test_help))


def test_stores():
    result = run(["stores", "--query", "papakura", "--limit", "1", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    stores = json.loads(result.stdout)
    if not isinstance(stores, list) or len(stores) < 1:
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected at least one PAK'nSAVE store for Papakura")
        return False
    return True


results.append(test("stores --query papakura returns >= 1 result", test_stores))


def test_search():
    result = run(["search", "milk", "--limit", "1", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    search = json.loads(result.stdout)
    if not isinstance(search.get("products"), list):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected PAK'nSAVE search JSON to include products[]")
        return False
    return True


results.append(test("search milk returns products[]", test_search))

if all(results):
    print("[PASS] live smoke assertions completed")
    sys.exit(0)
else:
    print(f"{results.count(False)} test(s) failed.")
    sys.exit(1)
