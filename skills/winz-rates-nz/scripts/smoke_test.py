#!/usr/bin/env python3
import json
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent
CLI = SKILL_DIR / "scripts" / "cli.py"


def run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI)] + args,
        capture_output=True,
        text=True,
        cwd=str(SKILL_DIR),
        timeout=75,
    )


def is_upstream_blocked(result: subprocess.CompletedProcess[str]) -> bool:
    text = (result.stderr + "\n" + result.stdout).lower()
    return result.returncode == 2 and any(term in text for term in ("blocked", "incapsula", "timeout", "network error", "http 403", "http 429"))


def test(name: str, fn):
    try:
        outcome = fn()
        if outcome == "skip":
            print(f"[SKIP] {name} (upstream unavailable or blocked)")
            return "skip"
        status = "PASS" if outcome else "FAIL"
        prefix = f"[{status}] contract" if status == "PASS" and name.startswith("--help") else f"[{status}] live" if status == "PASS" else f"[{status}]"
        print(f"{prefix} {name}")
        return bool(outcome)
    except Exception as e:
        print(f"[FAIL] {name}")
        print(f"  error: {e}")
        return False


results = []


def test_help():
    result = run(["--help"])
    if result.returncode != 0:
        print(result.stderr[:300])
    return result.returncode == 0 and "rates" in result.stdout and "benefits" in result.stdout


results.append(test("--help exits 0", test_help))


def test_rates_list():
    result = run(["rates", "--year", "2026", "--json"])
    if is_upstream_blocked(result):
        print(f"  stderr: {result.stderr[:300]}")
        return "skip"
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:500]}")
        return False
    data = json.loads(result.stdout)
    payments = data.get("payments")
    if not isinstance(payments, list) or len(payments) < 5:
        print(f"  stdout: {result.stdout[:500]}")
        return False
    slugs = {p.get("slug") for p in payments}
    return "jobseeker-support" in slugs and any(p.get("tables") for p in payments)


results.append(test("rates --year 2026 --json returns payment sections", test_rates_list))


def test_rates_get():
    result = run(["rates", "get", "jobseeker-support", "--year", "2026", "--json"])
    if is_upstream_blocked(result):
        print(f"  stderr: {result.stderr[:300]}")
        return "skip"
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:500]}")
        return False
    data = json.loads(result.stdout)
    return data.get("slug") == "jobseeker-support" and isinstance(data.get("tables"), list) and len(data["tables"]) >= 1


results.append(test("rates get jobseeker-support returns tables", test_rates_get))


def test_benefits_list():
    result = run(["benefits", "list", "--json"])
    if is_upstream_blocked(result):
        print(f"  stderr: {result.stderr[:300]}")
        return "skip"
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:500]}")
        return False
    data = json.loads(result.stdout)
    benefits = data.get("benefits")
    if not isinstance(benefits, list) or len(benefits) < 10:
        print(f"  stdout: {result.stdout[:500]}")
        return False
    return any(b.get("slug") == "accommodation-supplement" for b in benefits)


results.append(test("benefits list --json returns A-Z benefit pages", test_benefits_list))


def test_benefit_get():
    result = run(["benefits", "get", "accommodation-supplement", "--json"])
    if is_upstream_blocked(result):
        print(f"  stderr: {result.stderr[:300]}")
        return "skip"
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:500]}")
        return False
    data = json.loads(result.stdout)
    return data.get("slug") == "accommodation-supplement" and data.get("title") and isinstance(data.get("sections"), list)


results.append(test("benefits get accommodation-supplement returns sections", test_benefit_get))


def test_rate_table_fixture():
    import importlib.util

    spec = importlib.util.spec_from_file_location("winz_rates_cli", CLI)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    section = module.parse_rate_section(
        "Synthetic Support",
        """
        <h3>Weekly payment</h3>
        <table><tr><th>Situation</th><th>Net weekly rate</th></tr><tr><td>Single</td><td>$420.00</td></tr></table>
        <p>Rates apply from 1 April 2026.</p>
        """,
    )
    assert section["slug"] == "synthetic-support"
    assert section["tables"][0]["context"] == "Weekly payment"
    assert section["tables"][0]["rows"] == [{"Situation": "Single", "Net weekly rate": "$420.00"}]
    print("[PASS] fixture WINZ rate-table parser")
    return True


results.append(test("fixture rate table parser", test_rate_table_fixture))

failures = [r for r in results if r is False]
if failures:
    print(f"{len(failures)} test(s) failed.")
    sys.exit(1)
print("All non-skipped tests passed.")
sys.exit(0)
