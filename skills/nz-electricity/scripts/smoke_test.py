#!/usr/bin/env python3
import json
import importlib.util
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent
CLI = SKILL_DIR / "scripts" / "cli.py"

spec = importlib.util.spec_from_file_location("nz_electricity_cli", CLI)
cli = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(cli)


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


def test_help():
    result = run(["--help"])
    return result.returncode == 0


results.append(test("--help exits 0", test_help))


def test_spot():
    result = run(["spot", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("prices"), list):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected prices[] in spot response")
        return False
    return True


results.append(test("spot returns prices[]", test_spot))


def test_carbon():
    result = run(["carbon", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("readings"), list):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected readings[] in carbon response")
        return False
    return True


results.append(test("carbon returns readings[]", test_carbon))


def test_demand():
    result = run(["demand", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data, dict):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected dict response from demand")
        return False
    return True


results.append(test("demand returns dict", test_demand))


DG_SAMPLE = """Installed distributed generation trends

From www.emi.ea.govt.nz provided by the Electricity Authority (New Zealand)
Run at: 20260705203343

Parameters
Date range,01 Jan 2025 - 31 Dec 2025
Region type,New Zealand
Market segment,Residential
Capacity,All combined
Fuel type,Solar (all)

Month end,Region ID,Region name,Capacity,Fuel type,ICP count,ICP uptake rate (%),Total capacity installed (MW),Avg. capacity installed (kW),ICP count - new installations,Avg. capacity - new installations (kW)
31/01/2025,NZ,New Zealand,All combined,Solar (All),"64,571",3.25294,326.594,5.058,622,7.726
28/02/2025,NZ,New Zealand,All combined,Solar (All),65286,3.28550,332.142,5.087,760,
"""


def test_dg_parser_handles_metadata_and_numbers():
    parsed = cli.parse_dg_report_csv(DG_SAMPLE, "https://example.invalid/GUEHMT.csv")
    rows = parsed["rows"]
    if parsed["metadata"].get("run_at") != "20260705203343":
        print(f"  metadata: {parsed['metadata']}")
        return False
    if rows[0]["month_end"] != "2025-01-31":
        print(f"  first row: {rows[0]}")
        return False
    if rows[0]["icp_count"] != 64571:
        print(f"  Expected comma-formatted ICP count to normalise, got {rows[0]['icp_count']}")
        return False
    if rows[1]["avg_new_installation_capacity_kw"] is not None:
        print(f"  Expected blank numeric value to be None, got {rows[1]['avg_new_installation_capacity_kw']}")
        return False
    return True


results.append(test("fixture DG parser skips metadata and normalises numbers", test_dg_parser_handles_metadata_and_numbers))


def test_dg_latest_command():
    result = run(["dg-latest", "--fuel", "solar_all", "--market-segment", "All", "--json"])
    if result.returncode != 0:
        stderr = result.stderr.lower()
        flaky = ("network error" in stderr or "timeout" in stderr or "http 5" in stderr)
        if flaky:
            print(f"  skipping upstream failure: {result.stderr[:200]}")
            return True
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if data.get("report_code") != "GUEHMT" or not isinstance(data.get("latest"), list):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected GUEHMT latest[] response")
        return False
    return True


results.append(test("dg-latest returns GUEHMT latest[]", test_dg_latest_command))


def test_energy_margin_status():
    result = run(["energy-margin", "--company", "meridian", "--timeout", "5", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if data.get("source") != "Electricity Authority gentailer energy margin dashboard/article":
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected EA energy margin source label")
        return False
    if data.get("company_filter") != "Meridian":
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected company filter to normalise to Meridian")
        return False
    if not isinstance(data.get("source_checks"), list):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected source_checks[] diagnostics")
        return False
    if data.get("energy_margins") != []:
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected no copied or derived margin rows while the official feed is unavailable")
        return False
    if not data.get("guidance"):
        print("  Expected guidance text pointing at official alternatives")
        return False
    alternatives = data.get("alternatives")
    if not isinstance(alternatives, list) or not alternatives:
        print("  Expected non-empty alternatives[] to point AI at official per-company sources")
        return False
    if not all(alt.get("source_url") or alt.get("source_urls") for alt in alternatives):
        print("  Expected every alternative to carry a source URL")
        return False
    if not (data.get("aggregate_energy_margin") or {}).get("weekly_average_million_nzd"):
        print("  Expected official aggregate energy-margin reference")
        return False
    return True


results.append(test("energy-margin reports official source status", test_energy_margin_status))


def test_energy_margin_company_filters_alternatives():
    # Nova is not in the four-company EA net-profit list, so that alternative must drop out.
    result = run(["energy-margin", "--company", "nova", "--timeout", "5", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    for alt in data.get("alternatives") or []:
        refs = alt.get("reference_values_million_nzd") or {}
        if refs and "Nova" not in refs:
            print("  Expected net-profit alternative (no Nova) to be filtered out for --company nova")
            return False
    return True


results.append(
    test("energy-margin filters alternatives by company", test_energy_margin_company_filters_alternatives)
)


def test_energy_margin_rejects_unknown_company():
    result = run(["energy-margin", "--company", "not-a-company", "--json"])
    if result.returncode == 0:
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected unknown company to fail")
        return False
    return "unknown energy-margin company" in result.stderr


results.append(test("energy-margin rejects unknown company", test_energy_margin_rejects_unknown_company))


REGION_FIXTURE = (SKILL_DIR / "tests" / "fixtures" / "solar-region-sample.csv").read_text(encoding="utf-8")
STREET_FIXTURE = (SKILL_DIR / "tests" / "fixtures" / "solar-street-sample.csv").read_text(encoding="utf-8")


def test_fixture_solar_suppression_token():
    regions = cli.parse_solar_csv(REGION_FIXTURE, cli.SOLAR_REGION_COLUMNS, cli.SOLAR_REGION_MAX_ROWS)
    streets = cli.parse_solar_csv(STREET_FIXTURE, cli.SOLAR_STREET_COLUMNS, cli.SOLAR_STREET_MAX_ROWS)
    nelson = next(row for row in regions if row["region"] == "Nelson (Nelson Electricity)")
    suppressed = next(row for row in streets if row["physical_address_street"] == "EXAMPLE ROAD")
    numeric_three = next(row for row in streets if row["physical_address_street"] == "THREE ROAD")
    normal = next(row for row in streets if row["physical_address_street"] == "SECOND ROAD")
    if nelson["icps"] != "3 or less" or suppressed["icps"] != "3 or less":
        print(f"  suppressed values: {nelson['icps']!r} {suppressed['icps']!r}")
        return False
    if not isinstance(nelson["icps"], str) or isinstance(nelson["icps"], int):
        print("  suppressed ICP token must stay a string")
        return False
    if nelson["generation_capacity_kilowatts_sum"] is not None:
        print("  blank suppressed capacity sum must stay null")
        return False
    if numeric_three["icps"] != 3 or isinstance(numeric_three["icps"], str):
        print(f"  a published count of 3 must stay the integer 3, got {numeric_three['icps']!r}")
        return False
    if normal["icps"] != 21 or normal["generation_capacity_kilowatts_sum"] != 119.6:
        print(f"  normal street row: {normal}")
        return False
    rendered = cli.render_solar(
        {"meta": {"returned_count": 1, "matched_count": 1, "publisher": "Electricity Authority", "licence": "CC-BY-4.0", "source_url": "fixture", "units": cli.SOLAR_UNITS, "suppression": cli.SOLAR_SUPPRESSION_NOTE, "truncated": False}, "results": [suppressed]},
        "street",
    )
    if "3 or less" not in rendered:
        print("  human output dropped the suppression token")
        return False
    encoded = json.dumps(suppressed)
    if '"icps": "3 or less"' not in encoded:
        print(f"  JSON coerced the token: {encoded}")
        return False
    return True


results.append(test("fixture solar parser keeps literal 3 or less", test_fixture_solar_suppression_token))


def test_fixture_solar_street_filter_and_malformed():
    streets = cli.parse_solar_csv(STREET_FIXTURE, cli.SOLAR_STREET_COLUMNS, cli.SOLAR_STREET_MAX_ROWS)
    selected, matched = cli.filter_solar_streets(
        streets, region="north cape", sa2="100100", market_segment="Res", limit=1
    )
    if matched != 3 or len(selected) != 1 or selected[0]["icps"] != "3 or less":
        print(f"  filter: matched={matched} selected={selected}")
        return False
    try:
        cli.filter_solar_streets(streets, region=None, sa2=None, market_segment=None, limit=20)
    except cli.SolarCommandError as exc:
        if exc.code != 7:
            print(f"  unbounded filter code {exc.code}")
            return False
    else:
        print("  unbounded street filter was accepted")
        return False
    try:
        cli.parse_solar_csv("not,a,solar,header\n1,2,3,4\n", cli.SOLAR_REGION_COLUMNS, 10)
    except cli.SolarCommandError as exc:
        if exc.code != 6:
            print(f"  malformed header code {exc.code}")
            return False
    else:
        print("  malformed solar CSV was accepted")
        return False
    try:
        cli.parse_solar_csv("", cli.SOLAR_REGION_COLUMNS, 10)
    except cli.SolarCommandError as exc:
        if exc.code != 6:
            print(f"  empty CSV code {exc.code}")
            return False
    else:
        print("  empty solar CSV was accepted")
        return False
    return True


results.append(test("fixture solar street filter bounds and malformed CSV", test_fixture_solar_street_filter_and_malformed))


def test_contract_street_bounds():
    refused = run(["solar-streets", "--json"])
    if refused.returncode != 7:
        print(f"  unbounded exit {refused.returncode} stderr={refused.stderr[:200]!r}")
        return False
    payload = json.loads(refused.stdout)
    if payload.get("results") != [] or payload.get("error", {}).get("type") != "unsupported_operation":
        print(f"  unbounded payload: {refused.stdout[:300]}")
        return False
    if "3 or less" not in payload.get("meta", {}).get("suppression", ""):
        print("  error envelope dropped the suppression note")
        return False
    too_wide = run(["solar-streets", "--sa2", "100100", "--limit", "101", "--json"])
    if too_wide.returncode != 7:
        print(f"  oversize limit exit {too_wide.returncode} stdout={too_wide.stdout[:200]!r}")
        return False
    bad_segment = run(["solar-regions", "--market-segment", "SME", "--json"])
    if bad_segment.returncode != 2:
        print(f"  bad segment exit {bad_segment.returncode}")
        return False
    bad_sa2 = run(["solar-streets", "--sa2", "North Cape", "--json"])
    if bad_sa2.returncode != 2:
        print(f"  bad sa2 exit {bad_sa2.returncode}")
        return False
    if cli.SOLAR_STREET_MAX_LIMIT != 100 or cli.SOLAR_STREET_MAX_BYTES != 6_000_000:
        print("  street bounds constants moved")
        return False
    if cli.SOLAR_STREET_DEFAULT_LIMIT > cli.SOLAR_STREET_MAX_LIMIT:
        print("  default street limit exceeds the hard maximum")
        return False
    return True


results.append(test("contract street results and bytes stay bounded", test_contract_street_bounds))


def test_live_solar_regions():
    result = run(["solar-regions", "--json"])
    if result.returncode != 0:
        print(result.stderr[:400])
        print(result.stdout[:400])
        return False
    data = json.loads(result.stdout)
    meta = data.get("meta") or {}
    rows = data.get("results")
    if meta.get("publisher") != "Electricity Authority" or meta.get("licence") != "CC-BY-4.0":
        print(f"  meta: {meta}")
        return False
    if not str(meta.get("source_url", "")).startswith("https://emidatasets.blob.core.windows.net/"):
        print(f"  source_url: {meta.get('source_url')}")
        return False
    if not str(meta.get("retrieved_at", "")).endswith("Z"):
        print(f"  retrieved_at: {meta.get('retrieved_at')}")
        return False
    if not isinstance(rows, list) or not rows:
        print("  expected a non-empty region result list")
        return False
    expected_keys = {
        "region_type",
        "region_code",
        "region",
        "market_segment",
        "icps",
        "generation_capacity_kilowatts_avg",
        "generation_capacity_kilowatts_sum",
    }
    nz_res = None
    suppressed = 0
    for row in rows:
        if set(row) != expected_keys:
            print(f"  header keys: {sorted(row)}")
            return False
        icps = row["icps"]
        if icps == "3 or less":
            suppressed += 1
            if isinstance(icps, int):
                print("  live suppression token was coerced to an int")
                return False
        elif isinstance(icps, bool) or not isinstance(icps, int) or icps <= 0:
            print(f"  unexpected ICP value: {icps!r}")
            return False
        if row["region"] == "New Zealand" and row["market_segment"] == "Res" and row["region_type"] == "NZ":
            nz_res = row
    if nz_res is None or not isinstance(nz_res["icps"], int) or nz_res["icps"] <= 0:
        print(f"  New Zealand residential row: {nz_res}")
        return False
    if suppressed < 1:
        print("  live region file did not contain the literal suppression token")
        return False
    if "kilowatts" not in str(meta.get("units", "")).lower():
        print("  units note missing")
        return False
    return True


results.append(test("live solar-regions keeps a positive New Zealand residential ICP count", test_live_solar_regions))

if all(results):
    print("All tests passed.")
    sys.exit(0)
else:
    print(f"{results.count(False)} test(s) failed.")
    sys.exit(1)
