#!/usr/bin/env python3
"""Synthetic parser assertions plus bounded, outage-aware public live probes."""
import json
import subprocess
import sys
from pathlib import Path

from fixture_checks import run

CLI = Path(__file__).with_name('cli.py')


def probe(arguments):
    result = subprocess.run([sys.executable, str(CLI), *arguments, '--json'], capture_output=True, text=True, timeout=40)
    payload = json.loads(result.stdout)
    if result.returncode in (4, 5):
        assert payload['results'] == [] and payload['error']['code'] == result.returncode
        print(f'[SKIP] network {arguments}: {payload["error"]["message"]}')
        return None
    assert result.returncode == 0, payload
    assert {'source_url', 'publisher', 'retrieved_at'} <= payload['meta'].keys()
    assert payload['meta']['retrieved_at'].endswith('Z')
    return payload


def main():
    run()
    for utility in ('watercare', 'wellington', 'kiwirail'):
        payload = probe(['outages', '--utility', utility])
        if payload is not None:
            required = {'utility', 'kind', 'status', 'start', 'end', 'area', 'geometry', 'affected_count', 'source_url', 'publisher', 'retrieved_at'}
            assert all(required <= row.keys() for row in payload['results'])
            for row in payload['results']:
                if row['geometry']:
                    lon, lat = row['geometry']['coordinates']
                    assert -180 <= lon <= 180 and -90 <= lat <= 90
            print(f'[PASS] live {utility}: {len(payload["results"])} normalised records with provenance')
    payload = probe(['rail-closures'])
    if payload is not None:
        assert payload['meta']['coverage_start'] <= payload['meta']['coverage_end']
        assert payload['meta']['latest_data']
        assert all(payload['meta']['coverage_start'] <= row['start'] <= payload['meta']['coverage_end'] for row in payload['results'])
        print(f'[PASS] live rail calendar: {len(payload["results"])} closure days; coverage {payload["meta"]["coverage_start"]} to {payload["meta"]["coverage_end"]}')
    # The skipped adapters are source capabilities, not upstream-success assertions.
    print('[SKIP] Vector client-rendered map has no verified keyless outage feed; Counties blocked; PowerNet terms require consent')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
