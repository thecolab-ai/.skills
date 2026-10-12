#!/usr/bin/env python3
"""Deterministic STAC fixtures and bounded live Auckland checks."""
from __future__ import annotations

import argparse
import copy
import io
import json
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener

import cli

SKILL_DIR = Path(__file__).resolve().parents[1]
BBOX = [174.715, -36.905, 174.725, -36.895]
DEM = "elevation:auckland/auckland-part-1_2024/dem_1m/2193"
DSM = "elevation:auckland/auckland-part-1_2024/dsm_1m/2193"
OLD_DEM = "elevation:auckland/auckland-north_2016-2018/dem_1m/2193"
PART2_DEM = "elevation:auckland/auckland-part-2_2024/dem_1m/2193"
PART2_DSM = "elevation:auckland/auckland-part-2_2024/dsm_1m/2193"
RGB = "imagery:auckland/auckland_2024_0.075m/rgb/2193"
NIR = "imagery:auckland/auckland_2024_0.075m/rgbnir/2193"
COASTAL = "coastal:auckland/mangawhai-to-snells_2025/dem_1m/2193"
COASTAL_BBOX = [174.59, -36.01, 174.60, -36.00]
PROVENANCE = {"source_url", "publisher", "licence", "retrieved_at", "latest_data"}


