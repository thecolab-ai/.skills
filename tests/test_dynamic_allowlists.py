import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DynamicAllowlistTests(unittest.TestCase):
    def run_cli(self, skill: str, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(ROOT / "skills" / skill / "scripts" / "cli.py"), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )

    def load_cli(self, skill: str):
        path = ROOT / "skills" / skill / "scripts" / "cli.py"
        spec = importlib.util.spec_from_file_location(f"{skill}_cli", path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader if spec else None)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)
        return module

    def test_akahu_tokens_cannot_be_redirected_to_caller_host(self) -> None:
        completed = self.run_cli(
            "akahu-personal",
            "accounts",
            "--base-url",
            "https://example.org/v1",
            "--json",
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("declared Akahu API host", completed.stderr)
        self.assertNotIn("missing AKAHU_APP_TOKEN", completed.stderr)

    def test_education_workbook_rejects_undeclared_network_host(self) -> None:
        completed = self.run_cli(
            "education-counts-nz",
            "workbook",
            "--url",
            "https://example.org/source.xlsx",
            "--json",
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("declared Education Counts HTTPS host", completed.stderr)

    def test_transport_workbook_rejects_undeclared_network_host(self) -> None:
        completed = self.run_cli(
            "mot-fleet-statistics-nz",
            "workbook",
            "--url",
            "https://example.org/source.xlsx",
            "--json",
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("declared Ministry of Transport HTTPS host", completed.stdout + completed.stderr)

    def test_public_page_commands_reject_undeclared_network_hosts(self) -> None:
        cases = [
            ("eventfinda-nz", ("event", "https://example.org/event"), "declared Eventfinda NZ host"),
            ("nz-comcom", ("page", "https://www.comcom.govt.nz.example.org/page", "--json"), "only fetches comcom.govt.nz"),
            ("nz-council", ("event", "https://example.org/event", "--json"), "declared Eventfinda NZ HTTPS host"),
            ("nz-grants", ("fund", "get", "https://example.org/fund", "--json"), "declared Community Matters HTTPS host"),
            ("pbtech-nz", ("product", "https://example.org/product", "--json"), "declared PB Tech NZ HTTPS host"),
            ("public-trust-grants", ("detail", "https://example.org/grant", "--json"), "declared Public Trust HTTPS host"),
        ]
        for skill, args, expected in cases:
            with self.subTest(skill=skill):
                completed = self.run_cli(skill, *args)
                output = completed.stdout + completed.stderr
                self.assertNotEqual(completed.returncode, 0)
                self.assertIn(expected, output)
                self.assertNotIn("Traceback (most recent call last)", output)

    def test_public_trust_algolia_tenant_is_pinned(self) -> None:
        cli = self.load_cli("public-trust-grants")
        cli.fetch_text = lambda *_args, **_kwargs: (
            'algoliaAppId:"ATTACKER",algoliaApiKey:"public",'
            'algoliaGrantsIndex:"grants",algoliaGrantsAlphabeticalReplica:"grants_alpha"'
        )
        with self.assertRaisesRegex(cli.UpstreamError, "outbound allowlist"):
            cli.load_config()

    def test_briscoes_klevu_tenant_is_pinned(self) -> None:
        cli = self.load_cli("briscoes-nz")
        cli.graphql = lambda *_args, **_kwargs: {
            "storeConfig": {
                "klevu_search_url": "https://attacker.example",
                "klevu_search_js_api_key": "public-browser-key",
            }
        }
        with self.assertRaises(SystemExit):
            cli.klevu_config()

    def test_dataforseo_basic_auth_redirect_is_pinned(self) -> None:
        cli = self.load_cli("dataforseo")
        handler = cli.ExactApiRedirectHandler()
        with self.assertRaisesRegex(ValueError, "declared API host"):
            handler.redirect_request(
                object(),
                None,
                302,
                "Found",
                {},
                "https://attacker.example/collect",
            )

    def test_dataforseo_api_url_rejects_userinfo_and_non_default_port(self) -> None:
        cli = self.load_cli("dataforseo")
        for url in (
            "https://user:secret@api.dataforseo.com/v3/serp",
            "https://api.dataforseo.com:444/v3/serp",
        ):
            with self.subTest(url=url):
                with self.assertRaisesRegex(ValueError, "declared API host"):
                    cli.validate_api_url(url)


if __name__ == "__main__":
    unittest.main()
