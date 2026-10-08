#!/usr/bin/env python3
"""Deterministic summary and mocked gh lifecycle tests; no GitHub writes."""
import importlib.util
import json
import unittest
import io
import sys
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("smoke_failure_issues", ROOT / "scripts/smoke_failure_issues.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
RUN = "https://github.com/thecolab-ai/.skills/actions/runs/12345"


class IssueTests(unittest.TestCase):
    def setUp(self):
        self.summary = json.loads((ROOT / "tests/fixtures/smoke-summary.json").read_text())
        self.actions = module.parse_summary(self.summary, RUN)

    def test_fixture_summary(self):
        self.assertEqual([(a["skill"], a["action"]) for a in self.actions],
                         [("auckland-bin-schedule", "close"), ("fenz-incidents-nz", "upsert")])
        self.assertIn("HTTP 400", self.actions[1]["body"])
        self.assertIn(RUN, self.actions[1]["body"])
        self.assertEqual(self.actions[1]["title"], "Smoke failure: fenz-incidents-nz")

    def test_incomplete_or_duplicate_summary_rejected(self):
        with self.assertRaises(ValueError):
            module.parse_summary({"schema_version": "1", "failures": []}, RUN)
        self.summary["results"].append(self.summary["results"][0])
        with self.assertRaises(ValueError):
            module.parse_summary(self.summary, RUN)

    def test_runner_summary_preserves_all_observed_statuses(self):
        runner_spec = importlib.util.spec_from_file_location("issue_test_smoke_runner", ROOT / "scripts/run_smoke_tests.py")
        runner = importlib.util.module_from_spec(runner_spec)
        runner_spec.loader.exec_module(runner)
        records = [{**record, "fixture_assertions": 1, "skips": []} for record in self.summary["results"]]
        by_name = {record["skill"]: record for record in records}
        output = io.StringIO()
        with patch.object(sys, "argv", ["run_smoke_tests.py", "--summary-json"]), \
             patch.object(runner, "iter_skill_dirs", return_value=[Path(name) for name in by_name]), \
             patch.object(runner, "run_one", side_effect=lambda path, timeout: by_name[path.name]), \
             patch.object(runner, "write_summary"), redirect_stdout(output):
            self.assertEqual(runner.main(), 1)
        summary = json.loads(output.getvalue())
        self.assertEqual(summary["counts"], self.summary["counts"])
        self.assertEqual(module.parse_summary(summary, RUN), self.actions)

    def test_update_close_and_deduplicate(self):
        calls, bodies = [], []
        def fake_gh(args):
            calls.append(args)
            if args[1] == "list":
                title = "Smoke failure: " + ("auckland-bin-schedule" if "auckland-bin" in args[9] else "fenz-incidents-nz")
                return json.dumps([{"number": 9, "title": title, "state": "OPEN"},
                                   {"number": 11, "title": title, "state": "OPEN"},
                                   {"number": 12, "title": title + "-other", "state": "OPEN"}])
            if "--body-file" in args:
                bodies.append(Path(args[args.index("--body-file") + 1]).read_text())
            return ""
        with patch.object(module, "gh", fake_gh):
            module.reconcile(self.actions, "thecolab-ai/.skills", RUN)
        self.assertEqual(sum(call[1] == "close" for call in calls), 3)
        self.assertEqual(sum(call[1] == "edit" for call in calls), 1)
        self.assertEqual(bodies, [self.actions[1]["body"]])

    def test_create_when_absent_and_pass_without_issue(self):
        with patch.object(module, "gh", side_effect=["[]", "[]", "created"]) as gh:
            module.reconcile(self.actions, "thecolab-ai/.skills", RUN)
        self.assertEqual(gh.call_args_list[-1].args[0][1], "create")

    def test_recurrent_failure_reopens_the_same_issue(self):
        issue = {"number": 9, "title": self.actions[1]["title"], "state": "CLOSED"}
        with patch.object(module, "gh", side_effect=[json.dumps([issue]), "reopened", "edited"]) as gh:
            module.reconcile([self.actions[1]], "thecolab-ai/.skills", RUN)
        self.assertEqual([call.args[0][1] for call in gh.call_args_list], ["list", "reopen", "edit"])

    def test_repeated_pass_leaves_closed_issue_alone(self):
        issue = {"number": 9, "title": self.actions[0]["title"], "state": "CLOSED"}
        with patch.object(module, "gh", return_value=json.dumps([issue])) as gh:
            module.reconcile([self.actions[0]], "thecolab-ai/.skills", RUN)
        self.assertEqual(gh.call_count, 1)


if __name__ == "__main__":
    unittest.main()
