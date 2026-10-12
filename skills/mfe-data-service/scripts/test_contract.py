#!/usr/bin/env python3
"""Deterministic repository contract test for this skill."""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_DIR = Path(__file__).resolve().parent
FIXTURES = SCRIPT_DIR.parent / "tests" / "fixtures"
sys.path.insert(0, str(REPO_ROOT / "lib"))
sys.path.insert(0, str(SCRIPT_DIR))

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

DATA_COMMAND = (
    "search",
    "flood",
    "--limit",
    "1",
    "--fixture",
    str(FIXTURES / "search-one.json"),
    "--json",
)


def run(argv: list[str], transport=None) -> tuple[int, dict | None, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = cli.main(argv, transport=transport)
    text = stdout.getvalue()
    error_text = stderr.getvalue()
    payload = json.loads(text) if text else None
    return code, payload, error_text


def run_text(argv: list[str], transport=None) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = cli.main(argv, transport=transport)
    return code, stdout.getvalue(), stderr.getvalue()


def link_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8").strip()


def linked_transport(body_name: str, link: str | None):
    calls: list[str] = []
    body = json.loads((FIXTURES / body_name).read_text(encoding="utf-8"))

    def transport(url: str):
        calls.append(url)
        return cli.CatalogueDocument(body, link_header=link)

    return calls, transport


def assert_json_error(payload: dict, code: int, error_type: str) -> None:
    assert payload["results"] == []
    assert payload["error"]["code"] == code
    assert payload["error"]["type"] == error_type
    assert payload["meta"]["publisher"] == "Ministry for the Environment"
    assert payload["meta"]["retrieved_at"].endswith("Z")


def assert_deterministic_contracts() -> list[str]:
    """Offline parser, licence, bounds and transport-failure contracts."""
    calls: list[str] = []

    def boom(url: str):
        calls.append(url)
        raise AssertionError(f"network call was not allowed: {url}")

    code, payload, errors = run(
        ["search", "flood", "--limit", "1", "--fixture", str(FIXTURES / "search-one.json"), "--json"],
        transport=boom,
    )
    assert code == 0 and errors == "" and calls == []
    assert payload is not None and "error" not in payload
    assert payload["results"][0]["id"] == 125035
    assert payload["results"][0]["title"] == "Synthetic flood regulation layer"
    assert payload["results"][0]["published_at"] == "2026-08-09T21:18:09.254632Z"
    assert payload["meta"]["latest_data"] == "2026-08-09T21:18:09.254632Z"
    assert "licence" not in payload["meta"]
    assert payload["truncated"] is False
    assert payload["meta"]["source_url"].startswith("https://data.mfe.govt.nz/services/api/v1/data/")
    assert "page_size=1" in payload["meta"]["source_url"]
    assert "/query" not in payload["meta"]["source_url"]

    code, payload, errors = run(
        ["search", "nothing", "--limit", "1", "--fixture", str(FIXTURES / "search-empty.json"), "--json"],
        transport=boom,
    )
    assert code == 0 and errors == "" and payload is not None
    assert payload["results"] == [] and payload["truncated"] is False

    code, payload, errors = run(
        ["search", "page", "--limit", "1", "--fixture", str(FIXTURES / "search-page.json"), "--json"],
        transport=boom,
    )
    assert code == 0 and payload is not None
    assert [row["id"] for row in payload["results"]] == [1]
    assert payload["truncated"] is True
    assert calls == []

    code, payload, errors = run(
        ["layer", "117733", "--fixture", str(FIXTURES / "layer-open.json"), "--json"],
        transport=boom,
    )
    assert code == 0 and errors == "" and payload is not None
    row = payload["results"][0]
    assert row["field_names"] == ["Shape", "class_name"]
    assert row["feature_count"] == 3
    assert row["license_type"] == "cc-by"
    assert row["license_version"] == "4.0"
    assert row["crs"] == "EPSG:2193"
    assert payload["meta"]["licence"] == "Creative Commons Attribution 4.0 International"
    assert payload["meta"]["latest_data"] == "2024-06-01T12:00:00Z"
    assert payload["meta"]["source_url"] == "https://data.mfe.govt.nz/services/api/v1/layers/117733/"

    code, payload, errors = run(
        ["layer", "125035", "--fixture", str(FIXTURES / "layer-grid.json"), "--json"],
        transport=boom,
    )
    assert code == 0 and payload is not None
    assert payload["results"][0]["field_names"] == []
    assert payload["results"][0]["fields_state"] == "absent"
    assert payload["results"][0]["feature_count"] == 1
    assert payload["results"][0]["license_type"] == "cc-by"

    refusals = (
        ("42", "layer-closed.json"),
        ("43", "layer-missing-licence.json"),
        ("44", "layer-contradictory.json"),
        ("45", "layer-cc0.json"),
    )
    for layer_id, name in refusals:
        code, payload, errors = run(
            ["layer", layer_id, "--fixture", str(FIXTURES / name), "--json"],
            transport=boom,
        )
        assert code == 7 and errors == "" and payload is not None
        assert_json_error(payload, 7, "unsupported_operation")
        assert "open" in payload["error"]["message"] or "missing" in payload["error"]["message"]
        assert "class_name" not in json.dumps(payload)

    for name in ("malformed.txt", "truncated.txt"):
        code, payload, errors = run(
            ["layer", "1", "--fixture", str(FIXTURES / name), "--json"],
            transport=boom,
        )
        assert code == 6 and errors == "" and payload is not None
        assert_json_error(payload, 6, "schema_failure")

    rejected = (
        ["search", "--limit", "1", "--json"],
        ["search", "   ", "--json"],
        ["search", "https://example.test/layer", "--json"],
        ["search", "flood", "--limit", "0", "--json"],
        ["search", "flood", "--limit", "21", "--json"],
        ["layer", "0", "--json"],
        ["layer", "12abc", "--json"],
        ["layer", "1", "--fixture", "https://example.test/layer.json", "--json"],
        ["--thecolab-invalid-option", "--json"],
    )
    for argv in rejected:
        code, payload, errors = run(argv, transport=boom)
        assert code == 2 and errors == "" and payload is not None, argv
        assert_json_error(payload, 2, "invalid_input")
    assert calls == []

    limited = json.loads((FIXTURES / "http-429.json").read_text(encoding="utf-8"))
    code, message, retry_after = cli.outcome_for_exception(
        cli.nzfetch.RateLimited("rate limited", retry_after=limited["retry_after"])
    )
    assert code == limited["exit_code"] and retry_after == "30"
    code, payload, errors = run(["layer", "117733", "--json"], transport=lambda url: (_ for _ in ()).throw(
        cli.nzfetch.RateLimited("rate limited", retry_after="30")
    ))
    assert code == 4 and errors == "" and payload is not None
    assert_json_error(payload, 4, limited["error_type"])
    assert payload["error"]["retry_after"] == "30"

    unavailable = json.loads((FIXTURES / "http-503.json").read_text(encoding="utf-8"))
    code, message, retry_after = cli.outcome_for_exception(
        cli.nzfetch.FetchError("HTTP 503 from https://data.mfe.govt.nz/services/api/v1/layers/117733/")
    )
    assert code == unavailable["exit_code"] and retry_after is None
    code, payload, errors = run(
        ["search", "flood", "--limit", "1", "--json"],
        transport=lambda url: (_ for _ in ()).throw(
            cli.nzfetch.FetchError("HTTP 503 from https://data.mfe.govt.nz/services/api/v1/data/")
        ),
    )
    assert code == 5 and payload is not None
    assert_json_error(payload, 5, unavailable["error_type"])

    timed_out = json.loads((FIXTURES / "timeout.json").read_text(encoding="utf-8"))
    code, message, retry_after = cli.outcome_for_exception(
        cli.nzfetch.FetchError("catalogue unavailable after 1 attempt(s) (network error: timed out)")
    )
    assert code == timed_out["exit_code"]
    assert "timed out" in message

    redirect = json.loads((FIXTURES / "redirect-off-host.json").read_text(encoding="utf-8"))
    try:
        cli.nzfetch._validate_outbound_url(redirect["location"], frozenset({"data.mfe.govt.nz"}))
    except cli.nzfetch.FetchError as exc:
        code, message, retry_after = cli.outcome_for_exception(exc)
    else:
        raise AssertionError("off-host redirect was accepted")
    assert code == redirect["exit_code"]
    assert "data.mfe.govt.nz" in message

    calls, transport = linked_transport("search-one.json", link_fixture("link-page-next.txt"))
    code, payload, errors = run(["search", "flood", "--limit", "1", "--json"], transport=transport)
    assert code == 0 and errors == "" and payload is not None
    assert [row["id"] for row in payload["results"]] == [125035]
    assert payload["truncated"] is True
    assert payload["page"]["next"] == "https://data.mfe.govt.nz/services/api/v1/data/?q=flood&page_size=1&page=2"
    assert payload["page"]["last"] == "https://data.mfe.govt.nz/services/api/v1/data/?q=flood&page_size=1&page=102"
    assert "sort=" not in json.dumps(payload["page"])
    assert len(calls) == 1
    assert calls[0].startswith("https://data.mfe.govt.nz/services/api/v1/data/")
    assert "page=2" not in calls[0] and "/query" not in calls[0]
    code, text, errors = run_text(["search", "flood", "--limit", "1"], transport=transport)
    assert code == 0 and errors == ""
    assert "More catalogue rows exist; this command does not page further." in text
    assert "next page: https://data.mfe.govt.nz/services/api/v1/data/?q=flood&page_size=1&page=2" in text
    assert "last page: https://data.mfe.govt.nz/services/api/v1/data/?q=flood&page_size=1&page=102" in text
    assert len(calls) == 2
    assert all("page=2" not in url and "/query" not in url for url in calls)

    calls, transport = linked_transport("search-empty.json", link_fixture("link-sort-only.txt"))
    code, payload, errors = run(
        ["search", "__no_such_mfe_layer_zzqq__", "--limit", "1", "--json"],
        transport=transport,
    )
    assert code == 0 and errors == "" and payload is not None
    assert payload["results"] == [] and payload["truncated"] is False and "page" not in payload
    assert len(calls) == 1
    calls, transport = linked_transport("search-one.json", link_fixture("link-sort-only.txt"))
    code, payload, errors = run(["search", "flood", "--limit", "1", "--json"], transport=transport)
    assert code == 0 and payload is not None
    assert payload["truncated"] is False and "page" not in payload and len(payload["results"]) == 1
    assert len(calls) == 1

    calls, transport = linked_transport("search-one.json", link_fixture("link-malformed.txt"))
    code, payload, errors = run(["search", "flood", "--limit", "1", "--json"], transport=transport)
    assert code == 0 and errors == "" and payload is not None
    dumped = json.dumps(payload)
    assert payload["truncated"] is True and "page" not in payload
    assert "evil.example" not in dumped and "user:pass" not in dumped
    assert "/query" not in dumped and "not-a-url" not in dumped
    assert len(calls) == 1 and "page=3" not in calls[0]

    next_only = '<https://data.mfe.govt.nz/services/api/v1/data/?q=flood&page_size=1&page=2>; rel="next"'
    calls, transport = linked_transport("search-one.json", next_only)
    code, payload, errors = run(["search", "flood", "--limit", "1", "--json"], transport=transport)
    assert code == 0 and payload is not None and payload["truncated"] is True
    assert payload["page"] == {
        "next": "https://data.mfe.govt.nz/services/api/v1/data/?q=flood&page_size=1&page=2",
    }
    assert len(calls) == 1

    last_only = '<https://data.mfe.govt.nz/services/api/v1/data/?q=flood&page_size=1&page=9>; rel="page-last"'
    calls, transport = linked_transport("search-one.json", last_only)
    code, payload, errors = run(["search", "flood", "--limit", "1", "--json"], transport=transport)
    assert code == 0 and payload is not None and payload["truncated"] is False
    assert payload["page"] == {
        "last": "https://data.mfe.govt.nz/services/api/v1/data/?q=flood&page_size=1&page=9",
    }

    rows, truncated, _latest, page = cli.parse_search_document(
        {
            "results": [{
                "id": 1,
                "type": "layer",
                "title": "Synthetic",
                "published_at": "2024-01-01T00:00:00Z",
            }],
            "next": "https://evil.example/next",
        },
        limit=1,
    )
    assert truncated is True and page == {} and rows[0]["id"] == 1

    planted = "https://data.mfe.govt.nz/services/api/v1/data/?q=flood&page_size=1&page=2"
    early = f'<{planted}>; rel="page-next"'
    assert cli.parse_link_header(early + ("x" * 9000)) == (planted, None, True)
    assert cli.parse_link_header(("x" * 9000) + early) == (None, None, False)
    assert cli.parse_link_header("<<<") == (None, None, False)
    assert cli.parse_link_header(None) == (None, None, False)
    assert cli.parse_link_header(
        '<https://user:pass@data.mfe.govt.nz/services/api/v1/data/?page=2>; rel="page-next"'
    ) == (None, None, True)
    assert cli.parse_link_header(
        '<https://data.mfe.govt.nz/services/query/?page=2>; rel="page-last"'
    ) == (None, None, False)

    original_fetch = cli.nzfetch.fetch_json
    original_reader = cli.nzfetch._read_response_limited
    fetch_calls: list[str] = []

    def fake_fetch(url, **kwargs):
        fetch_calls.append(url)
        assert kwargs["timeout"] == cli.TIMEOUT
        assert kwargs["max_bytes"] == cli.MAX_BYTES
        assert set(kwargs["allowed_hosts"]) == {cli.HOST}

        class Headers:
            def get_all(self, name):
                if str(name).lower() == "link":
                    return [link_fixture("link-page-next.txt")]
                return []

            def get(self, name, default=None):
                found = self.get_all(name)
                return found[0] if found else default

        class Response:
            headers = Headers()

            def read(self, _size):
                return b""

        cli.nzfetch._read_response_limited(Response(), kwargs["max_bytes"])
        return json.loads((FIXTURES / "search-one.json").read_text(encoding="utf-8"))

    cli.nzfetch.fetch_json = fake_fetch
    try:
        code, payload, errors = run(["search", "flood", "--limit", "1", "--json"])
        assert code == 0 and errors == "" and payload is not None
        assert payload["truncated"] is True
        assert payload["page"]["next"].endswith("page=2")
        assert len(fetch_calls) == 1 and "page=2" not in fetch_calls[0]
    finally:
        cli.nzfetch.fetch_json = original_fetch
    assert cli.nzfetch._read_response_limited is original_reader

    try:
        cli.catalogue_url("services/query/")
    except cli.SkillFailure as exc:
        assert exc.code == 7
    else:
        raise AssertionError("query path was accepted")
    built = cli.catalogue_url("data/", {"q": "flood", "page_size": "1"})
    assert built.startswith("https://data.mfe.govt.nz/services/api/v1/data/")
    assert "/query" not in built

    return [
        "fixture positive search card keeps id, title and published_at",
        "fixture empty search is an empty result",
        "fixture search page is truncated to the requested limit",
        "fixture Link page-next marks one catalogue page truncated after a single request",
        "fixture sort-only Link stays complete for an empty page and a full page",
        "fixture malformed Link omits off-host, userinfo and query targets",
        "fixture rel=next is truncated and page-last alone is not",
        "contract Link header parsing is bounded and host-limited",
        "contract catalogue transport keeps the Link header from the same response",
        "fixture open layer keeps field names, feature count and cc-by licence",
        "fixture grid layer reports absent fields without inventing names",
        "fixture closed, missing, contradictory and cc0 licences are refused",
        "fixture malformed and truncated JSON are schema failures",
        "contract malformed arguments and oversize limits are rejected before any request",
        "fixture HTTP 429 is blocked and preserves retry_after",
        "fixture HTTP 503 is upstream unavailable",
        "fixture timeout is upstream unavailable",
        "contract off-host redirect is rejected",
        "contract query paths cannot be built",
    ]


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
        "https://example.invalid/data", "Fixture publisher",
        licence="Fixture terms", latest_data="2026-09", retrieved_at="2026-10-01T01:02:03Z",
    )
    assert cached["licence"] == "Fixture terms" and cached["latest_data"] == "2026-09"
    assert cached["retrieved_at"] == "2026-10-01T01:02:03Z"
    normalised = provenance(
        "https://example.invalid/data", "Fixture publisher",
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
    assert_deterministic_contracts()


def main() -> int:
    result = audit_skill(Path(__file__).resolve().parents[1])
    if result["ok"]:
        check_provenance_contract()
        result["checks"].extend(("provenance", "json_errors", "cached_metadata", "spatial_contract", "catalogue_contract"))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
