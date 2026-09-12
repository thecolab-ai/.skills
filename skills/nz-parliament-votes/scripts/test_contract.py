#!/usr/bin/env python3
"""Deterministic repository, parser, and CLI contract tests."""
from __future__ import annotations

import io
import json
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

SKILL = Path(__file__).resolve().parents[1]
REPO_ROOT = SKILL.parents[1]
sys.path.insert(0, str(REPO_ROOT / "lib"))
sys.path.insert(0, str(SKILL / "scripts"))

import nzfetch  # noqa: E402
import cli  # noqa: E402
from contract_test import audit_skill  # noqa: E402
from parliament_votes import parse_journal, parse_search  # noqa: E402

JOURNAL = json.loads((SKILL / "tests/fixtures/journal.json").read_text(encoding="utf-8"))
QUESTION_VARIANTS = json.loads((SKILL / "tests/fixtures/question-variants.json").read_text(encoding="utf-8"))
EMPTY = json.loads((SKILL / "tests/fixtures/source-sample.json").read_text(encoding="utf-8"))
ROW = {
    "id": JOURNAL["Id"], "title": "Synthetic weekly Journal", "documentType": "Journal",
    "parliamentNumber": 54, "publicationDate": "2025-10-15T00:00:00Z",
}


class ParserTests(unittest.TestCase):
    def test_fixture_preserves_only_printed_claims(self) -> None:
        result = parse_journal(JOURNAL, "https://journals.parliament.nz/api/data/Journal/" + JOURNAL["Id"])
        self.assertEqual(len(result["votes"]), 2)
        first = result["votes"][0]
        self.assertEqual(first["totals"], {"ayes": 4, "noes": 1, "abstentions": 1})
        self.assertEqual(first["event_date"], "2025-10-15")
        self.assertEqual(result["votes"][1]["event_date"], "2025-10-16")
        singleton = [row for row in first["participants"] if row["source_label"] == "Example-Surname"]
        self.assertEqual(singleton, [{"choice": "ayes", "entity_kind": "unknown", "source_label": "Example-Surname", "recorded_count": 1, "attribution_basis": "unresolved_singleton_label"}])
        self.assertNotIn("person_id", singleton[0])

    def test_rejects_search_schema_drift(self) -> None:
        with self.assertRaisesRegex(ValueError, "results must be an array"):
            parse_search({"results": {}, "page": 1, "pageSize": 1, "totalResults": 1})
        with self.assertRaisesRegex(ValueError, "result id"):
            parse_search({"results": [{**ROW, "id": "../bad"}], "page": 1, "pageSize": 1, "totalResults": 1})
        with self.assertRaisesRegex(ValueError, "exceeds pageSize"):
            parse_search({"results": [ROW], "page": 1, "pageSize": 0, "totalResults": 1})

    def test_does_not_infer_or_accept_prose_as_names(self) -> None:
        hostile = dict(JOURNAL)
        hostile["PublishHtml"] = hostile["PublishHtml"].replace("Example Party A 3; Example-Surname", "Example Party A 3; Example Member")
        result = parse_journal(hostile, "https://journals.parliament.nz/api/data/Journal/" + JOURNAL["Id"])
        first = result["votes"][0]
        self.assertEqual(first["participants"], [
            {"choice": "noes", "entity_kind": "party", "source_label": "Example Party B", "recorded_count": 1, "attribution_basis": "explicit_party_count"},
            {"choice": "abstentions", "entity_kind": "party", "source_label": "Example Party C", "recorded_count": 1, "attribution_basis": "explicit_party_count"},
        ])
        self.assertIn("participants_unresolved_ayes", first["warnings"])

    def test_discards_non_reconciling_participants(self) -> None:
        hostile = dict(JOURNAL)
        hostile["PublishHtml"] = hostile["PublishHtml"].replace("Example Party B 1</p><p class='jps-JVResultParty'>Abstentions", "Example Party B 9</p><p class='jps-JVResultParty'>Abstentions", 1)
        first = parse_journal(hostile, "https://journals.parliament.nz/api/data/Journal/" + JOURNAL["Id"])["votes"][0]
        self.assertFalse(any(row["choice"] == "noes" for row in first["participants"]))
        self.assertIn("participant_total_mismatch_noes", first["warnings"])

    def test_supports_captured_question_variants_and_diagnoses_unknown_phrasing(self) -> None:
        source_url = QUESTION_VARIANTS["capture_source_url"]
        parsed = parse_journal(QUESTION_VARIANTS, source_url)
        self.assertEqual(len(parsed["votes"]), 2)
        self.assertRegex(parsed["votes"][0]["question_text"], r"^On the question,")
        self.assertRegex(parsed["votes"][1]["question_text"], r"^On the question that")
        self.assertEqual(parsed["diagnostics"], [])

        hostile = dict(QUESTION_VARIANTS)
        hostile["PublishHtml"] = hostile["PublishHtml"].replace(
            "On the question that the amendment be agreed to",
            "When the amendment was put",
        )
        rejected = parse_journal(hostile, source_url)
        self.assertEqual(len(rejected["votes"]), 1)
        self.assertEqual(len(rejected["diagnostics"]), 1)
        self.assertEqual(rejected["diagnostics"][0]["kind"], "unrecognised_division_question")

    def test_ambiguous_singletons_are_not_inferred_to_be_people(self) -> None:
        for label in ("ACT", "Unknown", "Smith"):
            hostile = dict(JOURNAL)
            hostile["PublishHtml"] = hostile["PublishHtml"].replace(
                "Example Party B 1", label, 1
            )
            first = parse_journal(
                hostile,
                "https://journals.parliament.nz/api/data/Journal/" + JOURNAL["Id"],
            )["votes"][0]
            matching = [row for row in first["participants"] if row["source_label"] == label]
            self.assertEqual(len(matching), 1)
            self.assertEqual(matching[0]["entity_kind"], "unknown")
            self.assertEqual(matching[0]["attribution_basis"], "unresolved_singleton_label")
            self.assertIn("ambiguous_singleton_label_noes", first["warnings"])

    def test_unsupported_style_is_diagnostic_not_empty_evidence(self) -> None:
        hostile = dict(JOURNAL)
        hostile["PublishHtml"] = hostile["PublishHtml"].replace("jps-JVResultParty", "unknown-result")
        parsed = parse_journal(hostile, "https://journals.parliament.nz/api/data/Journal/" + JOURNAL["Id"])
        self.assertEqual(parsed["votes"], [])
        self.assertEqual(len(parsed["diagnostics"]), 2)


