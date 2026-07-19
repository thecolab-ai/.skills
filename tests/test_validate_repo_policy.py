import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from validate_repo_policy import (  # noqa: E402
    SHARED_RUNTIME_MODULES,
    valid_outbound_domain,
    validate_shared_lib,
)


class RepositoryPolicyTests(unittest.TestCase):
    def test_accepts_exact_lowercase_dns_host(self) -> None:
        self.assertTrue(valid_outbound_domain("api.example.govt.nz"))

    def test_rejects_partial_uppercase_and_malformed_hosts(self) -> None:
        for value in ("www", "HTTPS://example.org", "Example.org", ".example.org", "example..org", "-bad.example"):
            with self.subTest(value=value):
                self.assertFalse(valid_outbound_domain(value))

    def test_rejects_source_specific_module_in_top_level_lib(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            lib_dir = Path(temporary)
            (lib_dir / "pharmac_schedule.py").write_text("", encoding="utf-8")

            self.assertEqual(
                validate_shared_lib(lib_dir),
                ["top-level lib Python module is not an allowlisted shared runtime module: pharmac_schedule.py"],
            )

    def test_accepts_only_explicit_shared_runtime_modules(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            lib_dir = Path(temporary)
            for module in SHARED_RUNTIME_MODULES:
                (lib_dir / module).write_text("", encoding="utf-8")

            self.assertEqual(validate_shared_lib(lib_dir), [])


if __name__ == "__main__":
    unittest.main()
