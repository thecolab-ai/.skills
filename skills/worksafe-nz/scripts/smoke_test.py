#!/usr/bin/env python3
"""Synthetic parser assertions followed by bounded live WorkSafe probes."""
import json
import subprocess
import sys
from pathlib import Path
from test_contract import fixture_checks

CLI = Path(__file__).with_name('cli.py')


def main():
    fixture_checks()
    cases = [(['sources'], 'sources'), (['datasets'], 'datasets'),
             (['incidents', '--industry', 'Construction', '--region', 'Auckland', '--limit', '2'], 'construction incidents'),
             (['fatalities', '--year', '2025', '--industry', 'Construction'], 'construction fatalities'),
             (['summary', '--dataset', 'concerns', '--by', 'region', '--industry', 'Construction'], 'construction concerns summary')]
    for args, label in cases:
        proc = subprocess.run([sys.executable, str(CLI), *args, '--json'], capture_output=True, text=True, timeout=150)
        data = json.loads(proc.stdout)
        if proc.returncode in (4, 5):
            assert data['error']['code'] == proc.returncode and data['results'] == []
            print(f'[SKIP] live {label}: {data["error"]["message"]}')
            continue
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert data['meta']['source_url'] and data['meta']['retrieved_at'].endswith('Z')
        assert data['results'], f'{label} returned no results'
        if label == 'datasets':
            assert len(data['results']) == 5
            for record in data['results']:
                assert record['row_count'] > 0 and record['count'] > 0 and record['latest_data']
                print(f'[PASS] live {record["dataset"]}: {record["row_count"]} CSV rows, {record["count"]} count, latest {record["latest_data"]}')
        elif label == 'construction incidents':
            assert all('Construction' in r['industry'] and r['region'] == 'Auckland' for r in data['results'])
            print(f'[PASS] live {label}: matched count {data["meta"]["matched_count"]}, sample count {data["results"][0]["count"]}')
        else:
            print(f'[PASS] live {label}: {len(data["results"])} results')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
