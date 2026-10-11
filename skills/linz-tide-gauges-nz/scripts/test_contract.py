#!/usr/bin/env python3
"""Deterministic repository and parser contract for LINZ tide gauges."""
import argparse
import io
import json
import subprocess
import sys
import zipfile
import zlib
from contextlib import redirect_stderr, redirect_stdout
from datetime import date, datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import nzfetch  # noqa: E402
from contract_test import audit_skill  # noqa: E402
from provenance import (  # noqa: E402
    add_spatial_arguments,
    error_envelope,
    geojson_envelope,
    parse_bbox,
    provenance,
    result_envelope,
)

import cli  # noqa: E402
import smoke_test  # noqa: E402

DATA_COMMAND = (
    "readings",
    "--gauge",
    "AUCT",
    "--date",
    "2026-01-01",
    "--sensor",
    "40",
    "--fixture",
    "daily-excerpt.csv",
    "--limit",
    "2",
    "--json",
)


def invoke(arguments: list[str]) -> tuple[int, dict, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = cli.main(arguments)
    text = stdout.getvalue()
    payload = json.loads(text) if "--json" in arguments else {}
    return code, payload, stderr.getvalue()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run_parser_contracts() -> None:
    code, payload, stderr = invoke(list(DATA_COMMAND))
    require(code == 0 and stderr == "" and "error" not in payload, "fixture readings failed")
    require(payload["meta"]["retrieval_kind"] == "fixture", "fixture run was marked live")
    require(payload["meta"]["observation_time"] == "UTC", "readings clock was not UTC")
    require(payload["meta"]["latest_data"] == "2026-01-01T00:03:00Z", "latest_data followed the page instead of the file")
    require(payload["meta"]["matched_count"] == 4 and payload["meta"]["truncated"] is True, "page bounds were wrong")
    require(payload["results"][0]["observed_at"] == "2026-01-01T00:00:00Z", "midnight UTC was shifted")
    require(payload["results"][0]["height_m"] == "5.002", "source height precision changed")
    require(payload["meta"]["height_reference"] == "gauge zero (TG0)", "height reference missing")
    require(payload["meta"]["quality_control"] == "unquality-controlled", "quality caveat missing")
    require(payload["meta"]["sensor_origin"] == "request" and payload["meta"]["sensor_verified"] is False, "csv fixture claimed a verified sensor")
    require("no sensor column" in payload["meta"]["note"], "csv sensor caveat missing")
    require("New Zealand local" not in json.dumps(payload), "UTC readings were described as local time")

    code, payload, _stderr = invoke(
        ["readings", "--gauge", "AUCT", "--date", "2026-01-01", "--sensor", "40", "--fixture", "utc-midday.csv", "--json"]
    )
    require(code == 0 and payload["results"] == [
        {"gauge": "AUCT", "sensor": "40", "observed_at": "2026-01-01T11:00:00Z", "height_m": "4.594"}
    ], "11:00 UTC was converted as if it were New Zealand local time")

    code, payload, _stderr = invoke(
        ["readings", "--gauge", "AUCT", "--date", "2026-01-02", "--sensor", "40", "--fixture", "daily-excerpt.csv", "--json"]
    )
    require(code == 6 and payload["error"]["type"] == "schema_failure" and payload["results"] == [], "wrong UTC date was accepted")

    for arguments, expected in (
        (["readings", "--gauge", "AUCT", "--date", "2026-01-01", "--sensor", "40", "--fixture", "duplicate-daily.csv", "--json"], "duplicate"),
        (["readings", "--gauge", "AUCT", "--date", "2026-01-01", "--sensor", "40", "--fixture", "malformed-daily.csv", "--json"], "timestamp"),
        (["files", "--gauge", "AUCT", "--year", "2026", "--sensor", "40", "--fixture", "malformed-files.json", "--json"], "file name"),
    ):
        code, payload, _stderr = invoke(arguments)
        require(code == 6 and expected in payload["error"]["message"] and payload["results"] == [], expected)

    code, payload, _stderr = invoke(
        ["readings", "--gauge", "AUCT", "--date", "2026-01-01", "--sensor", "40", "--fixture", "bom-daily.csv", "--json"]
    )
    require(code == 0 and payload["results"][0]["height_m"] == "5.002", "UTF-8 BOM CSV failed")

    code, payload, _stderr = invoke(
        ["readings", "--gauge", "AUCT", "--date", "2026-01-01", "--sensor", "40", "--fixture", "daily-excerpt.zip", "--json"]
    )
    require(
        code == 0 and payload["meta"]["matched_count"] == 4 and payload["meta"]["sensor_origin"] == "archive_name" and payload["meta"]["sensor_verified"] is True,
        "zip fixture failed",
    )

    code, payload, _stderr = invoke(
        ["files", "--gauge", "AUCT", "--year", "2026", "--sensor", "40", "--fixture", "list-files.json", "--limit", "1", "--offset", "1", "--json"]
    )
    require(
        code == 0
        and payload["results"][0]["name"] == "AUCT_40_2026002.zip"
        and payload["results"][0]["utc_date"] == "2026-01-02"
        and payload["meta"]["matched_count"] == 3
        and payload["meta"]["truncated"] is True
        and payload["meta"]["latest_data"] == "2026-01-05"
        and "not an observation time" in payload["meta"]["latest_data_meaning"],
        "file page or modified-date meaning was wrong",
    )
    code, payload, _stderr = invoke(
        ["files", "--gauge", "AUCT", "--year", "2026", "--sensor", "40", "--fixture", "list-files.json", "--offset", "3", "--json"]
    )
    require(code == 0 and payload["results"] == [] and payload["meta"]["query_status"] == "ok" and payload["meta"]["matched_count"] == 3, "empty page looked like no match")

    code, payload, _stderr = invoke(
        ["files", "--gauge", "AUCT", "--year", "2026", "--sensor", "40", "--fixture", "empty-files.json", "--json"]
    )
    require(code == 0 and payload["results"] == [] and payload["meta"]["query_status"] == "ok" and "error" not in payload, "empty file list looked like an outage")

    code, payload, _stderr = invoke(
        ["datasets", "--gauge", "AUCT", "--fixture", "gauge-datasets.json", "--json"]
    )
    require(code == 0 and payload["meta"]["latest_data"] == "2026" and {row["sensor"] for row in payload["results"]} == {"40", "41"}, "dataset fixture failed")

    code, payload, _stderr = invoke(["gauges", "--fixture", "list-gauges.json", "--json"])
    require(code == 0 and "AUCT" in {row["gauge"] for row in payload["results"]} and "latest_data" not in payload["meta"], "gauge fixture failed")

    def gauges_only(url: str, *, expect_json: bool, timeout: int) -> bytes:
        require(timeout == 10 and expect_json is True, "gauge lookup was unbounded")
        if url.endswith("/api/listGauges"):
            return b'{"gauges":["AUCT"]}'
        raise AssertionError(url)

    original = cli.http_get
    cli.http_get = gauges_only
    try:
        code, payload, _stderr = invoke(["datasets", "--gauge", "ZZZZ", "--json"])
    finally:
        cli.http_get = original
    require(code == 0 and payload["meta"]["query_status"] == "no_match" and payload["results"] == [] and "error" not in payload, "unknown gauge looked like an outage")

    def fail_network(url: str, *, expect_json: bool, timeout: int) -> bytes:
        raise nzfetch.FetchError("timed out")

    cli.http_get = fail_network
    try:
        code, payload, stderr = invoke(["gauges", "--json"])
    finally:
        cli.http_get = original
    require(code == 5 and payload["results"] == [] and payload["error"]["type"] == "upstream_unavailable" and payload["error"]["message"].startswith("network error:") and stderr == "", "network failure looked like an empty result")

    def blocked(url: str, *, expect_json: bool, timeout: int) -> bytes:
        raise nzfetch.Blocked("challenge")

    cli.http_get = blocked
    try:
        code, payload, _stderr = invoke(["gauges", "--json"])
    finally:
        cli.http_get = original
    require(code == 4 and payload["error"]["type"] == "blocked" and "network error:" in payload["error"]["message"], "block was not explicit")

    def redirect(url: str, **kwargs) -> tuple[bytes, str, str]:
        require(kwargs.get("timeout") == 10, "redirect probe had no timeout")
        require(kwargs.get("allowed_hosts") == cli.ALLOWED_HOSTS, "redirect probe dropped the host allowlist")
        return b'{"gauges":["AUCT"]}', "application/json", "https://evil.example/api/listGauges"

    original_fetch = cli.nzfetch.fetch_bytes
    cli.nzfetch.fetch_bytes = redirect
    try:
        code, payload, _stderr = invoke(["gauges", "--json"])
    finally:
        cli.nzfetch.fetch_bytes = original_fetch
    require(code == 7 and payload["error"]["type"] == "unsupported_operation", "cross-host redirect was followed")

    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("../AUCT_40_2026001.csv", "AUCT,2026-01-01 00:00,5.002\n")
    try:
        cli.parse_daily_zip(archive.getvalue(), "AUCT", "2026-01-01", "40", "2026")
    except cli.UnsafeError:
        pass
    else:
        raise AssertionError("zip path escape was accepted")

    rejected = (
        ["readings", "--gauge", "AUCT", "--date", "2026-01-01", "--limit", "999999999999", "--json"],
        ["readings", "--gauge", "AUCT", "--date", "2026-01-01", "--offset", "100001", "--json"],
        ["files", "--gauge", "AUCT", "--year", "9999999999", "--json"],
        ["readings", "--gauge", "AUCT", "--date", "2026-02-31", "--json"],
        ["readings", "--gauge", "auct", "--date", "2026-01-01", "--json"],
        ["readings", "--gauge", "../AU", "--date", "2026-01-01", "--json"],
        ["readings", "--gauge", "AUCT", "--date", "2026-01-01", "--sensor", "100", "--json"],
        ["readings", "--gauge", "AUCT", "--date", "2026-01-01", "--sensor", "00", "--json"],
        ["gauges", "--url", "https://evil.example/api/listGauges", "--json"],
        ["gauges", "--fixture", "/etc/passwd", "--json"],
        ["gauges", "--fixture", "../cli.py", "--json"],
    )
    for arguments in rejected:
        code, payload, stderr = invoke(arguments)
        require(code == 2 and payload["error"]["type"] == "invalid_input" and payload["results"] == [] and stderr == "", " ".join(arguments))
    run_repair_regressions()


def write_fixture(name: str, blob: bytes):
    path = cli.FIXTURES / name
    path.write_bytes(blob)
    return path


def member_zip(payload: bytes, *, compression: int = zipfile.ZIP_STORED) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=compression) as handle:
        handle.writestr("AUCT_40_2026001.csv", payload)
    return buffer.getvalue()


