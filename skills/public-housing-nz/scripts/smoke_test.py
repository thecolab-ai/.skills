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
        timeout=120,
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


def test_help():
    result = run(["--help"])
    return result.returncode == 0


results.append(test("--help exits 0", test_help))


def test_datasets():
    result = run(["datasets", "--limit", "3", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("packages"), list) or not data["packages"]:
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected non-empty packages[] from datasets")
        return False
    return True


results.append(test("datasets returns packages", test_datasets))


def test_public_homes():
    result = run(["public-homes", "--provider", "KO", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("records"), list) or not data["records"]:
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected non-empty records[] from public-homes")
        return False
    if data.get("as_at_date") is None:
        print("  Expected as_at_date to be set")
        return False
    return True


results.append(test("public-homes returns records", test_public_homes))


def test_tenancies():
    result = run(["tenancies", "--area", "Invercargill City", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("records"), list) or not data["records"]:
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected non-empty records[] from tenancies")
        return False
    if data["records"][0].get("total_irrs_and_market_rent_tenancies") is None:
        print("  Expected tenancy value to be set")
        return False
    return True


results.append(test("tenancies returns records", test_tenancies))


def test_accommodation_supplement():
    result = run(["accommodation-supplement", "--area", "Ashburton", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("records"), list) or not data["records"]:
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected non-empty records[] from accommodation-supplement")
        return False
    return True


results.append(test("accommodation-supplement returns records", test_accommodation_supplement))


def test_local_stats():
    result = run(["local-stats", "--series", "Change in Housing Register", "--limit", "5", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("records"), list) or not data["records"]:
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected non-empty records[] from local-stats")
        return False
    return True


results.append(test("local-stats returns register-change records", test_local_stats))


def test_series():
    result = run(["series", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("themes"), dict) or not data["themes"]:
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected non-empty themes{} from series")
        return False
    return True


results.append(test("series lists themes", test_series))


def test_query():
    result = run(["query", "--resource", "sochouse", "--filter", "TLA_Name=WHANGAREI DISTRICT", "--limit", "3", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("records"), list) or not data["records"]:
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected non-empty records[] from query passthrough")
        return False
    return True


results.append(test("query passthrough returns records", test_query))


if all(results):
    print("All tests passed.")
    sys.exit(0)
else:
    print(f"{results.count(False)} test(s) failed.")
    sys.exit(1)
