#!/usr/bin/env python3
"""Deterministic executable-skill contract checks shared by every skill."""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

from skill_metadata import load_skill, split_csv
from result_contract import VALID_EXIT_CODES, validate_result_envelope


URL_PATTERN = re.compile(r"https?://[^\s\"'<>`)]+")
DOCUMENTED_COMMAND = re.compile(r"scripts/cli\.(?:py|mjs)\s+([^\n`]+)")
NON_OUTBOUND_LITERAL_HOSTS = {
    "example.com",
    "example.net",
    "example.org",
    "github.com",
    "purl.org",
    "schema.org",
    "schemas.microsoft.com",
    "schemas.openxmlformats.org",
    "twitter.com",
    "www.facebook.com",
    "www.linkedin.com",
    "www.w3.org",
}
REPO_ROOT = Path(__file__).resolve().parent.parent


def _python_files(skill_dir: Path) -> list[Path]:
    return sorted(path for path in skill_dir.rglob("*.py") if "__pycache__" not in path.parts)


def _documented_subcommands(skill_dir: Path) -> list[str]:
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    commands: set[str] = set()
    for match in DOCUMENTED_COMMAND.finditer(text):
        tail = match.group(1).strip()
        if not tail:
            continue
        first = tail.split()[0]
        if (
            first not in {"#", "..."}
            and not first.startswith(("-", "/", "~", "<", "[", "{"))
            and re.fullmatch(r"[a-z0-9][a-z0-9-]*", first)
        ):
            commands.add(first)
    return sorted(commands)


def _help_subcommands(help_text: str) -> list[str]:
    """Extract argparse subcommand choices from the top-level help surface."""
    for line in help_text.splitlines():
        match = re.match(r"^\s{2,}\{([a-z0-9,-]+)\}(?:\s|$)", line)
        if match:
            return [item for item in match.group(1).split(",") if item]
    return []


def _static_hosts(path: Path) -> set[str]:
    hosts: set[str] = set()
    text = path.read_text(encoding="utf-8")
    candidates = set(URL_PATTERN.findall(text))
    if path.suffix == ".py":
        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError:
            tree = None
        if tree is not None:
            constants: dict[str, str] = {}

            def static_string(node: ast.AST) -> str | None:
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    return node.value
                if isinstance(node, ast.Name):
                    return constants.get(node.id)
                if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
                    left = static_string(node.left)
                    right = static_string(node.right)
                    return left + right if left is not None and right is not None else None
                if isinstance(node, ast.JoinedStr):
                    parts: list[str] = []
                    for value in node.values:
                        part = static_string(value.value) if isinstance(value, ast.FormattedValue) else static_string(value)
                        if part is None:
                            return None
                        parts.append(part)
                    return "".join(parts)
                if (
                    isinstance(node, ast.Call)
                    and not node.args
                    and not node.keywords
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr in {"lower", "upper"}
                ):
                    value = static_string(node.func.value)
                    if value is not None:
                        return value.lower() if node.func.attr == "lower" else value.upper()
                return None

            for statement in tree.body:
                if not isinstance(statement, (ast.Assign, ast.AnnAssign)):
                    continue
                value_node = statement.value
                value = static_string(value_node) if value_node is not None else None
                if value is None:
                    continue
                targets = statement.targets if isinstance(statement, ast.Assign) else [statement.target]
                for target in targets:
                    if isinstance(target, ast.Name):
                        constants[target.id] = value
                candidates.update(URL_PATTERN.findall(value))

            for node in ast.walk(tree):
                if isinstance(node, (ast.JoinedStr, ast.BinOp)):
                    value = static_string(node)
                    if value is not None:
                        candidates.update(URL_PATTERN.findall(value))

    for raw in candidates:
        try:
            hostname = urlparse(raw.rstrip(".,;:")).hostname
        except ValueError:
            continue
        if hostname and any(marker in hostname for marker in ("{", "}", "\\")):
            continue
        if (
            hostname
            and "." in hostname
            and not hostname.endswith(".")
            and hostname not in NON_OUTBOUND_LITERAL_HOSTS
            and not hostname.endswith((".example", ".invalid", ".test"))
        ):
            hosts.add(hostname.lower())
    return hosts


