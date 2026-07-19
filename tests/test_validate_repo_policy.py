import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from validate_repo_policy import valid_outbound_domain  # noqa: E402


class RepositoryPolicyTests(unittest.TestCase):
    def test_accepts_exact_lowercase_dns_host(self) -> None:
        self.assertTrue(valid_outbound_domain("api.example.govt.nz"))

    def test_rejects_partial_uppercase_and_malformed_hosts(self) -> None:
        for value in ("www", "HTTPS://example.org", "Example.org", ".example.org", "example..org", "-bad.example"):
            with self.subTest(value=value):
                self.assertFalse(valid_outbound_domain(value))


if __name__ == "__main__":
    unittest.main()
