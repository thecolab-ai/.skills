#!/usr/bin/env python3
"""Deterministic and optional live smoke checks for the Trade Me skill."""

import importlib.util
import json
import subprocess
import sys
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent
CLI = SKILL_DIR / "scripts" / "cli.py"


def run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        capture_output=True,
        text=True,
        cwd=str(SKILL_DIR),
        timeout=45,
    )


def load_cli(name: str):
    spec = importlib.util.spec_from_file_location(name, CLI)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test(name: str, fn):
    try:
        ok = fn()
        if ok is None:
            print(f"[SKIP] {name}")
            return True
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
        return ok
    except Exception as exc:
        print(f"[FAIL] {name}")
        print(f"  error: {exc}")
        return False


def blocked(result: subprocess.CompletedProcess) -> bool:
    text = (result.stderr + result.stdout).lower()
    return any(
        marker in text
        for marker in (
            "network error",
            "rate-limited",
            "blocked after",
            "http 429",
            "http 503",
        )
    )


results = []


def test_listing_fixture():
    module = load_cli("trademe_nz_listing_cli")
    record = module.parse_listing(
        {
            "ListingId": 123456,
            "Title": "Synthetic Bicycle",
            "Region": "Wellington",
            "StartPrice": 100.0,
            "BuyNowPrice": 150.0,
            "StartDate": "/Date(1784419200000)/",
            "Attributes": [{"DisplayName": "Condition", "DisplayValue": "Used"}],
        },
        detail=True,
    )
    assert record["listing_id"] == 123456
    assert record["attributes"] == {"Condition": "Used"}
    assert record["url"].endswith("/123456/synthetic-bicycle")
    assert record["start_date"].startswith("2026-")
    return True


results.append(test("fixture public listing parser", test_listing_fixture))


def test_search_enforces_requested_limit():
    module = load_cli("trademe_nz_search_limit_cli")
    module.request_json = lambda path, params: {
        "TotalCount": 8,
        "Page": 1,
        "PageSize": 8,
        "List": [
            {"ListingId": index, "Title": f"Synthetic listing {index}"}
            for index in range(1, 9)
        ],
    }
    import argparse

    payload = module.search(
        argparse.Namespace(
            type="marketplace",
            query="synthetic",
            limit=3,
            page=1,
            region=None,
            category=None,
            price_min=None,
            price_max=None,
            bedrooms_min=None,
            bedrooms_max=None,
            sort=None,
        )
    )
    assert payload["page_size"] == 8
    assert payload["requested_limit"] == 3
    assert len(payload["listings"]) == 3
    assert [row["listing_id"] for row in payload["listings"]] == [1, 2, 3]
    return True


results.append(test("search enforces requested client limit", test_search_enforces_requested_limit))


def test_browser_read_plans():
    cases = {
        "seller-summary": "/a/my-trade-me/sell",
        "my-selling": "/a/my-trade-me/sell/selling",
        "my-sold": "/a/my-trade-me/sell/sold",
        "my-unsold": "/a/my-trade-me/sell/unsold",
    }
    for command, suffix in cases.items():
        result = run([command, "--json"])
        assert result.returncode == 0, result.stderr
        plan = json.loads(result.stdout)
        assert plan["surface"] == "browser"
        assert plan["url"].endswith(suffix)
        assert plan["authentication"] == "ordinary Trade Me website session"
        assert plan["mutation"] is False
        assert plan["action_time_confirmation_required"] is False
        assert "email/2FA" in plan["login_handoff"]
        assert "CAPTCHA" in plan["login_handoff"]
    detail = json.loads(run(["seller-listing", "1234567890", "--json"]).stdout)
    assert detail["url"].endswith("/a/listing/1234567890")
    assert detail["listing_id"] == 1234567890
    assert "exact visible listing id" in detail["target_match"]
    return True


results.append(test("browser-backed seller read plans", test_browser_read_plans))


def test_seller_plans_reject_non_positive_listing_ids():
    for command in (
        ["seller-listing", "-1", "--json"],
        ["prepare-edit", "0", "--json"],
        ["withdraw-listing", "-1", "--reason", "Synthetic", "--json"],
        ["relist-listing", "0", "--json"],
    ):
        result = run(command)
        assert result.returncode == 2
        assert "listing id must be a positive integer" in result.stderr
        assert not result.stdout
    return True


results.append(
    test(
        "seller plans reject non-positive listing ids",
        test_seller_plans_reject_non_positive_listing_ids,
    )
)


