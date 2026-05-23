#!/usr/bin/env python3
"""Validate one skill or all skills in the repo."""

import argparse
import json
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

FORBIDDEN_FILES = {"README.md", "CHANGELOG.md", "NOTES.md", "IDEAS.md"}
TEXT_EXTENSIONS = {".md", ".ts", ".js", ".json", ".yaml", ".yml", ".sh", ".txt"}
MAX_SKILL_MD_LINES = 250
LINK_PATTERN = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
PLACEHOLDER_PATTERNS = [
    re.compile(r"^\s*name:\s*your-skill-name\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*description:\s*Describe what this skill does", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*State the capability in 1 to 2 lines\.\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*- Add concrete trigger examples\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r'^\s*echo "Replace this with a real smoke test"\s*$', re.IGNORECASE | re.MULTILINE),
]


def display_path(path: Path) -> str:
    try:
        rel = path.relative_to(REPO_ROOT)
        return str(rel)
    except ValueError:
        return str(path)


def list_skill_dirs(directory: Path) -> list:
    results = []
    for entry in directory.iterdir():
        if entry.is_dir() and (entry / "SKILL.md").exists():
            results.append(entry)
    return results


def walk(directory: Path) -> list:
    results = []
    for entry in directory.iterdir():
        if entry.is_dir():
            results.extend(walk(entry))
        else:
            results.append(entry)
    return results


# ---------------------------------------------------------------------------
# Minimal YAML frontmatter parser (stdlib only — no PyYAML needed)
# Supports only the two scalar string keys this validator cares about:
# `name` and `description`.  Multi-line values use the YAML block-scalar
# style (|, |-) or simple quoted/unquoted strings.
# ---------------------------------------------------------------------------

def _parse_simple_yaml(text: str) -> dict:
    """Parse a flat YAML mapping with string scalar values (no nesting)."""
    result = {}
    # Split into logical lines, handling block scalars
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        # Skip blank lines and comments
        if not line.strip() or line.strip().startswith("#"):
            i += 1
            continue
        # Match key: value or key: | (block scalar)
        m = re.match(r'^([A-Za-z_][A-Za-z0-9_-]*):\s*(.*)', line)
        if not m:
            i += 1
            continue
        key = m.group(1)
        raw_value = m.group(2).strip()

        if raw_value in ("|", "|-", ">", ">-"):
            # Block scalar — collect indented continuation lines
            block_lines = []
            i += 1
            while i < len(lines) and (lines[i].startswith("  ") or lines[i].strip() == ""):
                block_lines.append(lines[i][2:] if lines[i].startswith("  ") else "")
                i += 1
            value = "\n".join(block_lines).strip()
        else:
            # Inline value — strip optional surrounding quotes
            if (raw_value.startswith('"') and raw_value.endswith('"')) or \
               (raw_value.startswith("'") and raw_value.endswith("'")):
                value = raw_value[1:-1]
            else:
                value = raw_value
            i += 1

        result[key] = value

    return result


def extract_frontmatter(content: str) -> dict:
    match = re.match(r"^---\n([\s\S]*?)\n---", content)
    if not match:
        raise ValueError("Missing or invalid frontmatter")
    raw = match.group(1)
    parsed = _parse_simple_yaml(raw)
    if not isinstance(parsed, dict):
        raise ValueError("Frontmatter must be a YAML object")
    return parsed


def resolve_skill_dirs(target_path: str) -> list:
    absolute = (REPO_ROOT / target_path).resolve()
    if not absolute.exists():
        raise FileNotFoundError(f"Path not found: {absolute}")

    # Direct skill dir
    if (absolute / "SKILL.md").exists():
        return [absolute]

    # Try <path>/skills/ first
    skills_dir = (
        absolute
        if (str(absolute).endswith("/skills") or absolute == REPO_ROOT / "skills")
        else absolute / "skills"
    )
    if skills_dir.exists():
        skill_dirs = list_skill_dirs(skills_dir)
        if skill_dirs:
            return skill_dirs

    # Try direct children
    direct_skill_dirs = list_skill_dirs(absolute)
    if direct_skill_dirs:
        return direct_skill_dirs

    raise FileNotFoundError(f"No skill directory found at: {absolute}")


