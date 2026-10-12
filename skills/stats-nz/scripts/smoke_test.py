#!/usr/bin/env python3
import json
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent
CLI = SKILL_DIR / "scripts" / "cli.py"


def run(args: list) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CLI)] + args,
        capture_output=True,
        text=True,
        cwd=str(SKILL_DIR),
        timeout=30,
    )


def test(name: str, fn):
    try:
        ok = fn()
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {name}")
        return ok
    except Exception as e:
        print(f"[FAIL] {name}")
        print(f"  error: {e}")
        return False


results = []


def test_series_row_fixture():
    import importlib.util

    spec = importlib.util.spec_from_file_location("stats_nz_cli", CLI)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    record = module.serialize_series_row(
        {
            "Period": "2026Q2",
            "Data_value": "123.45",
            "STATUS": "F",
            "UNITS": "Index",
            "MAGNITUDE": "0",
            "Series_title_1": "Synthetic series",
            "Series_title_2": "All groups",
        }
    )
    assert record["period"] == "2026Q2"
    assert record["value"] == 123.45
    assert record["magnitude"] == 0
    assert record["series_title"] == "Synthetic series - All groups"
    assert module.normalize_region("Wellington Region") == "wellington-region"
    print("[PASS] fixture Stats NZ CSV series-row normalisation")
    return True


results.append(test("fixture Stats NZ series parser", test_series_row_fixture))


def test_help():
    result = run(["--help"])
    return result.returncode == 0


results.append(test("--help exits 0", test_help))


