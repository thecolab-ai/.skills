#!/usr/bin/env python3
"""Deterministic repository contract and synthetic source checks."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'lib'))
from contract_test import audit_skill  # noqa: E402
from fixture_checks import check_fixtures  # noqa: E402


def main():
    result = audit_skill(Path(__file__).resolve().parents[1])
    if result['ok']:
        check_fixtures()
        result['checks'].extend(['xlsx_parsers', 'csv_parser', 'source_discovery', 'filters', 'json_errors', 'cache_provenance', 'geojson'])
    print(json.dumps(result, indent=2))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