def _network_timeout_findings(path: Path) -> list[str]:
    findings: list[str] = []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        return [f"Python syntax error: {exc}"]
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = ""
        if isinstance(node.func, ast.Name):
            name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            name = node.func.attr
        if name not in {"urlopen", "urlretrieve", "fetch_json", "fetch_text", "fetch_bytes"}:
            continue
        if name.startswith("fetch"):
            continue  # shared nzfetch always applies a bounded timeout
        if name == "urlretrieve":
            findings.append(f"{path.name}:{node.lineno}: urlretrieve has no timeout parameter; use urlopen")
            continue
        if not any(keyword.arg == "timeout" for keyword in node.keywords):
            findings.append(f"{path.name}:{node.lineno}: network call has no explicit timeout")
    return findings


def _target_names(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, (ast.Tuple, ast.List)):
        return [name for item in node.elts for name in _target_names(item)]
    return []


def _reads_environment(node: ast.AST) -> bool:
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        if isinstance(child.func, ast.Attribute) and child.func.attr in {"get", "getenv"}:
            value = child.func.value
            if isinstance(value, ast.Attribute) and value.attr == "environ":
                return True
            if isinstance(value, ast.Name) and value.id == "os":
                return True
    return False


def _credential_findings(path: Path) -> list[str]:
    findings: list[str] = []
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    sensitive = re.compile(
        r"(?:^|_)(?:API_?KEY|APP_TOKEN|USER_TOKEN|ACCESS_TOKEN|AUTH_TOKEN|PASSWORD|SECRET|CREDENTIAL)(?:$|_)",
        re.I,
    )
    for statement in tree.body:
        targets: list[str] = []
        value: ast.AST | None = None
        if isinstance(statement, (ast.Assign, ast.AnnAssign)):
            target_nodes = statement.targets if isinstance(statement, ast.Assign) else [statement.target]
            targets = [name for target in target_nodes for name in _target_names(target)]
            value = statement.value
        if value is not None and any(sensitive.search(name) for name in targets) and _reads_environment(value):
            findings.append(
                f"{path.name}:{statement.lineno}: credential environment variables must be loaded lazily inside the command path"
            )
    return findings


def _credential_environment_names(path: Path) -> set[str]:
    names: set[str] = set()
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    sensitive = re.compile(
        r"(?:API_?KEY|APP_TOKEN|USER_TOKEN|ACCESS_TOKEN|AUTH_TOKEN|PASSWORD|SECRET|"
        r"CREDENTIALS?|USERNAME|LOGIN)$",
        re.I,
    )
    for node in ast.walk(tree):
        name: str | None = None
        if isinstance(node, ast.Call) and node.args:
            if (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "get"
                and isinstance(node.func.value, ast.Attribute)
                and node.func.value.attr == "environ"
                and isinstance(node.func.value.value, ast.Name)
                and node.func.value.value.id == "os"
            ) or (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "getenv"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "os"
            ):
                first = node.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    name = first.value
        elif (
            isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Attribute)
            and node.value.attr == "environ"
            and isinstance(node.value.value, ast.Name)
            and node.value.value.id == "os"
            and isinstance(node.slice, ast.Constant)
            and isinstance(node.slice.value, str)
        ):
            name = node.slice.value
        if name and sensitive.search(name):
            names.add(name)
    return names


