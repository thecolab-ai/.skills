#!/usr/bin/env python3
"""Parser-fixture assertions plus a bounded, outage-aware live probe."""
from __future__ import annotations

import gzip
import importlib
import io
import json
import subprocess
import sys
import tarfile
from contextlib import redirect_stdout
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "scripts"))

customs_cli = importlib.import_module("cli")
customs_tariff = importlib.import_module("customs_tariff")
MAX_ARCHIVE_MEMBERS = customs_tariff.MAX_ARCHIVE_MEMBERS
SkillError = customs_tariff.SkillError
formula_records = customs_tariff.formula_records
lookup_records = customs_tariff.lookup_records
parse_archive = customs_tariff.parse_archive
search_records = customs_tariff.search_records


def build_archive(source_bytes: bytes, replacements: list[tuple[str, bytes, bytes]]) -> bytes:
    output = io.BytesIO()
    with tarfile.open(fileobj=io.BytesIO(source_bytes), mode="r:gz") as source, tarfile.open(
        fileobj=output,
        mode="w:gz",
    ) as target:
        for member in source:
            source_file = source.extractfile(member) if member.isfile() else None
            data = source_file.read() if source_file is not None else None
            if data is not None:
                for member_name, old, new in replacements:
                    if member.name == member_name:
                        data = data.replace(old, new)
                member.size = len(data)
            target.addfile(member, io.BytesIO(data) if data is not None else None)
    return output.getvalue()


def build_header_only_archive(source_bytes: bytes, member_name: str) -> bytes:
    output = io.BytesIO()
    with tarfile.open(fileobj=io.BytesIO(source_bytes), mode="r:gz") as source, tarfile.open(
        fileobj=output,
        mode="w:gz",
    ) as target:
        for member in source:
            source_file = source.extractfile(member) if member.isfile() else None
            data = source_file.read() if source_file is not None else None
            if data is not None and member.name == member_name:
                data = data.splitlines(keepends=True)[0]
                member.size = len(data)
            target.addfile(member, io.BytesIO(data) if data is not None else None)
    return output.getvalue()


def run_json_header_only_probe(source_bytes: bytes, member_name: str):
    original_fetch = customs_cli.fetch_archive
    original_argv = sys.argv
    captured = io.StringIO()

    def fetch_header_only(timeout):
        return parse_archive(
            build_header_only_archive(source_bytes, member_name),
            f"fixture://header-only-{member_name}",
            "2026-09-02T00:00:00Z",
        )

    try:
        customs_cli.fetch_archive = fetch_header_only
        sys.argv = [str(SKILL / "scripts" / "cli.py"), "lookup", "0901210000", "--json"]
        with redirect_stdout(captured):
            exit_code = customs_cli.main()
    finally:
        customs_cli.fetch_archive = original_fetch
        sys.argv = original_argv
    return exit_code, json.loads(captured.getvalue())


def run_json_malformed_first_row_probe(source_bytes: bytes):
    original_fetch = customs_cli.fetch_archive
    original_argv = sys.argv
    captured = io.StringIO()

    def fetch_malformed(timeout):
        return parse_archive(
            build_archive(
                source_bytes,
                [("Tariff_Levy_Formulas.csv", b"1~0.000000", b"~~overflow")],
            ),
            "fixture://malformed-first-row.tar.gz",
            "2026-09-02T00:00:00Z",
        )

    try:
        customs_cli.fetch_archive = fetch_malformed
        sys.argv = [str(SKILL / "scripts" / "cli.py"), "lookup", "0901210000", "--json"]
        with redirect_stdout(captured):
            exit_code = customs_cli.main()
    finally:
        customs_cli.fetch_archive = original_fetch
        sys.argv = original_argv
    return exit_code, json.loads(captured.getvalue())


def run_json_malformed_later_row_probe(source_bytes: bytes):
    original_fetch = customs_cli.fetch_archive
    original_argv = sys.argv
    captured = io.StringIO()

    def fetch_malformed(timeout):
        return parse_archive(
            build_archive(
                source_bytes,
                [("Tariff_Details.csv", b"ROASTED COFFEE \x97 SYNTHETIC", b"ROASTED COFFEE \x97 SYNTHETIC~overflow")],
            ),
            "fixture://malformed-later-row.tar.gz",
            "2026-09-02T00:00:00Z",
        )

    try:
        customs_cli.fetch_archive = fetch_malformed
        sys.argv = [str(SKILL / "scripts" / "cli.py"), "search", "horses", "--limit", "1", "--json"]
        with redirect_stdout(captured):
            exit_code = customs_cli.main()
    finally:
        customs_cli.fetch_archive = original_fetch
        sys.argv = original_argv
    return exit_code, json.loads(captured.getvalue())


