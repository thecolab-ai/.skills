import json
import importlib.util
import os
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "run_skill.py"
SPEC = importlib.util.spec_from_file_location("run_skill_module", RUNNER)
assert SPEC and SPEC.loader
RUN_SKILL_MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUN_SKILL_MODULE)


class RunSkillIntegrationTests(unittest.TestCase):
    def run_skill(self, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(RUNNER), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=15,
            check=False,
            env=env,
        )

    def test_success_uses_common_envelope(self) -> None:
        completed = self.run_skill("thecolab-brand", "palette")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["schema_version"], "1")
        self.assertIn("retrieved_at", payload["source"])
        self.assertEqual(payload["query"]["argv"], ["palette", "--json"])

    def test_missing_credentials_use_exit_three_without_leaking_values(self) -> None:
        env = os.environ.copy()
        env.pop("AKAHU_APP_TOKEN", None)
        env.pop("AKAHU_USER_TOKEN", None)
        completed = self.run_skill("akahu-personal", "accounts", env=env)
        self.assertEqual(completed.returncode, 3)
        payload = json.loads(completed.stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], 3)
        self.assertNotIn("AKAHU_USER_TOKEN=", completed.stdout)

    def test_guarded_mutation_uses_exit_seven(self) -> None:
        completed = self.run_skill("akahu-personal", "endpoint", "/payments", "--method", "POST")
        self.assertEqual(completed.returncode, 7)
        payload = json.loads(completed.stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], 7)

    def test_unknown_skill_uses_json_invalid_input_contract(self) -> None:
        completed = self.run_skill("does-not-exist", "status")
        self.assertEqual(completed.returncode, 2)
        payload = json.loads(completed.stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], 2)

    def test_skill_name_cannot_escape_catalogue(self) -> None:
        completed = self.run_skill("../lib", "--help")
        payload = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 2)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], 2)

    def test_secret_redaction_helper_never_emits_environment_value(self) -> None:
        previous = os.environ.get("EXAMPLE_API_KEY")
        previous_username = os.environ.get("EXAMPLE_API_USERNAME")
        os.environ["EXAMPLE_API_KEY"] = "super-secret-value"
        os.environ["EXAMPLE_API_USERNAME"] = "ab"
        try:
            self.assertEqual(
                RUN_SKILL_MODULE.redact_secrets("failure for ab: super-secret-value"),
                "failure for [REDACTED]: [REDACTED]",
            )
        finally:
            if previous is None:
                os.environ.pop("EXAMPLE_API_KEY", None)
            else:
                os.environ["EXAMPLE_API_KEY"] = previous
            if previous_username is None:
                os.environ.pop("EXAMPLE_API_USERNAME", None)
            else:
                os.environ["EXAMPLE_API_USERNAME"] = previous_username

    def test_help_is_wrapped_without_schema_failure(self) -> None:
        completed = self.run_skill("stats-nz", "--help")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertTrue(payload["ok"])
        self.assertIn("usage:", payload["data"]["help"])
        self.assertEqual(payload["query"]["argv"], ["--help"])

    def test_credential_like_arguments_are_redacted_from_provenance(self) -> None:
        self.assertEqual(
            RUN_SKILL_MODULE.redact_arguments(
                ["endpoint", "--api-key", "secret-value", "--password=hunter2", "--json"]
            ),
            ["endpoint", "--api-key", "[REDACTED]", "--password=[REDACTED]", "--json"],
        )
        self.assertEqual(
            RUN_SKILL_MODULE.redact_command_output(
                "authentication failed for secret-value and hunter2",
                ["--api-key", "secret-value", "--password=hunter2"],
            ),
            "authentication failed for [REDACTED] and [REDACTED]",
        )


if __name__ == "__main__":
    unittest.main()
