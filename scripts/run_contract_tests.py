#!/usr/bin/env python3
"""Run deterministic contract tests for every catalogue skill."""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "lib"))

from contract_test import audit_skill  # noqa: E402
from skill_metadata import iter_skill_dirs  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skills", nargs="*", help="optional skill folder names; defaults to all")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.skills:
        skill_dirs = [REPO_ROOT / "skills" / name for name in args.skills]
    else:
        skill_dirs = list(iter_skill_dirs(REPO_ROOT))
    with ThreadPoolExecutor(max_workers=min(16, max(1, len(skill_dirs)))) as executor:
        results = list(executor.map(audit_skill, skill_dirs))
    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        for result in results:
            state = "PASS" if result["ok"] else "FAIL"
            print(f"[{state}] {result['skill']}")
            for error in result["errors"]:
                print(f"  [ERROR] {error}")
            for warning in result["warnings"]:
                print(f"  [WARN] {warning}")
        passed = sum(1 for result in results if result["ok"])
        print(f"PASS: {passed}, FAIL: {len(results) - passed}")
    return 1 if any(not result["ok"] for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
