#!/usr/bin/env python3
"""Run smoke tests with one machine-readable result contract."""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "lib"))

from skill_metadata import iter_skill_dirs, load_skill  # noqa: E402


PASS_LINE = re.compile(r"^\s*(?:\[PASS\]|PASS\b|OK\b|✓)", re.I)
FAIL_LINE = re.compile(r"^\s*(?:\[FAIL\]|FAIL\b|✗)", re.I)
FAILURE_KIND = re.compile(
    r"^\s*(?:\[FAIL\]|FAIL\b|✗)\s*(fixture|contract|live|schema|parser)\b",
    re.I,
)
ASSERTION_KIND = re.compile(
    r"^\s*(?:\[PASS\]|PASS\b|OK\b|✓)\s*(fixture|contract|live)\b",
    re.I,
)
SKIP_LINE = re.compile(r"^\s*(?:\[SKIP\]|SKIP\b)", re.I)
CREDENTIAL_MARKER = re.compile(
    r"requires?.*(?:api[_ ]?key|token|credential|username|password)|"
    r"[A-Z][A-Z0-9_]+_(?:API_?KEY|TOKEN|USERNAME|PASSWORD|CREDENTIALS?)",
    re.I,
)
NETWORK_MARKER = re.compile(
    r"network error|upstream unavailable|blocked after|nodename nor servname|name or service not known|"
    r"temporary failure|timed? out|http (?:403|406|429|451|5\d\d)",
    re.I,
)
SKIP_GATING_MARKER = re.compile(
    r"network|upstream|unavailable|blocked|timed? out|credential|api[_ ]?key|token|username|password",
    re.I,
)
TRACEBACK_MARKER = re.compile(r"traceback|syntaxerror", re.I)


def assertion_kind(line: str) -> str | None:
    match = ASSERTION_KIND.search(line)
    return match.group(1).lower() if match else None


def failure_kind(line: str) -> str | None:
    match = FAILURE_KIND.search(line)
    return match.group(1).lower() if match else None


def changed_skills(base: str) -> list[str]:
    completed = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...HEAD"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or f"could not diff from {base}")
    names = {
        parts[1]
        for line in completed.stdout.splitlines()
        if (parts := Path(line).parts) and len(parts) >= 3 and parts[0] == "skills"
    }
    return sorted(names)


def static_assertions(path: Path) -> int:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError):
        return 0
    count = sum(isinstance(node, ast.Assert) for node in ast.walk(tree))
    count += sum(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"check", "require", "assert_true", "assert_equal"}
        for node in ast.walk(tree)
    )
    return count


def smoke_command(path: Path) -> list[str]:
    if os.environ.get("COLAB_SMOKE_WITH_CLOAKBROWSER") == "1" and shutil.which("uv"):
        command = ["uv", "run", "--no-project"]
        command.extend(("--with", "cloakbrowser"))
        command.extend(("python", str(path)))
        return command
    return [sys.executable, str(path)]


def run_one(skill_dir: Path, timeout: int) -> dict[str, object]:
    smoke = skill_dir / "scripts" / "smoke_test.py"
    metadata = load_skill(skill_dir).metadata
    if not smoke.is_file():
        return {
            "schema_version": "1",
            "skill": skill_dir.name,
            "status": "fail",
            "fixture_assertions": 0,
            "contract_assertions": 0,
            "live_assertions": 0,
            "static_assertion_sites": 0,
            "skips": [],
            "source_health": "untested",
            "declared_source_health": metadata.get("thecolab.health", "untested"),
            "raw_exit_code": 1,
            "log": "missing scripts/smoke_test.py",
        }
    try:
        environment = os.environ.copy()
        environment.setdefault("UV_CACHE_DIR", str(Path(tempfile.gettempdir()) / "thecolab-uv-cache"))
        completed = subprocess.run(
            smoke_command(smoke),
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
            env=environment,
        )
        log = "\n".join(part for part in (completed.stdout.strip(), completed.stderr.strip()) if part)
        exit_code = completed.returncode
    except subprocess.TimeoutExpired as exc:
        log = f"smoke timeout after {timeout}s: {exc}"
        exit_code = 5

    lines = log.splitlines()
    pass_candidates = [
        (index, line)
        for index, line in enumerate(lines)
        if PASS_LINE.search(line) and "--help" not in line and "skips without" not in line
    ]
    # Legacy test wrappers sometimes print [PASS] after the test body already
    # emitted [SKIP]. Do not turn that wrapper bookkeeping into an assertion.
    passes = [
        line
        for index, line in pass_candidates
        if index == 0
        or not SKIP_LINE.search(lines[index - 1])
        or assertion_kind(line) in {"fixture", "contract"}
    ]
    skips = [line.strip() for line in lines if SKIP_LINE.search(line)]
    classified = [(kind, line) for line in passes if (kind := assertion_kind(line))]
    fixture_passes = [line for kind, line in classified if kind == "fixture"]
    live_passes = [line for kind, line in classified if kind == "live"]
    contract_passes = [line for kind, line in classified if kind == "contract"]
    classified_passes = fixture_passes + live_passes + contract_passes
    static_count = static_assertions(smoke)

    explicit_failure_lines = [line for line in lines if FAIL_LINE.search(line)]
    network_failure_context = bool(NETWORK_MARKER.search(log))
    deterministic_failure = bool(TRACEBACK_MARKER.search(log)) or any(
        (kind := failure_kind(line)) in {"fixture", "schema", "parser", "contract"}
        or (kind == "live" and not network_failure_context)
        or (kind is None and exit_code == 0)
        for line in explicit_failure_lines
    )
    outage_only = exit_code != 0 and NETWORK_MARKER.search(log) and not deterministic_failure
    if deterministic_failure:
        status = "fail"
    elif outage_only:
        status = "gated"
        skips.append("upstream outage prevented live assertions")
    elif exit_code != 0:
        status = "fail"
    elif not classified_passes and skips and (
        CREDENTIAL_MARKER.search(log) or NETWORK_MARKER.search(log) or SKIP_GATING_MARKER.search(log)
    ):
        status = "gated"
    elif classified_passes:
        status = "pass"
    else:
        status = "untested"

    if outage_only or status == "fail":
        observed_health = "degraded"
    elif status == "gated":
        observed_health = "gated"
    elif live_passes:
        observed_health = "healthy"
    else:
        observed_health = "untested"

    return {
        "schema_version": "1",
        "skill": skill_dir.name,
        "status": status,
        "fixture_assertions": len(fixture_passes),
        "contract_assertions": len(contract_passes),
        "live_assertions": len(live_passes),
        "static_assertion_sites": static_count,
        "skips": skips,
        "source_health": observed_health,
        "declared_source_health": metadata.get("thecolab.health", "untested"),
        "raw_exit_code": exit_code,
        "log": log,
    }


