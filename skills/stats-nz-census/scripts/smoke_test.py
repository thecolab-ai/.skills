#!/usr/bin/env python3
"""Deterministic parser/adversarial checks plus bounded live Census probes."""
from __future__ import annotations

import importlib.util
import io
import json
import sys
import zipfile
from contextlib import redirect_stdout
from pathlib import Path

CLI = Path(__file__).with_name("cli.py")
FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "lib"))
from result_contract import validate_result_envelope  # noqa: E402


def load_cli():
    spec = importlib.util.spec_from_file_location("stats_nz_census_cli", CLI)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def check(kind: str, name: str, fn) -> bool:
    try:
        fn()
        print(f"[PASS] {kind} {name}")
        return True
    except Exception as exc:  # noqa: BLE001 - aggregate checks
        print(f"[FAIL] {kind} {name}: {exc}")
        return False


def zip_bytes(members: dict[str, bytes | str]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, body in members.items():
            archive.writestr(name, body)
    return output.getvalue()


def corrupt_first_member_crc(body: bytes) -> bytes:
    """Flip one stored member byte while leaving its recorded CRC unchanged."""
    damaged = bytearray(body)
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        info = archive.infolist()[0]
        offset = info.header_offset
        name_length = int.from_bytes(body[offset + 26 : offset + 28], "little")
        extra_length = int.from_bytes(body[offset + 28 : offset + 30], "little")
        data_offset = offset + 30 + name_length + extra_length
    damaged[data_offset] ^= 0x01
    return bytes(damaged)


def fetch_live_topics(cli):
    """Fetch live topics while distinguishing outages from invalid source data."""
    try:
        return cli.fetch_topics(), 0
    except cli.SourceBlockedError as exc:
        print(f"[SKIP] live Stats NZ Census normal/empty contracts: upstream blocked: {exc}")
        return None, 0
    except cli.SourceSchemaError as exc:
        print(f"[FAIL] live Stats NZ Census source/schema contract: {exc}")
        return None, 1
    except cli.SkillError as exc:
        print(f"[SKIP] live Stats NZ Census normal/empty contracts: upstream unavailable: {exc}")
        return None, 0


def main() -> int:
    cli = load_cli()
    fixture_text = (FIXTURES / "age-single-years-2018-census-csv.csv").read_text(encoding="utf-8")
    topic = cli.TopicFile(
        "age-single-years",
        "age-single-years-2018-census-csv.csv",
        fixture_text.encode("utf-8"),
    )
    results: list[bool] = []

    def parser_dimensions_and_markers() -> None:
        rows = cli.parse_topic(topic)
        assert len(rows) == 8
        first = rows[0]
        assert first["category_dimension"] == "Age_single_years"
        assert first["category_code"] == "000"
        assert first["measure"] == "Census_night_population_count"
        assert first["value"] == 12345 and first["raw_value"] == "12,345"
        confidential = next(row for row in rows if row["raw_value"] == "..C")
        assert confidential["value"] is None
        assert confidential["value_status"] == "confidentialised"
        assert confidential["source_symbol"] == "..C"
        suppressed = next(row for row in rows if row["raw_value"] == "S")
        assert suppressed["value"] is None and suppressed["value_status"] == "suppressed"
        zero = next(row for row in rows if row["raw_value"] == "0")
        assert zero["value"] == 0 and zero["value_status"] == "observed"
        unknown = next(row for row in rows if row["raw_value"] == "unmapped-marker")
        assert unknown["value"] is None and unknown["source_symbol"] == "unmapped-marker"

    def filters_do_not_collapse_dimensions() -> None:
        data, warnings = cli.query_topics([topic], "AGE-SINGLE", "one year", "usually", 10)
        assert warnings == []
        assert data["matched_count"] == 1
        row = data["observations"][0]
        assert row["category_code"] == "001"
        assert row["category_label"] == "One year"
        assert row["category_dimension"] == "Age_single_years"
        assert row["measure"] == "Census_usually_resident_population_count"
        assert row["source_symbol"] == "S"

    def empty_is_successful_data_contract() -> None:
        data, warnings = cli.query_topics([topic], "not-a-published-topic", None, None, 20)
        assert data["matched_count"] == 0 and data["observations"] == []
        assert warnings == ["No published topic matched the positional topic query."]

    def malformed_rows_fail_closed() -> None:
        malformed = (FIXTURES / "malformed-extra-field.csv").read_bytes()
        bad = cli.TopicFile("malformed", "malformed-2018-census-csv.csv", malformed)
        try:
            cli.parse_topic(bad)
        except cli.SourceSchemaError as exc:
            assert "unexpected field count" in str(exc)
        else:
            raise AssertionError("extra CSV fields must fail closed")

    def duplicate_headers_fail_closed() -> None:
        body = b"Code,Dimension,Measure, Measure \n001,One,1,2\n"
        bad = cli.TopicFile("duplicate", "duplicate-2018-census-csv.csv", body)
        try:
            cli.parse_topic(bad)
        except cli.SourceSchemaError as exc:
            assert "duplicate columns" in str(exc)
        else:
            raise AssertionError("normalised duplicate headers must fail closed")

    def windows_1252_source_text_is_preserved() -> None:
        body = (
            '"Code","Total_personal_income","Census_usually_resident_population_count"\r\n'
            '"13","$1–$5,000",210705\r\n'
        ).encode("cp1252")
        rows = cli.parse_topic(cli.TopicFile("total-personal-income", "income.csv", body))
        assert rows[0]["category_label"] == "$1–$5,000"
        assert rows[0]["value"] == 210705

    def undecodable_source_text_fails_closed() -> None:
        bad = cli.TopicFile("bad-encoding", "bad.csv", b"Code,Dimension,Measure\n001,\x81,1\n")
        try:
            cli.parse_topic(bad)
        except cli.SourceSchemaError as exc:
            assert "UTF-8 or Windows-1252" in str(exc)
        else:
            raise AssertionError("bytes invalid in both supported encodings must fail closed")

    def unsafe_archives_fail_closed() -> None:
        for body, expected in (
            (zip_bytes({"../escape.csv": "Code,Dimension,Measure\n001,One,1\n"}), "unsafe archive member"),
            (b"not a zip", "valid ZIP"),
        ):
            try:
                cli.validate_archive(body)
            except cli.SourceSchemaError as exc:
                assert expected in str(exc)
            else:
                raise AssertionError("unsafe archive was accepted")

    def expansion_ratio_fails_closed() -> None:
        bomb = zip_bytes({"repeat-2018-census-csv.csv": b"0" * (cli.MAX_MEMBER_BYTES - 1)})
        try:
            cli.validate_archive(bomb)
        except cli.SourceSchemaError as exc:
            assert "expansion-ratio" in str(exc)
        else:
            raise AssertionError("high-ratio archive was accepted")

    def corrupt_member_fails_with_schema_error() -> None:
        # Rebuild uncompressed so a flipped payload byte reaches the CRC check.
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as stored:
            stored.writestr(topic.member, topic.body)
        try:
            cli.validate_archive(corrupt_first_member_crc(output.getvalue()))
        except cli.SourceSchemaError as exc:
            assert "could not read archive member" in str(exc)
        else:
            raise AssertionError("corrupt ZIP member escaped schema handling")

    def operational_bounds() -> None:
        assert cli.TIMEOUT_SECONDS == 10
        assert cli.MAX_DOWNLOAD_BYTES == 2 * 1024 * 1024
        assert cli.MAX_RESULTS == 100
        assert cli.SourceBlockedError.exit_code == 4
        assert cli.SourceSchemaError.exit_code == 6
        try:
            cli.bounded_limit("101")
        except Exception as exc:
            assert "between 1 and 100" in str(exc)
        else:
            raise AssertionError("an unbounded result limit was accepted")

    def fetch_passes_pre_download_cap() -> None:
        captured: dict[str, object] = {}
        archive = zip_bytes({topic.member: topic.body})

        def fake_fetch(url: str, **kwargs):
            captured.update(kwargs)
            return archive, "application/zip", url

        original = cli.nzfetch.fetch_bytes
        cli.nzfetch.fetch_bytes = fake_fetch
        try:
            topics, final_url = cli.fetch_topics()
        finally:
            cli.nzfetch.fetch_bytes = original
        assert len(topics) == 1 and final_url == cli.SOURCE_URL
        assert captured["timeout"] == 10
        assert captured["max_bytes"] == cli.MAX_DOWNLOAD_BYTES
        assert captured["allowed_hosts"] == cli.ALLOWED_HOSTS

    def blocked_result_envelope() -> None:
        original = cli.fetch_topics
        cli.fetch_topics = lambda: (_ for _ in ()).throw(cli.SourceBlockedError("synthetic block"))
        output = io.StringIO()
        try:
            with redirect_stdout(output):
                code = cli.main(["age", "--json"])
        finally:
            cli.fetch_topics = original
        payload = json.loads(output.getvalue())
        assert code == 4
        assert payload["ok"] is False and payload["blocked"] is True
        assert payload["error"]["code"] == 4
        assert validate_result_envelope(payload) == []

    def schema_failure_is_not_skipped() -> None:
        original = cli.fetch_topics
        setattr(cli, "fetch_topics", lambda: (_ for _ in ()).throw(cli.SourceSchemaError("synthetic schema drift")))
        output = io.StringIO()
        try:
            with redirect_stdout(output):
                result, code = fetch_live_topics(cli)
        finally:
            setattr(cli, "fetch_topics", original)
        assert result is None and code == 1
        assert "[FAIL]" in output.getvalue()
        assert "[SKIP]" not in output.getvalue()

    fixture_checks = (
        ("CSV dimensions and status markers", parser_dimensions_and_markers),
        ("filters preserve dimensions", filters_do_not_collapse_dimensions),
        ("empty query result", empty_is_successful_data_contract),
        ("malformed row shape fails closed", malformed_rows_fail_closed),
        ("duplicate normalised headers fail closed", duplicate_headers_fail_closed),
        ("Windows-1252 source text is preserved", windows_1252_source_text_is_preserved),
        ("unsupported source encoding fails closed", undecodable_source_text_fails_closed),
        ("invalid and traversal archives fail closed", unsafe_archives_fail_closed),
        ("ZIP expansion ratio fails closed", expansion_ratio_fails_closed),
        ("corrupt ZIP member fails with schema error", corrupt_member_fails_with_schema_error),
        ("timeouts and bounds", operational_bounds),
        ("response cap is applied before download", fetch_passes_pre_download_cap),
    )
    results.extend(check("fixture", name, fn) for name, fn in fixture_checks)
    results.append(check("contract", "blocked result envelope", blocked_result_envelope))
    results.append(check("contract", "source schema failure is not skipped", schema_failure_is_not_skipped))
    if not all(results):
        return 1

    live_result, live_exit = fetch_live_topics(cli)
    if live_result is None:
        return live_exit
    live_topics, final_url = live_result

    try:
        normal, normal_warnings = cli.query_topics(live_topics, "age-single-years", None, None, 5)
        assert normal["kind"] == "census_observations"
        assert normal["matched_count"] > 5 and normal["returned_count"] == 5
        assert normal["selected_topics"] == ["age-single-years"]
        assert all(row["category_dimension"] and row["measure"] for row in normal["observations"])
        available = {topic.topic for topic in live_topics}
        assert len(available) == 57
        assert {
            "family-type",
            "household-composition",
            "usual-residence-one-year-ago-indicator",
            "usual-residence-five-years-ago-indicator",
        } <= available
        for cp1252_topic in ("total-personal-income", "weekly-rent-paid-by-household"):
            cp1252_result, _ = cli.query_topics(live_topics, cp1252_topic, None, None, 5)
            assert cp1252_result["matched_count"] > 0
            assert cp1252_result["returned_count"] == 5
        ethnicity, _ = cli.query_topics(live_topics, "ethnic-group-total-responses", "european", None, 5)
        assert ethnicity["matched_count"] > 0
        resident, _ = cli.query_topics(live_topics, "age-single-years", None, "Census_usually_resident", 5)
        assert resident["matched_count"] > 0
        assert final_url.startswith("https://www.stats.govt.nz/")
        assert normal_warnings and "truncated" in normal_warnings[0].casefold()
    except Exception as exc:  # noqa: BLE001 - live schema failures are real failures
        print(f"[FAIL] live Stats NZ Census normal result contract: {exc}")
        return 1
    print("[PASS] live Stats NZ Census normal result contract")

    try:
        empty, warnings = cli.query_topics(live_topics, "definitely-not-a-real-census-topic", None, None, 5)
        assert empty["matched_count"] == 0 and empty["observations"] == []
        assert warnings == ["No published topic matched the positional topic query."]
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] live Stats NZ Census empty result contract: {exc}")
        return 1
    print("[PASS] live Stats NZ Census empty result contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
