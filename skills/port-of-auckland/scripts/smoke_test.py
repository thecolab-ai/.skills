#!/usr/bin/env python3
"""Bounded fixture and live source checks; upstream outages are explicit skips."""
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_contract import run_fixture_tests

CLI = Path(__file__).resolve().parent / 'cli.py'


def main():
    if not run_fixture_tests():
        print('[FAIL] fixture assertions failed')
        return 1
    for command, port in [('arrivals', 'auckland'), ('truck-turns', 'auckland'),
                          ('arrivals', 'tauranga'), ('truck-turns', 'tauranga')]:
        try:
            result = subprocess.run([sys.executable, str(CLI), command, '--port', port, '--json', '--max-age', '0'],
                                    capture_output=True, text=True, timeout=45)
            payload = json.loads(result.stdout)
            if result.returncode in (4, 5):
                assert payload['error']['code'] == result.returncode
                assert payload['results'] == []
                print(f"[SKIP] live {port} {command}: {payload['error']['message']}")
                continue
            assert result.returncode == 0, payload.get('error', result.stderr)
            assert payload['meta']['source_url'].startswith('https://')
            assert payload['meta']['publisher']
            assert payload['meta']['retrieved_at'].endswith('Z')
            assert isinstance(payload['results'], list)
            if command == 'arrivals':
                assert all(r['vessel'] and r['port'] == port for r in payload['results'])
            else:
                assert payload['results']
                metric = 'turn_seconds' if port == 'auckland' else 'queue_trucks'
                assert all(isinstance(r[metric], int) and r[metric] >= 0 for r in payload['results'])
                assert payload['meta']['latest_data']
            print(f"[PASS] live {port} {command}: {len(payload['results'])} records with provenance")
        except subprocess.TimeoutExpired:
            print(f'[SKIP] live {port} {command}: network error: probe timed out')
        except (ValueError, AssertionError, KeyError) as exc:
            print(f'[FAIL] live {port} {command}: {exc}')
            return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