def run_json_error_probe(*argv_tail: str):
    original_fetch = customs_cli.fetch_archive
    original_argv = sys.argv
    captured = io.StringIO()
    fetch_called = False

    def forbidden_fetch(timeout):
        nonlocal fetch_called
        fetch_called = True
        raise AssertionError("invalid input reached the network fetch")

    try:
        customs_cli.fetch_archive = forbidden_fetch
        sys.argv = [str(SKILL / "scripts" / "cli.py"), *argv_tail, "--json"]
        with redirect_stdout(captured):
            exit_code = customs_cli.main()
    finally:
        customs_cli.fetch_archive = original_fetch
        sys.argv = original_argv
    return exit_code, json.loads(captured.getvalue()), fetch_called


def main() -> int:
    fixture = SKILL / "tests" / "fixtures" / "tariff-synthetic.tar.gz"
    fixture_bytes = fixture.read_bytes()
    dataset = parse_archive(fixture_bytes, "fixture://tariff-synthetic.tar.gz", "2026-09-02T00:00:00Z")
    assert dataset.source_timestamp == "2026-09-02T04:00:01+12:00"
    assert len(dataset.details) == 4
    assert dataset.details[0]["tariff_code"] == "0101210010"
    print("[PASS] fixture archive schema, delimiter, encoding and source timestamp parsing")

    search = search_records(dataset, "coffee", "2026-09-02", 10)
    assert [row["tariff_code"] for row in search] == ["0901210000"]
    assert search[0]["description"] == "ROASTED COFFEE — SYNTHETIC"
    print("[PASS] fixture classification search and active-date filtering")

    lookup = lookup_records(dataset, "09.01.21.00.00", "2026-09-02")
    assert lookup["classification"]["statistical_unit"] == "KGM"
    assert lookup["rates"][0]["rate_group"] == "NML"
    assert lookup["rates"][0]["factors"]["a"] == "5.000000"
    assert lookup["levies"][0]["levy_type_code"] == "AL"
    assert lookup["levies"][0]["formula_rate"] == "0.050000"
    print("[PASS] fixture exact lookup joins classifications, rates, levies and formula rates")

    formulas = formula_records(dataset, "2", 20)
    assert formulas == [{"formula_code": "2", "formula_rate": "0.050000"}]
    prefixed_formulas = formula_records(dataset, "2", 20, prefix=True)
    assert [record["formula_code"] for record in prefixed_formulas] == ["2", "20"]
    print("[PASS] fixture formula lookup distinguishes exact and explicit prefix matching")

    for member_name in customs_tariff.HEADERS:
        empty_exit, empty_payload = run_json_header_only_probe(fixture_bytes, member_name)
        assert empty_exit == 6
        assert empty_payload["ok"] is False
        assert empty_payload["blocked"] is False
        assert empty_payload["data"] is None
        assert empty_payload["error"]["code"] == 6
        assert empty_payload["error"]["kind"] == "source_schema"
        assert member_name in empty_payload["error"]["message"]
    print("[PASS] header-only required tables return the JSON source-schema error envelope")

    malformed_row_exit, malformed_row_payload = run_json_malformed_first_row_probe(fixture_bytes)
    assert malformed_row_exit == 6
    assert malformed_row_payload["ok"] is False
    assert malformed_row_payload["blocked"] is False
    assert malformed_row_payload["data"] is None
    assert malformed_row_payload["error"]["code"] == 6
    assert malformed_row_payload["error"]["kind"] == "source_schema"
    print("[PASS] malformed first CSV row returns the JSON source-schema error envelope")

    malformed_later_exit, malformed_later_payload = run_json_malformed_later_row_probe(fixture_bytes)
    assert malformed_later_exit == 6
    assert malformed_later_payload["ok"] is False
    assert malformed_later_payload["blocked"] is False
    assert malformed_later_payload["data"] is None
    assert malformed_later_payload["error"]["code"] == 6
    assert malformed_later_payload["error"]["kind"] == "source_schema"
    assert "Tariff_Details.csv line 3" in malformed_later_payload["error"]["message"]
    print("[PASS] malformed later CSV row cannot hide behind an early search limit")

    malformed_formulas = (
        (b"2~0.050000", b"A~0.050000", "invalid formula code"),
        (b"2~0.050000", b"\xb2~0.050000", "invalid formula code"),
        (b"2~0.050000", b"2~NaN", "invalid formula rate"),
    )
    for old, new, expected_message in malformed_formulas:
        try:
            parse_archive(
                build_archive(fixture_bytes, [("Tariff_Levy_Formulas.csv", old, new)]),
                "fixture://malformed-formula.tar.gz",
                "2026-09-02T00:00:00Z",
            )
        except SkillError as exc:
            assert exc.exit_code == 6 and exc.kind == "source_schema"
            assert expected_message in str(exc)
        else:
            raise AssertionError("malformed source formula was accepted during archive validation")
    print("[PASS] malformed formula types fail during complete archive validation")

    tar_buffer = io.BytesIO()
    with tarfile.open(fileobj=tar_buffer, mode="w") as excessive:
        for index in range(MAX_ARCHIVE_MEMBERS + 1):
            member = tarfile.TarInfo(f"tiny-{index}.txt")
            member.size = 0
            excessive.addfile(member, io.BytesIO())
    try:
        parse_archive(
            gzip.compress(tar_buffer.getvalue(), mtime=0),
            "fixture://excessive",
            "2026-09-02T00:00:00Z",
        )
    except SkillError as exc:
        assert exc.exit_code == 6 and "too many members" in str(exc)
    else:
        raise AssertionError("excessive archive member count was accepted")
    print("[PASS] fixture archive member-count bound rejects metadata exhaustion")

    redirect_handler = customs_tariff.ArchiveRedirectHandler()
    try:
        redirect_handler.redirect_request(
            customs_tariff.urllib.request.Request(customs_tariff.ARCHIVE_URL),
            None,
            302,
            "Found",
            {},
            "https://attacker.example/tariff.tar.gz",
        )
    except SkillError as exc:
        assert exc.exit_code == 7 and exc.kind == "unsafe_redirect"
    else:
        raise AssertionError("off-host archive redirect reached urllib redirect handling")
    print("[PASS] off-host archive redirect is rejected before a follow-up request")

    for argv_tail in (
        ("lookup", "٠٩٠١٢١٠٠٠٠"),
        ("lookup", "09.01.21.00.00Z"),
        ("search", "٠٩٠١"),
        ("formula", "2", "--limit", "101"),
    ):
        invalid_exit, invalid_json, fetch_called = run_json_error_probe(*argv_tail)
        assert invalid_exit == 2 and invalid_json["error"]["kind"] == "invalid_input"
        assert fetch_called is False
    print("[PASS] Unicode numeric lookalikes and parser bounds fail as JSON before fetch")

    required = {"schema_version", "ok", "blocked", "source", "query", "data", "warnings", "error"}
    runner = SKILL.parents[1] / "scripts" / "run_skill.py"
    for argv_tail in (("formula", "abc"), ("lookup", "09.01.21.00.00Z")):
        invalid = subprocess.run(
            [sys.executable, str(SKILL / "scripts" / "cli.py"), *argv_tail, "--json"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        invalid_payload = json.loads(invalid.stdout)
        assert invalid.returncode == 2 and required <= invalid_payload.keys()
        assert invalid_payload["source"]["retrieved_at"] and invalid_payload["error"]["code"] == 2
        canonical = subprocess.run(
            [sys.executable, str(runner), SKILL.name, *argv_tail],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        canonical_payload = json.loads(canonical.stdout)
        assert canonical.returncode == 2 and canonical_payload["error"]["code"] == 2
    print("[PASS] invalid input and unsupported check letters fail in direct and canonical JSON")

    command = [sys.executable, str(SKILL / "scripts" / "cli.py"), "formula", "2", "--json"]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
    if completed.returncode == 0:
        payload = json.loads(completed.stdout)
        assert payload["ok"] is True and payload["blocked"] is False
        assert payload["data"][0]["formula_code"]
        assert payload["source"]["timestamp"]
        print("[PASS] live Customs archive formula and timestamp retrieval")
    elif completed.returncode in {4, 5}:
        print(f"[SKIP] network or upstream unavailable: {completed.stderr.strip()}")
    else:
        print(f"[FAIL] live Customs probe failed: {completed.stderr.strip()}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
