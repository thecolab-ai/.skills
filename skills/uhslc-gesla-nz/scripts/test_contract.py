#!/usr/bin/env python3
"""Deterministic repository contract test for UHSLC GESLA New Zealand."""
import argparse
import io
import json
import subprocess
import sys
from contextlib import redirect_stdout
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from email.message import Message
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "lib"))

import cli  # noqa: E402
from contract_test import audit_skill  # noqa: E402
from provenance import (  # noqa: E402
    add_spatial_arguments,
    error_envelope,
    geojson_envelope,
    parse_bbox,
    provenance,
    result_envelope,
)

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
DATA_COMMAND = (
    "series",
    "--station",
    "auckland-auct-nzl-ttw",
    "--from",
    "2024-01-01T00:00:00Z",
    "--to",
    "2024-01-01T02:00:00Z",
    "--fixture",
    "series-positive.csv",
)
START = datetime(2024, 1, 1, tzinfo=timezone.utc)
END = datetime(2024, 1, 1, 2, tzinfo=timezone.utc)
STATION = "auckland-auct-nzl-ttw"


def check_provenance_contract() -> None:
    entry = Path(__file__).with_name("cli.py")
    cases = (
        ((*DATA_COMMAND, "--json"), 0),
        (("--thecolab-invalid-option", "--json"), 2),
    )
    for arguments, expected_code in cases:
        completed = subprocess.run(
            [sys.executable, str(entry), *arguments],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        assert completed.returncode == expected_code, completed.stderr or completed.stdout
        assert not completed.stderr, completed.stderr
        payload = json.loads(completed.stdout)
        meta = payload["meta"]
        assert meta["source_url"] and meta["publisher"] == cli.PUBLISHER
        assert meta["licence"] == cli.LICENCE
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
            assert payload["results"]

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


def expect_skill_error(function, code: int) -> cli.SkillError:
    try:
        function()
    except cli.SkillError as exc:
        assert exc.code == code, exc
        return exc
    raise AssertionError(f"expected exit code {code}")


def check_parser() -> None:
    rows = cli.parse_series_csv((FIXTURES / "series-positive.csv").read_bytes(), STATION, START, END)
    assert [row["source_row"] for row in rows] == [1, 2, 3]
    assert rows[0]["time"] == rows[1]["time"] == "2024-01-01T00:00:00Z"
    assert rows[0]["sea_level"] == "1.250"
    assert rows[1]["sea_level"] == "1.2500000002"
    assert rows[0]["sea_level_unit"] == "m"
    assert rows[0]["flag1"] == 1 and rows[0]["flag1_meaning"] == "correct_value"
    assert rows[0]["flag2"] == 1 and rows[0]["flag2_meaning"] == "use"
    assert rows[2]["sea_level"] is None and rows[2]["sea_level_missing"] is True
    assert rows[2]["flag1_meaning"] == "missing_value"
    assert rows[2]["flag2"] == 0 and rows[2]["flag2_meaning"] == "do_not_use"
    assert rows[2]["record_id"] == STATION
    assert all(row["sea_level"] != "-99.9999" for row in rows)

    assert cli.parse_series_csv((FIXTURES / "series-empty.csv").read_bytes(), STATION, START, END) == []
    for name in ("series-malformed.csv", "series-truncated.csv", "series-wrong-units.csv"):
        expect_skill_error(
            lambda name=name: cli.parse_series_csv((FIXTURES / name).read_bytes(), STATION, START, END),
            6,
        )
    for body in (b"<html>no data</html>", b'{"table":', b"\xff\xfe not text"):
        expect_skill_error(lambda body=body: cli.parse_series_csv(body, STATION, START, END), 6)

    outside = (
        "time,sea_level,flag1,flag2,record_id\n"
        "UTC,m,,,\n"
        "2024-01-01T02:00:00Z,1.000,1,1,auckland-auct-nzl-ttw\n"
    ).encode()
    expect_skill_error(lambda: cli.parse_series_csv(outside, STATION, START, END), 6)
    shifted = outside.replace(b"2024-01-01T02:00:00Z", b"2024-01-01T00:00:00+13:00")
    expect_skill_error(lambda: cli.parse_series_csv(shifted, STATION, START, END), 6)
    other_station = outside.replace(b"2024-01-01T02:00:00Z", b"2024-01-01T00:00:00Z").replace(
        b"auckland-auct-nzl-ttw", b"wellington-wlg-nzl-ttw"
    )
    expect_skill_error(lambda: cli.parse_series_csv(other_station, STATION, START, END), 6)
    unknown_flag = (
        "time,sea_level,flag1,flag2,record_id\n"
        "UTC,m,,,\n"
        "2024-01-01T00:00:00Z,1.000,9,1,auckland-auct-nzl-ttw\n"
    ).encode()
    expect_skill_error(lambda: cli.parse_series_csv(unknown_flag, STATION, START, END), 6)

    empty_404 = (FIXTURES / "http-404-empty.txt").read_bytes()
    outside_404 = (FIXTURES / "http-404-outside.txt").read_bytes()
    assert cli.interpret_response(404, {}, empty_404, STATION, START, END) == []
    assert cli.interpret_response(404, {}, outside_404, STATION, START, END) == []
    expect_skill_error(
        lambda: cli.interpret_response(404, {}, (FIXTURES / "http-404-other.txt").read_bytes(), STATION, START, END),
        6,
    )
    limited = expect_skill_error(
        lambda: cli.interpret_response(429, {"retry-after": "30"}, b"slow", STATION, START, END),
        4,
    )
    assert limited.retry_after == "30"
    expect_skill_error(lambda: cli.interpret_response(503, {}, b"down", STATION, START, END), 5)

    wide = "time,sea_level,flag1,flag2,record_id\nUTC,m,,,\n" + "".join(
        f"2024-01-01T00:00:00Z,1.000,1,1,{STATION}\n" for _ in range(cli.MAX_ROWS + 1)
    )
    expect_skill_error(lambda: cli.parse_series_csv(wide.encode(), STATION, START, END), 7)


class _BytesResponse:
    def __init__(self, body: bytes, url: str) -> None:
        self.status = 200
        self.headers = {}
        self._body = body
        self._url = url
        self._offset = 0

    def read(self, amount: int = -1) -> bytes:
        if amount is None or amount < 0:
            amount = len(self._body) - self._offset
        chunk = self._body[self._offset:self._offset + amount]
        self._offset += len(chunk)
        return chunk

    def geturl(self) -> str:
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> bool:
        return False


class _Opener:
    def __init__(self, action) -> None:
        self.action = action

    def open(self, request, timeout=None):
        assert timeout == cli.TIMEOUT_SECONDS
        return self.action(request)


def check_transport() -> None:
    url = cli.build_series_url(STATION, START, END)
    assert url.startswith(f"https://{cli.ALLOWED_HOST}/erddap/tabledap/{cli.DATASET_ID}.csv?")
    assert "record_id=%22auckland-auct-nzl-ttw%22" in url
    assert "time%3E=2024-01-01T00:00:00Z" in url
    assert "time%3C2024-01-01T02:00:00Z" in url
    assert "time,sea_level,flag1,flag2,record_id" in url
    expect_skill_error(lambda: cli.fetch_official("https://example.com/global.csv"), 7)
    expect_skill_error(lambda: cli.fetch_official("http://uhslc.soest.hawaii.edu/erddap/"), 7)

    handler = cli.AllowlistRedirect()
    request = urllib.request.Request(cli.INFO_URL)
    expect_skill_error(
        lambda: handler.redirect_request(request, None, 302, "Found", {}, "https://example.com/off"),
        7,
    )
    expect_skill_error(
        lambda: handler.redirect_request(request, None, 302, "Found", {}, "http://uhslc.soest.hawaii.edu/erddap/"),
        7,
    )
    stayed = handler.redirect_request(request, None, 302, "Found", {}, url)
    assert stayed.get_full_url().startswith(f"https://{cli.ALLOWED_HOST}/")

    headers = Message()
    headers["Retry-After"] = "17"

    def raise_limited(_request):
        raise urllib.error.HTTPError(url, 429, "Too Many Requests", headers, io.BytesIO(b"slow"))

    status, response_headers, body = cli.fetch_official(url, opener=_Opener(raise_limited))
    limited = expect_skill_error(
        lambda: cli.interpret_response(status, response_headers, body, STATION, START, END),
        4,
    )
    assert limited.retry_after == "17"

    def raise_unavailable(_request):
        raise urllib.error.HTTPError(url, 503, "Unavailable", Message(), io.BytesIO(b"down"))

    status, response_headers, body = cli.fetch_official(url, opener=_Opener(raise_unavailable))
    expect_skill_error(
        lambda: cli.interpret_response(status, response_headers, body, STATION, START, END),
        5,
    )

    def raise_timeout(_request):
        raise TimeoutError("timed out")

    expect_skill_error(lambda: cli.fetch_official(url, opener=_Opener(raise_timeout)), 5)

    huge = b"x" * (cli.MAX_BYTES + 1)
    expect_skill_error(
        lambda: cli.fetch_official(url, opener=_Opener(lambda _request: _BytesResponse(huge, url))),
        7,
    )
    expect_skill_error(
        lambda: cli.fetch_official(
            url,
            opener=_Opener(lambda _request: _BytesResponse(b"time\n", "https://example.com/stolen")),
        ),
        7,
    )

    class RedirectHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(302)
            self.send_header("Location", "https://example.com/off-host")
            self.end_headers()

        def log_message(self, _format, *_args) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), RedirectHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        local = f"http://127.0.0.1:{server.server_address[1]}/series.csv"
        opener = urllib.request.build_opener(cli.AllowlistRedirect)
        request = urllib.request.Request(local, headers={"User-Agent": cli.USER_AGENT})

        def follow_redirect() -> None:
            opener.open(request, timeout=cli.TIMEOUT_SECONDS)

        expect_skill_error(follow_redirect, 7)
    finally:
        server.shutdown()
        server.server_close()


