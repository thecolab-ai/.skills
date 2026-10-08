#!/usr/bin/env python3
"""Deterministic spatial checks using a captured public CAS response."""
import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
from unittest.mock import patch


def run_spatial_tests():
    root = Path(__file__).resolve().parents[1]
    fixture = json.loads((root / "tests/fixtures/spatial.json").read_text())
    spec = importlib.util.spec_from_file_location("cas_spatial_cli", root / "scripts/cli.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    calls = []

    def request(url, params=None, **kwargs):
        calls.append((url, copy.deepcopy(params)))
        if url == module.ARCGIS_LAYER:
            return copy.deepcopy(fixture["metadata"])
        if params.get("returnCountOnly") == "true":
            return copy.deepcopy(fixture["count"])
        response = copy.deepcopy(fixture["response"])
        offset, size = int(params["resultOffset"]), int(params["resultRecordCount"])
        response["features"] = response["features"][offset:offset + size]
        return response

    def run(argv, expect=0):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                module.main(argv)
                code = 0
            except SystemExit as exc:
                code = exc.code
        assert code == expect, (argv, code, err.getvalue())
        assert "Traceback" not in err.getvalue()
        return json.loads(out.getvalue()) if code == 0 else err.getvalue()

    common = ["crashes", "--from", "2025-01-01", "--to", "2025-12-31", "--limit", "3", "--json"]
    with patch.object(module, "request_json", request), patch.object(module, "PAGE_SIZE", 2):
        data = run(common + ["--bbox", fixture["bbox"], "--format", "geojson"])
        assert data["type"] == "FeatureCollection" and len(data["features"]) == 3
        assert data["total_matching"] == fixture["count"]["count"]
        first = data["features"][0]
        assert first["id"] == fixture["response"]["features"][0]["attributes"]["OBJECTID"]
        assert first["geometry"]["coordinates"] == [fixture["response"]["features"][0]["geometry"]["x"], fixture["response"]["features"][0]["geometry"]["y"]]
        assert first["properties"]["publisher"] == data["publisher"]
        assert data["licence"] == "CC BY 4.0" and data["retrieved_at"].endswith("Z") and data["latest_data"].endswith("Z")
        query_calls = [params for url, params in calls if url == module.ARCGIS_QUERY]
        assert len(query_calls) == 3
        assert all(p["geometryType"] == "esriGeometryEnvelope" and p["inSR"] == "4326" for p in query_calls)
        assert [p["resultOffset"] for p in query_calls if "resultOffset" in p] == ["0", "2"]
        print("[PASS] fixture CAS bbox count, paging, WGS84 GeoJSON and provenance")

        calls.clear()
        nearby = run(common + ["--near", "174.740,-36.890", "--radius", "500"])
        assert nearby["records"] and nearby["spatial_filter"]["distance"] == 500
        assert all(p["units"] == "esriSRUnit_Meter" for u, p in calls if u == module.ARCGIS_QUERY)
        legacy = run(common + ["--source", "arcgis"])
        assert legacy["kind"] == "crashes" and legacy["records"][0]["object_id"] == first["id"]
        assert "spatial_filter" not in legacy and "geometry" not in legacy["records"][0]
        print("[PASS] fixture CAS server distance filter and legacy record envelope")

        for args in (["--bbox", "174,-36,173,-35"], ["--bbox", "nan,-36,175,-35"],
                     ["--radius", "500"], ["--near", "174,-36", "--radius", "inf"],
                     ["--bbox", fixture["bbox"], "--source", "csv"]):
            run(common + args, 2)
        print("[PASS] contract CAS spatial validation fails cleanly")

    def unavailable(*args, **kwargs):
        raise module.DataError("network error: unavailable")

    with patch.object(module, "arcgis_query", unavailable), patch.object(module, "request_csv_rows", side_effect=AssertionError("spatial CSV fallback")):
        assert "network error" in run(common + ["--bbox", fixture["bbox"]], 1)
    print("[PASS] contract CAS spatial outages cannot return unfiltered CSV results")


if __name__ == "__main__":
    run_spatial_tests()
