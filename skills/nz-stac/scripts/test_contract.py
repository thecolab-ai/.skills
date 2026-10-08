#!/usr/bin/env python3
"""Deterministic CLI, repository policy and captured STAC parser checks."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))
from contract_test import audit_skill  # noqa: E402
from smoke_test import fixture_checks  # noqa: E402


def main():
    result = audit_skill(Path(__file__).resolve().parents[1])
    try:
        fixtures = fixture_checks()
        result["fixture_assertions"] += len(fixtures)
        result["checks"].append("captured_STAC_parser_and_bounded_spatial_search")
    except Exception as exc:
        result["errors"].append(f"STAC fixture failure: {exc}")
        result["ok"] = False
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
