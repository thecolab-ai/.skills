"""Exercise repaired CLI results through the canonical runner with synthetic HTTP data."""
import importlib.util
import io
import json
import subprocess
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import run_skill


def load_cli(name):
    folder = ROOT / "skills" / name
    sys.path.insert(0, str(folder / "scripts"))
    spec = importlib.util.spec_from_file_location(name.replace("-", "_") + "_runner_test", folder / "scripts/cli.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return folder, module


class HealthRunnerTests(unittest.TestCase):
    def run_result(self, name, command, cli):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main([*command, "--json"])
        self.assertEqual(code, 0)
        completed = subprocess.CompletedProcess([], code, out.getvalue(), err.getvalue())
        result = io.StringIO()
        with patch.object(run_skill.subprocess, "run", return_value=completed), \
             patch.object(sys, "argv", ["run_skill.py", name, *command]), redirect_stdout(result):
            self.assertEqual(run_skill.main(), 0)
        envelope = json.loads(result.getvalue())
        self.assertTrue(envelope["ok"])
        self.assertIsInstance(envelope["data"]["results"], list)
        self.assertTrue(envelope["data"]["meta"]["retrieved_at"].endswith("Z"))

    def test_every_fenz_data_command(self):
        folder, cli = load_cli("fenz-incidents-nz")
        def text(url, **kwargs):
            fixture = "annual-resources.html" if url == cli.ANNUAL_URL else "incidents.html"
            return (folder / "tests/fixtures" / fixture).read_text()
        def data(url, **kwargs):
            return (folder / "tests/fixtures/annual.tsv").read_bytes(), "text/plain", url
        with patch.object(cli.nzfetch, "fetch_text", side_effect=text), patch.object(cli.nzfetch, "fetch_bytes", side_effect=data):
            for command in (["recent"], ["search", "Wellington"], ["region", "Wellington"],
                            ["type", "Medical"], ["incident", "F1234567"],
                            ["annual", "--year", "2024-25"], ["trend", "--region", "Auckland"]):
                with self.subTest(command=command):
                    self.run_result("fenz-incidents-nz", command, cli)

    def test_council_schedule_and_candidate_statuses(self):
        _, cli = load_cli("auckland-bin-schedule")
        # Synthetic id and parsed schedule; no Council record is captured or invented as live data.
        items = [{"id": "123", "address": "12 Synthetic Road, Onehunga"}]
        with patch.object(cli, "lookup_properties", return_value=items), \
             patch.object(cli, "get_schedule", return_value={"property_id": "123", "address": items[0]["address"]}):
            for command in (["schedule", "12 Synthetic Road Onehunga"],
                            ["lookup", "12 Synthetic Road Onehunga"],
                            ["lookup", "12 Synthetic Road Onehunga", "--limit", "1"],
                            ["schedule", "99 Synthetic Road Onehunga"]):
                with self.subTest(command=command):
                    self.run_result("auckland-bin-schedule", command, cli)


if __name__ == "__main__":
    unittest.main()