def patch_zip(blob: bytes, *, file_size: int | None = None, method: int | None = None, flag_or: int | None = None) -> bytes:
    patched = bytearray(blob)

    def patch(signature: bytes, flag_at: int, method_at: int, size_at: int) -> None:
        start = 0
        while True:
            index = patched.find(signature, start)
            if index < 0:
                return
            if flag_or is not None:
                flags = int.from_bytes(patched[index + flag_at : index + flag_at + 2], "little") | flag_or
                patched[index + flag_at : index + flag_at + 2] = flags.to_bytes(2, "little")
            if method is not None:
                patched[index + method_at : index + method_at + 2] = method.to_bytes(2, "little")
            if file_size is not None:
                patched[index + size_at : index + size_at + 4] = file_size.to_bytes(4, "little")
            start = index + 4

    patch(b"PK\x03\x04", 6, 8, 22)
    patch(b"PK\x01\x02", 8, 10, 24)
    return bytes(patched)


def corrupt_deflate_zip() -> bytes:
    payload = b"AUCT,2026-01-01 00:00,5.002\n" * 20
    blob = bytearray(member_zip(payload, compression=zipfile.ZIP_DEFLATED))
    index = blob.find(b"PK\x03\x04")
    name_len = int.from_bytes(blob[index + 26 : index + 28], "little")
    extra_len = int.from_bytes(blob[index + 28 : index + 30], "little")
    blob[index + 30 + name_len + extra_len] ^= 0xFF
    return bytes(blob)


