#!/usr/bin/env python3
"""Deterministic summary and mocked gh lifecycle tests; no GitHub writes."""
import importlib.util
import json
import unittest
import io
import sys
import tempfile
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

    def issue(self, number, title, state="OPEN", author="github-actions", label=module.LABEL, body=module.MARKER):
        return {"number": number, "title": title, "state": state, "author": {"login": author},
                "labels": [{"name": label}], "body": body}

    def test_update_close_and_deduplicate(self):
        calls, bodies = [], []
        issues = [self.issue(n, action["title"]) for action in self.actions for n in (9, 11)]
        issues.append(self.issue(12, self.actions[1]["title"] + "-other"))
        def fake_gh(args):
            calls.append(args)
            if args[1] == "list":
                return json.dumps(issues)
            if "--body-file" in args:
                bodies.append(Path(args[args.index("--body-file") + 1]).read_text())
            return ""
        with patch.object(module, "gh", fake_gh):
            module.reconcile(self.actions, "thecolab-ai/.skills", RUN)
        self.assertEqual(sum(call[1] == "list" for call in calls), 1)
        self.assertNotIn("--search", calls[0])
        self.assertIn("number,title,state,author,labels,body", calls[0])
        self.assertEqual(sum(call[1] == "close" for call in calls), 3)
        self.assertEqual(sum(call[1] == "edit" for call in calls), 1)
        self.assertEqual(bodies, [self.actions[1]["body"]])

    def test_create_when_absent_and_pass_without_issue(self):
        with patch.object(module, "gh", side_effect=["[]", "label created", "created"]) as gh:
            module.reconcile(self.actions, "thecolab-ai/.skills", RUN)
        self.assertEqual([c.args[0][:2] for c in gh.call_args_list],
                         [["issue", "list"], ["label", "create"], ["issue", "create"]])
        self.assertIn("--label", gh.call_args_list[-1].args[0])
        self.assertIn(module.LABEL, gh.call_args_list[-1].args[0])

    def test_recurrent_failure_reopens_the_same_issue(self):
        issue = self.issue(9, self.actions[1]["title"], "CLOSED", author="app/github-actions")
        with patch.object(module, "gh", side_effect=[json.dumps([issue]), "reopened", "edited"]) as gh:
            module.reconcile([self.actions[1]], "thecolab-ai/.skills", RUN)
        self.assertEqual([call.args[0][1] for call in gh.call_args_list], ["list", "reopen", "edit"])

    def test_repeated_pass_leaves_closed_issue_alone(self):
        issue = self.issue(9, self.actions[0]["title"], "CLOSED")
        with patch.object(module, "gh", return_value=json.dumps([issue])) as gh:
            module.reconcile([self.actions[0]], "thecolab-ai/.skills", RUN)
        self.assertEqual(gh.call_count, 1)

    def test_matching_human_issue_is_never_mutated(self):
        for action in self.actions:
            with self.subTest(action=action["action"]):
                issues = [self.issue(1, action["title"], author="human")]
                with patch.object(module, "gh", side_effect=[json.dumps(issues), "label", "created"]) as gh:
                    module.reconcile([action], "thecolab-ai/.skills", RUN)
                operations = [call.args[0][1] for call in gh.call_args_list]
                self.assertFalse({"edit", "reopen", "close"}.intersection(operations))
                self.assertEqual("create" in operations, action["action"] == "upsert")

    def test_lower_number_human_is_not_canonical(self):
        issues = [self.issue(1, self.actions[1]["title"], author="human"),
                  self.issue(9, self.actions[1]["title"], "CLOSED")]
        with patch.object(module, "gh", side_effect=[json.dumps(issues), "reopened", "edited"]) as gh:
            module.reconcile([self.actions[1]], "thecolab-ai/.skills", RUN)
        self.assertEqual(gh.call_args_list[1].args[0][2], "9")
        self.assertEqual(gh.call_args_list[2].args[0][2], "9")

    def test_bot_without_marker_or_label_is_ignored(self):
        issues = [self.issue(3, self.actions[0]["title"]),
                  self.issue(1, self.actions[0]["title"], label="bug"),
                  self.issue(2, self.actions[0]["title"], body="human report")]
        issues[0]["author"] = None
        with patch.object(module, "gh", return_value=json.dumps(issues)) as gh:
            module.reconcile([self.actions[0]], "thecolab-ai/.skills", RUN)
        self.assertEqual(gh.call_count, 1)

    def test_per_skill_failure_does_not_stop_later_skills(self):
        issue = self.issue(9, self.actions[0]["title"])
        with patch.object(module, "gh", side_effect=[json.dumps([issue]), RuntimeError("rate limited"), "label", "created"]) as gh:
            with self.assertRaisesRegex(RuntimeError, "auckland-bin-schedule: rate limited"):
                module.reconcile(self.actions, "thecolab-ai/.skills", RUN)
        self.assertEqual(gh.call_args_list[-1].args[0][:2], ["issue", "create"])

    def test_redaction_and_failure_tail(self):
        log = ("noise " * 6000 + "\n[FAIL] error FAKE-KEY-VALUE Bearer abc123 "
               "eyJfake.part.signature ?key=some-value&token=another&sig=signature\nTHE-END")
        summary = {"schema_version": "1", "results": [{"skill": "synthetic", "status": "fail", "log": log}]}
        with patch.dict(module.os.environ, {"SYNTHETIC_API_KEY": "FAKE-KEY-VALUE"}):
            body = module.parse_summary(summary, RUN)[0]["body"]
        for secret in ("FAKE-KEY-VALUE", "abc123", "eyJfake.part.signature", "some-value", "another", "sig=signature"):
            self.assertNotIn(secret, body)
        self.assertIn("THE-END", body)
        self.assertIn("***", body)
        self.assertLess(len(body), 9500)

    def test_missing_empty_and_invalid_summary_upsert_runner(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "summary.json"
            for content in (None, "", "{}", "not json", '{"schema_version":"1","results":[]}'):
                if content is not None:
                    path.write_text(content)
                actions = module.load_actions(path, RUN)
                self.assertEqual([(a["skill"], a["action"]) for a in actions], [("runner", "upsert")])
            path.write_text(json.dumps(self.summary))
            self.assertIn(("runner", "close"), [(a["skill"], a["action"]) for a in module.load_actions(path, RUN)])

    def test_inventory_limit_fails_without_writes(self):
        with patch.object(module, "gh", return_value=json.dumps([{}] * 1000)) as gh:
            with self.assertRaisesRegex(RuntimeError, "pagination"):
                module.reconcile(self.actions, "thecolab-ai/.skills", RUN)
        self.assertEqual(gh.call_count, 1)


if __name__ == "__main__":
    unittest.main()
