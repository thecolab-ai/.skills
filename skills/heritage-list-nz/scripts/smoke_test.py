#!/usr/bin/env python3
"""Deterministic parser checks plus one bounded live Heritage List probe."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

CLI = Path(__file__).with_name("cli.py")
FIXTURE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "place-list-sample.csv"


def load_cli():
    spec = importlib.util.spec_from_file_location("heritage_list_cli", CLI)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def check(name: str, fn) -> bool:
    try:
        fn()
        print(f"[PASS] fixture {name}")
        return True
    except Exception as exc:  # noqa: BLE001 - aggregate fixture failures
        print(f"[FAIL] fixture {name}: {exc}")
        return False


def main() -> int:
    cli = load_cli()
    text = FIXTURE.read_text(encoding="utf-8")
    parsed: list[dict[str, str]] = []

    def parse_fixture() -> None:
        nonlocal parsed
        parsed = cli.parse_csv_text(text)
        assert len(parsed) == 4
        assert parsed[0]["name"] == "Te Whare Tāpere, Former"
        assert parsed[0]["list_number"] == "1001"
        assert parsed[2]["extent_of_list_entry"] == "Foreshore area,\nincluding associated structures."
        assert parsed[2]["nzaa_numbers"] == ["R27/12", "R27/13"]

    def search_and_filters() -> None:
        assert [row["list_number"] for row in cli.search_records(parsed, "tāpere")] == ["1001"]
        assert [row["list_number"] for row in cli.search_records(parsed, "state highway")] == ["2002"]
        assert [row["list_number"] for row in cli.search_records(parsed, "2002")] == ["2002"]
        assert [row["list_number"] for row in cli.search_records(parsed, "", district="waikato")] == ["2002", "4004"]
        assert [row["list_number"] for row in cli.search_records(parsed, "", entry_type="category 2")] == ["2002"]
        assert [row["list_number"] for row in cli.search_records(parsed, "", status="included")] == ["4004"]

    def exact_lookup_and_projection() -> None:
        record = cli.get_record(parsed, "3003")
        assert record["district_council"] == "Wellington City Council"
        summary = cli.project_record(record, detailed=False)
        assert "legal_description" not in summary
        assert "extent_of_list_entry" not in summary
        detailed = cli.project_record(record, detailed=True)
        assert detailed["date_of_effect"] == "05/05/2000"
        assert detailed["nzaa_numbers"] == ["R27/12", "R27/13"]
        assert "legal_description" not in detailed
        assert "extent_of_list_entry" not in detailed

    def schema_failure() -> None:
        bad = "ListNumber,Name\n1,Incomplete\n"
        try:
            cli.parse_csv_text(bad)
        except cli.SourceSchemaError as exc:
            assert "missing required columns" in str(exc)
        else:
            raise AssertionError("incomplete upstream schema must fail closed")

    def operational_contracts() -> None:
        assert cli.TIMEOUT_SECONDS == 10
        assert cli.MAX_DOWNLOAD_BYTES == 10 * 1024 * 1024
        assert cli.InputError.exit_code == 2
        assert cli.SourceBlockedError.exit_code == 4
        assert cli.SkillError.exit_code == 5
        assert cli.SourceSchemaError.exit_code == 6
        try:
            cli.bounded_limit("101")
        except Exception as exc:  # argparse.ArgumentTypeError without importing argparse
            assert "between 1 and 100" in str(exc)
        else:
            raise AssertionError("unbounded result limits must be rejected")

    def response_cap_is_pre_downloaded() -> None:
        captured: dict[str, int] = {}

        def fake_fetch_bytes(url: str, **kwargs):
            captured.update(kwargs)
            return (text.encode("utf-8"), "text/csv", url)

        original = cli.nzfetch.fetch_bytes
        cli.nzfetch.fetch_bytes = fake_fetch_bytes
        try:
            records, source, columns = cli.fetch_records()
        finally:
            cli.nzfetch.fetch_bytes = original
        assert len(records) == 4
        assert source["url"] == cli.CSV_URL
        assert columns == cli.REQUIRED_COLUMNS
        assert captured["max_bytes"] == cli.MAX_DOWNLOAD_BYTES

    results = [
        check("CSV quoting, Unicode and multiline parsing", parse_fixture),
        check("name/address/number/council/type/status search", search_and_filters),
        check("exact lookup and minimised search projection", exact_lookup_and_projection),
        check("source schema drift fails closed", schema_failure),
        check("timeouts, response caps, limits, and exit codes", operational_contracts),
        check("response cap is passed before decompression", response_cap_is_pre_downloaded),
    ]
    if not all(results):
        return 1

    completed = subprocess.run(
        [sys.executable, str(CLI), "status", "--json"],
        text=True,
        capture_output=True,
        timeout=25,
        check=False,
    )
    if completed.returncode in {4, 5}:
        detail = (completed.stdout or completed.stderr).strip().replace("\n", " ")
        print(f"[SKIP] live Heritage NZ CSV probe: upstream unavailable or blocked: {detail}")
        return 0
    if completed.returncode != 0:
        print(f"[FAIL] live Heritage NZ CSV probe: exit {completed.returncode}: {completed.stderr.strip()}")
        return 1
    try:
        payload = json.loads(completed.stdout)
        assert payload["kind"] == "heritage_list_status"
        assert payload["record_count"] > 1000
        assert payload["source"]["url"] == cli.CSV_URL
        assert payload["source"]["retrieved_at"].endswith("Z")
        assert set(cli.REQUIRED_COLUMNS) == set(payload["columns"])
    except (AssertionError, KeyError, json.JSONDecodeError) as exc:
        print(f"[FAIL] live Heritage NZ CSV probe: {exc}")
        return 1
    print("[PASS] live Heritage NZ CSV schema and record count")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
