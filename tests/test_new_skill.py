import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCAFFOLD = ROOT / "scripts" / "new_skill.py"
VALIDATE = ROOT / "scripts" / "validate_skill.py"


class NewSkillScaffoldTests(unittest.TestCase):
    def test_all_variants_generate_scaffolds_with_only_explicit_completion_gates(self) -> None:
        variants = (
            "public-api",
            "public-download",
            "html-readonly",
            "authenticated-personal",
            "documentation-workflow",
        )
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            for variant in variants:
                name = f"fixture-{variant}"
                created = subprocess.run(
                    [
                        sys.executable,
                        str(SCAFFOLD),
                        name,
                        "--variant",
                        variant,
                        "--path",
                        str(parent),
                        "--description",
                        f"Query the fixture source for {variant} records. Use for scaffold contract tests.",
                        "--source-owner",
                        "Fixture Agency",
                        "--source-url",
                        "https://fixture.example.govt.nz/api",
                    ],
                    cwd=ROOT,
                    text=True,
                    capture_output=True,
                    timeout=15,
                    check=False,
                )
                self.assertEqual(created.returncode, 0, created.stderr)
                validated = subprocess.run(
                    [sys.executable, str(VALIDATE), str(parent / name), "--strict"],
                    cwd=ROOT,
                    text=True,
                    capture_output=True,
                    timeout=15,
                    check=False,
                )
                self.assertEqual(validated.returncode, 1, validated.stdout + validated.stderr)
                self.assertIn("thecolab.health=untested is a scaffold gate", validated.stdout)
                self.assertIn(
                    "replace the unimplemented scaffold source fixture",
                    validated.stdout,
                )
                env = os.environ.copy()
                env["PYTHONPATH"] = str(ROOT / "lib")
                contracted = subprocess.run(
                    [sys.executable, str(parent / name / "scripts" / "test_contract.py")],
                    cwd=ROOT,
                    text=True,
                    capture_output=True,
                    timeout=15,
                    check=False,
                    env=env,
                )
                self.assertEqual(contracted.returncode, 0, contracted.stdout + contracted.stderr)
                smoked = subprocess.run(
                    [sys.executable, str(parent / name / "scripts" / "smoke_test.py")],
                    cwd=ROOT,
                    text=True,
                    capture_output=True,
                    timeout=15,
                    check=False,
                )
                self.assertEqual(smoked.returncode, 0, smoked.stdout + smoked.stderr)
                self.assertIn("[PASS] fixture", smoked.stdout)
                self.assertIn("[SKIP] source parser", smoked.stdout)

    def test_invalid_source_does_not_destroy_existing_target_with_force(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "existing-skill"
            target.mkdir()
            marker = target / "keep.txt"
            marker.write_text("keep", encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCAFFOLD),
                    "existing-skill",
                    "--variant",
                    "public-api",
                    "--path",
                    tmp,
                    "--force",
                    "--description",
                    "A fixture description that remains valid.",
                    "--source-owner",
                    "Fixture Agency",
                    "--source-url",
                    "not-a-url",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                timeout=15,
                check=False,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertEqual(marker.read_text(encoding="utf-8"), "keep")

    def test_force_cannot_delete_external_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "existing-skill"
            target.mkdir()
            marker = target / "keep.txt"
            marker.write_text("keep", encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCAFFOLD),
                    "existing-skill",
                    "--variant",
                    "public-api",
                    "--path",
                    tmp,
                    "--force",
                    "--description",
                    "Query the fixture source. Use for a scaffold safety test.",
                    "--source-owner",
                    "Fixture Agency",
                    "--source-url",
                    "https://fixture.example.govt.nz/api",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                timeout=15,
                check=False,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertEqual(marker.read_text(encoding="utf-8"), "keep")


if __name__ == "__main__":
    unittest.main()
