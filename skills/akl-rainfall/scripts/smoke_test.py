#!/usr/bin/env python3
"""Bounded real HTTP probes plus deterministic fixture checks."""
from datetime import datetime, timedelta
import json
from pathlib import Path
import subprocess
import sys

import cli
from test_contract import fixture_checks

ENTRY = Path(__file__).with_name('cli.py')


def run(*args):
    result = subprocess.run([sys.executable, str(ENTRY), *args, '--json'], capture_output=True, text=True, timeout=25)
    if result.returncode in (4, 5):
        print(f'[SKIP] live upstream unavailable: {result.stderr.strip() or result.stdout.strip()}')
        return None
    if result.returncode:
        raise AssertionError(result.stderr.strip() or result.stdout)
    return json.loads(result.stdout)


def no_recent_data(payload, site):
    if payload['meta']['count'] == 0 or all(row['value'] is None for row in payload['results']):
        print(f'[SKIP] live gauge {site} has no recent data (source health degraded)')
        return True
    return False


def main():
    try:
        fixture_checks()
    except (AssertionError, cli.SkillError, KeyError, ValueError) as exc:
        print(f'[FAIL] fixture {exc}')
        return 1
    try:
        sites = run('sites', '--parameter', 'rainfall', '--bbox', '174.88,-36.99,174.89,-36.97', '--format', 'geojson')
        if sites is not None:
            assert sites['type'] == 'FeatureCollection' and sites['meta']['count'] > 0
            assert any(f['properties']['site'] == '649940' for f in sites['features'])
            assert sites['meta']['publisher'] == 'Auckland Council' and sites['meta']['retrieved_at'].endswith('Z')
            print('[PASS] live rainfall site discovery, bbox, GeoJSON and provenance')
        end = datetime.now(cli.NZST).replace(hour=0, minute=0, second=0, microsecond=0)
        start = end - timedelta(days=1)
        for parameter, site, interval, units in [('rainfall', '649940', 'hour', 'mm'), ('level', '43803', 'hour', 'm'), ('flow', '43803', 'day', 'm^3/s')]:
            series = run('series', '--site', site, '--parameter', parameter, '--from', start.isoformat(), '--to', end.isoformat(), '--interval', interval)
            if series is not None:
                assert set(series) == {'meta', 'results'}
                assert series['meta']['publisher'] == 'Auckland Council' and series['meta']['source_url']
                assert series['meta']['retrieved_at'].endswith('Z')
                assert series['meta']['count'] == len(series['results'])
                if no_recent_data(series, site):
                    continue
                assert all(r['units'] == units and r['time'].endswith('+12:00') and r['period_end'] == r['time'] and r['period_start'].endswith('+12:00') for r in series['results'])
                print(f"[PASS] live {parameter} {interval} series: {series['meta']['count']} records, {units}")
        latest = run('latest', '--parameter', 'rainfall', '--bbox', '174.88,-36.99,174.89,-36.97')
        if latest is not None and not no_recent_data(latest, '649940'):
            assert latest['meta']['publisher'] == 'Auckland Council' and latest['meta']['retrieved_at'].endswith('Z')
            assert latest['meta']['count'] > 0 and any(r['site'] == '649940' for r in latest['results'])
            assert all(r['value'] is not None and r['time'] and 'age_hours' in r and r['source_url'] for r in latest['results'])
            print(f"[PASS] live latest rainfall: {latest['meta']['count']} gauges, quality and age preserved")
    except (AssertionError, subprocess.TimeoutExpired, KeyError, ValueError) as exc:
        print(f'[FAIL] live {exc}')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
