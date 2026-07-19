#!/usr/bin/env python3
"""Deterministic Electoral Commission export checks plus bounded live probe."""
import json, subprocess, sys
from pathlib import Path
SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL.parents[1] / "lib"))
from election_results import candidate_matches, parse_document_links, parse_overall_results, parse_turnout, parse_winning_candidates  # noqa: E402

stamp = "2026-07-19T00:00:00Z"; url = "https://electionresults.govt.nz/electionresults_2023/statistics/csv/overall-results-summary.csv"
rows = parse_overall_results((SKILL / "tests/fixtures/overall-results.csv").read_text(), url, stamp)
assert rows[0]["party"] == "National Party" and rows[0]["party_votes"] == 1085850 and rows[0]["total_seats"] == 48
turnout = parse_turnout((SKILL / "tests/fixtures/turnout.csv").read_text(), url, stamp)
assert turnout[0]["electorate"] == "Wellington Central" and turnout[0]["turnout_percentage"] == 80.3
candidates = parse_winning_candidates((SKILL / "tests/fixtures/winning-candidates.csv").read_text(), url, stamp)
assert candidate_matches(candidates[0]["candidate"], "Chlöe Swarbrick")
assert candidate_matches(candidates[0]["candidate"], "Chloe Swarbrick")
assert candidate_matches(candidates[0]["candidate"], "Swarbrick Chloe")
links = parse_document_links((SKILL / "tests/fixtures/finance.html").read_text(), "https://elections.nz/finance", stamp, "Example Party")
assert len(links) == 1 and links[0]["document_url"].endswith("example-party.pdf")
print("[PASS] fixture result CSV fields and first-party finance link")
run = subprocess.run([sys.executable, str(SKILL/"scripts/cli.py"), "results", "--year", "2023", "--limit", "2", "--json"], capture_output=True, text=True, timeout=45)
if run.returncode == 0:
    payload=json.loads(run.stdout); assert payload["data"] and payload["source"]["url"].startswith("https://electionresults.govt.nz/"); print("[PASS] live official election results CSV")
elif run.returncode in {4,5}:
    print(f"[SKIP] Electoral Commission blocked/unavailable: {run.stderr.strip()}")
else: print(run.stderr, file=sys.stderr); raise SystemExit(1)
