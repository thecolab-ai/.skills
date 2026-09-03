#!/usr/bin/env python3
"""Deterministic parser checks plus bounded live Heritage List probes."""
from __future__ import annotations

import argparse
import importlib.util
import io
import json
import re
import subprocess
import sys
from contextlib import redirect_stdout
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


def landing_page_is_valid(html_text: str) -> bool:
    """Require List-specific content and reject the site's HTTP-200 soft 404."""
    normalised = re.sub(r"\s+", " ", html_text).casefold()
    title_match = re.search(r"<title(?:\s[^>]*)?>(.*?)</title>", normalised, flags=re.DOTALL)
    if title_match is None:
        return False
    title = re.sub(r"<[^>]+>", " ", title_match.group(1))
    if "404 page not found" in title or "new zealand heritage list" not in title:
        return False
    return any(marker in normalised for marker in ("official national record", "search for historic places"))


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
        except argparse.ArgumentTypeError as exc:
            assert "between 1 and 100" in str(exc)
        else:
            raise AssertionError("unbounded result limits must be rejected")

    def landing_page_contract() -> None:
        assert cli.LANDING_URL == "https://www.heritage.org.nz/places"
        assert cli.CSV_URL == "https://hnzpt-prod-web.azurewebsites.net/api/report/GetPlaceListCsv"
        assert cli.ALLOWED_HOSTS == {"hnzpt-prod-web.azurewebsites.net"}
        assert not landing_page_is_valid(
            "<title>404 page not found</title>"
            "<script>New Zealand Heritage List official national record</script>"
        )
        assert landing_page_is_valid(
            "<title>Search the New Zealand Heritage List/Rārangi Kōrero</title>"
            '<meta name="description" content="Aotearoa New Zealand’s official national record">'
        )

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
        assert source["landing_page"] == cli.LANDING_URL
        assert columns == cli.REQUIRED_COLUMNS
        assert captured["max_bytes"] == cli.MAX_DOWNLOAD_BYTES

    def assert_csv_cli_schema_error(malformed: str) -> None:
        def fake_fetch_bytes(url: str, **kwargs):
            return (malformed.encode("utf-8"), "text/csv", url)

        original = cli.nzfetch.fetch_bytes
        captured = io.StringIO()
        cli.nzfetch.fetch_bytes = fake_fetch_bytes
        try:
            with redirect_stdout(captured):
                exit_code = cli.main(["status", "--json"])
        finally:
            cli.nzfetch.fetch_bytes = original
        payload = json.loads(captured.getvalue())
        assert exit_code == 6
        assert payload["error"] == "source_schema_error"

    def malformed_row_is_cli_schema_error() -> None:
        malformed = text.splitlines()[0] + "\n" + "," * len(cli.REQUIRED_COLUMNS) + "extra\n"
        assert_csv_cli_schema_error(malformed)

    def short_row_is_cli_schema_error() -> None:
        malformed = text.splitlines()[0] + "\n1001,Only two fields\n"
        assert_csv_cli_schema_error(malformed)

    def unclosed_quoted_field_is_cli_schema_error() -> None:
        values = ["1001", "Unclosed quote"] + [""] * (len(cli.REQUIRED_COLUMNS) - 3) + ['"unterminated']
        malformed = text.splitlines()[0] + "\n" + ",".join(values) + "\n"
        assert_csv_cli_schema_error(malformed)

    def duplicate_normalised_required_header_is_cli_schema_error() -> None:
        header = text.splitlines()[0] + ", ListNumber "
        values = ["1001", "Duplicate header"] + [""] * (len(cli.REQUIRED_COLUMNS) - 2) + ["shadow"]
        malformed = header + "\n" + ",".join(values) + "\n"
        assert_csv_cli_schema_error(malformed)

    def truncated_compression_is_cli_schema_error() -> None:
        def fake_fetch_bytes(url: str, **kwargs):
            raise cli.nzfetch.InvalidCompressedBody("synthetic truncated deflate")

        original = cli.nzfetch.fetch_bytes
        captured = io.StringIO()
        cli.nzfetch.fetch_bytes = fake_fetch_bytes
        try:
            with redirect_stdout(captured):
                exit_code = cli.main(["status", "--json"])
        finally:
            cli.nzfetch.fetch_bytes = original
        payload = json.loads(captured.getvalue())
        assert exit_code == 6
        assert payload["error"] == "source_schema_error"

    results = [
        check("CSV quoting, Unicode and multiline parsing", parse_fixture),
        check("name/address/number/council/type/status search", search_and_filters),
        check("exact lookup and minimised search projection", exact_lookup_and_projection),
        check("source schema drift fails closed", schema_failure),
        check("timeouts, response caps, limits, and exit codes", operational_contracts),
        check("landing page URL and semantic soft-404 guard", landing_page_contract),
        check("response cap is passed before decompression", response_cap_is_pre_downloaded),
        check("malformed CSV row shape returns CLI schema error", malformed_row_is_cli_schema_error),
        check("short CSV row shape returns CLI schema error", short_row_is_cli_schema_error),
        check("unclosed quoted CSV field returns CLI schema error", unclosed_quoted_field_is_cli_schema_error),
        check(
            "duplicate normalised required header returns CLI schema error",
            duplicate_normalised_required_header_is_cli_schema_error,
        ),
        check("truncated compression returns CLI schema error", truncated_compression_is_cli_schema_error),
    ]
    if not all(results):
        return 1

    try:
        landing_body, landing_content_type, landing_final_url = cli.nzfetch.fetch_bytes(
            cli.LANDING_URL,
            timeout=cli.TIMEOUT_SECONDS,
            accept="text/html,*/*;q=0.8",
            allowed_hosts={"www.heritage.org.nz"},
            max_bytes=2 * 1024 * 1024,
        )
    except cli.nzfetch.Blocked as exc:
        print(f"[SKIP] live Heritage NZ landing-page probe: upstream unavailable or blocked: {exc}")
    except (cli.nzfetch.ResponseTooLarge, cli.nzfetch.InvalidCompressedBody) as exc:
        print(f"[FAIL] live Heritage NZ landing-page probe: invalid bounded response: {exc}")
        return 1
    except cli.nzfetch.FetchError as exc:
        print(f"[SKIP] live Heritage NZ landing-page probe: upstream unavailable: {exc}")
    else:
        try:
            assert "html" in landing_content_type.casefold()
            assert landing_final_url.rstrip("/") == cli.LANDING_URL
            assert landing_page_is_valid(landing_body.decode("utf-8", errors="replace"))
        except AssertionError:
            print("[FAIL] live Heritage NZ landing-page probe: missing List semantics or unexpected response")
            return 1
        print("[PASS] live Heritage NZ landing page semantics")

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
