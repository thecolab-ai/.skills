import json
import os
import shutil
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

    def test_installed_skill_clis_do_not_require_source_specific_repository_libs(self) -> None:
        """Installed skills may use the common runtime, but must bundle source parsers."""

        with tempfile.TemporaryDirectory() as tmp:
            temporary_root = Path(tmp)
            target = temporary_root / "installed"
            installed_skills = []
            for manifest_path in sorted((ROOT / "packs").glob("*.json")):
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                installed = self.run_installer(
                    manifest["name"], "--target", str(target)
                )
                self.assertEqual(installed.returncode, 0, installed.stderr)
                installed_skills.extend(manifest["skills"])

            # Current CLIs deliberately support the repository's common HTTP/result
            # runtime. Do not copy any source-specific parser from top-level lib/:
            # those must resolve from each independently installed skill folder.
            common_runtime = temporary_root / "lib"
            common_runtime.mkdir()
            for module in ("nzfetch.py", "result_contract.py"):
                shutil.copy2(ROOT / "lib" / module, common_runtime / module)

            environment = os.environ.copy()
            environment.pop("PYTHONPATH", None)
            failures = []
            for skill in installed_skills:
                cli = target / skill / "scripts" / "cli.py"
                completed = subprocess.run(
                    [sys.executable, str(cli), "--help"],
                    cwd=temporary_root,
                    env=environment,
                    text=True,
                    capture_output=True,
                    timeout=10,
                    check=False,
                )
                if completed.returncode != 0:
                    diagnostic = (completed.stderr or completed.stdout).strip().splitlines()
                    failures.append(f"{skill}: {diagnostic[-1] if diagnostic else 'no diagnostic'}")

            self.assertEqual(
                failures,
                [],
                "installed skill CLIs imported source-specific top-level lib modules:\n"
                + "\n".join(failures),
            )


if __name__ == "__main__":
    unittest.main()
