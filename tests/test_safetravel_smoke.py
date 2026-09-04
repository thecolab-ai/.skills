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


CANONICAL_DESTINATION_URL = (
    "https://www.safetravel.govt.nz/destinations/australia"
)
CANONICAL_SITEMAP_URL = "https://www.safetravel.govt.nz/sitemap.xml"


def advice_payload() -> dict:
    return {
        "schema_version": "1",
        "ok": True,
        "source": {
            "url": CANONICAL_DESTINATION_URL,
            "retrieved_at": "2026-09-04T00:00:00Z",
            "page_updated": "13 May 2026",
        },
        "query": {"command": "advice", "destination": "australia"},
        "data": {
            "kind": "destination_advice",
            "destination": {
                "name": "Australia",
                "slug": "australia",
                "url": CANONICAL_DESTINATION_URL,
            },
            "advice_level": {"number": 1, "title": "Exercise normal precautions"},
        },
        "warnings": ["Travel advice can change."],
    }


def search_payload() -> dict:
    return {
        "source": {
            "url": CANONICAL_SITEMAP_URL,
            "retrieved_at": "2026-09-04T00:00:00Z",
        },
        "query": {"command": "search", "text": "australia", "limit": 5},
        "data": {
            "kind": "destination_search",
            "sitemap_url": CANONICAL_SITEMAP_URL,
            "destinations": [
                {
                    "name": "Australia",
                    "slug": "australia",
                    "url": CANONICAL_DESTINATION_URL,
                }
            ],
        },
    }


class SafeTravelSmokeTests(unittest.TestCase):
    def test_live_advice_accepts_exact_australia_identity(self) -> None:
        smoke = load_smoke()
        with mock.patch.object(
            smoke,
            "run",
            return_value=completed(0, stdout=json.dumps(advice_payload())),
        ), contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(smoke.check_live_advice())

    def test_live_advice_rejects_each_wrong_identity_field(self) -> None:
        mutations = {
            "source URL prefix attack": lambda payload: payload["source"].update(
                url=CANONICAL_DESTINATION_URL + "-evil"
            ),
            "query command": lambda payload: payload["query"].update(command="search"),
            "query destination": lambda payload: payload["query"].update(
                destination="wrong"
            ),
            "data kind": lambda payload: payload["data"].update(
                kind="destination_search"
            ),
            "destination name": lambda payload: payload["data"]["destination"].update(
                name="Wrong"
            ),
            "destination slug": lambda payload: payload["data"]["destination"].update(
                slug="wrong"
            ),
            "destination URL": lambda payload: payload["data"]["destination"].update(
                url=CANONICAL_DESTINATION_URL + "-evil"
            ),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                smoke = load_smoke()
                payload = advice_payload()
                mutate(payload)
                with mock.patch.object(
                    smoke,
                    "run",
                    return_value=completed(0, stdout=json.dumps(payload)),
                ), contextlib.redirect_stdout(io.StringIO()):
                    self.assertFalse(smoke.check_live_advice())

    def test_live_search_accepts_exact_australia_identity(self) -> None:
        smoke = load_smoke()
        with mock.patch.object(
            smoke,
            "run",
            return_value=completed(0, stdout=json.dumps(search_payload())),
        ), contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(smoke.check_live_search())

    def test_live_search_rejects_each_wrong_identity_field(self) -> None:
        mutations = {
            "source sitemap URL": lambda payload: payload["source"].update(
                url=CANONICAL_SITEMAP_URL + ".evil"
            ),
            "query command": lambda payload: payload["query"].update(command="advice"),
            "query text": lambda payload: payload["query"].update(text="wrong"),
            "query limit": lambda payload: payload["query"].update(limit=4),
            "data sitemap URL": lambda payload: payload["data"].update(
                sitemap_url=CANONICAL_SITEMAP_URL + ".evil"
            ),
            "destination name": lambda payload: payload["data"]["destinations"][
                0
            ].update(name="Wrong"),
            "destination slug": lambda payload: payload["data"]["destinations"][
                0
            ].update(slug="wrong"),
            "destination URL": lambda payload: payload["data"]["destinations"][
                0
            ].update(url=CANONICAL_DESTINATION_URL + "-evil"),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                smoke = load_smoke()
                payload = search_payload()
                mutate(payload)
                with mock.patch.object(
                    smoke,
                    "run",
                    return_value=completed(0, stdout=json.dumps(payload)),
                ), contextlib.redirect_stdout(io.StringIO()):
                    self.assertFalse(smoke.check_live_search())

    def test_advice_outage_does_not_prevent_search_probe(self) -> None:
        smoke = load_smoke()
        stdout = io.StringIO()
        with (
            mock.patch.object(
                smoke,
                "run",
                side_effect=[
                    completed(0, stdout="[PASS] fixture parser assertions"),
                    completed(0, stdout="usage: cli.py {search,advice}"),
                    completed(4, stderr="source unavailable"),
                    completed(0, stdout=json.dumps(search_payload())),
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