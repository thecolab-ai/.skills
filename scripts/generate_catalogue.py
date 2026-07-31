#!/usr/bin/env python3
"""Generate skills.json, trust-pack manifests, and the README skills table."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "lib"))

from skill_metadata import PACKS, iter_skill_dirs, load_skill, split_csv  # noqa: E402


PACK_DESCRIPTIONS = {
    "nz-public-data": "Public, read-only New Zealand data and public-interest sources.",
    "nz-commercial-web": "Read-only public commercial websites and market surfaces.",
    "nz-personal-data": "User-authorised personal data with runtime credentials and no live personal CI fixtures.",
    "thecolab-internal": "TheColab-specific documentation and operational workflows.",
    "artifact-tools": "Local artifact creation and editing with declared filesystem writes.",
    "paid-data-connectors": "Providers that require paid credentials or consume credits.",
}


def records() -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for skill_dir in iter_skill_dirs(REPO_ROOT):
        document = load_skill(skill_dir)
        metadata = document.metadata
        public_profile = None
        if metadata.get("thecolab.public_pack"):
            required_public = (
                "thecolab.public_commands",
                "thecolab.public_description",
                "thecolab.public_access_mode",
                "thecolab.public_health",
                "thecolab.public_risk",
                "thecolab.public_allowed_domains",
            )
            missing = [key for key in required_public if not metadata.get(key)]
            if missing:
                raise ValueError(
                    f"{skill_dir.name}: public profile is missing {', '.join(missing)}"
                )
            public_pack = metadata["thecolab.public_pack"]
            if public_pack not in PACKS or public_pack == metadata["thecolab.pack"]:
                raise ValueError(
                    f"{skill_dir.name}: public profile must name a distinct known pack"
                )
            public_profile = {
                "pack": public_pack,
                "description": metadata["thecolab.public_description"],
                "auth": "none",
                "access_mode": metadata["thecolab.public_access_mode"],
                "data_class": "public",
                "writes": False,
                "browser": False,
                "risk": metadata["thecolab.public_risk"],
                "health": metadata["thecolab.public_health"],
                "allowed_commands": split_csv(metadata["thecolab.public_commands"]),
                "allowed_domains": split_csv(metadata["thecolab.public_allowed_domains"]),
            }
        output.append(
            {
                "name": document.fields["name"],
                "description": document.fields["description"],
                "path": f"skills/{skill_dir.name}",
                "category": metadata["thecolab.category"],
                "source_owner": metadata["thecolab.source_owner"],
                "source_type": metadata["thecolab.source_type"],
                "source_url": metadata["thecolab.source_url"],
                "auth": metadata["thecolab.auth"],
                "access_mode": metadata["thecolab.access_mode"],
                "data_class": metadata["thecolab.data_class"],
                "writes": metadata["thecolab.writes"] == "true",
                "browser": metadata["thecolab.browser"] == "true",
                "risk": metadata["thecolab.risk"],
                "cache_ttl": metadata["thecolab.cache_ttl"],
                "schema_version": metadata["thecolab.schema_version"],
                "skill_type": metadata["thecolab.skill_type"],
                "pack": metadata["thecolab.pack"],
                "allowed_domains": [item for item in metadata["thecolab.allowed_domains"].split(",") if item],
                "last_verified": metadata["thecolab.last_verified"],
                "health": metadata["thecolab.health"],
                "maintainer": metadata["thecolab.maintainer"],
                **({"mutations": metadata["thecolab.mutations"].split(",")} if metadata.get("thecolab.mutations") else {}),
                **({"local_output": metadata["thecolab.local_output"].split(",")} if metadata.get("thecolab.local_output") else {}),
                **({"public_profile": public_profile} if public_profile else {}),
            }
        )
    return output


def encode(payload: object) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False) + "\n"


def readme_with_table(catalogue: list[dict[str, object]]) -> str:
    path = REPO_ROOT / "README.md"
    content = path.read_text(encoding="utf-8")
    start = content.index("## Available skills")
    end = content.index("\n## ", start + 4)
    rows = [
        "## Available skills",
        "",
        "<!-- BEGIN GENERATED SKILLS TABLE: run python3 scripts/generate_catalogue.py -->",
        "| Skill | Trust pack | Source owner | Description |",
        "|---|---|---|---|",
    ]
    for record in catalogue:
        description = str(record["description"]).replace("|", "\\|").replace("\n", " ")
        owner = str(record["source_owner"]).replace("|", "\\|")
        pack_label = f"`{record['pack']}`"
        public_profile = record.get("public_profile")
        if isinstance(public_profile, dict):
            pack_label += f", `{public_profile['pack']}` public profile"
        rows.append(
            f"| [{record['name']}](skills/{record['name']}/SKILL.md) | "
            f"{pack_label} | {owner} | {description} |"
        )
    rows.extend(
        (
            "<!-- END GENERATED SKILLS TABLE -->",
            "",
            "Machine-readable filters, health, authentication, access mode, maintenance ownership, and outbound domains are in [`skills.json`](skills.json).",
            "",
        )
    )
    return content[:start] + "\n".join(rows) + content[end:]


def desired_files() -> dict[Path, str]:
    catalogue = records()
    last_verified = max(str(record["last_verified"]) for record in catalogue)
    outputs: dict[Path, str] = {
        REPO_ROOT / "skills.json": encode(
            {
                "schema_version": "1",
                "generated_from": "skills/*/SKILL.md metadata",
                "last_verified": last_verified,
                "skill_count": len(catalogue),
                "skills": catalogue,
            }
        ),
        REPO_ROOT / "README.md": readme_with_table(catalogue),
    }
    for pack in sorted(PACKS):
        members = [record for record in catalogue if record["pack"] == pack]
        profiles = {
            str(record["name"]): record["public_profile"]
            for record in catalogue
            if isinstance(record.get("public_profile"), dict)
            and record["public_profile"]["pack"] == pack
        }
        outputs[REPO_ROOT / "packs" / f"{pack}.json"] = encode(
            {
                "schema_version": "1",
                "name": pack,
                "description": PACK_DESCRIPTIONS[pack],
                "default": pack == "nz-public-data",
                "skill_count": len(members),
                "skills": [record["name"] for record in members],
                **(
                    {
                        "public_profile_count": len(profiles),
                        "public_profiles": profiles,
                    }
                    if profiles
                    else {}
                ),
            }
        )
    return outputs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if generated files differ")
    args = parser.parse_args()
    outputs = desired_files()
    drift: list[str] = []
    for path, expected in outputs.items():
        if args.check:
            if not path.is_file() or path.read_text(encoding="utf-8") != expected:
                drift.append(str(path.relative_to(REPO_ROOT)))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(expected, encoding="utf-8")
            print(f"[OK] generated {path.relative_to(REPO_ROOT)}")
    if drift:
        for path in drift:
            print(f"[ERROR] generated output drift: {path}")
        print("Run: python3 scripts/generate_catalogue.py")
        return 1
    if args.check:
        print(f"[OK] {len(outputs)} generated catalogue files are current")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