def fixture_checks():
    samples = json.loads((SKILL_DIR / "tests/fixtures/stac-samples.json").read_text())
    responses = samples["responses"]
    passed = []

    def check(condition, name):
        if not condition:
            raise AssertionError(name)
        passed.append(name)

    def offline(url):
        if url not in responses:
            raise AssertionError(f"Fixture fetch escaped bounded captured responses: {url}")
        return copy.deepcopy(responses[url])

    with patch.object(cli, "fetch_json", side_effect=offline):
        check(cli.parse_bbox("174.715,-36.905,174.725,-36.895") == BBOX, "WGS84 bbox order")
        for bad in ("1,2,3", "180,0,179,1", "174,nan,175,1", "174,-91,175,0"):
            try:
                cli.parse_bbox(bad)
            except argparse.ArgumentTypeError:
                pass
            else:
                raise AssertionError(f"Accepted invalid bbox {bad}")
        check(True, "malformed, reversed and non-finite bbox rejected")
        records = cli.list_collections("imagery", "auckland")["collections"]
        check(any(r["collection"] == NIR and r["product"] == "infrared" and r["resolution_m"] == .075 and r["year"] == "2024-2025" for r in records), "catalogue infrared product, 7.5 cm and title capture years")
        listing = cli.list_collections("elevation", "auckland", limit=1, offset=1)
        check(listing["count"] == 1 and listing["truncated"] and PROVENANCE <= listing.keys() and PROVENANCE <= listing["collections"][0].keys(), "bounded catalogue paging and provenance")
        url = cli.collection_url(DEM)
        summary = cli.collection_summary(offline(url), url)
        check(summary["stac_id"] == "01JRGSXQ85EGQ0H6N7JHFP320Z" and summary["licence"] == "CC-BY-4.0" and summary["latest_data"] == "2024-06-26T12:00:00Z", "collection licence, published STAC id and capture end")
        check(cli.collection_url(url) == url and cli.selector(url) == DEM, "collection HTTPS URL and selector round trip")
        bounds = cli.grid_bounds("BA31_10000_0505")
        check(bounds == [1751200, 5910000, 1756000, 5917200], "published Topo50 grid subtile bounds")
        item_url = cli.urljoin(url, "BA31_10000_0505.json")
        ring = responses[item_url]["geometry"]["coordinates"][0]
        transformed = [cli.nztm(*p) for p in ring]
        expected = [(bounds[0], bounds[3]), (bounds[0], bounds[1]), (bounds[2], bounds[1]), (bounds[2], bounds[3]), (bounds[0], bounds[3])]
        check(all(abs(p[0]-q[0]) < .1 and abs(p[1]-q[1]) < .1 for p, q in zip(transformed, expected)), "projection agrees with captured STAC vertices within 10 cm")
        tiles = cli.find_tiles(DEM, BBOX)
        check(tiles["count"] == 1 and tiles["tiles"][0]["id"] == "BA31_10000_0505" and tiles["items_inspected"] == 1, "DEM bbox selects one captured tile without crawling distant items")
        tile = tiles["tiles"][0]
        check(PROVENANCE <= tile.keys() and PROVENANCE <= tile["cog_assets"][0].keys() and tile["cog_assets"][0]["url"].endswith("BA31_10000_0505.tiff"), "relative COG URL resolution and record/asset provenance")
        old = cli.find_tiles(OLD_DEM, BBOX)
        check(old["tiles"][0]["latest_data"] == "2018-08-08T12:00:00Z", "historic DEM capture end retained")
        check(cli.find_tiles(PART2_DEM, BBOX)["count"] == 0, "Part 2 has no tile at Mt Albert")
        imagery = cli.find_tiles(RGB, BBOX, limit=2)
        check(imagery["count"] == 2 and imagery["truncated"] and imagery["items_inspected"] == 3 and imagery["candidates"] == 9, "imagery cap stops after one extra footprint match")
        gj = cli.geojson(imagery)
        check(gj["type"] == "FeatureCollection" and len(gj["features"]) == 2 and gj["features"][0]["geometry"]["type"] == "Polygon" and PROVENANCE <= gj["features"][0]["properties"].keys(), "GeoJSON actual footprints and provenance")
        check(gj["query_bbox"] == BBOX and all(cli.intersects(gj["bbox"], f["bbox"]) for f in gj["features"]), "GeoJSON extent uses returned geometry and preserves query bbox")
        point = cli.point_result(DEM, 174.72, -36.9)
        check(point["sampling_status"] == "sampling_required" and point["elevation"] is None and "-wgs84 /vsicurl/" in point["tiles"][0]["gdal_command"], "point fallback returns range-read GDAL command without a claimed value")
        check(cli.geojson(point)["features"][0]["geometry"]["coordinates"] == [174.72, -36.9], "point GeoJSON coordinate order")
        try:
            cli.point_result(RGB, 174.72, -36.9)
        except cli.SourceError as exc:
            check(exc.code == 2, "point rejects imagery before sampling")
        else:
            raise AssertionError("point accepted imagery")
        # A narrow bbox can intersect the envelope while missing the rotated tile.
        check(not cli.geometry_hits_bbox(tile["geometry"], [174.69658,-36.9439372,174.6966,-36.9439]), "footprint filtering removes envelope-only matches")
        polygon = {"type": "Polygon", "coordinates": [[[0,0],[4,0],[4,4],[0,4],[0,0]], [[1,1],[3,1],[3,3],[1,3],[1,1]]]}
        check(not cli.geometry_hits_bbox(polygon, [1.5,1.5,2,2]) and cli.geometry_hits_bbox(polygon, [-1,1,.5,2]), "polygon holes and crossing edges handled")
        bad_item = copy.deepcopy(responses[item_url]); bad_item["assets"] = {}
        try:
            cli.tile_record(bad_item, item_url, summary)
        except cli.SourceError as exc:
            check(exc.code == 6, "missing COG asset fails as schema error")
        else:
            raise AssertionError("missing COG asset accepted")
        with patch.object(cli, "MAX_CANDIDATES", 1):
            try:
                cli.find_tiles(RGB, BBOX)
            except cli.SourceError as exc:
                check(exc.code == 7 and "smaller bbox" in str(exc), "oversized candidate set fails before item retrieval")
            else:
                raise AssertionError("candidate cap ignored")
        coastal_list = cli.list_collections("coastal", "auckland")
        check(any(r["collection"] == COASTAL and r["product"] == "DEM" and r["resolution_m"] == 1 and r["year"] == "2025" and r["licence"] is None for r in coastal_list["collections"]), "coastal catalogue lists the contracted DEM and leaves licence unset")
        coastal_page = cli.list_collections("coastal", limit=1)
        check(coastal_page["count"] == 1 and coastal_page["matched"] == 2 and coastal_page["truncated"] and PROVENANCE <= coastal_page.keys(), "coastal catalogue page is bounded")
        coastal_url = cli.collection_url(COASTAL)
        coastal_summary = cli.collection_summary(offline(coastal_url), coastal_url)
        check(coastal_summary["licence"] == "CC-BY-4.0" and coastal_summary["latest_data"] == "2025-03-15T11:00:00Z" and coastal_summary["stac_id"] == "01KGZEQTHQ02B1ZJS35F1WFBCG" and cli.selector(coastal_url) == COASTAL, "coastal collection licence, published capture end and STAC id")
        coastal_tiles = cli.find_tiles(COASTAL, COASTAL_BBOX)
        coastal_tile = coastal_tiles["tiles"][0]
        check(coastal_tiles["count"] == 1 and coastal_tiles["items_inspected"] == 1 and coastal_tile["id"] == "AY31_10000_0103" and coastal_tile["cog_assets"][0]["url"].endswith("/AY31_10000_0103.tiff") and coastal_tile["licence"] == "CC-BY-4.0", "coastal bbox returns one COG href without a raster fetch")
        check(cli.find_tiles(COASTAL, BBOX)["count"] == 0, "coastal bbox outside the fixture tile is an empty result")
        try:
            cli.point_result(COASTAL, 174.595, -36.005)
        except cli.SourceError as exc:
            check(exc.code == 2, "point rejects a coastal collection")
        else:
            raise AssertionError("point accepted a coastal collection")
    hillshade = cli.title_fields("New Zealand Coastal DEM Hillshade", "https://nz-coastal.s3.ap-southeast-2.amazonaws.com/new-zealand/new-zealand/dem-hillshade/2193/collection.json")
    check(hillshade["product"] == "unknown", "coastal hillshade path is not labelled DEM")
    for url in ("https://example.invalid/collection.json", "https://nz-elevation.s3.ap-southeast-2.amazonaws.com/catalog.json?token=x", "http://nz-elevation.s3.ap-southeast-2.amazonaws.com/catalog.json", "https://nz-coastal.s3.ap-southeast-2.amazonaws.com/catalog.json?X-Amz-Signature=abc"):
        try:
            cli.safe_url(url)
        except cli.SourceError:
            pass
        else:
            raise AssertionError("unsafe URL accepted")
    check(True, "foreign, non-HTTPS and query-bearing URLs rejected")

    def opener_raising(exc):
        class Opener:
            def open(self, request, timeout=None):
                if timeout != 10:
                    raise AssertionError(f"timeout was {timeout}")
                raise exc
        return Opener()

    cli.fetch_json.cache_clear()
    with patch.object(cli, "build_opener", return_value=opener_raising(URLError("down"))):
        try:
            cli.fetch_json(cli.ROOTS["coastal"])
        except cli.SourceError as exc:
            check(exc.code == 5 and str(exc).startswith("network error:"), "coastal outage is an upstream error")
        else:
            raise AssertionError("coastal outage returned a document")
    cli.fetch_json.cache_clear()
    with patch.object(cli, "build_opener", return_value=opener_raising(TimeoutError("slow"))):
        try:
            cli.fetch_json(cli.ROOTS["coastal"])
        except cli.SourceError as exc:
            check(exc.code == 5, "coastal timeout is an upstream error")
        else:
            raise AssertionError("coastal timeout returned a document")
    cli.fetch_json.cache_clear()
    rate_error = HTTPError(cli.ROOTS["coastal"], 429, "rate", {"Retry-After": "12"}, None)
    with patch.object(cli, "build_opener", return_value=opener_raising(rate_error)):
        try:
            cli.fetch_json(cli.ROOTS["coastal"])
        except cli.SourceError as exc:
            check(exc.code == 4 and exc.retry_after == "12", "coastal rate limit keeps Retry-After")
        else:
            raise AssertionError("rate limit returned a document")

    class BytesOpener:
        def __init__(self, payload):
            self.payload = payload

        def open(self, request, timeout=None):
            body = self.payload

            class Response:
                def read(self, _n):
                    return body

                def __enter__(self):
                    return self

                def __exit__(self, *_args):
                    return False

            return Response()

    for payload, name in ((b"[]", "coastal JSON array is a schema error"), (b"{", "truncated coastal JSON is a schema error")):
        cli.fetch_json.cache_clear()
        with patch.object(cli, "build_opener", return_value=BytesOpener(payload)):
            try:
                cli.fetch_json(cli.ROOTS["coastal"])
            except cli.SourceError as exc:
                check(exc.code == 6, name)
            else:
                raise AssertionError(name)
    cli.fetch_json.cache_clear()
    with patch.object(cli, "MAX_JSON_BYTES", 8), patch.object(cli, "build_opener", return_value=BytesOpener(b'{"type":"Catalog","links":[]}')):
        try:
            cli.fetch_json(cli.ROOTS["coastal"])
        except cli.SourceError as exc:
            check(exc.code == 7 and "limit" in str(exc), "oversized coastal JSON is rejected")
        else:
            raise AssertionError("oversized JSON accepted")

    def empty_catalog(url):
        if url != cli.ROOTS["coastal"]:
            raise AssertionError(url)
        return {"type": "Catalog", "id": "nz-coastal", "links": []}

    with patch.object(cli, "fetch_json", side_effect=empty_catalog):
        empty = cli.list_collections("coastal")
    check(empty["matched"] == 0 and empty["count"] == 0 and empty["collections"] == [] and empty["truncated"] is False, "empty coastal catalogue is an empty page")

    def missing_links(url):
        return {"type": "Catalog", "id": "nz-coastal"}

    with patch.object(cli, "fetch_json", side_effect=missing_links):
        try:
            cli.list_collections("coastal")
        except cli.SourceError as exc:
            check(exc.code == 6, "coastal catalogue without links is a schema error")
        else:
            raise AssertionError("missing links accepted")

    stdout, stderr = io.StringIO(), io.StringIO()

    def boom(_url):
        raise cli.SourceError("network error: could not retrieve coastal catalogue", 5)

    with redirect_stdout(stdout), redirect_stderr(stderr), patch.object(sys, "argv", ["cli.py", "collections", "--kind", "coastal", "--limit", "1", "--json"]), patch.object(cli, "fetch_json", side_effect=boom):
        code = cli.main()
    payload = json.loads(stdout.getvalue())
    check(code == 5 and payload["ok"] is False and payload["exit_code"] == 5 and "collections" not in payload, "coastal outage is not an empty catalogue")

    with redirect_stderr(io.StringIO()):
        for arguments in (
            ["collections", "--kind", "coastal", "--limit", "0"],
            ["collections", "--kind", "coastal", "--limit", "201"],
            ["collections", "--kind", "coastal", "--offset=-1"],
            ["tiles", COASTAL, "--bbox", "174.60,-36.00,174.59,-36.01"],
        ):
            try:
                cli.parser().parse_args(arguments)
            except SystemExit as exc:
                if exc.code in (0, None):
                    raise AssertionError(f"accepted out-of-bounds arguments {arguments}")
            else:
                raise AssertionError(f"accepted out-of-bounds arguments {arguments}")
    check(True, "coastal limit, offset and reversed bbox are rejected")
    return passed


