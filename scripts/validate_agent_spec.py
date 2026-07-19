#!/usr/bin/env python3
"""Validate only the public Agent Skills SKILL.md format specification."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "lib"))

from skill_metadata import AGENT_SPEC_FIELDS, FrontmatterError, iter_skill_dirs, load_skill  # noqa: E402


NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def resolve(path: str) -> list[Path]:
    target = (REPO_ROOT / path).resolve()
    if (target / "SKILL.md").is_file():
        return [target]
    if target.name == "skills":
        return list(iter_skill_dirs(target))
    if (target / "skills").is_dir():
        return list(iter_skill_dirs(target))
    raise FileNotFoundError(f"no skill or skills directory at {target}")


def validate(skill_dir: Path) -> dict[str, object]:
    result: dict[str, object] = {
        "skill": display_path(skill_dir),
        "errors": [],
        "warnings": [],
    }
    errors: list[str] = result["errors"]  # type: ignore[assignment]
    warnings: list[str] = result["warnings"]  # type: ignore[assignment]
    try:
        document = load_skill(skill_dir)
    except (OSError, FrontmatterError) as exc:
        errors.append(str(exc))
        return result

    fields = document.fields
    unknown = sorted(set(fields) - AGENT_SPEC_FIELDS)
    if unknown:
        errors.append(f"unsupported Agent Skills frontmatter fields: {', '.join(unknown)}")

    name = fields.get("name")
    if not isinstance(name, str) or not name:
        errors.append("name must be a non-empty string")
    else:
        if len(name) > 64:
            errors.append("name must be at most 64 characters")
        if not NAME_PATTERN.fullmatch(name):
            errors.append("name must use lowercase letters, digits, and single hyphens")
        if name != skill_dir.name:
            errors.append(f"name {name!r} must match parent directory {skill_dir.name!r}")

    description = fields.get("description")
    if not isinstance(description, str) or not description.strip():
        errors.append("description must be a non-empty string")
    elif len(description) > 1024:
        errors.append("description must be at most 1024 characters")

    license_value = fields.get("license")
    if license_value is not None and (not isinstance(license_value, str) or not license_value.strip()):
        errors.append("license must be a non-empty string when provided")

    compatibility = fields.get("compatibility")
    if compatibility is not None:
        if not isinstance(compatibility, str) or not compatibility.strip():
            errors.append("compatibility must be a non-empty string when provided")
        elif len(compatibility) > 500:
            errors.append("compatibility must be at most 500 characters")

    metadata = fields.get("metadata")
    if metadata is not None:
        if not isinstance(metadata, dict):
            errors.append("metadata must be a string-to-string mapping")
        else:
            for key, value in metadata.items():
                if not isinstance(key, str) or not isinstance(value, str):
                    errors.append("metadata must contain only string keys and string values")
                    break

    allowed_tools = fields.get("allowed-tools")
    if allowed_tools is not None and (not isinstance(allowed_tools, str) or not allowed_tools.strip()):
        errors.append("allowed-tools must be a non-empty space-separated string when provided")

    if not document.body.strip():
        errors.append("SKILL.md body must not be empty")
    line_count = len((skill_dir / "SKILL.md").read_text(encoding="utf-8").splitlines())
    if line_count > 500:
        warnings.append(f"SKILL.md has {line_count} lines; the specification recommends fewer than 500")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", default="skills")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    try:
        results = [validate(path) for path in resolve(args.path)]
    except (OSError, FileNotFoundError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    if args.strict:
        for result in results:
            result["errors"].extend(f"strict: {warning}" for warning in result["warnings"])
            result["warnings"] = []
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
    return 1 if any(result["errors"] for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
