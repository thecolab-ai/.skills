import importlib.util
import io
import json
import os
import subprocess
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

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
        self.assertIn("palette", payload["data"])
        self.assertNotIn("schema_version", payload["data"])

    def run_mocked_direct_cli(
        self,
        skill: str,
        arguments: list[str],
        direct_payload: dict[str, object],
        returncode: int,
        *,
        failure_stream: bool = False,
        stderr_payload: dict[str, object] | tuple[dict[str, object], ...] | None = None,
        stdout_text: str | None = None,
        stderr_text: str | None = None,
    ) -> tuple[int, dict[str, object], str]:
        encoded = json.dumps(direct_payload)
        if isinstance(stderr_payload, tuple):
            encoded_stderr = "\n".join(json.dumps(item) for item in stderr_payload)
        elif stderr_payload is not None:
            encoded_stderr = json.dumps(stderr_payload)
        else:
            encoded_stderr = encoded if failure_stream else ""
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=returncode,
            stdout=stdout_text if stdout_text is not None else "" if failure_stream else encoded,
            stderr=stderr_text if stderr_text is not None else encoded_stderr,
        )
        stdout = io.StringIO()
        stderr = io.StringIO()
        argv = [str(RUNNER), skill, *arguments]
        with (
            mock.patch.object(sys, "argv", argv),
            mock.patch.object(RUN_SKILL_MODULE.subprocess, "run", return_value=completed),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            exit_code = RUN_SKILL_MODULE.main()
        return exit_code, json.loads(stdout.getvalue()), stderr.getvalue()

    def test_new_skill_success_envelopes_are_forwarded_without_nesting(self) -> None:
        cases = (
            ("pharmac-schedule-nz", "Pharmac", "https://schedule.pharmac.govt.nz/pub/schedule/archive/"),
            ("statsnz-building-consents", "Stats NZ", "https://www.stats.govt.nz/information-releases/building-consents-issued-may-2026/"),
        )
        for skill, source_name, source_url in cases:
            with self.subTest(skill=skill):
                direct = {
                    "schema_version": "1",
                    "ok": True,
                    "source": {
                        "name": source_name,
                        "url": source_url,
                        "retrieved_at": "2026-07-19T00:00:00Z",
                    },
                    "query": {"command": "latest"},
                    "data": [{"id": "fixture-record", "source_url": source_url}],
                    "warnings": ["fixture warning"],
                    "blocked": False,
                }
                exit_code, payload, stderr = self.run_mocked_direct_cli(
                    skill,
                    ["latest"],
                    direct,
                    0,
                )
                self.assertEqual(exit_code, 0)
                self.assertEqual(stderr, "")
                self.assertEqual(payload, direct)
                self.assertEqual(payload["data"], direct["data"])
                self.assertNotIn("schema_version", payload["data"][0])

    def test_new_skill_nonzero_result_envelope_is_forwarded(self) -> None:
        direct = {
            "schema_version": "1",
            "ok": False,
            "source": {
                "name": "New Zealand Police",
                "url": "https://www.police.govt.nz/about-us/publications-statistics/data-and-statistics/policedatanz",
                "retrieved_at": "2026-07-19T00:00:00Z",
            },
            "query": {"command": "area", "name": "Atlantis"},
            "data": None,
            "warnings": ["The official Tableau surface has no stable documented row-query API."],
            "blocked": False,
            "error": {"code": 7, "message": "this statistical filter cannot be applied honestly"},
        }
        exit_code, payload, stderr = self.run_mocked_direct_cli(
            "nz-police-data",
            ["area", "Atlantis"],
            direct,
            7,
            failure_stream=True,
        )
        self.assertEqual(exit_code, 7)
        self.assertEqual(stderr, "")
        self.assertEqual(payload, direct)

    def test_zero_exit_structured_legacy_errors_fail_closed_on_either_stream(self) -> None:
        for failure_stream in (False, True):
            for legacy_code in (7, None, "7", 0):
                with self.subTest(failure_stream=failure_stream, code=legacy_code):
                    exit_code, payload, stderr = self.run_mocked_direct_cli(
                        "school-terms-nz",
                        ["years"],
                        {
                            "status": "error",
                            "code": legacy_code,
                            "error": "synthetic_failure",
                            "message": "synthetic legacy failure",
                        },
                        0,
                        failure_stream=failure_stream,
                    )
                    self.assertEqual(exit_code, 6)
                    self.assertEqual(stderr, "")
                    self.assertFalse(payload["ok"])
                    self.assertIsNone(payload["data"])
                    error = payload["error"]
                    self.assertIsInstance(error, dict)
                    assert isinstance(error, dict)
                    self.assertEqual(error["code"], 6)
                    self.assertIn("zero exit status", error["message"])

    def test_zero_exit_success_envelope_cannot_hide_structured_stderr_failure(self) -> None:
        success = {
            "schema_version": "1",
            "ok": True,
            "source": {
                "name": "Ministry of Education",
                "url": "https://www.education.govt.nz/school/school-terms-and-holidays",
                "retrieved_at": "2026-09-03T00:00:00Z",
            },
            "query": {"command": "years"},
            "data": {"years": [2026]},
            "warnings": [],
            "blocked": False,
        }
        stderr_failures: tuple[dict[str, object], ...] = (
            {
                "status": "error",
                "code": 7,
                "error": "synthetic_failure",
                "message": "synthetic legacy failure",
            },
            {"code": 6, "message": "parser failed"},
            {"schema_version": "1", "ok": None},
            {"blocked": True, "message": "source access blocked"},
        )
        for stderr_failure in stderr_failures:
            with self.subTest(stderr_failure=stderr_failure):
                exit_code, payload, stderr = self.run_mocked_direct_cli(
                    "school-terms-nz",
                    ["years"],
                    success,
                    0,
                    stderr_payload=stderr_failure,
                )

                self.assertEqual(exit_code, 6)
                self.assertEqual(stderr, "")
                self.assertFalse(payload["ok"])
                error = payload["error"]
                self.assertIsInstance(error, dict)
                assert isinstance(error, dict)
                self.assertEqual(error["code"], 6)

    def test_zero_exit_multiple_structured_stderr_documents_fail_closed(self) -> None:
        success: dict[str, object] = {
            "schema_version": "1",
            "ok": True,
            "source": {
                "name": "Ministry of Education",
                "url": "https://www.education.govt.nz/school/school-terms-and-holidays",
                "retrieved_at": "2026-09-03T00:00:00Z",
            },
            "query": {"command": "years"},
            "data": {"years": [2026]},
            "warnings": [],
            "blocked": False,
            "error": None,
        }
        failure: dict[str, object] = {
            "success": False,
            "message": "synthetic failure",
        }
        for documents in ((success, success), (failure, failure)):
            with self.subTest(documents=documents):
                exit_code, payload, stderr = self.run_mocked_direct_cli(
                    "school-terms-nz",
                    ["years"],
                    {},
                    0,
                    failure_stream=True,
                    stderr_payload=documents,
                )
                self.assertEqual(exit_code, 6)
                self.assertEqual(stderr, "")
                self.assertFalse(payload["ok"])
                error = payload["error"]
                self.assertIsInstance(error, dict)
                assert isinstance(error, dict)
                self.assertEqual(error["code"], 6)

    def test_direct_success_rejects_json_looking_opposing_stream(self) -> None:
        success: dict[str, object] = {
            "schema_version": "1",
            "ok": True,
            "source": {
                "name": "Ministry of Education",
                "url": "https://www.education.govt.nz/school/school-terms-and-holidays",
                "retrieved_at": "2026-09-03T00:00:00Z",
            },
            "query": {"command": "years"},
            "data": {"years": [2026]},
            "warnings": [],
            "blocked": False,
            "error": None,
        }
        opposing_streams = (
            '{"status":"error"',
            json.dumps({"ok": True}),
            json.dumps({"blocked": False}),
            json.dumps({"success": True}),
            json.dumps({"status": "ok"}),
            json.dumps({"rows": [1]}),
            "null",
            '"diagnostic"',
            "0",
            '\ufeff{"status":"error"',
            "\ufeff",
            "undefined",
            "NaN",
            "Infinity",
            "None",
            "nil",
            "NULL",
            "True",
            "False",
            "true trailing",
            "truefalse",
            'true {"status":"error"}',
            "null junk",
            "undefined junk",
            'diagnostic\n{"status":"error","message":"hidden"}',
            "~",
        )
        for opposing in opposing_streams:
            for success_on_stderr in (False, True):
                with self.subTest(opposing=opposing, success_on_stderr=success_on_stderr):
                    exit_code, payload, stderr = self.run_mocked_direct_cli(
                        "school-terms-nz",
                        ["years"],
                        success,
                        0,
                        failure_stream=success_on_stderr,
                        stdout_text=opposing if success_on_stderr else None,
                        stderr_text=None if success_on_stderr else opposing,
                    )
                    self.assertEqual(exit_code, 6)
                    self.assertEqual(stderr, "")
                    self.assertFalse(payload["ok"])

    def test_direct_success_preserves_normal_plain_diagnostics(self) -> None:
        success: dict[str, object] = {
            "schema_version": "1",
            "ok": True,
            "source": {
                "name": "Ministry of Education",
                "url": "https://www.education.govt.nz/school/school-terms-and-holidays",
                "retrieved_at": "2026-09-03T00:00:00Z",
            },
            "query": {"command": "years"},
            "data": {"years": [2026]},
            "warnings": [],
            "blocked": False,
            "error": None,
        }
        for success_on_stderr in (False, True):
            with self.subTest(success_on_stderr=success_on_stderr):
                exit_code, payload, stderr = self.run_mocked_direct_cli(
                    "school-terms-nz",
                    ["years"],
                    success,
                    0,
                    failure_stream=success_on_stderr,
                    stdout_text="cache diagnostic" if success_on_stderr else None,
                    stderr_text=None if success_on_stderr else "cache diagnostic",
                )
                self.assertEqual(exit_code, 0)
                self.assertEqual(stderr, "")
                self.assertEqual(payload, success)

    def test_ordinary_legacy_json_data_is_wrapped_as_success(self) -> None:
        legacy_data: dict[str, object] = {"rows": [1], "message": "ordinary data"}
        exit_code, payload, stderr = self.run_mocked_direct_cli(
            "school-terms-nz",
            ["years"],
            legacy_data,
            0,
            stderr_text="cache diagnostic",
        )
        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"], legacy_data)
        self.assertEqual(payload["warnings"], ["cache diagnostic"])

    def test_direct_envelope_with_trailing_non_json_fails_closed(self) -> None:
        success: dict[str, object] = {
            "schema_version": "1",
            "ok": True,
            "source": {
                "name": "Ministry of Education",
                "url": "https://www.education.govt.nz/school/school-terms-and-holidays",
                "retrieved_at": "2026-09-03T00:00:00Z",
            },
            "query": {},
            "data": {},
            "warnings": [],
            "blocked": False,
            "error": None,
        }
        for suffix in ("diagnostic", '{"status":"error"'):
            with self.subTest(suffix=suffix):
                exit_code, payload, stderr = self.run_mocked_direct_cli(
                    "school-terms-nz",
                    ["years"],
                    success,
                    0,
                    stdout_text=f"{json.dumps(success)}\n{suffix}",
                )
                self.assertEqual(exit_code, 6)
                self.assertEqual(stderr, "")
                self.assertFalse(payload["ok"])

    def test_zero_exit_partial_result_failure_cannot_be_wrapped_as_success(self) -> None:
        exit_code, payload, stderr = self.run_mocked_direct_cli(
            "school-terms-nz",
            ["years"],
            {"ok": False, "error": {"code": 7, "message": "synthetic failure"}},
            0,
        )

        self.assertEqual(exit_code, 6)
        self.assertEqual(stderr, "")
        self.assertFalse(payload["ok"])
        error = payload["error"]
        self.assertIsInstance(error, dict)
        assert isinstance(error, dict)
        self.assertEqual(error["code"], 6)

    def test_zero_exit_contradictory_success_markers_fail_closed(self) -> None:
        cases: tuple[dict[str, object], ...] = (
            {
                "status": "ok",
                "code": 7,
                "error": "synthetic_failure",
                "message": "contradictory legacy result",
            },
            {
                "ok": True,
                "error": {"code": 7, "message": "contradictory partial result"},
            },
            {
                "code": None,
                "error": "synthetic_failure",
                "message": "malformed legacy result",
            },
            {"code": 5, "message": "upstream unavailable"},
            {"error": "upstream unavailable"},
            {"status": "failed", "message": "upstream unavailable"},
            {"blocked": True, "message": "source access blocked"},
            {"ok": True, "blocked": True, "message": "contradictory blocked result"},
            {"status": "ok", "blocked": True, "message": "blocked result"},
            {"status": False, "message": "malformed status"},
            {"success": False, "message": "failed result"},
            {"ok": 0, "message": "malformed ok marker"},
        )
        for direct in cases:
            with self.subTest(direct=direct):
                exit_code, payload, stderr = self.run_mocked_direct_cli(
                    "school-terms-nz",
                    ["years"],
                    direct,
                    0,
                )
                self.assertEqual(exit_code, 6)
                self.assertEqual(stderr, "")
                self.assertFalse(payload["ok"])
                error = payload["error"]
                self.assertIsInstance(error, dict)
                assert isinstance(error, dict)
                self.assertEqual(error["code"], 6)

    def test_invalid_legacy_error_codes_fail_closed_without_crashing(self) -> None:
        for invalid_code in (None, 0, 99, True):
            with self.subTest(code=invalid_code):
                exit_code, payload, stderr = self.run_mocked_direct_cli(
                    "school-terms-nz",
                    ["years"],
                    {
                        "status": "error",
                        "code": invalid_code,
                        "error": "synthetic_failure",
                        "message": "synthetic legacy failure",
                    },
                    1,
                    failure_stream=True,
                )
                self.assertEqual(exit_code, 6)
                self.assertEqual(stderr, "")
                self.assertFalse(payload["ok"])
                error = payload["error"]
                self.assertIsInstance(error, dict)
                assert isinstance(error, dict)
                self.assertEqual(error["code"], 6)
                self.assertIn("invalid legacy error code", error["message"])

    def test_explicit_nested_null_legacy_error_code_overrides_valid_top_level_code(self) -> None:
        exit_code, payload, stderr = self.run_mocked_direct_cli(
            "school-terms-nz",
            ["years"],
            {
                "status": "error",
                "code": 7,
                "error": {
                    "code": None,
                    "type": "unsupported_operation",
                    "message": "synthetic guarded operation",
                },
            },
            7,
            failure_stream=True,
        )

        self.assertEqual(exit_code, 6)
        self.assertEqual(stderr, "")
        self.assertFalse(payload["ok"])
        error = payload["error"]
        self.assertIsInstance(error, dict)
        assert isinstance(error, dict)
        self.assertEqual(error["code"], 6)
        self.assertIn("invalid legacy error code None", error["message"])

    def test_mismatched_stable_legacy_error_code_fails_closed(self) -> None:
        exit_code, payload, stderr = self.run_mocked_direct_cli(
            "school-terms-nz",
            ["years"],
            {
                "status": "error",
                "code": 7,
                "error": "unsupported_operation",
                "message": "synthetic guarded operation",
            },
            1,
            failure_stream=True,
        )
        self.assertEqual(exit_code, 6)
        self.assertEqual(stderr, "")
        error = payload["error"]
        self.assertIsInstance(error, dict)
        assert isinstance(error, dict)
        self.assertEqual(error["code"], 6)
        self.assertIn("matching exit status 1", error["message"])

    def test_coherent_stable_legacy_error_code_is_preserved(self) -> None:
        exit_code, payload, stderr = self.run_mocked_direct_cli(
            "school-terms-nz",
            ["years"],
            {
                "status": "error",
                "code": 7,
                "error": "unsupported_operation",
                "message": "synthetic guarded operation",
            },
            7,
            failure_stream=True,
        )
        self.assertEqual(exit_code, 7)
        self.assertEqual(stderr, "")
        error = payload["error"]
        self.assertIsInstance(error, dict)
        assert isinstance(error, dict)
        self.assertEqual(error["code"], 7)
        self.assertEqual(error["type"], "unsupported_operation")

    def test_new_skill_legacy_structured_failure_is_normalised(self) -> None:
        completed = self.run_skill("nz-police-data", "area", "Atlantis")
        self.assertEqual(completed.returncode, 7, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], 7)
        self.assertEqual(payload["error"]["type"], "unsupported_operation")
        self.assertEqual(
            payload["error"]["message"],
            "The official Tableau surface has no stable documented row-query API, so this requested statistical filter cannot be applied honestly. Use `datasets` to open the official report.",
        )

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

    def test_canonical_school_terms_timeout_zero_remains_invalid_input(self) -> None:
        completed = self.run_skill("school-terms-nz", "years", "--timeout", "0")
        self.assertEqual(completed.returncode, 2, completed.stdout)
        payload = json.loads(completed.stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], 2)
        self.assertEqual(payload["error"]["type"], "invalid_input")
        self.assertIn("--timeout must be greater than zero", payload["error"]["message"])

    def test_canonical_school_terms_oversized_timeout_is_concise_invalid_input(self) -> None:
        completed = self.run_skill("school-terms-nz", "years", "--timeout", "9" * 72)
        self.assertEqual(completed.returncode, 2, completed.stdout)
        self.assertEqual(completed.stderr, "")
        self.assertNotIn("Traceback", completed.stdout)
        payload = json.loads(completed.stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], 2)
        self.assertEqual(payload["error"]["type"], "invalid_input")
        self.assertEqual(payload["error"]["message"], "--timeout must be between 1 and 120 seconds")

    def test_canonical_school_terms_argument_error_is_preserved(self) -> None:
        completed = self.run_skill("school-terms-nz", "date")
        self.assertEqual(completed.returncode, 2, completed.stdout)
        payload = json.loads(completed.stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], 2)
        self.assertEqual(payload["error"]["type"], "invalid_input")
        self.assertEqual(payload["error"]["message"], "the following arguments are required: date")

    def test_skill_name_cannot_escape_catalogue(self) -> None:
        completed = self.run_skill("../lib", "--help")
        payload = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 2)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], 2)

    def test_unknown_skill_uses_json_invalid_input_contract(self) -> None:
        completed = self.run_skill("does-not-exist", "status")
        self.assertEqual(completed.returncode, 2)
        payload = json.loads(completed.stdout)
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