def assert_member_error(blob: bytes, label: str, expected: type[BaseException]) -> None:
    try:
        zipfile.ZipFile(io.BytesIO(blob)).read("AUCT_40_2026001.csv")
    except expected:
        pass
    else:
        raise AssertionError(f"{label} did not raise {expected.__name__}")
    path = write_fixture(f"tmp-{label}.zip", blob)
    try:
        code, payload, stderr = invoke(
            ["readings", "--gauge", "AUCT", "--date", "2026-01-01", "--sensor", "40", "--fixture", path.name, "--json"]
        )
    finally:
        path.unlink(missing_ok=True)
    require(
        code == 6
        and payload["error"]["type"] == "schema_failure"
        and payload["results"] == []
        and stderr == ""
        and "could not be read" in payload["error"]["message"],
        label,
    )


def run_repair_regressions() -> None:
    code, payload, stderr = invoke(
        ["files", "--gauge", "AUCT", "--year", "2025", "--sensor", "40", "--fixture", "auct-2025-files.json", "--limit", "1", "--json"]
    )
    require(
        code == 0
        and stderr == ""
        and payload["results"][0]["name"] == "AUCT_40_2025001.zip"
        and payload["results"][0]["utc_date"] == "2025-01-01"
        and payload["results"][0]["size"] <= 2_000_000
        and payload["meta"]["matched_count"] == 3
        and payload["meta"]["archive_bundles"][0]["name"] == "AUCT_40_2025.zip"
        and payload["meta"]["archive_bundles"][0]["kind"] == "annual"
        and payload["meta"]["archive_bundles"][0]["size"] == 2515571
        and payload["meta"]["latest_data"] == "2026-01-06"
        and "excluded from daily readings" in payload["meta"]["note"],
        "annual bundle was treated as a daily file",
    )
    code, human, stderr = invoke_stdout(
        ["files", "--gauge", "AUCT", "--year", "2025", "--sensor", "40", "--fixture", "auct-2025-files.json", "--limit", "1"]
    )
    require(code == 0 and stderr == "" and "AUCT_40_2025001.zip" in human and "bundle annual AUCT_40_2025.zip not a daily reading" in human, "human bundle label missing")

    code, payload, _stderr = invoke(
        ["files", "--gauge", "AUCT", "--year", "2009", "--sensor", "40", "--fixture", "auct-2009-files.json", "--json"]
    )
    require(
        code == 0
        and [row["utc_date"] for row in payload["results"]] == ["2009-03-26", "2009-12-01", "2009-12-31"]
        and payload["meta"]["archive_bundles"] == [
            {
                "name": "AUCT_40_2009_085-365.zip",
                "kind": "part_year",
                "size": 2109554,
                "modified": "2021-11-08",
                "utc_start": "2009-03-26",
                "utc_end": "2009-12-31",
            }
        ],
        "part-year bundle was not labeled",
    )

    listing = json.loads((cli.FIXTURES / "auct-2025-files.json").read_text(encoding="utf-8"))
    evil_uri = json.loads(json.dumps(listing))
    evil_uri["files"][0]["uri"] = "https://evil.example/AUCT_40_2025.zip"
    try:
        cli.parse_files(evil_uri, "AUCT", "2025", "40")
    except cli.SchemaError as exc:
        require("URI" in str(exc), "bundle URI was not fail-closed")
    else:
        raise AssertionError("external bundle URI was accepted")
    reversed_span = {
        "files": [
            {
                "name": "AUCT_40_2009_365-085.zip",
                "uri": "/tidegauge/AUCT/2009/40/AUCT_40_2009_365-085.zip",
                "size": 10,
                "modified": "2021-11-08",
            }
        ]
    }
    try:
        cli.parse_files(reversed_span, "AUCT", "2009", "40")
    except cli.SchemaError as exc:
        require("reversed" in str(exc), "reversed part-year span was accepted")
    else:
        raise AssertionError("reversed part-year span was accepted")
    broken = json.loads(json.dumps(listing))
    broken["files"].append({"name": "EVIL.zip", "uri": "/tidegauge/AUCT/2025/40/EVIL.zip", "size": 10, "modified": "2026-01-01"})
    try:
        cli.parse_files(broken, "AUCT", "2025", "40")
    except cli.SchemaError as exc:
        require("file name" in str(exc), "unknown archive name was skipped")
    else:
        raise AssertionError("unknown archive name was accepted")

    unicode_name = "AUCT_40_2025" + "０" + "01.zip"
    try:
        cli.parse_files(
            {"files": [{"name": unicode_name, "uri": f"/tidegauge/AUCT/2025/40/{unicode_name}", "size": 10, "modified": "2026-01-01"}]},
            "AUCT",
            "2025",
            "40",
        )
    except cli.SchemaError:
        pass
    else:
        raise AssertionError("non-ASCII daily name was accepted")

    for modified in ("2026-99-99", "2026-02-31", "２０２６-01-06"):
        try:
            cli.parse_files(
                {"files": [{"name": "AUCT_40_2025001.zip", "uri": "/tidegauge/AUCT/2025/40/AUCT_40_2025001.zip", "size": 10, "modified": modified}]},
                "AUCT",
                "2025",
                "40",
            )
        except cli.SchemaError as exc:
            require("ISO date" in str(exc), modified)
        else:
            raise AssertionError(modified)

    oversized = json.loads(json.dumps(listing))
    oversized["files"][1]["size"] = 2_000_001
    try:
        cli.parse_files(oversized, "AUCT", "2025", "40")
    except cli.SchemaError as exc:
        require("daily file size" in str(exc), "daily size bound was loosened")
    else:
        raise AssertionError("daily file above 2MB was accepted")
    huge_bundle = json.loads(json.dumps(listing))
    huge_bundle["files"][0]["size"] = 10**13
    try:
        cli.parse_files(huge_bundle, "AUCT", "2025", "40")
    except cli.SchemaError as exc:
        require("archive bundle size" in str(exc), "unbounded bundle size was accepted")
    else:
        raise AssertionError("unbounded bundle size was accepted")

    try:
        cli.parse_datasets(
            {"gauge": "AUCT", "files": [], "datasets": [{"year": "２０２５", "sensor": "40", "datasetid": "AUCT/２０２５/40"}]},
            "AUCT",
        )
    except cli.SchemaError:
        pass
    else:
        raise AssertionError("non-ASCII dataset year was accepted")

    code, payload, stderr = invoke(
        ["readings", "--gauge", "AUCT", "--date", "2026-01-01", "--sensor", "41", "--fixture", "daily-excerpt.csv", "--json"]
    )
    require(
        code == 0
        and payload["results"][0]["sensor"] == "41"
        and payload["meta"]["sensor_verified"] is False
        and payload["meta"]["sensor_origin"] == "request",
        "sensor 41 relabel of a CSV fixture looked verified",
    )
    code, payload, stderr = invoke(
        ["readings", "--gauge", "AUCT", "--date", "2026-01-01", "--sensor", "41", "--fixture", "daily-excerpt.zip", "--json"]
    )
    require(code == 6 and payload["error"]["type"] == "schema_failure" and stderr == "", "sensor 41 relabel of a zip fixture was accepted")

    duplicate = "AUCT,2026-01-01 00:00,5.002\nAUCT,2026-1-1 0:0,5.006\n"
    path = write_fixture("tmp-unpadded.csv", duplicate.encode())
    try:
        code, payload, stderr = invoke(
            ["readings", "--gauge", "AUCT", "--date", "2026-01-01", "--sensor", "40", "--fixture", path.name, "--json"]
        )
    finally:
        path.unlink(missing_ok=True)
    require(code == 6 and "duplicate" in payload["error"]["message"] and stderr == "", "unpadded duplicate minute was accepted")

    fullwidth = "AUCT,２０２６-01-01 00:00,5.002\n"
    path = write_fixture("tmp-fullwidth.csv", fullwidth.encode())
    try:
        code, payload, stderr = invoke(
            ["readings", "--gauge", "AUCT", "--date", "2026-01-01", "--sensor", "40", "--fixture", path.name, "--json"]
        )
    finally:
        path.unlink(missing_ok=True)
    require(code == 6 and "timestamp" in payload["error"]["message"] and stderr == "", "fullwidth timestamp was accepted")

    huge = "AUCT,2026-01-01 00:00," + ("1" * 5000) + "\n"
    path = write_fixture("tmp-huge-height.csv", huge.encode())
    try:
        code, payload, stderr = invoke(
            ["readings", "--gauge", "AUCT", "--date", "2026-01-01", "--sensor", "40", "--fixture", path.name, "--json"]
        )
    finally:
        path.unlink(missing_ok=True)
    require(code == 6 and "height" in payload["error"]["message"] and stderr == "", "unbounded height was accepted")

    nested = ('{"a":' * 10000 + "0" + "}" * 10000).encode()
    path = write_fixture("tmp-deep.json", nested)
    try:
        code, payload, stderr = invoke(["gauges", "--fixture", path.name, "--json"])
    finally:
        path.unlink(missing_ok=True)
    require(code == 6 and payload["error"]["type"] == "schema_failure" and "nested" in payload["error"]["message"] and stderr == "", "deep JSON leaked a traceback")

    original = cli.http_get

    def refuse_network(url: str, *, expect_json: bool, timeout: int) -> bytes:
        raise AssertionError(url)

    cli.http_get = refuse_network
    try:
        code, payload, stderr = invoke(["gauges", "--fixture", "", "--json"])
    finally:
        cli.http_get = original
    require(code == 2 and payload["error"]["type"] == "invalid_input" and stderr == "" and payload["results"] == [], "blank fixture went live")

    row = b"AUCT,2026-01-01 00:00,5.002\n"
    stored = member_zip(row)
    flipped = bytearray(stored)
    at = flipped.find(row)
    flipped[at] ^= 0x01
    assert_member_error(bytes(flipped), "crc", zipfile.BadZipFile)
    assert_member_error(patch_zip(stored, file_size=1), "declared-size", zipfile.BadZipFile)
    assert_member_error(patch_zip(stored, flag_or=1), "encrypted", RuntimeError)
    assert_member_error(patch_zip(stored, method=99), "compression", NotImplementedError)
    assert_member_error(corrupt_deflate_zip(), "deflate", zlib.error)

    calls: list[str] = []

    def fake_history(url: str, *, expect_json: bool, timeout: int) -> bytes:
        require(timeout == 10, "historical fixture probe had no timeout")
        calls.append(url)
        if url.endswith("/api/listGauges"):
            return b'{"gauges":["AUCT"]}'
        if url.endswith("/api/getGaugeData/AUCT"):
            return b'{"gauge":"AUCT","files":[],"datasets":[{"year":"2025","sensor":"40","datasetid":"AUCT/2025/40"}]}'
        if url.endswith("/api/listDatasetFiles/AUCT/2025/40"):
            return (cli.FIXTURES / "auct-2025-files.json").read_bytes()
        if url.endswith("/AUCT_40_2025152.zip"):
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w") as handle:
                handle.writestr("AUCT_40_2025152.csv", "AUCT,2025-06-01 00:00,6.346\n")
            return buffer.getvalue()
        raise AssertionError(url)

    cli.http_get = fake_history
    try:
        code, payload, stderr = invoke(["readings", "--gauge", "AUCT", "--date", "2025-06-01", "--sensor", "40", "--limit", "1", "--json"])
    finally:
        cli.http_get = original
    require(
        code == 0
        and stderr == ""
        and payload["results"][0]["height_m"] == "6.346"
        and payload["meta"]["source_url"].endswith("/AUCT_40_2025152.zip")
        and not any(url.endswith("/AUCT_40_2025.zip") for url in calls),
        "readings downloaded an annual bundle",
    )

    published_2026 = {(date(2026, 1, 1) + timedelta(days=offset)).isoformat() for offset in range(365)}
    require("2026-12-31" in published_2026, "2026 fixture missed 31 December")
    frozen = smoke_test.unpublished_utc_day(published_2026, date(2027, 1, 15))
    require(frozen == "2029-01-01" and frozen not in published_2026, "2027 clock still selected a published 2026 day")
    prefix = {(date(2026, 1, 1) + timedelta(days=offset)).isoformat() for offset in range(279)}
    require(smoke_test.unpublished_utc_day(prefix, date(2026, 10, 11)) == "2028-01-01", "open 2026 year selected 31 December")
    require(smoke_test.unpublished_utc_day({"2026-01-01", "2026-01-03"}, date(2027, 6, 1)) == "2026-01-02", "published gap was ignored")


