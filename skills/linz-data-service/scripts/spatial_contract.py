#!/usr/bin/env python3
"""Deterministic feature-query checks using captured public LINZ polygons."""
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
    spec = importlib.util.spec_from_file_location("linz_spatial_cli", root / "scripts/cli.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    calls = []

    def fetch(url, params=None):
        calls.append((url, copy.deepcopy(params)))
        for dataset in module.FEATURE_LAYERS:
            source = fixture["datasets"][dataset]
            if url == source["source_url"]:
                return copy.deepcopy(source["metadata"])
            if url == source["source_url"] + "/query":
                if params.get("returnCountOnly") == "true":
                    return copy.deepcopy(source["count"])
                response = copy.deepcopy(source["response"])
                offset, size = params["resultOffset"], params["resultRecordCount"]
                response["features"] = response["features"][offset:offset + size]
                return response
        raise AssertionError(f"unexpected URL {url}")

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

    with patch.object(module, "arcgis_get", fetch), patch.object(module, "PAGE_SIZE", 2):
        for dataset in module.FEATURE_LAYERS:
            calls.clear()
            common = ["features", dataset, "--bbox", fixture["bbox"], "--limit", "3", "--json"]
            data = run(common + ["--format", "geojson"])
            assert data["type"] == "FeatureCollection" and data["returned"] == 3 and data["truncated"]
            assert data["total_matching"] == fixture["datasets"][dataset]["count"]["count"]
            assert data["features"][0]["geometry"] == fixture["datasets"][dataset]["response"]["features"][0]["geometry"]
            assert data["features"][0]["properties"]["publisher"] == "Toitū Te Whenua LINZ"
            assert data["licence"] == "CC BY 4.0" and data["latest_data"].endswith("Z") and data["retrieved_at"].endswith("Z")
            queries = [p for u, p in calls if u.endswith("/query")]
            assert len(queries) == 3 and all(p["geometryType"] == "esriGeometryEnvelope" and p["inSR"] == 4326 for p in queries)
            assert [p["resultOffset"] for p in queries if "resultOffset" in p] == [0, 2]
            normal = run(common)
            assert normal["kind"] == "features" and len(normal["records"]) == 3
            print(f"[PASS] fixture LINZ {dataset} server bbox, paging, GeoJSON and provenance")
        layers = run(["feature-layers", "--json"])
        assert len(layers["layers"]) == 3 and layers["layers"][-1]["status"] == "unsupported"
        assert fixture["datasets"]["directory_services"] == ["LINZ_NZ_Primary_Parcels"]
        assert "not published" in run(["features", "parcels", "--bbox", fixture["bbox"], "--json"], 7)
        print("[PASS] contract LINZ NZ Parcels cannot silently substitute primary parcels")
        for bbox in ("174,-36,173,-35", "nan,-36,175,-35", "174,-36,175", "166,-48,180,-33"):
            run(["features", "primary-parcels", "--bbox", bbox], 2)
        run(["features", "primary-parcels", "--bbox", fixture["bbox"], "--limit", "2001"], 2)
        print("[PASS] contract LINZ bounded inputs fail cleanly")

    with patch.object(module.nzfetch, "fetch_json", return_value={"error": {"message": "Invalid URL", "details": []}}), contextlib.redirect_stderr(io.StringIO()):
        try:
            module.arcgis_get(module.MIRROR)
            raise AssertionError("ArcGIS error was accepted")
        except SystemExit as exc:
            assert exc.code == 5
    with patch.object(module, "arcgis_get", side_effect=[fixture["datasets"]["primary-parcels"]["metadata"], fixture["datasets"]["primary-parcels"]["count"], {"type": "FeatureCollection", "features": []}]):
        run(["features", "primary-parcels", "--bbox", fixture["bbox"], "--json"], 6)
    print("[PASS] contract LINZ ArcGIS errors and missing feature pages fail explicitly")


if __name__ == "__main__":
    run_spatial_tests()
