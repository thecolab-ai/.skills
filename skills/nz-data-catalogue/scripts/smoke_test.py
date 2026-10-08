#!/usr/bin/env python3
"""Real fixtures plus bounded, outage-aware public endpoint GET probes."""
import json
import subprocess
import sys
from pathlib import Path
from test_contract import fixture_checks

CLI = Path(__file__).with_name('cli.py')

def main():
    try:
        fixture_checks()
    except Exception as exc:
        print(f'[FAIL] fixture catalogue/source parser: {exc}')
        return 1
    for id in ('C0024', 'C0064'):
        try:
            result = subprocess.run([sys.executable, str(CLI), 'check', id, '--json'], capture_output=True, text=True, timeout=30)
            data = json.loads(result.stdout)
            probe = data['data'].get('check', {})
        except subprocess.TimeoutExpired:
            print(f'[SKIP] live {id}: network error: timed out')
            continue
        except (OSError, ValueError) as exc:
            print(f'[FAIL] live {id}: invalid CLI result ({type(exc).__name__})')
            return 1
        if result.returncode in (4, 5):
            print(f"[SKIP] live {id}: {data.get('error')}")
            continue
        try:
            assert result.returncode == 0, data.get('error') or result.stderr
            assert data['ok'] and probe['http_status'] == 200
            assert probe['status'] == 'reachable'
            assert data['retrieval_kind'] == 'live_get'
            assert probe['sample_bytes'] <= 65536
            assert data['source_url'] and data['publisher'] and data['retrieved_at'].endswith('Z')
            assert probe['fetch_skills']
        except (AssertionError, KeyError, TypeError) as exc:
            print(f'[FAIL] live {id}: {exc}')
            return 1
        print(f"[PASS] live {id}: HTTP 200, {probe['sample_bytes']} bytes, provenance and skill route")
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
