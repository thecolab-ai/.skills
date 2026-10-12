#!/usr/bin/env python3
"""Deterministic repository and parser contract for NZ point clouds."""
from __future__ import annotations

import argparse
import io
import json
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

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

DATA_COMMAND = (
    "collections",
    "--bbox",
    "174.7,-36.9,174.8,-36.8",
    "--fixture",
    "catalog-ok",
    "--json",
)
CC_ID = "OTLAS.042025.2193.9"
REFUSED_ID = "OTLAS.062016.2193.9"


def invoke(arguments: list[str]) -> tuple[int, dict, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = cli.main(arguments)
    text = stdout.getvalue()
    machine = "--json" in arguments or "--format" in arguments and "geojson" in arguments
    payload = json.loads(text) if machine and text else {}
    return code, payload, stderr.getvalue()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def check_provenance_contract() -> None:
    code, payload, stderr = invoke(list(DATA_COMMAND))
    require(code == 0 and stderr == "", stderr)
    meta = payload["meta"]
    require(meta["source_url"].startswith("https://portal.opentopography.org/API/otCatalog?"), meta["source_url"])
    require("detail=true" not in meta["source_url"], "catalogue requested detailed geometry")
    require(meta["publisher"] == "OpenTopography", "publisher changed")
    require("licence" not in meta, "catalogue licence was invented")
    require(meta["retrieved_at"].endswith("Z"), "retrieved_at was not UTC")
    retrieved = datetime.fromisoformat(meta["retrieved_at"].replace("Z", "+00:00"))
    require(retrieved.utcoffset() == timedelta(0), "retrieved_at was not UTC")
    require(isinstance(payload["results"], list) and payload["results"], "catalogue fixture was empty")
    require("error" not in payload, "success payload contained error")

    code, payload, stderr = invoke(["--thecolab-invalid-option", "--json"])
    require(code == 2 and stderr == "", stderr)
    require(payload["results"] == [] and payload["error"]["type"] == "invalid_input", payload)

    meta = provenance("https://example.invalid/data", "Fixture publisher")
    require("licence" not in meta and "latest_data" not in meta, "unknown licence was invented")
    cached = provenance(
        "https://example.invalid/data",
        "Fixture publisher",
        licence="Fixture terms",
        latest_data="2026-09",
        retrieved_at="2026-10-01T01:02:03Z",
    )
    require(cached["licence"] == "Fixture terms" and cached["latest_data"] == "2026-09", "cached facts changed")
    require(cached["retrieved_at"] == "2026-10-01T01:02:03Z", "cached retrieval time changed")
    normalised = provenance(
        "https://example.invalid/data",
        "Fixture publisher",
        retrieved_at="2026-10-01T14:02:03+13:00",
    )
    require(normalised["retrieved_at"] == "2026-10-01T01:02:03Z", "offset was not normalised to Z")
    try:
        provenance("https://example.invalid/data", "Fixture publisher", retrieved_at="2026-10-01T01:02:03")
    except ValueError:
        pass
    else:
        raise AssertionError("naive retrieval timestamp accepted")
    require(result_envelope([], cached)["results"] == [], "empty envelope dropped results")
    failure = error_envelope(4, "rate-limited", meta, retry_after="60")
    require(failure["error"]["type"] == "blocked" and failure["error"]["retry_after"] == "60", "retry_after dropped")
    require(parse_bbox("174,-37,175,-36") == (174.0, -37.0, 175.0, -36.0), "bbox parser changed")
    for invalid in (
        "174,-37,175", "a,b,c,d", "nan,-37,175,-36", "174,-37,inf,-36",
        "175,-37,174,-36", "174,-36,175,-37", "-181,-37,175,-36",
        "174,-91,175,-36", "174,-37,181,-36", "174,-37,175,91", "174,-37,174,-36",
    ):
        try:
            parse_bbox(invalid)
        except argparse.ArgumentTypeError:
            pass
        else:
            raise AssertionError(f"invalid bbox accepted: {invalid}")
    parser = argparse.ArgumentParser()
    add_spatial_arguments(parser)
    args = parser.parse_args(["--bbox", "174,-37,175,-36", "--format", "geojson"])
    require(args.bbox == (174.0, -37.0, 175.0, -36.0) and args.format == "geojson", "spatial args changed")
    require(parser.parse_args(["--bbox=-180,-90,180,90"]).bbox == (-180.0, -90.0, 180.0, 90.0), "negative bbox split")
    collection = geojson_envelope([], meta)
    require(collection == {"type": "FeatureCollection", "features": [], "meta": meta}, "geojson envelope changed")


def check_parser_contracts() -> None:
    code, payload, stderr = invoke(list(DATA_COMMAND))
    require(code == 0 and stderr == "", "catalogue fixture failed")
    require(payload["page"]["matched"] == 2 and payload["page"]["returned"] == 2, payload["page"])
    require(payload["results"][0]["alternate_name"] == "NZ24_Fixture", "first collection changed")
    doi = payload["results"][0]["doi"]
    require(doi.endswith("/10.0000/fixture.harbour") and "doi.org" in doi, "doi dropped")
    require(payload["results"][1]["name"] == "Fixture Wānaka Ridge", "HTML entity was not decoded")
    require(all("raster" not in record["name"].lower() for record in payload["results"]), "raster was returned")
    require(any("skipped 1 non-point-cloud" in item for item in payload["warnings"]), payload["warnings"])
    require(any("licence is not in the catalogue" in item for item in payload["warnings"]), payload["warnings"])
    require("fixture: catalog-ok" in payload["warnings"][0], "fixture was presented as live")

    code, payload, _stderr = invoke(
        ["collections", "--bbox", "174.7,-36.9,174.8,-36.8", "--offset", "1", "--limit", "1", "--fixture", "catalog-ok", "--json"]
    )
    require(code == 0 and payload["page"]["returned"] == 1, "offset slice failed")
    require(payload["results"][0]["opentopo_id"] == "OTLAS.042025.2193.8", "offset selected the wrong row")
    require(payload["page"]["truncated"] is False, "last slice was marked truncated")

    code, payload, stderr = invoke(["info", CC_ID, "--fixture", "dataset-cc-by", "--json"])
    require(code == 0 and stderr == "", stderr)
    record = payload["results"][0]
    require(record["licence"] == "CC-BY-4.0" and record["reusable"] is True, record)
    require(record["prefix"] == "NZ24_Fixture/", record["prefix"])
    require([round(value, 2) for value in record["bbox"]] == [174.7, -36.9, 174.8, -36.8], record.get("bbox"))
    require(payload["meta"]["latest_data"] == "2024-03-04", "latest_data was not the capture end")
    require(payload["meta"]["licence"] == "CC-BY-4.0", "info licence missing")

    code, payload, _stderr = invoke(["info", CC_ID, "--fixture", "dataset-cc-by", "--format", "geojson"])
    require(code == 0 and payload["type"] == "FeatureCollection", payload)
    feature = payload["features"][0]
    require(feature["geometry"]["type"] == "Polygon", feature["geometry"])
    first = feature["geometry"]["coordinates"][0][0]
    require([round(value, 2) for value in first] == [174.7, -36.9], "geojson was not longitude, latitude")
    require(payload["meta"]["licence"] == "CC-BY-4.0", "geojson dropped the licence")

    code, payload, stderr = invoke(["files", CC_ID, "--limit", "2", "--fixture", "files-cc-by", "--json"])
    require(code == 0 and stderr == "", stderr)
    require(len(payload["results"]) == 2, payload["results"])
    laz = payload["results"][1]
    require(laz["key"] == "NZ24_Fixture/tile.laz" and laz["size_bytes"] == 40, laz)
    require(laz["url"] == "https://opentopography.s3.sdsc.edu/pc-bulk/NZ24_Fixture/tile.laz", laz["url"])
    require(payload["page"]["truncated"] is True and payload["page"]["next_page"] == "FixturePageTwo", payload["page"])
    require(payload["meta"]["source_url"].startswith("https://opentopography.s3.sdsc.edu/pc-bulk?"), payload["meta"])
    require("max-keys=2" in payload["meta"]["source_url"], "list limit was not sent")
    require(any("not downloaded" in item for item in payload["warnings"]), payload["warnings"])

    code, payload, _stderr = invoke(
        ["files", CC_ID, "--limit", "2", "--suffix", "laz", "--fixture", "files-cc-by", "--json"]
    )
    require(code == 0 and len(payload["results"]) == 1 and payload["results"][0]["suffix"] == ".laz", payload["results"])

    code, payload, stderr = invoke(["files", REFUSED_ID, "--fixture", "files-not-provided", "--json"])
    require(code == 7 and payload["error"]["type"] == "unsupported_operation", payload)
    require("Not-Provided" in payload["error"]["message"], payload["error"]["message"])
    require(payload["results"] == [], "refused listing returned files")
    rendered = json.dumps(payload)
    require("tile.laz" not in rendered and "opentopography.s3.sdsc.edu" not in rendered, rendered)
    require("Traceback" not in stderr, stderr)

    code, payload, _stderr = invoke(["info", REFUSED_ID, "--fixture", "dataset-not-provided", "--json"])
    require(code == 0 and payload["results"][0]["reusable"] is False, "unstated licence was marked reusable")
    require(payload["results"][0]["licence"] == "Not-Provided", payload["results"][0])

    code, payload, _stderr = invoke(["info", CC_ID, "--fixture", "dataset-not-found", "--json"])
    require(code == 0 and payload["results"] == [], "missing dataset was not an empty success")
    require(any("dataset_not_found" in item for item in payload["warnings"]), payload.get("warnings"))

    code, payload, _stderr = invoke(["files", CC_ID, "--fixture", "dataset-not-found", "--json"])
    require(code == 7 and "not found" in payload["error"]["message"], payload)


def check_negative_contracts() -> None:
    cases = (
        (["collections", "--bbox", "10,10,12,12", "--json"], 2, "invalid_input"),
        (["collections", "--bbox", "174,-37,175,-36", "--limit", "51", "--json"], 2, "invalid_input"),
        (["files", "not-an-id", "--json"], 2, "invalid_input"),
        (["files", CC_ID, "--page", "https://off-host.invalid/x", "--json"], 2, "invalid_input"),
        (["collections", "--bbox", "174,-37,175,-36", "--fixture", "catalog-malformed", "--json"], 6, "schema_failure"),
        (["collections", "--bbox", "174,-37,175,-36", "--fixture", "transport-timeout", "--json"], 5, "upstream_unavailable"),
        (["collections", "--bbox", "174,-37,175,-36", "--fixture", "transport-rate-limit", "--json"], 4, "blocked"),
        (["collections", "--bbox", "174,-37,175,-36", "--fixture", "transport-unavailable", "--json"], 5, "upstream_unavailable"),
        (["collections", "--bbox", "174,-37,175,-36", "--fixture", "transport-off-host", "--json"], 7, "unsupported_operation"),
        (["files", CC_ID, "--fixture", "files-outside-prefix", "--json"], 6, "schema_failure"),
        (["files", CC_ID, "--fixture", "files-doctype", "--json"], 6, "schema_failure"),
        (["files", CC_ID, "--fixture", "files-off-host", "--json"], 7, "unsupported_operation"),
    )
    for arguments, expected, error_type in cases:
        code, payload, stderr = invoke(arguments)
        require(code == expected and payload["error"]["type"] == error_type, f"{arguments} -> {code} {payload}")
        require("Traceback" not in stderr and "Traceback" not in json.dumps(payload), arguments)
        require(payload["results"] == [], arguments)

    code, payload, _stderr = invoke(
        ["collections", "--bbox", "174,-37,175,-36", "--fixture", "transport-rate-limit", "--json"]
    )
    require(payload["error"]["retry_after"] == "30", "retry_after was dropped")
    require("<html>" not in json.dumps(payload), "upstream HTML leaked into the error")

    code, payload, _stderr = invoke(
        ["collections", "--bbox", "174,-37,175,-36", "--fixture", "transport-unavailable", "--json"]
    )
    require("busy" not in json.dumps(payload), "HTTP 503 body leaked")

    try:
        cli.parse_catalog(
            {
                "Datasets": [
                    {
                        "Dataset": {
                            "name": "Ok",
                            "identifier": {"value": CC_ID},
                            "alternateName": "bad/name",
                            "fileFormat": "Point Cloud Data",
                        }
                    }
                ]
            }
        )
    except cli.SchemaError:
        pass
    else:
        raise AssertionError("slash prefix was accepted")

    naked = """<?xml version="1.0"?><ListBucketResult>
<Name>pc-bulk</Name><Prefix>NZ24_Fixture/</Prefix><IsTruncated>true</IsTruncated>
<Contents><Key>NZ24_Fixture/tile.laz</Key><Size>4</Size></Contents>
</ListBucketResult>"""
    try:
        cli.parse_listing(naked, "NZ24_Fixture/", 5)
    except cli.SchemaError:
        pass
    else:
        raise AssertionError("truncated listing without a next page was accepted")

    url = cli.list_url("NZ24_Fixture/", 5, None)
    require(url.startswith("https://opentopography.s3.sdsc.edu/pc-bulk?"), url)
    require("max-keys=5" in url and "NZ24_Fixture" in url, url)
    require("/NZ24_Fixture/" not in urllib_path(url), "list URL used an object path")
    cli.assert_allowed_url(url, "listing")
    try:
        cli.assert_allowed_url(cli.asset_url("NZ24_Fixture/tile.laz"), "listing")
    except cli.UnsafeError:
        pass
    else:
        raise AssertionError("object URL was accepted as a listing request")

    calls: list[str] = []

    def boom(url: str, **_kwargs: object) -> tuple[bytes, str, str]:
        calls.append(url)
        raise AssertionError(url)

    original = cli.nzfetch.fetch_bytes
    cli.nzfetch.fetch_bytes = boom
    try:
        code, _payload, stderr = invoke(["files", REFUSED_ID, "--fixture", "files-not-provided", "--json"])
    finally:
        cli.nzfetch.fetch_bytes = original
    require(code == 7 and calls == [], f"refused listing called the network: {calls} {stderr}")


def urllib_path(url: str) -> str:
    import urllib.parse

    return urllib.parse.urlparse(url).path


def main() -> int:
    result = audit_skill(Path(__file__).resolve().parents[1])
    if result["ok"]:
        check_provenance_contract()
        check_parser_contracts()
        check_negative_contracts()
        result["checks"].extend(("provenance", "parser_fixtures", "negative_fixtures"))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
