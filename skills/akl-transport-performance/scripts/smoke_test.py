#!/usr/bin/env python3
"""Synthetic fixtures plus bounded, outage-aware public source probes."""
import json
import subprocess
import sys
from pathlib import Path
from fixture_checks import check_fixtures


def main():
    check_fixtures()
    script = Path(__file__).with_name('cli.py')
    cases = [
        ('daily patronage', ['patronage', '--mode', 'bus'], 'boardings'),
        ('monthly route patronage', ['patronage', '--mode', 'bus', '--route', '101'], 'route'),
        ('monthly service performance', ['punctuality', '--route', '101'], 'reliability'),
        ('Metlink daily bus performance', ['metlink', '--route', '1'], 'patronage'),
        ('parking inventory (undated availability)', ['carparks', '--inventory'], 'total_spaces'),
    ]
    for label, arguments, field in cases:
        if arguments[0] != 'carparks':
            arguments = [*arguments, '--max-age', '0']
        completed = subprocess.run([sys.executable, str(script), *arguments, '--json'],
                                   capture_output=True, text=True, timeout=55, check=False)
        payload = json.loads(completed.stdout)
        if completed.returncode in {4, 5}:
            print(f"[SKIP] {label}: network error: {payload['error']['message']}")
            continue
        if completed.returncode:
            print(f"[FAIL] schema {label}: {payload}")
            return 1
        assert payload['results'] and field in payload['results'][0]
        meta = payload['meta']
        assert meta['source_url'].startswith('https://') and meta['publisher'] and meta['retrieved_at'].endswith('Z')
        if arguments[0] != 'carparks':
            assert meta['latest_data'] and all(r['source_url'] and r['retrieved_at'] for r in payload['results'])
        if '--route' in arguments:
            route = arguments[arguments.index('--route') + 1]
            assert all(r['route'] == route for r in payload['results'])
        print(f"[PASS] live {label}: {len(payload['results'])} records; latest_data={meta.get('latest_data', 'not stated')}")
    print('[SKIP] AT city vacancy endpoint: robots.txt disallows /umbraco/; not queried')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
