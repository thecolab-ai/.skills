#!/usr/bin/env python3
"""Smoke test for the colab-course-publisher validator."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
CLI = SKILL_ROOT / "scripts" / "cli.py"


def write(path: Path, content: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def build_fixture(root: Path) -> None:
    write(
        root / "courses" / "sample-course" / "course.json",
        json.dumps(
            {
                "id": "sample-course",
                "title": "Sample Course",
                "description": "A small supported course.",
                "estimatedDuration": "30 minutes",
                "coverImage": "cover.png",
                "welcomePath": "welcome.md",
                "modules": ["sample-module"],
            },
            indent=2,
        ),
    )
    write(root / "courses" / "sample-course" / "welcome.md", "# Welcome\n\nStart here.\n")
    write(root / "courses" / "sample-course" / "assets" / "cover.png", b"png")
    write(
        root / "modules" / "sample-module" / "manifest.json",
        json.dumps(
            {
                "id": "sample-module",
                "title": "Sample Module",
                "description": "A module with media and a quiz.",
                "lessons": [
                    {"id": "intro", "title": "Intro", "type": "content", "markdownPath": "intro.md"},
                    {"id": "quiz", "title": "Quiz", "type": "quiz", "quizPath": "quiz.json"},
                ],
            },
            indent=2,
        ),
    )
    write(
        root / "modules" / "sample-module" / "intro.md",
        """# Intro

![Diagram](./assets/diagram.webp)

<video controls playsinline preload="metadata">
  <source src="./assets/intro.mp4" type="video/mp4">
</video>

:::widget readiness-check
title: Readiness check
:::
""",
    )
    write(root / "modules" / "sample-module" / "assets" / "diagram.webp", b"webp")
    write(root / "modules" / "sample-module" / "assets" / "intro.mp4", b"mp4")
    write(
        root / "modules" / "sample-module" / "quiz.json",
        json.dumps(
            {
                "title": "Sample Quiz",
                "type": "quiz",
                "passingScore": 70,
                "questions": [
                    {
                        "id": "q1",
                        "questionNumber": 1,
                        "type": "MULTIPLE_CHOICE",
                        "question": "Which option is correct?",
                        "answers": [
                            {"id": "q1_a", "text": "A", "correct": False},
                            {"id": "q1_b", "text": "B", "correct": True},
                        ],
                    },
                    {
                        "id": "q2",
                        "questionNumber": 2,
                        "type": "MULTIPLE_RESPONSE",
                        "question": "Select all correct options.",
                        "answers": [
                            {"id": "q2_a", "text": "A", "correct": True},
                            {"id": "q2_b", "text": "B", "correct": True},
                            {"id": "q2_c", "text": "C", "correct": False},
                        ],
                    },
                    {
                        "id": "q3",
                        "questionNumber": 3,
                        "type": "MATCHING",
                        "question": "Match the pairs.",
                        "answers": [
                            {"id": "q3_a", "text": "Left A", "matchText": "Right A", "correct": True},
                            {"id": "q3_b", "text": "Left B", "matchText": "Right B", "correct": True},
                        ],
                    },
                ],
            },
            indent=2,
        ),
    )
    write(
        root / "widgets" / "readiness-check.html",
        """<!doctype html>
<html><body><main>Ready?</main><script>
function notify() {
  parent.postMessage({ type: 'widget-ready' }, '*');
  parent.postMessage({ type: 'widget-resize', height: document.body.scrollHeight }, '*');
}
window.addEventListener('load', notify);
</script></body></html>
""",
    )


def main() -> int:
    outline_result = run_cli("outline", "--json")
    if outline_result.returncode != 0:
        print(outline_result.stderr or outline_result.stdout)
        return 1
    parsed = json.loads(outline_result.stdout)
    if "recommended_structure" not in parsed:
        print("outline JSON missing recommended_structure")
        return 1

    temp_root = Path(tempfile.mkdtemp(prefix="colab-course-publisher-"))
    bad_root = temp_root.parent / f"{temp_root.name}-bad"
    try:
        build_fixture(temp_root)
        ok_result = run_cli("validate", str(temp_root), "--json")
        if ok_result.returncode != 0:
            print(ok_result.stdout)
            print(ok_result.stderr)
            return 1
        ok_payload = json.loads(ok_result.stdout)
        if not ok_payload.get("ok"):
            print(ok_result.stdout)
            return 1
        course_result = run_cli("validate", str(temp_root / "courses" / "sample-course"), "--json")
        if course_result.returncode != 0:
            print(course_result.stdout)
            print(course_result.stderr)
            return 1
        course_payload = json.loads(course_result.stdout)
        checked = course_payload.get("checked", [])
        if "module:sample-module" not in checked:
            print("single-course validation did not follow referenced module")
            print(course_result.stdout)
            return 1

        shutil.copytree(temp_root, bad_root)
        quiz_path = bad_root / "modules" / "sample-module" / "quiz.json"
        quiz = json.loads(quiz_path.read_text(encoding="utf-8"))
        quiz["questions"][0]["answers"][1]["isCorrect"] = True
        quiz["questions"][0]["answers"][1].pop("correct")
        quiz_path.write_text(json.dumps(quiz, indent=2), encoding="utf-8")
        bad_result = run_cli("validate", str(bad_root / "courses" / "sample-course"), "--json")
        if bad_result.returncode == 0:
            print("bad fixture unexpectedly passed")
            print(bad_result.stdout)
            return 1
        bad_payload = json.loads(bad_result.stdout)
        if bad_payload["summary"]["errors"] < 1:
            print("bad fixture did not report an error")
            print(bad_result.stdout)
            return 1
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
        shutil.rmtree(bad_root, ignore_errors=True)

    print("colab-course-publisher smoke test passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
