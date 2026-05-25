#!/usr/bin/env python3
"""Smoke test for the nzpost-tracking deprecation alias.

This skill is a stub. Real functionality lives in skills/nzpost. The smoke test
validates that the deprecation contract is intact: SKILL.md exists, declares
the right name, is clearly marked DEPRECATED, points users at the replacement,
and the replacement skill is actually present in the repo.
"""
from pathlib import Path
import re
import sys

SKILL_DIR = Path(__file__).parent.parent
REPO_ROOT = SKILL_DIR.parent.parent


def test(name, fn):
    try:
        ok = fn()
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
        return ok
    except Exception as e:
        print(f"[FAIL] {name}")
        print(f"  error: {e}")
        return False


def _read_skill_md():
    return (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")


def _frontmatter(text):
    m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    return m.group(1) if m else ""


def test_skill_md_exists():
    return (SKILL_DIR / "SKILL.md").is_file()


def test_frontmatter_name():
    fm = _frontmatter(_read_skill_md())
    return re.search(r"^name:\s*nzpost-tracking\s*$", fm, re.MULTILINE) is not None


def test_marked_deprecated():
    fm = _frontmatter(_read_skill_md())
    return "DEPRECATED" in fm


def test_points_to_replacement():
    return "nzpost" in _read_skill_md().lower()


def test_replacement_skill_present():
    return (REPO_ROOT / "skills" / "nzpost" / "SKILL.md").is_file()


def test_no_stale_cli():
    # Stub must not ship a fake cli.py that pretends to work.
    return not (SKILL_DIR / "scripts" / "cli.py").exists()


results = [
    test("SKILL.md exists", test_skill_md_exists),
    test("frontmatter name is nzpost-tracking", test_frontmatter_name),
    test("frontmatter marks skill as DEPRECATED", test_marked_deprecated),
    test("body points users at nzpost", test_points_to_replacement),
    test("replacement skill (nzpost) is present in repo", test_replacement_skill_present),
    test("stub does not ship a fake cli.py", test_no_stale_cli),
]

if all(results):
    print("All tests passed.")
    sys.exit(0)
else:
    print(f"{results.count(False)} test(s) failed.")
    sys.exit(1)
