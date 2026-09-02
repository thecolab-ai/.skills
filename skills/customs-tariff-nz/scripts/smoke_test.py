#!/usr/bin/env python3
"""Parser-fixture assertions plus a bounded, outage-aware live probe."""
from __future__ import annotations

import gzip
import io
import json
import subprocess
import sys
import tarfile
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "scripts"))

from customs_tariff import (
    MAX_ARCHIVE_MEMBERS,
    SkillError,
    formula_records,
    lookup_records,
    parse_archive,
    search_records,
)


def main() -> int:
    fixture = SKILL / "tests" / "fixtures" / "tariff-synthetic.tar.gz"
    dataset = parse_archive(fixture.read_bytes(), "fixture://tariff-synthetic.tar.gz", "2026-09-02T00:00:00Z")
    assert dataset.source_timestamp == "2026-09-02T04:00:01+12:00"
    assert len(dataset.details) == 4
    assert dataset.details[0]["tariff_code"] == "0101210010"
    print("[PASS] fixture archive schema, delimiter, encoding and source timestamp parsing")

    search = search_records(dataset, "coffee", "2026-09-02", 10)
    assert [row["tariff_code"] for row in search] == ["0901210000"]
    assert search[0]["description"] == "ROASTED COFFEE — SYNTHETIC"
    print("[PASS] fixture classification search and active-date filtering")

    lookup = lookup_records(dataset, "09.01.21.00.00", "2026-09-02")
    assert lookup["classification"]["statistical_unit"] == "KGM"
    assert lookup["rates"][0]["rate_group"] == "NML"
    assert lookup["rates"][0]["factors"]["a"] == "5.000000"
    assert lookup["levies"][0]["levy_type_code"] == "AL"
    assert lookup["levies"][0]["formula_rate"] == "0.050000"
    print("[PASS] fixture exact lookup joins classifications, rates, levies and formula rates")

    formulas = formula_records(dataset, "2", 20)
    assert formulas == [{"formula_code": "2", "formula_rate": "0.050000"}]
    prefixed_formulas = formula_records(dataset, "2", 20, prefix=True)
    assert [record["formula_code"] for record in prefixed_formulas] == ["2", "20"]
    print("[PASS] fixture formula lookup distinguishes exact and explicit prefix matching")

    tar_buffer = io.BytesIO()
    with tarfile.open(fileobj=tar_buffer, mode="w") as excessive:
        for index in range(MAX_ARCHIVE_MEMBERS + 1):
            member = tarfile.TarInfo(f"tiny-{index}.txt")
            member.size = 0
            excessive.addfile(member, io.BytesIO())
    try:
        parse_archive(
            gzip.compress(tar_buffer.getvalue(), mtime=0),
            "fixture://excessive",
            "2026-09-02T00:00:00Z",
        )
    except SkillError as exc:
        assert exc.exit_code == 6 and "too many members" in str(exc)
    else:
        raise AssertionError("excessive archive member count was accepted")
    print("[PASS] fixture archive member-count bound rejects metadata exhaustion")

    invalid_command = [sys.executable, str(SKILL / "scripts" / "cli.py"), "formula", "abc", "--json"]
    invalid = subprocess.run(invalid_command, capture_output=True, text=True, timeout=10, check=False)
    invalid_payload = json.loads(invalid.stdout)
    required = {"schema_version", "ok", "blocked", "source", "query", "data", "warnings", "error"}
    assert invalid.returncode == 2 and required <= invalid_payload.keys()
    assert invalid_payload["source"]["retrieved_at"] and invalid_payload["error"]["code"] == 2
    runner = SKILL.parents[1] / "scripts" / "run_skill.py"
    canonical = subprocess.run(
        [sys.executable, str(runner), SKILL.name, "formula", "abc"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    canonical_payload = json.loads(canonical.stdout)
    assert canonical.returncode == 2 and canonical_payload["error"]["code"] == 2
    print("[PASS] invalid-input envelope preserves exit code through canonical runner")

    command = [sys.executable, str(SKILL / "scripts" / "cli.py"), "formula", "2", "--json"]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
    if completed.returncode == 0:
        payload = json.loads(completed.stdout)
        assert payload["ok"] is True and payload["blocked"] is False
        assert payload["data"][0]["formula_code"]
        assert payload["source"]["timestamp"]
        print("[PASS] live Customs archive formula and timestamp retrieval")
    elif completed.returncode in {4, 5}:
        print(f"[SKIP] network or upstream unavailable: {completed.stderr.strip()}")
    else:
        print(f"[FAIL] live Customs probe failed: {completed.stderr.strip()}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