def run_cli(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(Path(__file__).with_name("cli.py")), *arguments],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )


def check_cli_bounds() -> None:
    calls: list[str] = []
    original = cli.fetch_official

    def spy(url, opener=None):
        calls.append(url)
        raise AssertionError("network fetch was called")

    cli.fetch_official = spy
    try:
        captured = io.StringIO()
        with redirect_stdout(captured):
            invalid = cli.main(
                ["series", "--station", "global-table", "--from", "2024-01-01T00:00:00Z", "--to", "2024-01-02T00:00:00Z", "--json"]
            )
            long_window = cli.main(
                [
                    "series",
                    "--station",
                    STATION,
                    "--from",
                    "2024-01-01T00:00:00Z",
                    "--to",
                    "2024-01-03T00:00:01Z",
                    "--json",
                ]
            )
            naive = cli.main(
                ["series", "--station", STATION, "--from", "2024-01-01T00:00:00", "--to", "2024-01-01T01:00:00Z", "--json"]
            )
            reversed_window = cli.main(
                ["series", "--station", STATION, "--from", "2024-01-02T00:00:00Z", "--to", "2024-01-01T00:00:00Z", "--json"]
            )
            fixture = cli.main([*DATA_COMMAND, "--json"])
        assert invalid == 2 and long_window == 7 and naive == 2 and reversed_window == 2
        assert fixture == 0 and calls == []
        assert '"type": "unsupported_operation"' in captured.getvalue()
    finally:
        cli.fetch_official = original

    positive = run_cli(*DATA_COMMAND, "--json")
    assert positive.returncode == 0, positive.stderr
    payload = json.loads(positive.stdout)
    assert payload["results"][2]["sea_level"] is None
    assert payload["meta"]["source_url"].startswith(f"https://{cli.ALLOWED_HOST}/")
    assert "record_id=%22" in payload["meta"]["source_url"]
    empty = run_cli(
        "series",
        "--station",
        STATION,
        "--from",
        "2024-01-01T00:30:00Z",
        "--to",
        "2024-01-01T00:31:00Z",
        "--fixture",
        "series-empty.csv",
        "--json",
    )
    assert empty.returncode == 0
    assert json.loads(empty.stdout)["results"] == []
    malformed = run_cli(
        "series",
        "--station",
        STATION,
        "--from",
        "2024-01-01T00:00:00Z",
        "--to",
        "2024-01-01T02:00:00Z",
        "--fixture",
        "series-malformed.csv",
        "--json",
    )
    assert malformed.returncode == 6
    assert json.loads(malformed.stdout)["error"]["type"] == "schema_failure"
    escaped = run_cli(
        "series",
        "--station",
        STATION,
        "--from",
        "2024-01-01T00:00:00Z",
        "--to",
        "2024-01-01T02:00:00Z",
        "--fixture",
        "../cli.py",
        "--json",
    )
    assert escaped.returncode == 2


def fixture_checks() -> None:
    check_parser()
    check_transport()
    check_cli_bounds()


def main() -> int:
    result = audit_skill(Path(__file__).resolve().parents[1])
    try:
        check_provenance_contract()
        fixture_checks()
    except Exception as exc:
        result["ok"] = False
        result["errors"].append(f"{type(exc).__name__}: {exc}")
    else:
        result["checks"].extend(("provenance", "json_errors", "parser_fixtures", "transport_bounds"))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
