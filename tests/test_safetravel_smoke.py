import contextlib
import importlib.util
import io
import json
import subprocess
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SMOKE = ROOT / "skills" / "safetravel-nz" / "scripts" / "smoke_test.py"


def load_smoke():
    spec = importlib.util.spec_from_file_location("safetravel_nz_smoke", SMOKE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def completed(returncode: int, *, stdout: str = "", stderr: str = ""):
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


class SafeTravelSmokeTests(unittest.TestCase):
    def test_advice_outage_does_not_prevent_search_probe(self) -> None:
        smoke = load_smoke()
        search_payload = {
            "data": {
                "kind": "destination_search",
                "destinations": [{"slug": "australia"}],
            },
            "source": {"retrieved_at": "2026-09-04T00:00:00Z"},
        }
        stdout = io.StringIO()
        with (
            mock.patch.object(
                smoke,
                "run",
                side_effect=[
                    completed(0, stdout="[PASS] fixture parser assertions"),
                    completed(0, stdout="usage: cli.py {search,advice}"),
                    completed(4, stderr="source unavailable"),
                    completed(0, stdout=json.dumps(search_payload)),
                ],
            ) as run,
            contextlib.redirect_stdout(stdout),
        ):
            exit_code = smoke.main()

        self.assertEqual(exit_code, 0)
        self.assertEqual(run.call_count, 4)
        self.assertIn("[SKIP] live advice unavailable", stdout.getvalue())
        self.assertIn("[PASS] live search returns", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()