def validate_frontmatter(frontmatter: dict, result: dict) -> None:
    allowed_keys = {"name", "description"}
    extra_keys = [k for k in frontmatter if k not in allowed_keys]
    if extra_keys:
        result["errors"].append(f"Unsupported frontmatter keys: {', '.join(extra_keys)}")

    name = frontmatter.get("name")
    if not isinstance(name, str) or not name.strip():
        result["errors"].append("Frontmatter must include a non-empty 'name'")
    else:
        if (
            not re.match(r"^[a-z0-9-]+$", name)
            or name.startswith("-")
            or name.endswith("-")
            or "--" in name
        ):
            result["errors"].append("'name' must be lowercase hyphen-case")

    description = frontmatter.get("description")
    if not isinstance(description, str) or not description.strip():
        result["errors"].append("Frontmatter must include a non-empty 'description'")
    else:
        if len(description) > 1024:
            result["errors"].append(
                "Description is too long, keep it under 1024 characters"
            )
        lower = description.lower()
        if (
            "helps with" in lower
            or lower.strip() == "nz data skill"
            or "stuff" in lower
        ):
            result["warnings"].append(
                "Description looks vague, make the trigger surface more specific"
            )


def validate_links(skill_dir: Path, file_path: Path, content: str, result: dict) -> None:
    for match in LINK_PATTERN.finditer(content):
        target = match.group(1)
        if not target:
            continue
        if (
            target.startswith("http://")
            or target.startswith("https://")
            or target.startswith("mailto:")
            or target.startswith("#")
        ):
            continue
        resolved_target = (file_path.parent / target).resolve()
        skill_dir_resolved = skill_dir.resolve()
        try:
            resolved_target.relative_to(skill_dir_resolved)
        except ValueError:
            rel = file_path.relative_to(skill_dir)
            result["errors"].append(
                f"Link escapes skill root in {rel}: {target}"
            )
            continue
        if not resolved_target.exists():
            rel = file_path.relative_to(skill_dir)
            result["errors"].append(
                f"Broken local link in {rel}: {target}"
            )


def validate_skill(skill_dir: Path) -> dict:
    result = {
        "skill": display_path(skill_dir),
        "errors": [],
        "warnings": [],
    }

    skill_md_path = skill_dir / "SKILL.md"
    skill_md = skill_md_path.read_text(encoding="utf-8")

    try:
        frontmatter = extract_frontmatter(skill_md)
        validate_frontmatter(frontmatter, result)
    except Exception as exc:
        result["errors"].append(str(exc))

    line_count = len(re.split(r"\r?\n", skill_md))
    if line_count > MAX_SKILL_MD_LINES:
        result["warnings"].append(
            f"SKILL.md is long, consider splitting detail into references/ "
            f"({line_count} lines)"
        )

    if (skill_dir / "references").exists() and "references/" not in skill_md:
        result["warnings"].append(
            "references/ exists but SKILL.md does not mention it"
        )
    if (skill_dir / "scripts").exists() and "scripts/" not in skill_md:
        result["warnings"].append(
            "scripts/ exists but SKILL.md does not mention it"
        )

    files = walk(skill_dir)
    for file_path in files:
        rel_path = file_path.relative_to(skill_dir)
        base = rel_path.name
        if base in FORBIDDEN_FILES:
            result["errors"].append(f"Forbidden clutter file: {rel_path}")

        ext = file_path.suffix.lower()
        if ext not in TEXT_EXTENSIONS and file_path.name != "SKILL.md":
            continue

        try:
            content = file_path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, PermissionError):
            continue

        validate_links(skill_dir, file_path, content, result)
        for pattern in PLACEHOLDER_PATTERNS:
            if pattern.search(content):
                result["errors"].append(
                    f"Placeholder scaffold text found in {rel_path}"
                )
                break

    return result


def print_human(results: list) -> None:
    error_count = 0
    warning_count = 0

    for result in results:
        if not result["errors"] and not result["warnings"]:
            print(f"[OK] {result['skill']}")
            continue

        print(f"\n{result['skill']}")
        for error in result["errors"]:
            print(f"  [ERROR] {error}")
            error_count += 1
        for warning in result["warnings"]:
            print(f"  [WARN] {warning}")
            warning_count += 1

    if error_count == 0 and warning_count == 0:
        print("[OK] All skills passed validation with no issues.")
    elif error_count == 0:
        print(f"\n[OK] Validation passed with {warning_count} warning(s).")


def main():
    parser = argparse.ArgumentParser(
        prog="validate-skill",
        description="Validate one skill or all skills in the repo",
    )
    parser.add_argument(
        "path",
        nargs="?",
        default="skills",
        help="skill path or repo root (default: skills)",
    )
    parser.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        default=False,
        help="print machine-readable output",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        default=False,
        help="treat warnings as errors",
    )
    args = parser.parse_args()

    try:
        skill_dirs = resolve_skill_dirs(args.path)
        results = [validate_skill(d) for d in skill_dirs]
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        sys.exit(1)

    if args.strict:
        for result in results:
            result["errors"].extend(
                f"Strict mode: {w}" for w in result["warnings"]
            )
            result["warnings"] = []

    if args.json_output:
        print(json.dumps(results, indent=2))
    else:
        print_human(results)

    has_errors = any(result["errors"] for result in results)
    sys.exit(1 if has_errors else 0)


if __name__ == "__main__":
    main()
