#!/usr/bin/env python3
"""Live smoke tests for the SEEK.co.nz skill."""
from __future__ import annotations

import json
import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CLI = ROOT / "skills" / "seek-co-nz" / "scripts" / "cli.py"


def load_cli():
    spec = importlib.util.spec_from_file_location("seek_cli", CLI)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_json(*args: str) -> dict:
    proc = subprocess.run(
        [sys.executable, str(CLI), *args, "--json"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=60,
    )
    if proc.returncode != 0:
        raise AssertionError(f"command failed: {proc.args}\nSTDERR:\n{proc.stderr}\nSTDOUT:\n{proc.stdout}")
    return json.loads(proc.stdout)


def main() -> int:
    cli = load_cli()
    fixture = '''<h1>1 jobs</h1><article data-testid="job-card" data-job-id="123"><a data-automation="jobTitle" href="/job/123">Python Developer</a><span data-automation="jobCompany">Fixture Ltd</span><span data-automation="jobLocation">Auckland</span></article>'''
    parsed = cli.parse_search_page(fixture, source_url="https://nz.seek.com/python-jobs", elapsed_ms=1, limit=3)
    assert parsed["returned_count"] == 1 and parsed["jobs"][0]["job_id"] == "123", parsed
    print("[PASS] fixture SEEK job card parses")

    try:
        search = run_json("search", "python developer", "--where", "Auckland", "--limit", "3")
    except AssertionError as exc:
        detail = str(exc).lower()
        if "network error" in detail or "blocked after" in detail or "timed out" in detail:
            print("[SKIP] SEEK live assertions: upstream unavailable")
            return 0
        raise
    jobs = search.get("jobs") or []
    assert search.get("returned_count", 0) >= 1, search
    assert search.get("total_count") is None or search["total_count"] >= search["returned_count"]
    first = jobs[0]
    assert first.get("job_id"), first
    assert first.get("title"), first
    assert first.get("url", "").startswith("https://nz.seek.com/job/"), first

    detail = run_json("job", str(first["job_id"]))
    job = detail.get("job") or {}
    assert job.get("job_id") == str(first["job_id"]), job
    assert job.get("title"), job
    assert job.get("company"), job
    assert job.get("url", "").startswith("https://nz.seek.com/job/"), job

    bad = subprocess.run(
        [sys.executable, str(CLI), "job", "not-a-job-id", "--json"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
    )
    assert bad.returncode != 0
    assert "job id must contain digits" in bad.stderr

    print(
        "OK seek-co-nz smoke: "
        f"{search['returned_count']} jobs, first={first['job_id']} {first['title']!r}, "
        f"detail_company={job.get('company')!r}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
