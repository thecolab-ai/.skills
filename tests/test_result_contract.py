#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "lib"))

from result_contract import (  # noqa: E402
    EXIT_BLOCKED,
    EXIT_MISSING_CONFIGURATION,
    EXIT_SCHEMA_FAILURE,
    EXIT_UNSAFE_OPERATION,
    classify_legacy_error,
    result_envelope,
    validate_result_envelope,
)


class ResultContractTests(unittest.TestCase):
    def test_success_envelope_is_valid(self) -> None:
        payload = result_envelope(
            ok=True,
            source_name="Example",
            source_url="https://example.govt.nz/data",
            query={"q": "test"},
            data=[{"value": 1}],
        )
        self.assertEqual(validate_result_envelope(payload), [])
        self.assertTrue(payload["source"]["retrieved_at"].endswith("Z"))

    def test_missing_credential_maps_to_three(self) -> None:
        self.assertEqual(
            classify_legacy_error(1, "missing AKAHU_APP_TOKEN; export it before running"),
            EXIT_MISSING_CONFIGURATION,
        )

    def test_block_and_schema_failures_are_distinct(self) -> None:
        self.assertEqual(classify_legacy_error(1, "rate_limited: HTTP 429"), EXIT_BLOCKED)
        self.assertEqual(classify_legacy_error(1, "source schema changed"), EXIT_SCHEMA_FAILURE)
        self.assertEqual(classify_legacy_error(1, "Akahu POST can mutate state"), EXIT_UNSAFE_OPERATION)

    def test_legacy_exit_two_upstream_error_is_not_invalid_input(self) -> None:
        self.assertEqual(classify_legacy_error(2, '{"error":"upstream_unavailable"}'), 5)

    def test_argparse_exit_two_remains_invalid_input(self) -> None:
        self.assertEqual(
            classify_legacy_error(
                2,
                "usage: cli [--timeout TIMEOUT] {token}; the following arguments are required: command",
            ),
            2,
        )

    def test_blocked_flag_and_exit_code_must_agree(self) -> None:
        missing_flag = result_envelope(
            ok=False,
            source_name="Example",
            source_url="https://example.govt.nz/data",
            query={},
            data=None,
            error={"code": 4, "message": "blocked"},
        )
        wrong_code = result_envelope(
            ok=False,
            source_name="Example",
            source_url="https://example.govt.nz/data",
            query={},
            data=None,
            blocked=True,
            error={"code": 5, "message": "unavailable"},
        )
        self.assertIn("exit code 4 results must set blocked true", validate_result_envelope(missing_flag))
        self.assertIn("blocked results must use exit code 4", validate_result_envelope(wrong_code))

    def test_failure_requires_stable_error_code(self) -> None:
        payload = result_envelope(
            ok=False,
            source_name="Example",
            source_url="https://example.govt.nz/data",
            query={},
            data=None,
            error={"code": 5, "message": "upstream unavailable"},
        )
        self.assertEqual(validate_result_envelope(payload), [])
        payload["error"]["code"] = 99
        self.assertIn("error.code must be a stable non-zero exit code", validate_result_envelope(payload))

    def test_failure_requires_an_actionable_message(self) -> None:
        payload = result_envelope(
            ok=False,
            source_name="Example",
            source_url="https://example.govt.nz/data",
            query={},
            data=None,
            error={"code": 5, "message": ""},
        )
        self.assertIn("error.message must be a non-empty string", validate_result_envelope(payload))

    def test_source_provenance_rejects_credentials_and_naive_time(self) -> None:
        payload = result_envelope(
            ok=True,
            source_name="Example",
            source_url="https://user:secret@example.govt.nz/data",
            query={},
            data=[],
            retrieved_at="2026-07-19T12:00:00",
        )
        errors = validate_result_envelope(payload)
        self.assertIn("source.url must not contain user information", errors)
        self.assertIn("source.retrieved_at must include a timezone", errors)

    def test_source_provenance_rejects_non_default_port(self) -> None:
        payload = result_envelope(
            ok=True,
            source_name="Example",
            source_url="https://example.govt.nz:444/data",
            query={},
            data=[],
        )
        self.assertIn(
            "source.url must use the default port for its scheme",
            validate_result_envelope(payload),
        )


if __name__ == "__main__":
    unittest.main()
