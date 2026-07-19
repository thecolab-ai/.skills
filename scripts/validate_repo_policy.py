#!/usr/bin/env python3
"""Validate TheColab repository policy independently of Agent Skills format."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "lib"))

from skill_metadata import (  # noqa: E402
    AUTH_TYPES,
    DATA_CLASSES,
    HEALTH_STATES,
    PACKS,
    REQUIRED_THECOLAB_METADATA,
    RISK_LEVELS,
    SKILL_TYPES,
    SOURCE_TYPES,
    iter_skill_dirs,
    load_skill,
    split_csv,
)


FORBIDDEN_FILES = {"README.md", "CHANGELOG.md", "NOTES.md", "IDEAS.md"}
PLACEHOLDERS = (
    "Describe what this skill does",
    "State the capability in 1 to 2 lines.",
    "Add concrete trigger examples",
    "Replace this with a real smoke test",
)
NETWORK_TYPES = {"public-api", "public-download", "html-readonly", "authenticated-personal"}
LINK_PATTERN = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
SHARED_RUNTIME_MODULES = frozenset(
    {
        "contract_test.py",
        "nzfetch.py",
        "result_contract.py",
        "skill_metadata.py",
    }
)


def valid_outbound_domain(domain: str) -> bool:
    if domain != domain.lower() or len(domain) > 253 or "." not in domain:
        return False
    labels = domain.split(".")
    return all(
        len(label) <= 63
        and re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) is not None
        for label in labels
    )


def validate_shared_lib(lib_dir: Path = REPO_ROOT / "lib") -> list[str]:
    """Reject source-specific Python modules from the shared runtime directory."""
    return [
        f"top-level lib Python module is not an allowlisted shared runtime module: {path.name}"
        for path in sorted(lib_dir.glob("*.py"))
        if path.name not in SHARED_RUNTIME_MODULES
    ]


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
    errors: list[str] = []
    warnings: list[str] = []
    document = load_skill(skill_dir)
    metadata = document.metadata
    missing = [key for key in REQUIRED_THECOLAB_METADATA if not metadata.get(key)]
    if missing:
        errors.append(f"missing TheColab metadata: {', '.join(missing)}")
        return {"skill": display_path(skill_dir), "errors": errors, "warnings": warnings}

    enumerations = {
        "thecolab.source_type": SOURCE_TYPES,
        "thecolab.auth": AUTH_TYPES,
        "thecolab.data_class": DATA_CLASSES,
        "thecolab.risk": RISK_LEVELS,
        "thecolab.health": HEALTH_STATES,
        "thecolab.skill_type": SKILL_TYPES,
        "thecolab.pack": PACKS,
    }
    for key, allowed in enumerations.items():
        if metadata[key] not in allowed:
            errors.append(f"{key} must be one of: {', '.join(sorted(allowed))}")
    if metadata.get("thecolab.health") == "untested":
        errors.append(
            "thecolab.health=untested is a scaffold gate; record healthy, degraded, or gated after verification"
        )
    for key in ("thecolab.writes", "thecolab.browser"):
        if metadata[key] not in {"true", "false"}:
            errors.append(f"{key} must be the string true or false")
    if metadata["thecolab.schema_version"] != "1":
        errors.append("thecolab.schema_version must be 1")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", metadata["thecolab.last_verified"]):
        errors.append("thecolab.last_verified must be an ISO date")
    source = urlparse(metadata["thecolab.source_url"])
    if source.scheme not in {"http", "https"} or not source.hostname:
        errors.append("thecolab.source_url must be an absolute HTTP(S) URL")
    domains = split_csv(metadata["thecolab.allowed_domains"])
    if not domains:
        errors.append("thecolab.allowed_domains must contain at least one host")
    for domain in domains:
        if not valid_outbound_domain(domain):
            errors.append(f"invalid outbound allowlist host: {domain}")

    required_files = [
        "scripts/cli.py",
        "scripts/test_contract.py",
        "scripts/smoke_test.py",
    ]
    if metadata["thecolab.skill_type"] in NETWORK_TYPES:
        required_files.append("references/source-notes.md")
    for relative in required_files:
        if not (skill_dir / relative).is_file():
            errors.append(f"missing required file for {metadata['thecolab.skill_type']}: {relative}")
    source_notes_path = skill_dir / "references" / "source-notes.md"
    if metadata["thecolab.skill_type"] in NETWORK_TYPES and source_notes_path.is_file():
        source_notes = source_notes_path.read_text(encoding="utf-8")
        required_notes = {
            "primary source URL": metadata["thecolab.source_url"],
            "authentication declaration": f"Authentication: {metadata['thecolab.auth']}",
            "last-verified date": f"Last verified: {metadata['thecolab.last_verified']}",
        }
        for label, expected in required_notes.items():
            if expected not in source_notes:
                errors.append(f"source notes do not contain the current {label}: {expected}")
        for domain in domains:
            if domain not in source_notes:
                errors.append(f"source notes omit declared outbound host: {domain}")
    fixture_dir = skill_dir / "tests" / "fixtures"
    if not fixture_dir.is_dir() or not any(path.is_file() for path in fixture_dir.rglob("*")):
        errors.append("tests/fixtures must contain at least one fixture")
    else:
        for path in sorted(fixture_dir.rglob("*.json")):
            try:
                fixture_payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                errors.append(f"invalid JSON fixture {path.relative_to(skill_dir)}: {exc}")
                continue
            if isinstance(fixture_payload, dict) and fixture_payload.get("implemented") is False:
                errors.append(
                    "replace the unimplemented scaffold source fixture before catalogue inclusion"
                )

    if metadata["thecolab.writes"] == "true" and not metadata.get("thecolab.mutations"):
        errors.append("write-capable skill must declare thecolab.mutations")
    if metadata["thecolab.writes"] == "false" and metadata.get("thecolab.mutations"):
        errors.append("read-only skill must not declare thecolab.mutations")
    if metadata["thecolab.data_class"] == "personal" and metadata["thecolab.pack"] != "nz-personal-data":
        errors.append("personal-data skills must be in nz-personal-data")
    if metadata["thecolab.pack"] == "nz-public-data" and (
        metadata["thecolab.data_class"] != "public" or metadata["thecolab.writes"] != "false"
    ):
        errors.append("nz-public-data may contain only public, read-only skills")

    for path in skill_dir.rglob("*"):
        if not path.is_file():
            continue
        if path.name in FORBIDDEN_FILES:
            errors.append(f"forbidden clutter file: {path.relative_to(skill_dir)}")
        if path.suffix.lower() in {".js", ".ts", ".mjs", ".cjs"} and not metadata.get("thecolab.javascript_exception"):
            errors.append(f"JavaScript/TypeScript helper requires an explicit exception: {path.relative_to(skill_dir)}")
        if path.suffix.lower() in {".md", ".py", ".sh", ".json", ".yaml", ".yml", ".mjs"}:
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for placeholder in PLACEHOLDERS:
                if placeholder in text:
                    errors.append(f"placeholder text in {path.relative_to(skill_dir)}: {placeholder}")
                    break
            if path.suffix.lower() == ".md":
                for match in LINK_PATTERN.finditer(text):
                    target = match.group(1).strip()
                    if not target or target.startswith(("http://", "https://", "mailto:", "#")):
                        continue
                    resolved = (path.parent / target).resolve()
                    try:
                        resolved.relative_to(skill_dir.resolve())
                    except ValueError:
                        errors.append(f"local link escapes skill root in {path.relative_to(skill_dir)}: {target}")
                        continue
                    if not resolved.exists():
                        errors.append(f"broken local link in {path.relative_to(skill_dir)}: {target}")
    body_lines = len(document.body.splitlines())
    if body_lines > 250:
        warnings.append(f"SKILL.md body has {body_lines} lines; move deep detail into references/")
    if (skill_dir / "references").is_dir() and "references/" not in document.body:
        warnings.append("references/ exists but SKILL.md does not mention it")
    if (skill_dir / "scripts").is_dir() and "scripts/" not in document.body:
        warnings.append("scripts/ exists but SKILL.md does not mention it")
    return {"skill": display_path(skill_dir), "errors": errors, "warnings": warnings}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", default="skills")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    try:
        results = [validate(path) for path in resolve(args.path)]
    except (OSError, ValueError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    shared_lib_errors = validate_shared_lib()
    if shared_lib_errors:
        results.insert(0, {"skill": "lib", "errors": shared_lib_errors, "warnings": []})
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
