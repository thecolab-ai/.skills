#!/usr/bin/env python3
"""Deterministic Electoral Commission export checks plus bounded live probe."""
import json, subprocess, sys
from pathlib import Path
SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL.parents[1] / "lib"))
from election_results import candidate_matches, parse_document_links, parse_overall_results, parse_turnout, parse_winning_candidates  # noqa: E402
from political_finance import ANNUAL_URL, EXPENSE_URLS, filter_party, parse_annual_aggregates, parse_expense_aggregates, parse_reporting_rules  # noqa: E402
import nzfetch  # noqa: E402

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
annual_html = (SKILL / "tests/fixtures/finance-annual.html").read_text()
annual = parse_annual_aggregates(annual_html, ANNUAL_URL, stamp, 2025)
assert len(annual) == 4 and annual[0]["amount_nzd"] == "1234.50" and annual[1]["amount_nzd"] == "0.00"
assert filter_party(annual, "not a published party") == []
rules = parse_reporting_rules(annual_html, ANNUAL_URL, stamp, 2025)
assert any(row["amounts_nzd_mentioned"] == ["5000.00"] and row["effective_from"] is None for row in rules)
expense_html = (SKILL / "tests/fixtures/finance-expenses.html").read_text()
expenses = parse_expense_aggregates(expense_html, "https://elections.nz/democracy-in-nz/historical-events/2023-general-election/party-expenses", stamp, 2023)
assert len(expenses) == 8 and {row["metric"] for row in expenses} == {"election_expense_limit", "total_party_election_expenses", "broadcasting_allocation", "total_broadcasting_allocation_expenses"}
assert all(row["period_start"] == "2023-07-14" and row["period_end"] == "2023-10-13" for row in expenses)
print("[PASS] fixture aggregate finance, empty filter, reporting rules and privacy boundary")
unit = subprocess.run([sys.executable, str(SKILL/"scripts/test_finance.py")], capture_output=True, text=True, timeout=30)
assert unit.returncode == 0, unit.stdout + unit.stderr
print("[PASS] contract adversarial finance layouts and normal/empty/blocked CLI states")
run = subprocess.run([sys.executable, str(SKILL/"scripts/cli.py"), "results", "--year", "2023", "--limit", "2", "--json"], capture_output=True, text=True, timeout=45)
if run.returncode == 0:
    payload=json.loads(run.stdout); assert payload["data"] and payload["source"]["url"].startswith("https://electionresults.govt.nz/"); print("[PASS] live official election results CSV")
elif run.returncode in {4,5}:
    print(f"[SKIP] Electoral Commission blocked/unavailable: {run.stderr.strip()}")
else: print(run.stderr, file=sys.stderr); raise SystemExit(1)

try:
    live_html = nzfetch.fetch_text(ANNUAL_URL, timeout=20, allowed_hosts={"elections.nz", "www.elections.nz"})
    live_finance = parse_annual_aggregates(live_html, ANNUAL_URL, stamp, 2025)
    assert live_finance and all(row["reporting_year"] == 2025 for row in live_finance)
    assert filter_party(live_finance, "definitely-no-such-published-party-9f42") == []
    rules_2023 = parse_reporting_rules(live_html, ANNUAL_URL, stamp, 2023)
    rules_2024 = parse_reporting_rules(live_html, ANNUAL_URL, stamp, 2024)
    assert any(row["amounts_nzd_mentioned"] == ["20000.00"] for row in rules_2023)
    assert not any(row["amounts_nzd_mentioned"] == ["20000.00"] for row in rules_2024)
    try:
        parse_annual_aggregates(live_html, ANNUAL_URL, stamp, 2016)
    except ValueError as exc:
        assert "requested reporting year 2016" in str(exc)
    else:
        raise AssertionError("unsupported 2016 annual layout returned empty success")
    print("[PASS] live annual finance normal, empty-filter, year-scoped rules and unsupported-layout behaviour")
except (nzfetch.Blocked, nzfetch.RateLimited) as exc:
    print(f"[SKIP] live finance blocked: {exc}")
except nzfetch.FetchError as exc:
    print(f"[SKIP] live finance upstream unavailable: {exc}")

try:
    expense_url = EXPENSE_URLS[2023]
    live_expense_html = nzfetch.fetch_text(expense_url, timeout=20, allowed_hosts={"elections.nz", "www.elections.nz"})
    live_expenses = parse_expense_aggregates(live_expense_html, expense_url, stamp, 2023)
    assert live_expenses and all(row["period_start"] == "2023-07-14" and row["period_end"] == "2023-10-13" for row in live_expenses)
    live_expense_rules = parse_reporting_rules(live_expense_html, expense_url, stamp, 2023)
    evidence = "\n".join(str(row["evidence_text"]) for row in live_expense_rules)
    for required in ("$1,388,000", "$32,600", "13 March, 2024", "need to declare", "required to include an audit report"):
        assert required in evidence
    print("[PASS] live expense aggregates retain regulated period and complete core rules")
except (nzfetch.Blocked, nzfetch.RateLimited) as exc:
    print(f"[SKIP] live expense finance blocked: {exc}")
except nzfetch.FetchError as exc:
    print(f"[SKIP] live expense finance upstream unavailable: {exc}")