def invoke_stdout(arguments: list[str]) -> tuple[int, str, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = cli.main(arguments)
    return code, stdout.getvalue(), stderr.getvalue()


def check_provenance_contract() -> None:
    cli_path = Path(__file__).with_name("cli.py")
    cases = (
        ((*DATA_COMMAND,), 0),
        (("--thecolab-invalid-option", "--json"), 2),
    )
    for arguments, expected_code in cases:
        completed = subprocess.run(
            [sys.executable, str(cli_path), *arguments],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        assert completed.returncode == expected_code, completed.stderr or completed.stdout
        assert not completed.stderr, completed.stderr
        payload = json.loads(completed.stdout)
        meta = payload["meta"]
        assert meta["source_url"] and meta["publisher"]
        assert meta["retrieved_at"].endswith("Z")
        retrieved = datetime.fromisoformat(meta["retrieved_at"].replace("Z", "+00:00"))
        assert retrieved.utcoffset() == timedelta(0)
        assert isinstance(payload["results"], list)
        if expected_code:
            assert payload["results"] == []
            assert payload["error"]["code"] == expected_code
            assert payload["error"]["type"] == "invalid_input"
        else:
            assert "error" not in payload

    meta = provenance("https://example.invalid/data", "Fixture publisher")
    assert "licence" not in meta and "latest_data" not in meta
    cached = provenance(
        "https://example.invalid/data",
        "Fixture publisher",
        licence="Fixture terms",
        latest_data="2026-09",
        retrieved_at="2026-10-01T01:02:03Z",
    )
    assert cached["licence"] == "Fixture terms" and cached["latest_data"] == "2026-09"
    assert cached["retrieved_at"] == "2026-10-01T01:02:03Z"
    normalised = provenance(
        "https://example.invalid/data",
        "Fixture publisher",
        retrieved_at="2026-10-01T14:02:03+13:00",
    )
    assert normalised["retrieved_at"] == cached["retrieved_at"]
    try:
        provenance("https://example.invalid/data", "Fixture publisher", retrieved_at="2026-10-01T01:02:03")
    except ValueError:
        pass
    else:
        raise AssertionError("naive retrieval timestamp accepted")
    assert result_envelope([], cached)["results"] == []
    failure = error_envelope(4, "rate-limited", meta, retry_after="60")
    assert failure["error"]["type"] == "blocked" and failure["error"]["retry_after"] == "60"
    assert parse_bbox("174,-37,175,-36") == (174.0, -37.0, 175.0, -36.0)
    invalid_boxes = (
        "174,-37,175", "a,b,c,d", "nan,-37,175,-36", "174,-37,inf,-36",
        "175,-37,174,-36", "174,-36,175,-37", "-181,-37,175,-36",
        "174,-91,175,-36", "174,-37,181,-36", "174,-37,175,91", "174,-37,174,-36",
    )
    for invalid in invalid_boxes:
        try:
            parse_bbox(invalid)
        except argparse.ArgumentTypeError:
            pass
        else:
            raise AssertionError(f"invalid bbox accepted: {invalid}")
    parser = argparse.ArgumentParser()
    add_spatial_arguments(parser)
    args = parser.parse_args(["--bbox", "174,-37,175,-36", "--format", "geojson"])
    assert args.bbox == (174.0, -37.0, 175.0, -36.0) and args.format == "geojson"
    assert parser.parse_args(["--bbox=-180,-90,180,90"]).bbox == (-180.0, -90.0, 180.0, 90.0)
    collection = geojson_envelope([], meta)
    assert collection == {"type": "FeatureCollection", "features": [], "meta": meta}


def main() -> int:
    result = audit_skill(Path(__file__).resolve().parents[1])
    if result["ok"]:
        try:
            check_provenance_contract()
            run_parser_contracts()
        except (AssertionError, json.JSONDecodeError, KeyError) as exc:
            result["ok"] = False
            result["errors"].append(str(exc))
        else:
            result["checks"].extend(("provenance", "json_errors", "cached_metadata", "spatial_contract", "parser_fixtures"))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
