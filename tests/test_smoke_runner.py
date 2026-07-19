import tempfile
import unittest
from pathlib import Path


import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from run_smoke_tests import run_one  # noqa: E402


class SmokeRunnerTests(unittest.TestCase):
    def make_skill(self, root: Path, script: str) -> Path:
        skill = root / "fixture-skill"
        (skill / "scripts").mkdir(parents=True)
        (skill / "SKILL.md").write_text(
            """---
name: fixture-skill
description: "Fixture skill for smoke classification tests."
metadata:
  thecolab.health: "untested"
---

# Fixture skill
""",
            encoding="utf-8",
        )
        smoke = skill / "scripts" / "smoke_test.py"
        smoke.write_text("#!/usr/bin/env python3\n" + script, encoding="utf-8")
        return skill

    def test_network_error_cannot_mask_a_fixture_parser_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill = self.make_skill(
                Path(tmp),
                "print('[FAIL] fixture parser rejected expected source row')\n"
                "print('network error calling live source')\n"
                "raise SystemExit(1)\n",
            )
            result = run_one(skill, 10)
            self.assertEqual(result["status"], "fail")

    def test_network_only_live_failure_is_gated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill = self.make_skill(
                Path(tmp),
                "print('[FAIL] live endpoint did not respond')\n"
                "print('network error calling live source')\n"
                "raise SystemExit(1)\n",
            )
            result = run_one(skill, 10)
            self.assertEqual(result["status"], "gated")

    def test_live_assertion_failure_without_outage_is_hard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill = self.make_skill(
                Path(tmp),
                "print('[FAIL] live result omitted required source URL')\n"
                "raise SystemExit(0)\n",
            )
            result = run_one(skill, 10)
            self.assertEqual(result["status"], "fail")

    def test_zero_assertion_success_is_untested(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill = self.make_skill(Path(tmp), "raise SystemExit(0)\n")
            result = run_one(skill, 10)
            self.assertEqual(result["status"], "untested")

    def test_untagged_legacy_pass_is_not_a_contract_assertion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill = self.make_skill(Path(tmp), "print('[PASS] search returned rows')\n")
            result = run_one(skill, 10)
            self.assertEqual(result["status"], "untested")
            self.assertEqual(result["contract_assertions"], 0)

    def test_incidental_live_word_is_not_a_live_assertion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill = self.make_skill(
                Path(tmp),
                "print('[PASS] command returns live rows or explicit blocked')\n",
            )
            result = run_one(skill, 10)
            self.assertEqual(result["status"], "untested")
            self.assertEqual(result["live_assertions"], 0)

    def test_skip_followed_by_wrapper_pass_does_not_become_live_assertion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill = self.make_skill(
                Path(tmp),
                "print('[SKIP] requires EXAMPLE_API_KEY')\n"
                "print('[PASS] live source returned rows')\n",
            )
            result = run_one(skill, 10)
            self.assertEqual(result["status"], "gated")
            self.assertEqual(result["live_assertions"], 0)

    def test_explicit_contract_after_skip_remains_meaningful(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill = self.make_skill(
                Path(tmp),
                "print('[SKIP] live source unavailable')\n"
                "print('[PASS] contract invalid input is rejected')\n",
            )
            result = run_one(skill, 10)
            self.assertEqual(result["status"], "pass")
            self.assertEqual(result["contract_assertions"], 1)

    def test_generic_live_summary_after_any_skip_is_not_live_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill = self.make_skill(
                Path(tmp),
                "print('[PASS] fixture parser retained source identifier')\n"
                "print('[SKIP] optional live command requires EXAMPLE_API_KEY')\n"
                "print('[PASS] live smoke assertions completed')\n",
            )
            result = run_one(skill, 10)
            self.assertEqual(result["status"], "pass")
            self.assertEqual(result["fixture_assertions"], 1)
            self.assertEqual(result["live_assertions"], 0)
            self.assertEqual(result["source_health"], "untested")

    def test_explicit_fixture_pass_is_meaningful(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill = self.make_skill(Path(tmp), "print('[PASS] fixture parser retained identifier')\n")
            result = run_one(skill, 10)
            self.assertEqual(result["status"], "pass")
            self.assertEqual(result["fixture_assertions"], 1)

    def test_explicit_unavailable_skip_is_gated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill = self.make_skill(Path(tmp), "print('[SKIP] source asset unavailable')\n")
            result = run_one(skill, 10)
            self.assertEqual(result["status"], "gated")

    def test_fixture_failure_is_hard_even_if_script_exits_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill = self.make_skill(Path(tmp), "print('[FAIL] fixture parser shape changed')\n")
            result = run_one(skill, 10)
            self.assertEqual(result["status"], "fail")

    def test_fixture_pass_describing_fail_closed_behaviour_is_not_a_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill = self.make_skill(
                Path(tmp),
                "print('[PASS] fixture malformed input remains fail-closed')\n",
            )
            result = run_one(skill, 10)
            self.assertEqual(result["status"], "pass")


if __name__ == "__main__":
    unittest.main()