def test_cpi():
    result = run(["cpi", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("latest"), dict):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected latest{} in cpi response")
        return False
    if data["latest"].get("value") is None:
        print("  Expected latest.value to be set")
        return False
    return True


results.append(test("live cpi returns latest.value", test_cpi))


def test_fpi():
    result = run(["fpi", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("latest"), dict):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected latest{} in fpi response")
        return False
    if data["latest"].get("value") is None:
        print("  Expected latest.value to be set")
        return False
    return True


results.append(test("live fpi returns latest.value", test_fpi))


def test_population():
    result = run(["population", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data, dict):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected dict response from population")
        return False
    return True


results.append(test("live population returns dict", test_population))


def test_migration():
    result = run(["migration", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data, dict):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected dict response from migration")
        return False
    return True


results.append(test("live migration returns dict", test_migration))


def load_travel_cli():
    import importlib.util

    spec = importlib.util.spec_from_file_location("stats_nz_place_travel", CLI)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_population_command_preserved():
    import inspect

    module = load_travel_cli()
    assert module.PLACE_BASE == "https://tools.summaries.stats.govt.nz/places/RC"
    source = inspect.getsource(module.regional_population)
    assert 'variable1_code") != "ERP"' in source or "variable1_code" in source and "ERP" in source
    assert ("figure" + ".nz") not in inspect.getsource(module).lower()
    help_result = run(["population", "--help"])
    assert help_result.returncode == 0
    assert "--region" in help_result.stdout
    assert "--projection" in help_result.stdout
    return True


results.append(test("fixture population command still reads regional ERP", test_population_command_preserved))


def test_place_travel_fixture():
    module = load_travel_cli()
    page = (SKILL_DIR / "tests" / "fixtures" / "place-travel-auckland.html").read_text(encoding="utf-8")
    rows = module.parse_place_travel_html(
        page,
        url="https://tools.summaries.stats.govt.nz/places/UR/auckland",
        address="usual",
    )
    assert [row["mode"] for row in rows] == [
        "Work at home",
        "Drive a private car, truck or van",
        "Synthetic suppressed mode",
    ]
    drive = rows[1]
    assert drive["mode_code"] == "3"
    assert drive["period"] == "2023"
    assert drive["percent"] == 55.4
    assert drive["count"] == 408939
    assert drive["percent_unit"] == "percent"
    assert drive["count_unit"] == "people"
    assert drive["suppressed"] is False
    assert drive["collection"] == "Census"
    assert drive["place"] == "Auckland"
    suppressed = rows[2]
    assert suppressed["suppressed"] is True
    assert suppressed["confidentiality_indicator"] == "S"
    assert suppressed["percent"] is None
    assert suppressed["count"] is None
    assert all(row["percent"] != 99.9 for row in rows)
    try:
        module.parse_place_travel_html(
            page,
            url="https://tools.summaries.stats.govt.nz/places/UR/auckland",
            address="workplace",
        )
    except module.PlaceTravelError as exc:
        assert exc.code == 6
        assert "workplace" in exc.message
    else:
        raise AssertionError("empty workplace address returned rows")
    return True


results.append(test("fixture place-travel pins 55.4 percent and count 408939", test_place_travel_fixture))


def test_place_travel_malformed():
    module = load_travel_cli()
    url = "https://tools.summaries.stats.govt.nz/places/UR/auckland"
    cases = [
        ('<script id="__NEXT_DATA__" type="application/json">{"props":', 6),
        ('<script id="__NEXT_DATA__" type="application/json">not-json</script>', 6),
        ("<html>no embedded place</html>", 6),
    ]
    for text, code in cases:
        try:
            module.parse_place_travel_html(text, url=url, address="usual")
        except module.PlaceTravelError as exc:
            assert exc.code == code
        else:
            raise AssertionError(f"malformed page was accepted: {text[:40]}")
    huge = {
        "period": "2023",
        "variable1_code": "3",
        "variable1_descriptor": "Drive a private car, truck or van",
        "value": 1,
        "count_value": 1,
        "confidentiality_indicator": None,
    }
    numbers = []
    for index in range(41):
        row = dict(huge)
        row["variable1_code"] = str(index + 1)
        row["variable1_descriptor"] = f"Mode {index + 1}"
        numbers.append(row)
    payload = {
        "props": {
            "pageProps": {
                "place": [
                    {
                        "classification_label": "Urban Rural",
                        "classification_descriptor": "Auckland",
                        "classification_code": "1108",
                        "concepts": [
                            {
                                "concept_title": "Main means of travel to work",
                                "sections": [
                                    {
                                        "section_title": "Main means of travel to work (usual residence address)",
                                        "numbers_data": {"value_label": "percent", "numbers": numbers},
                                    }
                                ],
                            }
                        ],
                    }
                ]
            }
        }
    }
    page = '<script id="__NEXT_DATA__" type="application/json">' + json.dumps(payload) + "</script>"
    try:
        module.parse_place_travel_html(page, url=url, address="usual")
    except module.PlaceTravelError as exc:
        assert exc.code == 7
    else:
        raise AssertionError("row bound was not enforced")
    empty = page.replace(json.dumps(numbers), "[]")
    try:
        module.parse_place_travel_html(empty, url=url, address="usual")
    except module.PlaceTravelError as exc:
        assert exc.code == 6
    else:
        raise AssertionError("empty concept was accepted")
    return True


results.append(test("fixture place-travel rejects truncated, malformed, empty, and over-bound pages", test_place_travel_malformed))


def test_place_travel_input_and_outage():
    module = load_travel_cli()
    import nzfetch

    def unused(url):
        raise AssertionError(f"fetcher should not be called for {url}")

    republisher = "https://" + (chr(102) + "igure.nz") + "/table/example"
    for place in (republisher, "UR/auckland/extra", "../UR/auckland", ""):
        try:
            module.load_place_travel(place, "usual", fetcher=unused)
        except module.PlaceTravelError as exc:
            assert exc.code == 2
        else:
            raise AssertionError(f"invalid place was accepted: {place!r}")
    try:
        module.load_place_travel("UR/auckland", "education", fetcher=unused)
    except module.PlaceTravelError as exc:
        assert exc.code == 2
    else:
        raise AssertionError("invalid address was accepted")

    def outage(*_args, **_kwargs):
        raise nzfetch.FetchError(
            "https://tools.summaries.stats.govt.nz/places/UR/auckland unavailable after 1 attempt(s) (network error: timed out)"
        )

    original = nzfetch.fetch_bytes
    nzfetch.fetch_bytes = outage
    try:
        module.fetch_place_html("https://tools.summaries.stats.govt.nz/places/UR/auckland")
    except module.PlaceTravelError as exc:
        assert exc.code == 5
        assert "network error" in exc.message
        assert "upstream unavailable" in exc.message
    else:
        raise AssertionError("outage was treated as success")
    finally:
        nzfetch.fetch_bytes = original

    result = run(["place-travel", republisher, "--json"])
    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["results"] == []
    assert payload["error"]["type"] == "invalid_input"
    assert payload["error"]["code"] == 2
    assert payload["meta"]["publisher"] == "Stats NZ"
    assert ("figure" + ".nz") not in payload["meta"]["source_url"]
    return True


results.append(test("fixture place-travel rejects bad input and records outage", test_place_travel_input_and_outage))


def test_place_travel_live():
    result = run(["place-travel", "UR/auckland", "--address", "usual", "--json"])
    if result.returncode != 0:
        print(result.stderr.strip()[:500] or result.stdout.strip()[:500])
        return False
    data = json.loads(result.stdout)
    assert set(data) == {"meta", "results"}
    meta = data["meta"]
    assert meta["publisher"] == "Stats NZ"
    assert meta["source_url"] == "https://tools.summaries.stats.govt.nz/places/UR/auckland"
    assert meta["retrieved_at"].endswith("Z")
    assert "CC BY 4.0" in meta["licence"]
    assert isinstance(meta.get("latest_data"), str) and meta["latest_data"]
    rows = data["results"]
    assert isinstance(rows, list) and rows
    measured = [
        row
        for row in rows
        if isinstance(row.get("mode"), str)
        and row["mode"].strip()
        and isinstance(row.get("percent"), (int, float))
        and not isinstance(row.get("percent"), bool)
        and isinstance(row.get("count"), (int, float))
        and not isinstance(row.get("count"), bool)
    ]
    assert measured, "travel concept did not return a mode with a numeric percent and count"
    assert all(row["percent_unit"] == "percent" and row["count_unit"] == "people" for row in rows)
    assert all(row["concept"] == "Main means of travel to work" for row in rows)
    assert all(row["address"] == "usual" for row in rows)
    return True


results.append(test("live place-travel Auckland usual residence returns mode, percent and count", test_place_travel_live))

if all(results):
    sys.exit(0)
print(f"{results.count(False)} test(s) failed.")
sys.exit(1)