def run_cli(arguments, canonical=False):
    invocation = [sys.executable, str(SKILL_DIR.parents[1] / "scripts/run_skill.py"), "nz-stac"] if canonical else [sys.executable, str(SKILL_DIR / "scripts/cli.py")]
    try:
        result = subprocess.run([*invocation, *arguments, "--json"],
                                capture_output=True, text=True, timeout=45)
    except subprocess.TimeoutExpired as exc:
        raise cli.SourceError("network error: live CLI probe timed out after 45 s", 5) from exc
    if result.returncode:
        if result.returncode in (4, 5):
            raise cli.SourceError(result.stderr.strip(), result.returncode)
        raise AssertionError(f"CLI exit {result.returncode}: {result.stderr.strip()}")
    payload = json.loads(result.stdout)
    if canonical:
        assert payload["ok"] is True and payload["schema_version"] == "1"
        return payload["data"]
    return payload


def main():
    failures = 0
    try:
        for name in fixture_checks():
            print(f"[PASS] fixture {name}")
    except (AssertionError, cli.SourceError, KeyError, ValueError) as exc:
        print(f"[FAIL] fixture {exc}")
        return 1

    for kind in ("elevation", "imagery"):
        try:
            result = run_cli(["collections", "--kind", kind, "--region", "auckland"])
            assert result["matched"] >= 8 and result["count"] > 0 and PROVENANCE <= result.keys()
            if kind == "imagery":
                assert {RGB, NIR} <= {r["collection"] for r in result["collections"]}
            else:
                assert {DEM, DSM, OLD_DEM, PART2_DEM, PART2_DSM} <= {r["collection"] for r in result["collections"]}
            print(f"[PASS] live {kind} Auckland catalogue: {result['matched']} collections")
        except cli.SourceError as exc:
            print(f"[SKIP] {exc}")
        except (AssertionError, ValueError, subprocess.TimeoutExpired) as exc:
            print(f"[FAIL] live {kind} catalogue: {exc}"); failures += 1

    first_cog = None
    for collection in (DEM, DSM, OLD_DEM, RGB, NIR):
        try:
            result = run_cli(["tiles", collection, "--bbox", ",".join(map(str,BBOX)), "--format", "geojson", "--limit", "20"])
            features = result["features"]
            assert result["type"] == "FeatureCollection" and features and len(features) <= 20
            assert not result["truncated"] and PROVENANCE <= result.keys()
            assert all(f["geometry"]["type"] in ("Polygon", "MultiPolygon") and f["properties"]["licence"] == "CC-BY-4.0" for f in features)
            if collection == DEM:
                first_cog = features[0]["properties"]["cog_assets"][0]["url"]
            print(f"[PASS] live Mt Albert {collection}: {len(features)} tiles, first={features[0]['id']}, inspected={result['items_inspected']}")
        except cli.SourceError as exc:
            print(f"[SKIP] {collection}: {exc}")
        except (AssertionError, KeyError, ValueError, subprocess.TimeoutExpired) as exc:
            print(f"[FAIL] live {collection}: {exc}"); failures += 1

    for collection in (PART2_DEM, PART2_DSM):
        try:
            result = run_cli(["info", collection])
            assert result["product"] in ("DEM", "DSM") and result["resolution_m"] == 1 and result["year"] == "2024" and result["tile_count"] > 0
            print(f"[PASS] live Part 2 metadata: {result['product']}, {result['tile_count']} tiles")
        except cli.SourceError as exc:
            print(f"[SKIP] {exc}")
        except (AssertionError, KeyError, ValueError, subprocess.TimeoutExpired) as exc:
            print(f"[FAIL] live Part 2 metadata: {exc}"); failures += 1

    try:
        point = run_cli(["point", "--lon", "174.72", "--lat", "-36.9", "--collection", DEM], canonical=True)
        assert point["sampling_status"] == "sampling_required" and point["elevation"] is None and point["tiles"][0]["gdal_command"].startswith("gdallocationinfo -valonly -wgs84 /vsicurl/")
        print(f"[PASS] live canonical runner point fallback: {point['tiles'][0]['id']}")
    except cli.SourceError as exc:
        print(f"[SKIP] {exc}")
    except (AssertionError, KeyError, ValueError, subprocess.TimeoutExpired) as exc:
        print(f"[FAIL] live point fallback: {exc}"); failures += 1

    if first_cog:
        try:
            cli.safe_url(first_cog)
            request = Request(first_cog, headers={"Range": "bytes=0-15", "User-Agent": "TheColab-nz-stac-smoke/1"})
            with build_opener(cli.SafeRedirect()).open(request, timeout=10) as response:
                assert response.status == 206 and response.headers.get("Content-Range", "").startswith("bytes 0-15/")
                header = response.read(17)
            assert len(header) == 16 and header[:4] in (b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+")
            print(f"[PASS] live COG HTTP 206 range: 16 bytes, TIFF header={header[:4].hex()}")
        except (HTTPError, URLError, OSError, TimeoutError) as exc:
            print(f"[SKIP] network error: COG range probe ({type(exc).__name__})")
        except AssertionError:
            print("[FAIL] live COG did not honour a 16-byte TIFF range"); failures += 1
    else:
        print("[SKIP] no live DEM tile available for the COG range probe")

    coastal_cog = None
    try:
        listing = run_cli(["collections", "--kind", "coastal", "--region", "auckland", "--limit", "20"])
        assert 1 <= listing["count"] <= 20 and listing["matched"] >= 1 and PROVENANCE <= listing.keys()
        match = next(row for row in listing["collections"] if row["collection"] == COASTAL)
        assert match["product"] == "DEM" and match["resolution_m"] == 1 and match["year"] == "2025" and match["licence"] is None
        print(f"[PASS] live coastal Auckland catalogue: {listing['matched']} collections")
    except cli.SourceError as exc:
        print(f"[SKIP] {exc}")
    except (AssertionError, KeyError, StopIteration, ValueError, subprocess.TimeoutExpired) as exc:
        print(f"[FAIL] live coastal catalogue: {exc}"); failures += 1

    try:
        bounded = run_cli(["collections", "--kind", "coastal", "--limit", "1"])
        assert bounded["count"] == 1 and bounded["matched"] > bounded["count"] and bounded["truncated"] is True
        print(f"[PASS] live coastal catalogue page: 1 of {bounded['matched']}")
    except cli.SourceError as exc:
        print(f"[SKIP] {exc}")
    except (AssertionError, KeyError, ValueError, subprocess.TimeoutExpired) as exc:
        print(f"[FAIL] live coastal catalogue page: {exc}"); failures += 1

    try:
        info = run_cli(["info", COASTAL])
        assert info["licence"] == "CC-BY-4.0" and info["latest_data"] == "2025-03-15T11:00:00Z"
        assert info["stac_id"] == "01KGZEQTHQ02B1ZJS35F1WFBCG" and info["tile_count"] >= 1
        assert info["source_url"].endswith("/auckland/mangawhai-to-snells_2025/dem_1m/2193/collection.json")
        print(f"[PASS] live coastal collection: licence={info['licence']}, tiles={info['tile_count']}")
    except cli.SourceError as exc:
        print(f"[SKIP] {exc}")
    except (AssertionError, KeyError, ValueError, subprocess.TimeoutExpired) as exc:
        print(f"[FAIL] live coastal collection: {exc}"); failures += 1

    try:
        tiles = run_cli(["tiles", COASTAL, "--bbox", ",".join(map(str, COASTAL_BBOX)), "--format", "geojson", "--limit", "5"])
        features = tiles["features"]
        assert tiles["type"] == "FeatureCollection" and 1 <= len(features) <= 5 and not tiles["truncated"]
        feature = next(item for item in features if item["id"] == "AY31_10000_0103")
        assert feature["geometry"]["type"] in ("Polygon", "MultiPolygon") and feature["properties"]["licence"] == "CC-BY-4.0"
        coastal_cog = feature["properties"]["cog_assets"][0]["url"]
        assert coastal_cog.startswith("https://nz-coastal.s3.ap-southeast-2.amazonaws.com/") and coastal_cog.endswith("/AY31_10000_0103.tiff")
        print(f"[PASS] live coastal tile AY31_10000_0103: COG href only, inspected={tiles['items_inspected']}")
    except cli.SourceError as exc:
        print(f"[SKIP] {exc}")
    except (AssertionError, KeyError, StopIteration, ValueError, subprocess.TimeoutExpired) as exc:
        print(f"[FAIL] live coastal tiles: {exc}"); failures += 1

    if coastal_cog:
        try:
            cli.safe_url(coastal_cog)
            request = Request(coastal_cog, headers={"Range": "bytes=0-15", "User-Agent": "TheColab-nz-stac-smoke/1"})
            with build_opener(cli.SafeRedirect()).open(request, timeout=10) as response:
                assert response.status == 206 and response.headers.get("Content-Range", "").startswith("bytes 0-15/")
                header = response.read(17)
            assert len(header) == 16 and header[:4] in (b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+")
            print(f"[PASS] live coastal COG HTTP 206 range: 16 bytes, TIFF header={header[:4].hex()}")
        except (HTTPError, URLError, OSError, TimeoutError) as exc:
            print(f"[SKIP] network error: coastal COG range probe ({type(exc).__name__})")
        except AssertionError:
            print("[FAIL] live coastal COG did not honour a 16-byte TIFF range"); failures += 1
    else:
        print("[SKIP] no live coastal tile available for the COG range probe")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
