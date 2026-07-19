#!/usr/bin/env python3
"""Install one generated trust pack into an explicit local skills directory."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "lib"))

from skill_metadata import PACKS  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pack", nargs="?", choices=sorted(PACKS), default="nz-public-data")
    parser.add_argument("--target", required=True, help="explicit destination directory")
    parser.add_argument("--force", action="store_true", help="replace existing skill folders in the target")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    manifest_path = REPO_ROOT / "packs" / f"{args.pack}.json"
    if not manifest_path.is_file():
        parser.error(f"unknown pack: {args.pack}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != "1" or manifest.get("name") != args.pack:
        parser.error("pack manifest identity or schema is invalid")
    target = Path(args.target).expanduser().resolve()
    if target == Path(target.anchor):
        parser.error("refusing to install into a filesystem root")
    repository_root = REPO_ROOT.resolve()
    canonical_skills = (repository_root / "skills").resolve()
    if target == repository_root or repository_root in target.parents:
        parser.error("refusing to install anywhere inside the source repository")

    skills = manifest.get("skills")
    if not isinstance(skills, list) or not skills:
        parser.error("pack manifest must contain a non-empty skills list")
    if len(skills) != len(set(skills)):
        parser.error("pack manifest contains duplicate skills")
    if manifest.get("skill_count") != len(skills):
        parser.error("pack manifest skill_count does not match its skills list")
    operations: list[tuple[Path, Path]] = []
    for skill in skills:
        if not isinstance(skill, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", skill):
            parser.error(f"invalid skill name in pack manifest: {skill!r}")
        source = REPO_ROOT / "skills" / skill
        destination = target / skill
        if (
            not source.is_dir()
            or not (source / "SKILL.md").is_file()
            or source.resolve().parent != canonical_skills
        ):
            parser.error(f"pack source is missing or outside the canonical skills tree: {skill}")
        if destination.exists():
            if destination.is_symlink():
                parser.error(f"refusing to replace a symbolic-link destination: {destination}")
            if not destination.is_dir():
                parser.error(f"refusing to replace a non-directory destination: {destination}")
            if not args.force:
                parser.error(f"destination exists (use --force deliberately): {destination}")
        operations.append((source, destination))

    for source, destination in operations:
        print(f"{source} -> {destination}")
        if args.dry_run:
            continue
        target.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(source, destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