class CliContractTests(unittest.TestCase):
    def invoke(self, argv: list[str], fetcher):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = cli.main(argv, fetcher)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_normal_live_shape(self) -> None:
        response = {"results": [ROW], "page": 1, "pageSize": 5, "totalResults": 1}
        code, stdout, _ = self.invoke(["search", "synthetic", "--limit", "5", "--json"], lambda *_a, **_kw: response)
        payload = json.loads(stdout)
        self.assertEqual(code, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["results"][0]["id"], JOURNAL["Id"])

    def test_empty_is_successful_and_explicit(self) -> None:
        code, stdout, _ = self.invoke(["search", "absent", "--limit", "5", "--json"], lambda *_a, **_kw: EMPTY)
        payload = json.loads(stdout)
        self.assertEqual(code, 0)
        self.assertEqual(payload["data"]["results"], [])
        self.assertFalse(payload["blocked"])

    def test_blocked_is_not_empty_success(self) -> None:
        def blocked(*_a, **_kw):
            raise nzfetch.Blocked("synthetic challenge")
        code, stdout, _ = self.invoke(["search", "--json"], blocked)
        payload = json.loads(stdout)
        self.assertEqual(code, 4)
        self.assertFalse(payload["ok"])
        self.assertTrue(payload["blocked"])
        self.assertIsNone(payload["data"])

    def test_invalid_response_body_errors_are_schema_failures(self) -> None:
        failures = (
            nzfetch.FetchError("invalid JSON from https://journals.parliament.nz/api/data/search: synthetic"),
            nzfetch.InvalidCompressedBody("synthetic corrupt gzip response"),
            nzfetch.ResponseTooLarge("synthetic response exceeded limit"),
        )
        for malformed in failures:
            with self.subTest(error=type(malformed).__name__):
                code, stdout, _ = self.invoke(
                    ["search", "--json"],
                    lambda *_a, _error=malformed, **_kw: (_ for _ in ()).throw(_error),
                )
                payload = json.loads(stdout)
                self.assertEqual(code, 6)
                self.assertEqual(payload["error"]["type"], "source_schema_failure")
                self.assertFalse(payload["blocked"])

    def test_connectivity_fetch_error_remains_source_unavailable(self) -> None:
        unavailable = nzfetch.FetchError("network error: synthetic timeout")
        code, stdout, _ = self.invoke(
            ["search", "--json"],
            lambda *_a, **_kw: (_ for _ in ()).throw(unavailable),
        )
        payload = json.loads(stdout)
        self.assertEqual(code, 5)
        self.assertEqual(payload["error"]["type"], "source_unavailable")

    def test_invalid_uuid_never_fetches(self) -> None:
        fetcher = mock.Mock()
        code, stdout, _ = self.invoke(["votes", "not-a-uuid", "--json"], fetcher)
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(stdout)["error"]["code"], 2)
        fetcher.assert_not_called()


if __name__ == "__main__":
    audit = audit_skill(SKILL)
    print(json.dumps(audit, indent=2, ensure_ascii=False))
    if not audit["ok"]:
        raise SystemExit(1)
    unittest.main(verbosity=2)
