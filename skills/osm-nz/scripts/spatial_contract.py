#!/usr/bin/env python3
"""Deterministic tag-query checks using captured public OSM fences."""
import contextlib
import copy
import importlib.util
import io
import json
import sys
from pathlib import Path
from unittest.mock import patch


def run_spatial_tests():
    root = Path(__file__).resolve().parents[1]
    fixture = json.loads((root / "tests/fixtures/spatial.json").read_text())
    spec = importlib.util.spec_from_file_location("osm_spatial_cli", root / "scripts/cli.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    queries = []

    def fetch(query):
        queries.append(query)
        return copy.deepcopy(fixture["response"])

    def run(argv, expect=0):
        out, err = io.StringIO(), io.StringIO()
        with patch.object(sys, "argv", ["cli.py", *argv]), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                module.main()
                code = 0
            except SystemExit as exc:
                code = exc.code
        assert code == expect, (argv, code, err.getvalue())
        assert "Traceback" not in err.getvalue()
        return json.loads(out.getvalue()) if code == 0 else err.getvalue()

    common = ["query", "--bbox", fixture["bbox"], "--tag", "barrier=fence", "--limit", "2", "--json"]
    with patch.object(module, "fetch_overpass", fetch):
        data = run(common)
        assert data["count"] == 2 and data["truncated"] is True
        assert data["records"][0]["osm_id"] == fixture["response"]["elements"][0]["id"]
        assert data["records"][0]["tags"] == {"barrier": "fence"}
        assert data["latest_data"] == fixture["response"]["osm3s"]["timestamp_osm_base"]
        assert data["records"][0]["licence"] == "ODbL 1.0" and data["retrieved_at"].endswith("Z")
        assert 'nwr["barrier"="fence"](-36.905,174.735,-36.875,174.745)' in queries[-1]
        assert "out center tags 3;" in queries[-1]
        geojson = run(common + ["--format", "geojson"])
        assert geojson["type"] == "FeatureCollection" and len(geojson["features"]) == 2
        assert geojson["features"][0]["geometry"]["coordinates"] == [data["records"][0]["lon"], data["records"][0]["lat"]]
        run(common + ["--tag", "repair=*"])
        assert '["barrier"="fence"]["repair"]' in queries[-1]
        run(["query", "--area", "3602094141", "--tag", "amenity=recycling", "--json"])
        assert "area(3602094141)->.searchArea" in queries[-1] and "(area.searchArea)" in queries[-1]
        print("[PASS] fixture OSM unnamed tags, bbox/area filters, wildcard, truncation and GeoJSON")
        for args in (["--tag", 'amenity"];', "--bbox", fixture["bbox"]],
                     ["--tag", "shop=", "--bbox", fixture["bbox"]],
                     ["--tag", "repair=*", "--bbox", "nan,-36,175,-35"],
                     ["--tag", "repair=*", "--bbox", "174,-36,173,-35"],
                     ["--tag", "repair=*", "--bbox", fixture["bbox"], "--limit", "101"]):
            run(["query", *args], 2)
        escaped = module.build_tag_query([("name", 'x";out;\\')], module.bbox_value(fixture["bbox"]), None, 2)
        assert '["name"="x\\\";out;\\\\"]' in escaped
        print("[PASS] contract OSM invalid inputs and QL literal escaping")

    captured = {}
    def network(url, **kwargs):
        captured.update(kwargs)
        return copy.deepcopy(fixture["response"])
    with patch.object(module.nzfetch, "fetch_json", network):
        assert module.fetch_overpass("query")["elements"]
    assert captured["timeout"] == 10 and captured["max_bytes"] == 8 * 1024 * 1024
    for incomplete in ({"elements": [], "remark": "runtime error: Query timed out"}, {"error": "bad schema"}):
        with patch.object(module.nzfetch, "fetch_json", return_value=incomplete), contextlib.redirect_stderr(io.StringIO()):
            try:
                module.fetch_overpass("query")
                raise AssertionError("incomplete response was accepted")
            except SystemExit as exc:
                assert exc.code != 0
    print("[PASS] contract OSM timeout, byte cap and incomplete-source errors")


if __name__ == "__main__":
    run_spatial_tests()
