#!/usr/bin/env python3
"""Deterministic STAC fixtures and bounded live Auckland checks."""
from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
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
    for url in ("https://example.invalid/collection.json", "https://nz-elevation.s3.ap-southeast-2.amazonaws.com/catalog.json?token=x", "http://nz-elevation.s3.ap-southeast-2.amazonaws.com/catalog.json"):
        try:
            cli.safe_url(url)
        except cli.SourceError:
            pass
        else:
            raise AssertionError("unsafe URL accepted")
    check(True, "foreign, non-HTTPS and query-bearing URLs rejected")
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

    for kind in cli.ROOTS:
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
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