def write_summary(results: list[dict[str, object]]) -> None:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    counts = {state: sum(result["status"] == state for result in results) for state in ("pass", "gated", "untested", "fail")}
    lines = [
        "## Skill smoke results",
        "",
        "| Skill | Status | Fixtures | Contract | Live | Skips |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    lines.extend(
        f"| `{result['skill']}` | {result['status']} | {result['fixture_assertions']} | {result['contract_assertions']} | {result['live_assertions']} | {len(result['skips'])} |"
        for result in results
    )
    lines.extend(("", f"PASS: {counts['pass']} | GATED: {counts['gated']} | UNTESTED: {counts['untested']} | FAIL: {counts['fail']}", ""))
    for result in results:
        if result["status"] == "fail":
            lines.extend((f"<details><summary>{result['skill']}</summary>", "", "```", str(result["log"]), "```", "</details>", ""))
    with Path(summary_path).open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skills", nargs="*", help="optional skill names; defaults to all")
    parser.add_argument("--changed-from", help="run skills changed from this git revision")
    parser.add_argument("--jobs", type=int, default=16)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--summary-json",
        action="store_true",
        help="emit counts plus failing, untested, and missing-fixture records",
    )
    args = parser.parse_args()
    try:
        names = args.skills or (changed_skills(args.changed_from) if args.changed_from else [])
    except RuntimeError as exc:
        parser.error(str(exc))
    if names:
        skill_dirs = [REPO_ROOT / "skills" / name for name in names]
    elif args.changed_from:
        skill_dirs = []
    else:
        skill_dirs = list(iter_skill_dirs(REPO_ROOT))
    with ThreadPoolExecutor(max_workers=min(max(1, args.jobs), max(1, len(skill_dirs)))) as executor:
        results = list(executor.map(lambda path: run_one(path, args.timeout), skill_dirs))
    results.sort(key=lambda result: str(result["skill"]))
    write_summary(results)
    if args.summary_json:
        counts = {
            state: sum(result["status"] == state for result in results)
            for state in ("pass", "gated", "untested", "fail")
        }
        print(
            json.dumps(
                {
                    "schema_version": "1",
                    "counts": counts,
                    "failures": [result for result in results if result["status"] == "fail"],
                    "untested": [
                        {"skill": result["skill"], "skips": result["skips"]}
                        for result in results
                        if result["status"] == "untested"
                    ],
                    "without_fixture_assertions": [
                        result["skill"]
                        for result in results
                        if result["fixture_assertions"] == 0
                    ],
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    elif args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        for result in results:
            print(
                f"[{str(result['status']).upper()}] {result['skill']} "
                f"fixtures={result['fixture_assertions']} contract={result['contract_assertions']} "
                f"live={result['live_assertions']} skips={len(result['skips'])}"
            )
            if result["status"] == "fail":
                print(result["log"])
        counts = {state: sum(result["status"] == state for result in results) for state in ("pass", "gated", "untested", "fail")}
        print(f"PASS: {counts['pass']}, GATED: {counts['gated']}, UNTESTED: {counts['untested']}, FAIL: {counts['fail']}")
    return 1 if any(result["status"] == "fail" for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
