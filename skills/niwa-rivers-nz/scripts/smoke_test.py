#!/usr/bin/env python3
"""Synthetic assertions followed by bounded, outage-aware keyless live queries."""
from __future__ import annotations

import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from test_contract import fixture_checks

CLI = Path(__file__).with_name('cli.py')


def probe(name, argv):
    try:
        completed = subprocess.run([sys.executable, str(CLI), *argv], capture_output=True,
                                   text=True, timeout=70, check=False)
        data = json.loads(completed.stdout)
    except subprocess.TimeoutExpired:
        return True, f'[SKIP] live {name}: network error: bounded CLI timeout'
    except (ValueError, OSError) as exc:
        return False, f'[FAIL] live {name}: invalid CLI result ({type(exc).__name__})'
    if completed.returncode in (4, 5):
        return True, f'[SKIP] live {name}: {data.get("error", {}).get("message", "upstream unavailable")}'
    try:
        assert completed.returncode == 0, data.get('error') or completed.stderr
        meta = data['meta']
        assert meta['source_url'] and meta['publisher'] and meta['retrieved_at'].endswith('Z')
        assert meta['licence']
        rows = data.get('results', data.get('features'))
        assert isinstance(rows, list) and rows, 'expected a non-empty live sample'
        if name == 'stations':
            assert all(row['station'].isdigit() and row['observations_available'] is False for row in rows)
            assert meta['region_filter'] == 'Canterbury' and meta['unique_stations'] > 0
            assert meta['latest_data'] and all(row['latest_data'] for row in rows)
        elif name == 'flood coverage':
            assert data['type'] == 'FeatureCollection'
            assert all(row['properties']['geometry_role'] == 'product_coverage_bbox' for row in rows)
            assert all(row['properties']['region'] == 'Auckland' for row in rows)
            assert all(row['properties']['hazard_values_available'] is False for row in rows)
        elif name == 'fish passage':
            assert data['type'] == 'FeatureCollection' and len(rows) <= 3
            assert meta['number_matched'] >= len(rows)
            assert all(row['geometry']['type'] == 'Point' and row['properties']['structure_type'] for row in rows)
            assert all(174.6 <= row['geometry']['coordinates'][0] <= 174.9 and
                       -37 <= row['geometry']['coordinates'][1] <= -36.7 for row in rows)
        elif name == 'river predictions':
            assert data['type'] == 'FeatureCollection' and len(rows) <= 2
            assert meta['metric'] == 'Mean Flow' and meta['matched_in_box'] >= len(rows)
            assert all(row['properties']['metric'] == 'Mean Flow' for row in rows)
            assert all(row['properties']['value'] is None or row['properties']['value'] >= 0 for row in rows)
            assert all(row['geometry']['type'] == 'MultiLineString' for row in rows)
            assert all(row['properties']['distance_km'] < 10 for row in rows)
        return True, f'[PASS] live {name}: {len(rows)} records; source total/matches={meta.get("source_total", meta.get("number_matched", meta.get("matched_in_box")))}; provenance and source semantics'
    except (AssertionError, KeyError, TypeError) as exc:
        return False, f'[FAIL] live {name}: {exc}'


def main():
    try:
        fixture_checks()
    except Exception as exc:
        print(f'[FAIL] fixture NIWA freshwater: {exc}')
        return 1
    cases = [
        ('stations', ['stations', '--region', 'Canterbury', '--json']),
        ('flood coverage', ['flood-hazard', '--region', 'Auckland', '--bbox', '174.6,-37,174.9,-36.7', '--format', 'geojson']),
        ('fish passage', ['fish-passage', '--bbox', '174.6,-37,174.9,-36.7', '--limit', '3', '--offset', '5', '--format', 'geojson']),
        ('river predictions', ['rivers', '--near', '174.7,-36.9', '--limit', '2', '--format', 'geojson']),
    ]
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda case: probe(*case), cases))
    for _, message in results:
        print(message)
    print('[SKIP] live hourly observation values: DataHub authentication required; keyless catalogue metadata tested separately')
    print('[SKIP] live flood raster values: account/licence download required; public coverage metadata tested separately')
    return 0 if all(ok for ok, _ in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
