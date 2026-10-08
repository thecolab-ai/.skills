#!/usr/bin/env python3
"""Open/update one issue per failed skill; close it only on an explicit pass.

Uses gh and GH_TOKEN (the workflow's GITHUB_TOKEN). --dry-run never calls gh.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

MARKER = "<!-- thecolab-nightly-smoke -->"


def parse_summary(summary: dict, run_url: str) -> list[dict]:
    """Retain all observed statuses so a missing/gated skill never looks recovered."""
    if not isinstance(summary, dict) or summary.get("schema_version") != "1" or not isinstance(summary.get("results"), list):
        raise ValueError("summary must contain schema_version 1 and complete results")
    if not re.fullmatch(r"https://[^\s]+/actions/runs/\d+", run_url):
        raise ValueError("--run-url must be a GitHub Actions run URL")
    actions, seen = [], set()
    for result in summary["results"]:
        if not isinstance(result, dict):
            raise ValueError("summary results must be objects")
        skill, status = result.get("skill", ""), result.get("status")
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", skill) or skill in seen:
            raise ValueError("invalid or duplicate skill in summary")
        if status not in {"pass", "fail", "gated", "untested"}:
            raise ValueError(f"invalid smoke status for {skill}")
        seen.add(skill)
        if status not in {"pass", "fail"}:
            continue
        log = str(result.get("log") or "No failure log was recorded.")[:24000]
        # Indentation keeps upstream log text from escaping a fenced Markdown block.
        body = (
            f"{MARKER}\nSmoke checks failed for `{skill}`.\n\n"
            f"Run: {run_url}\n\n"
            f"Source health: {result.get('source_health', 'unknown')}\n"
            f"Exit code: {result.get('raw_exit_code', 'unknown')}\n\n"
            "Failure summary:\n\n" + "\n".join("    " + line for line in log.splitlines()) + "\n"
        )
        actions.append({"skill": skill, "action": "upsert" if status == "fail" else "close",
                        "title": f"Smoke failure: {skill}",
                        "body": body if status == "fail" else f"Smoke checks passed again: {run_url}"})
    return sorted(actions, key=lambda item: item["skill"])


def gh(arguments: list[str]) -> str:
    result = subprocess.run(["gh", *arguments], capture_output=True, text=True, timeout=10, check=False)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "gh command failed")
    return result.stdout


def reconcile(actions: list[dict], repo: str, run_url: str) -> None:
    for action in actions:
        issues = json.loads(gh(["issue", "list", "--repo", repo, "--state", "all", "--limit", "1000",
                               "--search", f'"{action["title"]}" in:title', "--json", "number,title,state"]))
        matches = sorted((issue for issue in issues if issue["title"] == action["title"]),
                         key=lambda issue: issue["number"])
        if action["action"] == "close":
            for issue in matches:
                if issue["state"] == "OPEN":
                    gh(["issue", "close", str(issue["number"]), "--repo", repo,
                        "--comment", f"Smoke checks passed again: {run_url}"])
            continue
        with tempfile.TemporaryDirectory(prefix="smoke-issue-", dir=".") as directory:
            body_file = Path(directory) / "body.md"
            body_file.write_text(action["body"], encoding="utf-8")
            if matches:
                if matches[0]["state"] == "CLOSED":
                    gh(["issue", "reopen", str(matches[0]["number"]), "--repo", repo])
                gh(["issue", "edit", str(matches[0]["number"]), "--repo", repo, "--body-file", str(body_file)])
                for duplicate in matches[1:]:
                    if duplicate["state"] == "OPEN":
                        gh(["issue", "close", str(duplicate["number"]), "--repo", repo,
                            "--comment", f'Duplicate of #{matches[0]["number"]}; latest run: {run_url}'])
            else:
                gh(["issue", "create", "--repo", repo, "--title", action["title"], "--body-file", str(body_file)])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("summary", type=Path)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--run-url", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        actions = parse_summary(json.loads(args.summary.read_text(encoding="utf-8")), args.run_url)
        if not args.dry_run:
            reconcile(actions, args.repo, args.run_url)
        print(json.dumps(actions, indent=2) if args.json else f"{'Planned' if args.dry_run else 'Reconciled'} {len(actions)} skill issue states")
        return 0
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(f"smoke-failure-issues: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
