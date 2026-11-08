import tempfile
import os
import unittest
from pathlib import Path
from unittest import mock


import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_smoke_tests  # noqa: E402
from run_smoke_tests import run_in_lane, run_one, smoke_command, uses_browser  # noqa: E402


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

    def test_summary_log_and_skips_are_redacted_before_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill = self.make_skill(Path(tmp),
                "import os\nprint('[SKIP] error ' + os.environ['SYNTHETIC_API_KEY'])\n"
                "print('Bearer synthetic-auth eyJfake.part.signature ?token=synthetic-query')\n")
            with mock.patch.dict(os.environ, {"SYNTHETIC_API_KEY": "FAKE-ARTIFACT-SECRET"}), \
                 mock.patch("run_smoke_tests.smoke_command", side_effect=lambda p: [sys.executable, str(p)]):
                result = run_one(skill, 10)
            for value in ("FAKE-ARTIFACT-SECRET", "synthetic-auth", "eyJfake.part.signature", "synthetic-query"):
                self.assertNotIn(value, result["log"])
                self.assertNotIn(value, " ".join(result["skips"]))
            self.assertIn("***", result["log"])

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

    def test_browser_launch_failure_is_hard_even_with_network_words(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill = self.make_skill(
                Path(tmp),
                "print('[FAIL] live search returns products')\n"
                "print('{\"error\": \"browser_launch_failed\", \"message\": \"TimeoutError: timed out\"}')\n"
                "raise SystemExit(1)\n",
            )
            result = run_one(skill, 10)
            self.assertEqual(result["status"], "fail")

    def test_browser_session_limit_skip_is_gated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill = self.make_skill(
                Path(tmp),
                "print('[PASS] fixture only the CloakBrowser exit-76 session limit skips')\n"
                "print('[SKIP] search: CloakBrowser concurrent-session limit reached (CloakBrowserLicenseError, exit 76)')\n",
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
            self.assertEqual(result["status"], "gated")
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
            self.assertEqual(result["status"], "gated")
            self.assertEqual(result["fixture_assertions"], 1)
            self.assertEqual(result["live_assertions"], 0)
            self.assertEqual(result["source_health"], "gated")

    def test_deterministic_passes_with_only_skipped_live_probes_are_gated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill = self.make_skill(
                Path(tmp),
                "print('[PASS] fixture parser retained source identifier')\n"
                "print('[PASS] contract CLI help declares commands')\n"
                "print('[SKIP] live probe intentionally skipped')\n",
            )
            result = run_one(skill, 10)
            self.assertEqual(result["status"], "gated")
            self.assertEqual(result["fixture_assertions"], 1)
            self.assertEqual(result["contract_assertions"], 1)
            self.assertEqual(result["live_assertions"], 0)
            self.assertEqual(result["source_health"], "gated")

    def test_explicit_fixture_pass_is_meaningful(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill = self.make_skill(
                Path(tmp), "print('[PASS] fixture parser retained identifier')\n"
            )
            result = run_one(skill, 10)
            self.assertEqual(result["status"], "pass")
            self.assertEqual(result["fixture_assertions"], 1)

    def test_explicit_unavailable_skip_is_gated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill = self.make_skill(
                Path(tmp), "print('[SKIP] source asset unavailable')\n"
            )
            result = run_one(skill, 10)
            self.assertEqual(result["status"], "gated")

    def test_fixture_failure_is_hard_even_if_script_exits_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill = self.make_skill(
                Path(tmp), "print('[FAIL] fixture parser shape changed')\n"
            )
            result = run_one(skill, 10)
            self.assertEqual(result["status"], "fail")

    def test_fixture_pass_describing_fail_closed_behaviour_is_not_a_failure(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill = self.make_skill(
                Path(tmp),
                "print('[PASS] fixture malformed input remains fail-closed')\n",
            )
            result = run_one(skill, 10)
            self.assertEqual(result["status"], "pass")

    def test_declared_skill_requirements_are_installed_with_uv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill = self.make_skill(
                Path(tmp), "print('[PASS] fixture dependency loaded')\n"
            )
            requirements = skill / "requirements.txt"
            requirements.write_text("example-package==1.0\n", encoding="utf-8")
            smoke = skill / "scripts" / "smoke_test.py"
            with mock.patch("run_smoke_tests.shutil.which", return_value="/usr/bin/uv"):
                command = smoke_command(smoke)
            self.assertEqual(
                command,
                [
                    "uv",
                    "run",
                    "--no-project",
                    "--with-requirements",
                    str(requirements),
                    "python",
                    str(smoke),
                ],
            )

    def test_browser_skills_are_detected_from_their_scripts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill = self.make_skill(Path(tmp), "print('[PASS] fixture ok')\n")
            self.assertFalse(uses_browser(skill))
            (skill / "scripts" / "cli.py").write_text(
                "from cloakbrowser import launch\n", encoding="utf-8"
            )
            self.assertTrue(uses_browser(skill))

    def test_browser_smokes_never_overlap_when_cloakbrowser_is_enabled(self) -> None:
        # Nightly 42416982995: 16 parallel workers shared one free CloakBrowser
        # seat and four browser skills failed at launch.
        import threading
        import time
        from concurrent.futures import ThreadPoolExecutor

        active = 0
        peak = 0
        guard = threading.Lock()

        def fake_run_one(skill_dir, timeout):
            nonlocal active, peak
            with guard:
                active += 1
                peak = max(peak, active)
            time.sleep(0.05)
            with guard:
                active -= 1
            return {"skill": skill_dir.name}

        with tempfile.TemporaryDirectory() as tmp:
            skills = []
            for index in range(4):
                skill = self.make_skill(Path(tmp) / str(index), "print('[PASS] fixture ok')\n")
                (skill / "scripts" / "cli.py").write_text("import cloakbrowser\n", encoding="utf-8")
                skills.append(skill)
            for enabled, expected_peak in (("1", 1), ("", 4)):
                active = peak = 0
                with mock.patch.dict(os.environ, {"COLAB_SMOKE_WITH_CLOAKBROWSER": enabled}), \
                     mock.patch.object(run_smoke_tests, "run_one", side_effect=fake_run_one):
                    with ThreadPoolExecutor(max_workers=4) as executor:
                        list(executor.map(lambda path: run_in_lane(path, 10), skills))
                self.assertEqual(peak, expected_peak, f"enabled={enabled!r}")


# A stand-in CloakBrowser that fails at launch the way the real 0.7 wrapper does.
FAKE_CLOAKBROWSER = '''
import os


class CloakBrowserLicenseError(RuntimeError):
    pass


MESSAGES = {
    "licence-76": "CloakBrowser Pro: session limit reached for your plan. Close another running session or upgrade your plan.",
    "licence-77": "CloakBrowser Pro: license key is invalid, expired, or missing.",
    "licence-78": "CloakBrowser Pro: could not reach license server (network error, timed out).",
}


def launch(*args, **kwargs):
    mode = os.environ["FAKE_CLOAKBROWSER_MODE"]
    if mode in MESSAGES:
        raise CloakBrowserLicenseError(MESSAGES[mode])
    if mode == "timeout":
        raise TimeoutError("Timed out after 30000ms: network error connecting to CDP")
    raise TypeError("launch() got an unexpected keyword argument 'timezone'")


async def launch_async(*args, **kwargs):
    return launch(*args, **kwargs)
'''

# Every outbound connection fails, so the smokes' non-browser checks report a
# network outage, as on a night when an upstream (eventfinda) blocks the runner.
NO_NETWORK_SITECUSTOMIZE = '''
import socket


def _refuse(*args, **kwargs):
    raise OSError("outbound connections disabled for this test")


socket.socket.connect = _refuse
socket.create_connection = _refuse
socket.getaddrinfo = _refuse
'''


class RealBrowserSmokeClassificationTests(unittest.TestCase):
    """Run the real nz-council and the-warehouse-nz smokes through run_one.

    Their CLIs report browser_launch_failed in a JSON payload on stdout. The runner
    must still see that marker and FAIL the skill when another check in the same smoke
    hit a network block; only the exit-76 session limit may end up gated.
    """

    HARD_FAILURES = ("licence-77", "licence-78", "api-break", "timeout")

    def run_real_smoke(self, skill: str, mode: str) -> dict[str, object]:
        with tempfile.TemporaryDirectory() as tmp:
            package = Path(tmp) / "cloakbrowser"
            package.mkdir()
            (package / "__init__.py").write_text(FAKE_CLOAKBROWSER, encoding="utf-8")
            (Path(tmp) / "sitecustomize.py").write_text(NO_NETWORK_SITECUSTOMIZE, encoding="utf-8")
            environment = {
                "PYTHONPATH": tmp,
                "COLAB_SMOKE_USE_BROWSER": "1",
                "FAKE_CLOAKBROWSER_MODE": mode,
            }
            with mock.patch.dict(os.environ, environment), \
                 mock.patch.object(run_smoke_tests, "smoke_command", side_effect=lambda p: [sys.executable, str(p)]):
                return run_one(ROOT / "skills" / skill, 300)

    def test_council_launch_failure_fails_despite_unrelated_network_block(self) -> None:
        for mode in self.HARD_FAILURES:
            with self.subTest(mode=mode):
                result = self.run_real_smoke("nz-council", mode)
                log = str(result["log"])
                # The unrelated network failure is present, so only the marker keeps this a FAIL.
                self.assertRegex(log, run_smoke_tests.NETWORK_MARKER)
                self.assertEqual(result["status"], "fail", log[-1500:])
                self.assertIn("error: browser_launch_failed:", log)
                self.assertEqual(result["live_assertions"], 0)

    def test_council_session_limit_stays_gated(self) -> None:
        result = self.run_real_smoke("nz-council", "licence-76")
        log = str(result["log"])
        self.assertEqual(result["status"], "gated", log[-1500:])
        self.assertNotIn("browser_launch_failed:", log)
        self.assertTrue(any("exit 76" in skip for skip in result["skips"]), result["skips"])

    def test_warehouse_launch_failure_marker_reaches_the_log(self) -> None:
        for mode in self.HARD_FAILURES:
            with self.subTest(mode=mode):
                result = self.run_real_smoke("the-warehouse-nz", mode)
                log = str(result["log"])
                self.assertEqual(log.count("error: browser_launch_failed:"), 3, log[-1500:])
                self.assertEqual(result["status"], "fail", log[-1500:])

    def test_warehouse_session_limit_stays_gated(self) -> None:
        result = self.run_real_smoke("the-warehouse-nz", "licence-76")
        log = str(result["log"])
        self.assertEqual(result["status"], "gated", log[-1500:])
        self.assertNotIn("browser_launch_failed:", log)
        self.assertEqual(sum("exit 76" in skip for skip in result["skips"]), 3, result["skips"])


if __name__ == "__main__":
    unittest.main()
