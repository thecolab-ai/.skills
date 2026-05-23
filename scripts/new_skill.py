#!/usr/bin/env python3
"""Scaffold a new skill from an opinionated template."""

import argparse
import os
import re
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = REPO_ROOT / "templates"
ALLOWED_VARIANTS = ("minimal", "cli-workflow", "tool-wrapper")


def normalize_name(raw: str) -> str:
    name = raw.strip().lower()
    name = re.sub(r"[^a-z0-9]+", "-", name)
    name = re.sub(r"-{2,}", "-", name)
    name = name.strip("-")
    return name


def title_case(name: str) -> str:
    return " ".join(part.capitalize() for part in name.split("-"))


def default_description(variant: str) -> str:
    if variant == "cli-workflow":
        return (
            "Describe what this skill does and when to use it. "
            "Include concrete triggers, data sources, inputs, or file types."
        )
    elif variant == "tool-wrapper":
        return (
            "Describe the specific tool or API this skill wraps and when to use it. "
            "Include concrete triggers, commands, or failure cases."
        )
    else:
        return (
            "Describe what this skill does and when to use it. "
            "Include concrete trigger phrases, task types, or file types."
        )


def render_template(content: str, values: dict) -> str:
    def replacer(match):
        key = match.group(1)
        return values.get(key, match.group(0))

    return re.sub(r"\{\{([A-Z_]+)\}\}", replacer, content)


def walk(directory: Path) -> list:
    results = []
    for entry in directory.iterdir():
        if entry.is_dir():
            results.extend(walk(entry))
        else:
            results.append(entry)
    return results


def display_path(path: Path) -> str:
    try:
        rel = path.relative_to(REPO_ROOT)
        return str(rel)
    except ValueError:
        return str(path)


def scaffold_skill(name: str, variant: str, parent_path: str, force: bool) -> None:
    name = normalize_name(name)
    if not name:
        raise ValueError("Skill name must include at least one letter or digit.")
    if len(name) > 64:
        raise ValueError(f"Skill name is too long ({len(name)} > 64).")

    source_dir = TEMPLATES_DIR / f"skill-{variant}"
    if not source_dir.exists():
        raise FileNotFoundError(f"Template not found: {source_dir}")

    target_dir = (REPO_ROOT / parent_path / name).resolve()
    if target_dir.exists():
        if not force:
            raise FileExistsError(f"Target already exists: {target_dir}")
        shutil.rmtree(target_dir)

    target_dir.mkdir(parents=True, exist_ok=True)
    shutil.copytree(str(source_dir), str(target_dir), dirs_exist_ok=True)

    values = {
        "SKILL_NAME": name,
        "SKILL_TITLE": title_case(name),
        "DESCRIPTION": default_description(variant),
    }

    for file_path in walk(target_dir):
        try:
            content = file_path.read_text(encoding="utf-8")
            file_path.write_text(render_template(content, values), encoding="utf-8")
        except (UnicodeDecodeError, PermissionError):
            pass
        if file_path.suffix == ".sh":
            current_mode = file_path.stat().st_mode
            file_path.chmod(current_mode | 0o755)

    print(f"[OK] Created {variant} skill scaffold at {target_dir}")
    print(
        f"[NEXT] Fill in the description, remove placeholders, "
        f"then run: python3 scripts/validate_skill.py {display_path(target_dir)}"
    )


def main():
    parser = argparse.ArgumentParser(
        prog="new-skill",
        description="Scaffold a new skill from an opinionated template",
    )
    parser.add_argument("name", help="skill name, normalized to hyphen-case")
    parser.add_argument(
        "--variant",
        default="minimal",
        help=f"template variant (default: minimal, choices: {', '.join(ALLOWED_VARIANTS)})",
    )
    parser.add_argument(
        "--path",
        default="skills",
        help="parent directory for the generated skill (default: skills)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="overwrite an existing target directory",
    )
    args = parser.parse_args()

    if args.variant not in ALLOWED_VARIANTS:
        print(f"[ERROR] Invalid variant: {args.variant}", file=sys.stderr)
        print(f"        Use one of: {', '.join(ALLOWED_VARIANTS)}", file=sys.stderr)
        sys.exit(1)

    try:
        scaffold_skill(
            name=args.name,
            variant=args.variant,
            parent_path=args.path,
            force=args.force,
        )
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
