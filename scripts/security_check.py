#!/usr/bin/env python3
"""Static security checks for skill bundles and distribution metadata."""

from __future__ import annotations

import ast
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

SECRET_PATTERNS = {
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "GitHub token": re.compile(r"\bgh[opusr]_[A-Za-z0-9_]{30,}\b"),
    "OpenAI key": re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"),
    "Slack token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
}

CREDENTIAL_URL = re.compile(r"https?://([^\s/:@]+):([^\s/@]+)@([^\s/:]+)")

TEXT_SUFFIXES = {".md", ".py", ".sh", ".json", ".yaml", ".yml", ".txt", ".mjs"}

# These are deliberately public, read-only browser search keys published to any
# visitor by the named storefront. Keep exceptions narrow and document each in
# the skill's source notes; user/API credentials must never be added here.
PUBLIC_BROWSER_KEY_EXCEPTIONS = {
    ("skills/briscoes-nz/scripts/cli.py", "DEFAULT_KLEVU_API_KEY"),
    ("skills/grocer-nz/scripts/cli.py", "MEILI_KEY"),
    ("skills/mitre10-nz/scripts/cli.py", "ALGOLIA_SEARCH_KEY"),
    ("skills/petstock-nz/scripts/cli.py", "ALGOLIA_API_KEY"),
}

SENSITIVE_ENV_NAME = re.compile(
    r"(?:^|_)(?:API_KEY|KEY|TOKEN|PASSWORD|SECRET|CREDENTIALS?|USERNAME|LOGIN)$"
)
SENSITIVE_CONSTANT_NAME = re.compile(
    r"(?:^|_)(?:API_KEY|KEY|TOKEN|PASSWORD|SECRET|CREDENTIALS?|USERNAME|LOGIN)$"
)


def _target_names(node: ast.Assign | ast.AnnAssign) -> list[str]:
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    return [target.id for target in targets if isinstance(target, ast.Name)]


def credential_default_errors(relative: Path, content: str) -> list[str]:
    """Find committed credential defaults without mistaking public test text for values."""
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return []  # compilation is enforced by the repository validator

    errors: list[str] = []
    relative_text = relative.as_posix()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or len(node.args) < 2:
            continue
        func = node.func
        is_environ_get = (
            isinstance(func, ast.Attribute)
            and func.attr == "get"
            and isinstance(func.value, ast.Attribute)
            and func.value.attr == "environ"
            and isinstance(func.value.value, ast.Name)
            and func.value.value.id == "os"
        )
        is_getenv = (
            isinstance(func, ast.Attribute)
            and func.attr == "getenv"
            and isinstance(func.value, ast.Name)
            and func.value.id == "os"
        )
        name_arg, default_arg = node.args[0], node.args[1]
        if not (is_environ_get or is_getenv):
            continue
        if not (
            isinstance(name_arg, ast.Constant)
            and isinstance(name_arg.value, str)
            and SENSITIVE_ENV_NAME.search(name_arg.value.upper())
            and isinstance(default_arg, ast.Constant)
            and isinstance(default_arg.value, str)
            and default_arg.value
        ):
            continue
        errors.append(
            f"credential environment variable {name_arg.value} has a committed fallback in "
            f"{relative}:{node.lineno}"
        )

    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        value = node.value
        if not (isinstance(value, ast.Constant) and isinstance(value.value, str) and len(value.value) >= 12):
            continue
        for name in _target_names(node):
            if not SENSITIVE_CONSTANT_NAME.search(name.upper()):
                continue
            if (relative_text, name) in PUBLIC_BROWSER_KEY_EXCEPTIONS:
                continue
            errors.append(f"possible committed credential constant {name} in {relative}:{node.lineno}")
    return errors


def main() -> int:
    errors: list[str] = []
    for path in sorted(REPO_ROOT.rglob("*")):
        if not path.is_file() or ".git" in path.parts or "__pycache__" in path.parts:
            continue
        relative = path.relative_to(REPO_ROOT)
        if path.name.startswith(".env") and path.name not in {".env.example", ".env.sample"}:
            errors.append(f"environment file must not be committed: {relative}")
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in {"SKILL.md", "LICENSE"}:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(content):
                errors.append(f"possible {label} in {relative}")
        for match in CREDENTIAL_URL.finditer(content):
            username, password, host = match.groups()
            if host.endswith((".test", ".example", ".invalid")):
                continue
            if username in {"user", "username"} and password in {"pass", "password", "secret"}:
                continue
            errors.append(f"possible credential URL in {relative}")
        if re.search(r"print\([^\n]*(?:FETCH_PROXY|HTTPS_PROXY|AKAHU_(?:APP|USER)_TOKEN)", content):
            errors.append(f"sensitive environment value may be printed in {relative}")
        if path.suffix == ".py" and relative.parts[:1] == ("skills",):
            errors.extend(credential_default_errors(relative, content))
        if relative.parts[:2] == ("skills", "akahu-personal") and "tests/fixtures" in str(relative):
            if '"contains_personal_data": false' not in content:
                errors.append(f"personal-data fixture lacks explicit synthetic-data marker: {relative}")

    plugin = (REPO_ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
    if '"license": "MIT"' not in plugin:
        errors.append(".claude-plugin/plugin.json must declare MIT")
    if errors:
        for error in errors:
            print(f"[ERROR] {error}")
        return 1
    print("[OK] static security checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
