#!/usr/bin/env python3
"""Run Agent Skills format and TheColab repository-policy validation."""

from __future__ import annotations

import argparse
import json
import sys

import validate_agent_spec
import validate_repo_policy


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", default="skills")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    try:
        skill_dirs = validate_agent_spec.resolve(args.path)
        results = []
        for skill_dir in skill_dirs:
            spec_result = validate_agent_spec.validate(skill_dir)
            policy_result = validate_repo_policy.validate(skill_dir)
            warnings = [
                *(f"Agent Skills spec: {item}" for item in spec_result["warnings"]),
                *(f"Repository policy: {item}" for item in policy_result["warnings"]),
            ]
            errors = [
                *(f"Agent Skills spec: {item}" for item in spec_result["errors"]),
                *(f"Repository policy: {item}" for item in policy_result["errors"]),
            ]
            if args.strict:
                errors.extend(f"strict: {warning}" for warning in warnings)
                warnings = []
            results.append({"skill": spec_result["skill"], "errors": errors, "warnings": warnings})
    except (OSError, ValueError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        for result in results:
            if not result["errors"] and not result["warnings"]:
                print(f"[OK] {result['skill']}")
                continue
            print(result["skill"])
            for error in result["errors"]:
                print(f"  [ERROR] {error}")
            for warning in result["warnings"]:
                print(f"  [WARN] {warning}")
        if not any(result["errors"] or result["warnings"] for result in results):
            print("[OK] All skills passed Agent Skills and repository-policy validation.")
    return 1 if any(result["errors"] for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
