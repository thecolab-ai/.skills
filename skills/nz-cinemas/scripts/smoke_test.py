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
        # movies/nowplaying fan out across ~10 cinema sites sequentially (~25s
        # direct); a rotating proxy adds retry latency on any blocked sub-site, so
        # 30s was too tight — the data is correct, it just needs headroom.
        timeout=75,
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


def test_movie_fixture():
    import importlib.util

    spec = importlib.util.spec_from_file_location("nz_cinemas_cli", CLI)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    movies = module.parse_event_movies(
        "event",
        {
            "Movies": [{
                "Id": 42,
                "Name": "Synthetic Film",
                "Rating": "PG",
                "RunningTime": 105,
                "MovieGenres": [{"Name": "Drama"}],
                "CinemaModels": [{"Name": "Example Cinema", "Sessions": [{"Id": 1}, {"Id": 2}]}],
                "CinemaIds": [10],
                "MovieUrl": "/Movies/Synthetic-Film",
            }]
        },
    )
    assert len(movies) == 1
    assert movies[0]["title"] == "Synthetic Film"
    assert movies[0]["genres"] == ["Drama"]
    assert movies[0]["sessions_count"] == 2
    print("[PASS] fixture cinema movie-bundle parser")
    return True


results.append(test("fixture cinema bundle parser", test_movie_fixture))


def test_help():
    result = run(["--help"])
    return result.returncode == 0


results.append(test("--help exits 0", test_help))


def test_cinemas():
    result = run(["cinemas", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("cinemas"), list) or len(data["cinemas"]) < 1:
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected cinemas[] with at least one result")
        return False
    return True


results.append(test("cinemas returns cinemas[]", test_cinemas))


def test_movies():
    result = run(["movies", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("movies"), list):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected movies[] in response")
        return False
    return True


results.append(test("movies returns movies[]", test_movies))


def test_nowplaying():
    result = run(["nowplaying", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("sessions"), list):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected sessions[] in nowplaying response")
        return False
    return True


results.append(test("nowplaying returns sessions[]", test_nowplaying))

if all(results):
    print("[PASS] live smoke assertions completed")
    sys.exit(0)
else:
    print(f"{results.count(False)} test(s) failed.")
    sys.exit(1)
