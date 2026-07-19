import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("security_check", ROOT / "scripts" / "security_check.py")
assert SPEC and SPEC.loader
SECURITY_CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SECURITY_CHECK)


class SecurityCheckTests(unittest.TestCase):
    def test_rejects_environment_credential_fallback(self) -> None:
        errors = SECURITY_CHECK.credential_default_errors(
            Path("skills/example/scripts/cli.py"),
            'import os\nKEY = os.environ.get("EXAMPLE_API_KEY", "committed-secret")\n',
        )
        self.assertEqual(len(errors), 1)
        self.assertIn("EXAMPLE_API_KEY", errors[0])

    def test_rejects_environment_username_fallback(self) -> None:
        errors = SECURITY_CHECK.credential_default_errors(
            Path("skills/example/scripts/cli.py"),
            'import os\nUSERNAME = os.environ.get("EXAMPLE_API_USERNAME", "bundled-user")\n',
        )
        self.assertEqual(len(errors), 1)
        self.assertIn("EXAMPLE_API_USERNAME", errors[0])

    def test_allows_empty_environment_default(self) -> None:
        errors = SECURITY_CHECK.credential_default_errors(
            Path("skills/example/scripts/cli.py"),
            'import os\nKEY = os.environ.get("EXAMPLE_API_KEY", "")\n',
        )
        self.assertEqual(errors, [])

    def test_rejects_unapproved_top_level_credential_constant(self) -> None:
        errors = SECURITY_CHECK.credential_default_errors(
            Path("skills/example/scripts/cli.py"),
            'API_PASSWORD = "committed-password"\n',
        )
        self.assertEqual(len(errors), 1)
        self.assertIn("API_PASSWORD", errors[0])

    def test_public_browser_key_exception_is_exact(self) -> None:
        content = 'DEFAULT_KLEVU_API_KEY = "public-browser-search-key"\n'
        allowed = SECURITY_CHECK.credential_default_errors(
            Path("skills/briscoes-nz/scripts/cli.py"), content
        )
        rejected = SECURITY_CHECK.credential_default_errors(
            Path("skills/other/scripts/cli.py"), content
        )
        self.assertEqual(allowed, [])
        self.assertEqual(len(rejected), 1)


if __name__ == "__main__":
    unittest.main()
