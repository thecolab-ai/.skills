import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts" / "install_pack.py"


class InstallPackTests(unittest.TestCase):
    def run_installer(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(INSTALLER), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=15,
            check=False,
        )

    def test_force_replaces_the_selected_skill_directory_without_stale_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "installed"
            first = self.run_installer("artifact-tools", "--target", str(target))
            self.assertEqual(first.returncode, 0, first.stderr)
            stale = target / "pptx" / "stale.txt"
            stale.write_text("stale", encoding="utf-8")

            refused = self.run_installer("artifact-tools", "--target", str(target))
            self.assertNotEqual(refused.returncode, 0)
            self.assertTrue(stale.exists())

            replaced = self.run_installer("artifact-tools", "--target", str(target), "--force")
            self.assertEqual(replaced.returncode, 0, replaced.stderr)
            self.assertFalse(stale.exists())
            self.assertTrue((target / "pptx" / "SKILL.md").is_file())

    def test_dry_run_does_not_create_the_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "preview"
            completed = self.run_installer("artifact-tools", "--target", str(target), "--dry-run")
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertFalse(target.exists())

    def test_repository_skills_tree_is_never_an_install_target(self) -> None:
        completed = self.run_installer(
            "artifact-tools",
            "--target",
            str(ROOT / "skills"),
            "--force",
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("inside the source repository", completed.stderr)

    def test_repository_root_is_never_an_install_target(self) -> None:
        completed = self.run_installer(
            "artifact-tools",
            "--target",
            str(ROOT),
            "--force",
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("inside the source repository", completed.stderr)

    def test_pack_name_cannot_traverse_outside_manifest_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            completed = self.run_installer("../skills", "--target", tmp)
        self.assertEqual(completed.returncode, 2)
        self.assertIn("invalid choice", completed.stderr)


if __name__ == "__main__":
    unittest.main()
