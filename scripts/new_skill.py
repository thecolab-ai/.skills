#!/usr/bin/env python3
"""Scaffold a new skill from an opinionated template."""

import argparse
import os
import re
import shutil
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = REPO_ROOT / "templates"
ALLOWED_VARIANTS = (
    "public-api",
    "public-download",
    "html-readonly",
    "authenticated-personal",
    "documentation-workflow",
)


def normalize_name(raw: str) -> str:
    name = raw.strip().lower()
    name = re.sub(r"[^a-z0-9]+", "-", name)
    name = re.sub(r"-{2,}", "-", name)
    name = name.strip("-")
    return name


def title_case(name: str) -> str:
    return " ".join(part.capitalize() for part in name.split("-"))


def variant_defaults(variant: str) -> dict[str, str]:
    values = {
        "SKILL_TYPE": variant,
        "ACCESS_MODE": variant,
        "AUTH": "none",
        "DATA_CLASS": "public",
        "PACK": "nz-public-data",
        "RISK": "low",
    }
    if variant == "html-readonly":
        values.update(PACK="nz-commercial-web", RISK="medium")
    elif variant == "authenticated-personal":
        values.update(AUTH="personal-token", DATA_CLASS="personal", PACK="nz-personal-data", RISK="high")
    elif variant == "documentation-workflow":
        values.update(DATA_CLASS="internal", PACK="thecolab-internal", RISK="medium")
    return values


def render_template(content: str, values: dict) -> str:
    def replacer(match):
        key = match.group(1)
        return values.get(key, match.group(0))

    return re.sub(r"\{\{([A-Z_]+)\}\}", replacer, content)


def quoted_template_value(value: str) -> str:
    """Escape a value that will be inserted inside a double-quoted YAML scalar."""
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


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


def scaffold_skill(
    name: str,
    variant: str,
    parent_path: str,
    force: bool,
    description: str,
    source_owner: str,
    source_url: str,
    category: str,
    source_type: str,
    pack: str | None,
) -> None:
    name = normalize_name(name)
    if not name:
        raise ValueError("Skill name must include at least one letter or digit.")
    if len(name) > 64:
        raise ValueError(f"Skill name is too long ({len(name)} > 64).")

    source_dir = TEMPLATES_DIR / f"skill-{variant}"
    shared_dir = TEMPLATES_DIR / "_shared-executable"
    if not source_dir.exists():
        raise FileNotFoundError(f"Template not found: {source_dir}")
    if not shared_dir.exists():
        raise FileNotFoundError(f"Shared template not found: {shared_dir}")

    parsed_source = urlparse(source_url)
    if parsed_source.scheme not in {"http", "https"} or not parsed_source.hostname:
        raise ValueError("--source-url must be an absolute HTTP(S) URL")

    target_dir = (REPO_ROOT / parent_path / name).resolve()
    if target_dir.exists():
        if not force:
            raise FileExistsError(f"Target already exists: {target_dir}")
        canonical_skills = (REPO_ROOT / "skills").resolve()
        if target_dir.parent != canonical_skills:
            raise ValueError("--force may replace only a direct child of the repository skills/ directory")
        if target_dir.is_symlink():
            raise ValueError("refusing to replace a symbolic-link skill target")
        if not target_dir.is_dir():
            raise ValueError("refusing to replace a non-directory skill target")
        shutil.rmtree(target_dir)

    target_dir.mkdir(parents=True, exist_ok=True)
    shutil.copytree(str(shared_dir), str(target_dir), dirs_exist_ok=True)
    shutil.copytree(str(source_dir), str(target_dir), dirs_exist_ok=True)

    defaults = variant_defaults(variant)
    if pack:
        defaults["PACK"] = pack

    values = {
        "SKILL_NAME": name,
        "SKILL_TITLE": title_case(name),
        "DESCRIPTION": quoted_template_value(description),
        "SOURCE_OWNER": quoted_template_value(source_owner),
        "SOURCE_URL": quoted_template_value(source_url),
        "ALLOWED_DOMAINS": parsed_source.hostname.lower(),
        "CATEGORY": category,
        "SOURCE_TYPE": source_type,
        "LAST_VERIFIED": date.today().isoformat(),
        **defaults,
    }

    for file_path in walk(target_dir):
        try:
            content = file_path.read_text(encoding="utf-8")
            file_path.write_text(render_template(content, values), encoding="utf-8")
        except (UnicodeDecodeError, PermissionError):
            pass
        if file_path.suffix in {".py", ".sh"}:
            current_mode = file_path.stat().st_mode
            file_path.chmod(current_mode | 0o755)

    print(f"[OK] Created {variant} skill scaffold at {target_dir}")
    print(
        "[NEXT] Validation intentionally remains gated: replace the unimplemented source fixture, "
        "record verified source health, then run: "
        f"python3 scripts/validate_skill.py {display_path(target_dir)}"
    )


def main():
    parser = argparse.ArgumentParser(
        prog="new-skill",
        description="Scaffold a new skill from an opinionated template",
    )
    parser.add_argument("name", help="skill name, normalized to hyphen-case")
    parser.add_argument(
        "--variant",
        default="public-api",
        help=f"template variant (default: public-api, choices: {', '.join(ALLOWED_VARIANTS)})",
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
    parser.add_argument("--description", required=True, help="Agent Skills trigger description")
    parser.add_argument("--source-owner", required=True, help="agency, operator, project, or internal owner")
    parser.add_argument("--source-url", required=True, help="canonical absolute primary-source URL")
    parser.add_argument("--category", default="public-data", help="catalogue category")
    parser.add_argument(
        "--source-type",
        choices=("official", "commercial", "community", "internal", "mixed"),
        default="official",
    )
    parser.add_argument(
        "--pack",
        choices=("nz-public-data", "nz-commercial-web", "nz-personal-data", "thecolab-internal", "artifact-tools", "paid-data-connectors"),
        help="override the variant's default trust pack",
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
            description=args.description,
            source_owner=args.source_owner,
            source_url=args.source_url,
            category=args.category,
            source_type=args.source_type,
            pack=args.pack,
        )
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
