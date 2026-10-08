#!/usr/bin/env python3
"""Reconcile bot-owned nightly smoke issues; --dry-run never calls gh."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

MARKER = "<!-- thecolab-nightly-smoke -->"
LABEL = "nightly-smoke"
BOT_AUTHORS = {"app/github-actions", "github-actions"}
SENSITIVE_ENV_NAME = re.compile(r"API_?KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL", re.I)


def redact_log(log: str) -> str:
    """Redact before truncation, including before publishing summary artifacts."""
    values = {value for name, value in os.environ.items() if SENSITIVE_ENV_NAME.search(name) and value}
    for value in sorted(values, key=len, reverse=True):
        log = log.replace(value, "***")
    log = re.sub(r"Bearer\s+\S+", "Bearer ***", log, flags=re.I)
    log = re.sub(r"eyJ[\w-]+\.[\w-]+\.[\w-]+", "***", log)
    return re.sub(r"(key|token|sig)=[^&\s]+", r"\1=***", log, flags=re.I)


def failure_excerpt(log: str) -> str:
    log = redact_log(log)
    highlights = "\n".join(line for line in log.splitlines()
                           if re.search(r"\[FAIL\]|\[SKIP\]|error", line, re.I))
    # Bound both sections and retain the end, where tracebacks usually occur.
    tail = log[-4096:]
    return highlights[-4096:] + "\n\nLog tail:\n" + tail if highlights else tail


def parse_summary(summary: dict, run_url: str) -> list[dict]:
    """Missing/gated skills never count as recovered."""
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
        log = failure_excerpt(str(result.get("log") or "No failure log was recorded."))
        # Every upstream-controlled line, including metadata, stays indented.
        details = redact_log(f"Source health: {result.get('source_health', 'unknown')}\n"
                             f"Exit code: {result.get('raw_exit_code', 'unknown')}")
        body = (f"{MARKER}\nSmoke checks failed for `{skill}`.\n\nRun: {run_url}\n\n"
                "Failure summary (see the run for the full log):\n\n" +
                "\n".join("    " + line for line in (details + "\n" + log).splitlines()) + "\n")
        actions.append({"skill": skill, "action": "upsert" if status == "fail" else "close",
                        "title": f"Smoke failure: {skill}",
                        "body": body if status == "fail" else f"Smoke checks passed again: {run_url}"})
    return sorted(actions, key=lambda item: item["skill"])


def load_actions(path: Path, run_url: str) -> list[dict]:
    """A missing, empty or invalid run artifact is a runner failure, never recovery."""
    try:
        summary = json.loads(path.read_text(encoding="utf-8"))
        if not summary.get("results"):
            raise ValueError("summary has no observed results")
        actions = parse_summary(summary, run_url)
    except (OSError, ValueError, TypeError, AttributeError):
        return parse_summary({"schema_version": "1", "results": [
            {"skill": "runner", "status": "fail", "log": "error: this run's smoke summary is missing, empty or invalid"}
        ]}, run_url)
    # A complete artifact proves summary production recovered, even if skills failed.
    actions += parse_summary({"schema_version": "1", "results": [
        {"skill": "runner", "status": "pass"}
    ]}, run_url)
    return actions


def gh(arguments: list[str]) -> str:
    result = subprocess.run(["gh", *arguments], capture_output=True, text=True, timeout=10, check=False)
    if result.returncode:
        raise RuntimeError(redact_log(result.stderr.strip() or "gh command failed"))
    return result.stdout


def owned_issue(issue: dict) -> bool:
    author = issue.get("author") or {}
    return (isinstance(author, dict) and author.get("login") in BOT_AUTHORS
            and LABEL in {label.get("name") for label in issue.get("labels", [])}
            and MARKER in (issue.get("body") or ""))


def reconcile(actions: list[dict], repo: str, run_url: str) -> None:
    issues = json.loads(gh(["issue", "list", "--repo", repo, "--label", LABEL,
                           "--state", "all", "--limit", "1000",
                           "--json", "number,title,state,author,labels,body"]))
    # Refuse a possibly truncated inventory rather than create duplicate issues.
    if len(issues) >= 1000:
        raise RuntimeError("nightly-smoke issue inventory reached 1000; pagination is required")
    by_title: dict[str, list[dict]] = {}
    for issue in issues:
        if owned_issue(issue):
            by_title.setdefault(issue["title"], []).append(issue)
    errors = []
    label_ready = False
    for action in actions:
        try:
            matches = sorted(by_title.get(action["title"], []), key=lambda issue: issue["number"])
            if action["action"] == "close":
                for issue in matches:
                    if issue["state"] == "OPEN":
                        gh(["issue", "close", str(issue["number"]), "--repo", repo,
                            "--comment", f"Smoke checks passed again: {run_url}"])
                continue
            with tempfile.TemporaryDirectory(prefix="smoke-issue-") as directory:
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
                    if not label_ready:
                        gh(["label", "create", LABEL, "--repo", repo, "--color", "B60205",
                            "--description", "Automated nightly smoke failures", "--force"])
                        label_ready = True
                    gh(["issue", "create", "--repo", repo, "--label", LABEL,
                        "--title", action["title"], "--body-file", str(body_file)])
        except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.TimeoutExpired) as exc:
            errors.append(f"{action['skill']}: {redact_log(str(exc))}")
    if errors:
        raise RuntimeError("; ".join(errors))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("summary", type=Path)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--run-url", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        actions = load_actions(args.summary, args.run_url)
        if not args.dry_run:
            reconcile(actions, args.repo, args.run_url)
        print(json.dumps(actions, indent=2) if args.json else f"{'Planned' if args.dry_run else 'Reconciled'} {len(actions)} issue states")
        return 0
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(f"smoke-failure-issues: {redact_log(str(exc))}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
