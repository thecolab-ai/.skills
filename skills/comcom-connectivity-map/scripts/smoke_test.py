#!/usr/bin/env python3
"""Smoke tests for comcom-connectivity-map."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
CLI = SKILL_DIR / "scripts" / "cli.py"


def load_cli():
    spec = importlib.util.spec_from_file_location("comcom_connectivity_cli", CLI)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI)] + args,
        capture_output=True,
        text=True,
        cwd=str(SKILL_DIR),
        timeout=60,
    )


def report(status: str, name: str, detail: str = "") -> str:
    print(f"[{status}] {name}")
    if detail:
        print(f"  {detail}")
    return status


def is_network_or_blocked(result: subprocess.CompletedProcess[str]) -> bool:
    text = (result.stderr + "\n" + result.stdout).lower()
    return any(
        marker in text
        for marker in (
            "network error",
            "timeout",
            "timed out",
            "http 403",
            "http 429",
            "http 500",
            "http 502",
            "http 503",
            "http 504",
            "blocked",
            "bot",
            "incapsula",
            "urlopen error",
        )
    )


def json_command(name: str, args: list[str], check) -> str:
    result = run(args)
    if result.returncode != 0:
        if is_network_or_blocked(result):
            return report("SKIP", name, result.stderr[:240] or result.stdout[:240])
        return report("FAIL", name, result.stderr[:240] or result.stdout[:240])
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        return report("FAIL", name, str(exc))
    ok, detail = check(data)
    return report("PASS" if ok else "FAIL", name, detail)


results: list[str] = []


def test_fixture_parsing() -> str:
    cli = load_cli()
    html = """
    <html><body>
      <iframe src="https://comcom.emtel.co.nz/publicWebsite/"></iframe>
      <ul>
        <li>all the data is as at 30 June 2025.</li>
        <li>at least 50% of the parcel falls within the coverage area.</li>
      </ul>
      <a href="/assets/Provider-List-Updated-26-August-2025.xlsx">
        <span class="file__title">Provider List - Updated 26 August 2025</span>
        <span class="file__description">( 10 KB, XLSX )</span>
      </a>
      <a href="https://example.test/coverage/LayerServer">Rural broadband FeatureServer</a>
      <a href="/assets/2025-Telecommunications-Monitoring-Report-29-June-2026.pdf">
        2025 Telecommunications Monitoring Report - 29 June 2026
      </a>
    </body></html>
    """
    metadata = cli.parse_connectivity_page(html, cli.CONNECTIVITY_URL)
    ok = (
        metadata["map"]["embed_url"] == "https://comcom.emtel.co.nz/publicWebsite/"
        and metadata["coverage_date"] == "2025-06-30"
        and cli.date_from_text("Provider-List-Updated-26-August-2025.xlsx") == "2025-08-26"
        and metadata["provider_list"]["format"] == "xlsx"
        and metadata["methodology"]["parcel_threshold"] == "50%"
        and metadata["layers"][0]["url"] == "https://example.test/coverage/LayerServer"
    )
    if not ok:
        return report("FAIL", "fixture parser extracts map metadata", json.dumps(metadata, indent=2)[:400])

    annual = cli.parse_annual_reports(html, cli.ANNUAL_REPORT_URL)
    ok = annual and annual[0]["year"] == 2025 and annual[0]["format"] == "pdf"
    return report("PASS" if ok else "FAIL", "fixture parser extracts annual report years", json.dumps(annual, indent=2)[:400])


def test_help() -> str:
    result = run(["--help"])
    if result.returncode == 0 and "connectivity" in result.stdout.lower():
        return report("PASS", "--help exits 0")
    return report("FAIL", "--help exits 0", result.stderr[:240] or result.stdout[:240])


results.append(test_fixture_parsing())
results.append(test_help())
results.append(
    json_command(
        "list-years returns annual report years",
        ["list-years", "--json"],
        lambda data: (
            data.get("status") == "ok"
            and isinstance(data.get("years"), list)
            and any(item.get("year") for item in data["years"]),
            "expected at least one annual report year",
        ),
    )
)
results.append(
    json_command(
        "coverage-summary returns source method and map caveats",
        ["coverage-summary", "--year", "2025", "--json"],
        lambda data: (
            data.get("status") == "ok"
            and data.get("fetch_method") == "direct_http"
            and data.get("coverage_date")
            and data.get("map_data_year") == 2025
            and data.get("current_map_only") is True
            and data.get("year_supported_for_map") is True
            and data.get("map", {}).get("embed_url"),
            "expected direct_http, map year context, and map embed URL",
        ),
    )
)
results.append(
    json_command(
        "providers returns honest provider workbook status",
        ["providers", "--year", "2025", "--json"],
        lambda data: (
            data.get("status") in {"ok", "dead_link", "blocked_by_upstream", "network_error", "network_timeout"}
            and data.get("provider_list", {}).get("url", "").endswith(".xlsx"),
            "expected provider_list XLSX URL and non-misleading status",
        ),
    )
)
results.append(
    json_command(
        "providers flags unsupported map years",
        ["providers", "--year", "1900", "--json"],
        lambda data: (
            data.get("status") == "year_not_available"
            and data.get("map_data_year") == 2025
            and data.get("year_supported_for_map") is False,
            "expected year_not_available for non-current map year",
        ),
    )
)
results.append(
    json_command(
        "layer-metadata reports discovered or not_discovered",
        ["layer-metadata", "--year", "2025", "--json"],
        lambda data: (
            data.get("status") in {"ok", "not_discovered"}
            and data.get("fetch_method") == "direct_http"
            and isinstance(data.get("layers"), list),
            "expected direct_http layer metadata payload",
        ),
    )
)

failures = results.count("FAIL")
skips = results.count("SKIP")
if failures:
    print(f"{failures} test(s) failed; {skips} skipped.")
    sys.exit(1)

print(f"All non-skipped tests passed; {skips} skipped.")
sys.exit(0)
