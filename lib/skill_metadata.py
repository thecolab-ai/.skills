#!/usr/bin/env python3
"""Agent Skills frontmatter parsing and TheColab metadata helpers.

The repository deliberately stays dependency-free.  This module implements the
small YAML subset used by SKILL.md: top-level string scalars, block scalars, and
one nested string-to-string ``metadata`` mapping.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, cast


AGENT_SPEC_FIELDS = {
    "name",
    "description",
    "license",
    "compatibility",
    "metadata",
    "allowed-tools",
}

REQUIRED_THECOLAB_METADATA = (
    "thecolab.category",
    "thecolab.source_owner",
    "thecolab.source_type",
    "thecolab.auth",
    "thecolab.access_mode",
    "thecolab.data_class",
    "thecolab.writes",
    "thecolab.browser",
    "thecolab.risk",
    "thecolab.cache_ttl",
    "thecolab.schema_version",
    "thecolab.skill_type",
    "thecolab.pack",
    "thecolab.source_url",
    "thecolab.allowed_domains",
    "thecolab.last_verified",
    "thecolab.health",
    "thecolab.maintainer",
)

PACKS = {
    "nz-public-data",
    "nz-commercial-web",
    "nz-personal-data",
    "thecolab-internal",
    "artifact-tools",
    "paid-data-connectors",
}

SKILL_TYPES = {
    "public-api",
    "public-download",
    "html-readonly",
    "authenticated-personal",
    "documentation-workflow",
}

SOURCE_TYPES = {"official", "commercial", "community", "internal", "mixed"}
AUTH_TYPES = {"none", "api-key", "personal-token", "paid-credential", "mixed"}
DATA_CLASSES = {"public", "personal", "internal"}
RISK_LEVELS = {"low", "medium", "high"}
HEALTH_STATES = {"healthy", "degraded", "gated", "untested"}


class FrontmatterError(ValueError):
    """Raised when SKILL.md frontmatter is outside the supported spec subset."""


@dataclass(frozen=True)
class SkillDocument:
    path: Path
    fields: dict[str, object]
    body: str

    @property
    def metadata(self) -> dict[str, str]:
        value = self.fields.get("metadata", {})
        return cast(dict[str, str], value) if isinstance(value, dict) else {}


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        quote = value[0]
        inner = value[1:-1]
        if quote == '"':
            inner = (
                inner.replace(r"\n", "\n")
                .replace(r'\"', '"')
                .replace(r"\\", "\\")
            )
        return inner
    return value


def _metadata_scalar(value: str) -> object:
    stripped = value.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {'"', "'"}:
        return _unquote(stripped)
    lower = stripped.lower()
    if lower in {"true", "false"}:
        return lower == "true"
    if lower in {"null", "~"}:
        return None
    if re.fullmatch(r"[-+]?\d+", stripped):
        return int(stripped)
    if re.fullmatch(r"[-+]?(?:\d+\.\d*|\d*\.\d+)", stripped):
        return float(stripped)
    return stripped


def parse_frontmatter_text(content: str, path: Path | None = None) -> SkillDocument:
    label = str(path or "SKILL.md")
    match = re.match(r"\A---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|\Z)", content)
    if not match:
        raise FrontmatterError(f"{label}: missing or invalid YAML frontmatter")

    raw = match.group(1)
    lines = raw.splitlines()
    fields: dict[str, object] = {}
    index = 0

    while index < len(lines):
        line = lines[index]
        if not line.strip() or line.lstrip().startswith("#"):
            index += 1
            continue
        if line.startswith((" ", "\t")):
            raise FrontmatterError(f"{label}: unexpected indentation on frontmatter line {index + 2}")
        key_match = re.fullmatch(r"([A-Za-z][A-Za-z0-9_-]*):(?:\s*(.*))?", line)
        if not key_match:
            raise FrontmatterError(f"{label}: invalid frontmatter line {index + 2}: {line!r}")
        key = key_match.group(1)
        raw_value = (key_match.group(2) or "").strip()
        if key in fields:
            raise FrontmatterError(f"{label}: duplicate frontmatter key {key!r}")

        if key == "metadata":
            if raw_value not in {"", "{}"}:
                raise FrontmatterError(f"{label}: metadata must be a mapping")
            metadata: dict[str, object] = {}
            index += 1
            while index < len(lines) and (not lines[index].strip() or lines[index].startswith("  ")):
                nested = lines[index]
                if not nested.strip() or nested.lstrip().startswith("#"):
                    index += 1
                    continue
                nested_match = re.fullmatch(r"  ([A-Za-z0-9_.-]+):\s*(.*)", nested)
                if not nested_match:
                    raise FrontmatterError(
                        f"{label}: metadata line {index + 2} must use two-space indentation"
                    )
                nested_key = nested_match.group(1)
                if nested_key in metadata:
                    raise FrontmatterError(f"{label}: duplicate metadata key {nested_key!r}")
                nested_value = _metadata_scalar(nested_match.group(2))
                if nested_value == "":
                    raise FrontmatterError(f"{label}: metadata value {nested_key!r} must be a string")
                metadata[nested_key] = nested_value
                index += 1
            fields[key] = metadata
            continue

        if raw_value in {"|", "|-", ">", ">-"}:
            folded = raw_value.startswith(">")
            block: list[str] = []
            index += 1
            while index < len(lines) and (not lines[index].strip() or lines[index].startswith("  ")):
                block.append(lines[index][2:] if lines[index].startswith("  ") else "")
                index += 1
            value = (" " if folded else "\n").join(block).strip()
        else:
            value = _unquote(raw_value)
            index += 1
        fields[key] = value

    body = content[match.end() :]
    return SkillDocument(path=path or Path("SKILL.md"), fields=fields, body=body)


def load_skill(skill_dir: Path) -> SkillDocument:
    path = skill_dir / "SKILL.md"
    return parse_frontmatter_text(path.read_text(encoding="utf-8"), path)


def split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def iter_skill_dirs(root: Path) -> Iterable[Path]:
    # Accept either the repo root or the skills/ directory itself; checking for
    # the child directory (rather than the root's name) keeps a checkout that is
    # itself named "skills" from being mistaken for the skills directory.
    skills_dir = root / "skills" if (root / "skills").is_dir() else root
    for skill_dir in sorted(skills_dir.iterdir()):
        if skill_dir.is_dir() and (skill_dir / "SKILL.md").is_file():
            yield skill_dir