def _common_runner_findings(skill_dir: Path) -> list[str]:
    """Exercise the canonical JSON envelope without making a live source call."""
    try:
        relative = skill_dir.resolve().relative_to((REPO_ROOT / "skills").resolve())
    except ValueError:
        return []
    if len(relative.parts) != 1:
        return []
    runner = REPO_ROOT / "scripts" / "run_skill.py"
    findings: list[str] = []
    cases = (
        (["--help"], 0, True),
        (["--thecolab-invalid-option"], 2, False),
    )
    for arguments, expected_exit, expected_ok in cases:
        completed = subprocess.run(
            [sys.executable, str(runner), skill_dir.name, *arguments],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
        label = " ".join(arguments)
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            findings.append(f"common runner {label} did not emit JSON: {exc.msg}")
            continue
        envelope_errors = validate_result_envelope(payload)
        findings.extend(f"common runner {label}: {error}" for error in envelope_errors)
        if completed.returncode != expected_exit:
            findings.append(
                f"common runner {label} exit code was {completed.returncode}, expected {expected_exit}"
            )
        if payload.get("ok") is not expected_ok:
            findings.append(f"common runner {label} ok state was not {expected_ok}")
        if not expected_ok:
            error = payload.get("error")
            code = error.get("code") if isinstance(error, dict) else None
            if code not in VALID_EXIT_CODES - {0} or code != completed.returncode:
                findings.append(f"common runner {label} error code does not match its stable exit code")
    return findings


def audit_skill(skill_dir: Path, *, run_help: bool = True) -> dict[str, object]:
    document = load_skill(skill_dir)
    metadata = document.metadata
    errors: list[str] = []
    warnings: list[str] = []
    checks: list[str] = []

    cli = skill_dir / "scripts" / "cli.py"
    legacy_cli = skill_dir / "scripts" / "cli.mjs"
    if not cli.is_file():
        errors.append("missing canonical scripts/cli.py")
    elif not cli.read_text(encoding="utf-8").startswith("#!/usr/bin/env python3"):
        errors.append("scripts/cli.py must start with #!/usr/bin/env python3")
    else:
        checks.append("python_cli")

    for path in _python_files(skill_dir):
        try:
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
        except SyntaxError as exc:
            errors.append(f"{path.relative_to(skill_dir)}: Python compilation failed: {exc}")
    checks.append("python_compile")

    if cli.is_file():
        allowed = set(split_csv(metadata.get("thecolab.allowed_domains", "")))
        source_host = urlparse(metadata.get("thecolab.source_url", "")).hostname
        if source_host and source_host not in allowed:
            errors.append("thecolab.source_url host must be in thecolab.allowed_domains")
        static_hosts = set()
        for executable in [*_python_files(skill_dir), *skill_dir.rglob("*.mjs")]:
            static_hosts.update(_static_hosts(executable))
        undeclared = sorted(host for host in static_hosts if host not in allowed)
        if undeclared:
            errors.append(f"static URL hosts not in allowlist: {', '.join(undeclared)}")
        checks.append("outbound_domains")
        for path in _python_files(skill_dir):
            errors.extend(_network_timeout_findings(path))
        checks.append("network_timeouts")
        for path in _python_files(skill_dir):
            errors.extend(_credential_findings(path))
        checks.append("lazy_credentials")
        credential_names = set().union(
            *(_credential_environment_names(path) for path in _python_files(skill_dir))
        )
        if credential_names and metadata.get("thecolab.auth") == "none":
            errors.append(
                "credential environment variables contradict thecolab.auth=none: "
                + ", ".join(sorted(credential_names))
            )
        checks.append("declared_auth")

    if legacy_cli.is_file() and not metadata.get("thecolab.javascript_exception"):
        errors.append("JavaScript helper requires thecolab.javascript_exception")

    if metadata.get("thecolab.writes") == "true" and not metadata.get("thecolab.mutations"):
        errors.append("write-capable skill must declare thecolab.mutations")
    if cli.is_file():
        cli_text = cli.read_text(encoding="utf-8")
        exposes_mutation = (
            "--i-understand-this-can-mutate" in cli_text
            or "MUTATING_METHODS" in cli_text
        )
        if exposes_mutation and metadata.get("thecolab.writes") != "true":
            errors.append("CLI exposes mutation methods but thecolab.writes is not true")
        explicit_local_output = bool(
            re.search(r"Path\([^\n]*(?:args|a)\.(?:output|out_dir|destination)", cli_text)
            or re.search(r"(?:args|a)\.(?:output|out_dir|destination)[^\n]*(?:write_|open\()", cli_text)
        )
        if explicit_local_output and not metadata.get("thecolab.local_output"):
            errors.append("CLI exposes user-requested local output but thecolab.local_output is not declared")

    if run_help and cli.is_file():
        top_invocation = [sys.executable, str(cli), "--help"]
        completed = subprocess.run(
            top_invocation,
            cwd=skill_dir,
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )
        top_help = completed.stdout + completed.stderr
        if completed.returncode != 0:
            errors.append(f"top-level --help failed: {completed.stderr.strip()}")
        actual_commands = _help_subcommands(top_help)
        documented_commands = _documented_subcommands(skill_dir)
        commands = sorted(set(actual_commands) | set(documented_commands))
        queue: list[tuple[str, ...]] = [(command,) for command in commands]
        visited: set[tuple[str, ...]] = set()
        leaf_help: dict[tuple[str, ...], str] = {}
        while queue:
            command_path = queue.pop(0)
            if command_path in visited:
                continue
            visited.add(command_path)
            invocation = [sys.executable, str(cli), *command_path, "--help"]
            completed = subprocess.run(
                invocation,
                cwd=skill_dir,
                text=True,
                capture_output=True,
                timeout=5,
                check=False,
            )
            if completed.returncode != 0:
                errors.append(f"documented help command failed ({' '.join(invocation[2:])}): {completed.stderr.strip()}")
                continue
            help_text = completed.stdout + completed.stderr
            children = _help_subcommands(help_text) if len(command_path) < 2 else []
            if children:
                queue.extend((*command_path, child) for child in children)
            else:
                leaf_help[command_path] = help_text
        if "--json" not in top_help and commands:
            missing_json = sorted(" ".join(path) for path, text in leaf_help.items() if "--json" not in text)
            if missing_json:
                errors.append(f"data commands missing --json in help: {', '.join(missing_json)}")
        elif "--json" not in top_help and not commands:
            errors.append("documented CLI help does not expose --json")
        checks.extend(("help", "documented_commands", "json_flag"))

        invalid = subprocess.run(
            [sys.executable, str(cli), "--thecolab-invalid-option", "--json"],
            cwd=skill_dir,
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )
        invalid_output = invalid.stdout + invalid.stderr
        if invalid.returncode == 0:
            errors.append("unknown command must fail with a non-zero exit code")
        if "Traceback (most recent call last)" in invalid_output:
            errors.append("unknown command emitted a Python traceback instead of an actionable failure")
        checks.append("actionable_errors")

        errors.extend(_common_runner_findings(skill_dir))
        checks.append("common_json_envelope")

    fixture_dir = skill_dir / "tests" / "fixtures"
    fixture_files = sorted(path for path in fixture_dir.rglob("*") if path.is_file()) if fixture_dir.is_dir() else []
    fixture_assertions = 0
    if not fixture_files:
        errors.append("tests/fixtures must contain at least one deterministic fixture")
    else:
        contract_fixture = fixture_dir / "contract.json"
        if not contract_fixture.is_file():
            errors.append("tests/fixtures/contract.json is required")
        else:
            try:
                fixture = json.loads(contract_fixture.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                errors.append(f"tests/fixtures/contract.json is invalid: {exc}")
            else:
                expected = {
                    "schema_version": "1",
                    "skill": skill_dir.name,
                    "fixture": "synthetic-contract-sentinel",
                    "contains_live_credentials": False,
                    "contains_personal_data": False,
                }
                for key, value in expected.items():
                    fixture_assertions += 1
                    if fixture.get(key) != value:
                        errors.append(f"contract fixture {key} must be {value!r}")
        checks.append("fixtures")

    return {
        "schema_version": "1",
        "skill": skill_dir.name,
        "ok": not errors,
        "checks": checks,
        "errors": errors,
        "warnings": warnings,
        "fixture_assertions": fixture_assertions,
        "live_assertions": 0,
        "skips": [],
        "source_health": metadata.get("thecolab.health", "untested"),
    }


def run_contract_test(skill_dir: Path) -> int:
    result = audit_skill(skill_dir)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ok"] else 1