def test_browser_mutation_plans():
    fixture = SKILL_DIR / "tests" / "fixtures" / "listing-form.json"
    commands = (
        ["create-listing", "--data-file", str(fixture), "--json"],
        ["edit-listing", "--data-file", str(fixture), "--json"],
        [
            "withdraw-listing",
            "1234567890",
            "--reason",
            "Synthetic plan only",
            "--json",
        ],
        ["relist-listing", "1234567892", "--json"],
    )
    for command in commands:
        result = run(command)
        assert result.returncode == 0, result.stderr
        plan = json.loads(result.stdout)
        assert plan["surface"] == "browser"
        assert plan["mutation"] is True
        assert plan["action_time_confirmation_required"] is True
        assert "Stop on Trade Me's review/confirmation screen" in plan["final_step"]
        assert "final submit click" in plan["final_step"]
        if "listing_id" in plan:
            assert "exact visible listing id" in plan["target_match"]
        assert "executed" not in plan
        assert "fee_preview" not in plan
    return True


results.append(test("mutation plans require final browser confirmation", test_browser_mutation_plans))


def test_local_listing_validation():
    fixture = SKILL_DIR / "tests" / "fixtures" / "listing-form.json"
    result = run(["validate-listing", "--data-file", str(fixture), "--json"])
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["valid_for_browser_preparation"] is True
    assert all(payload["checks"].values())
    assert "no authenticated API call" in payload["note"]
    return True


results.append(test("local listing-input validation", test_local_listing_validation))


def test_withdraw_argument_gate():
    module = load_cli("trademe_nz_withdraw_cli")
    import argparse

    with redirect_stderr(StringIO()):
        try:
            module.validate_withdraw_args(
                argparse.Namespace(sold=True, sale_price=None)
            )
        except SystemExit as exc:
            assert exc.code == 2
        else:
            raise AssertionError("sold withdrawal accepted without sale price")
    module.validate_withdraw_args(
        argparse.Namespace(sold=True, sale_price=25.0)
    )
    return True


results.append(test("withdrawal intent validation", test_withdraw_argument_gate))


def test_no_credential_or_member_api_path():
    source = CLI.read_text(encoding="utf-8")
    forbidden = (
        "TRADEME_CONSUMER_KEY",
        "TRADEME_ACCESS_TOKEN",
        "oauth-request",
        "oauth-access",
        "SellerClient",
        "document.cookie",
        "localStorage",
        "sessionStorage",
        '"Authorization"',
        "mytrademe/summary.json",
        "Selling/Fees.json",
    )
    for marker in forbidden:
        assert marker not in source, marker
    result = run(["--help"])
    assert result.returncode == 0
    assert "browser-backed seller workflow planner" in result.stdout
    assert "oauth" not in result.stdout.lower()
    return True


results.append(test("no OAuth, credential, or browser-session extraction path", test_no_credential_or_member_api_path))


_listing_id = None


def test_search_marketplace():
    global _listing_id
    result = run(["search", "iphone", "--limit", "3", "--json"])
    if result.returncode != 0:
        if blocked(result):
            print(f"  Trade Me live search unavailable: {result.stderr[:160]}")
            return None
        print(f"  stderr: {result.stderr[:200]}")
        return False
    marketplace = json.loads(result.stdout)
    if not isinstance(marketplace.get("listings"), list) or not marketplace["listings"]:
        print(f"  stdout: {result.stdout[:200]}")
        return False
    if len(marketplace["listings"]) > 3:
        print("  --limit 3 returned more than three listings")
        return False
    _listing_id = str(marketplace["listings"][0].get("listing_id", ""))
    return True


results.append(test("search iphone returns listings[]", test_search_marketplace))


def test_listing():
    if not _listing_id:
        print("  No listing_id captured because live search was skipped")
        return None
    result = run(["listing", _listing_id, "--json"])
    if result.returncode != 0:
        if blocked(result):
            print(f"  Trade Me live listing unavailable: {result.stderr[:160]}")
            return None
        return False
    listing = json.loads(result.stdout)
    return bool(listing.get("listing", {}).get("listing_id"))


results.append(test("listing <id> returns listing.listing_id", test_listing))


if all(results):
    print("[PASS] deterministic assertions completed; live probes passed or were explicitly skipped")
    raise SystemExit(0)

print(f"{results.count(False)} test(s) failed.")
raise SystemExit(1)
