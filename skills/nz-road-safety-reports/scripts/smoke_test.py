#!/usr/bin/env python3
"""Synthetic parser assertions and bounded, outage-aware public endpoint probes."""
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import cli
from provenance import provenance

FIXTURES = Path(__file__).resolve().parents[1] / 'tests' / 'fixtures'


def fixture_checks():
    meta = provenance(cli.BIKE, 'Synthetic fixture publisher')
    bike = json.loads((FIXTURES / 'bikemaps.json').read_text())
    records = cli.parse_bike(bike, 'nearmiss', meta, cli.AUCKLAND)
    assert len(records) == 1 and records[0]['properties']['kind'] == 'nearmiss'
    assert not {'pk', 'age', 'gender', 'details'} & records[0]['properties'].keys()
    assert meta['latest_data'] == '2025-03-01T09:00:00'
    assert cli.parse_bike(bike, 'nearmiss', meta, (175, -37, 176, -36)) == []
    for bad in ({}, {'type': 'FeatureCollection', 'features': [{}]}):
        try: cli.parse_bike(bad, 'nearmiss', meta, cli.AUCKLAND)
        except cli.SourceError as exc: assert exc.code == 6
        else: raise AssertionError('malformed BikeMaps accepted')
    print('[PASS] fixture BikeMaps geometry, filtering, source dates and field minimisation')

    meta = provenance(cli.CAMERAS, cli.NZTA)
    cameras = cli.parse_cameras((FIXTURES / 'cameras.html').read_text(), meta, cli.AUCKLAND)
    assert len(cameras) == 1 and cameras[0]['geometry']['coordinates'] == [174.74, -36.89]
    assert cameras[0]['properties']['region'] == 'Synthetic Region'
    assert meta['latest_data'] == '2026-10-01'
    assert all(f['properties']['latest_data'] == '2026-10-01' for f in cameras)
    try: cli.parse_cameras('<table><tr><td>Changed schema</td></tr></table>', meta)
    except cli.SourceError as exc: assert exc.code == 6
    else: raise AssertionError('malformed camera table accepted')
    print('[PASS] fixture camera table, WGS84 conversion and update date')

    meta = provenance(cli.ZONES, 'Synthetic mirror publisher')
    zones = cli.parse_zones((FIXTURES / 'zones.csv').read_text(), meta, (174.739, -36.891, 174.741, -36.889))
    assert len(zones) == 1 and zones[0]['geometry']['type'] == 'LineString'
    assert zones[0]['properties']['go_live'] == '2018-08'
    assert cli.distance(zones[0]['geometry'], (174.74, -36.89)) < 1
    assert not cli.line_hits_box(zones[0]['geometry']['coordinates'], (175, -37, 176, -36))
    assert abs(cli.distance({'type': 'Point', 'coordinates': [174.74, -36.88]}, (174.74, -36.89)) - 1111.95) < 0.01
    print('[PASS] fixture historical camera zones, segment intersection and corridor distance')

    meta = provenance(cli.POLICE, 'New Zealand Police')
    alerts = cli.parse_alerts((FIXTURES / 'police.xml').read_text(), meta)
    assert len(alerts) == 1 and alerts[0]['spatial_status'] == 'unlocated'
    assert alerts[0]['published_at'] == '2026-10-07T23:00:00Z'
    assert '<' not in alerts[0]['description'] and 'Example' in alerts[0]['description']
    print('[PASS] fixture Police RSS dates and text extraction')

    meta = provenance(cli.RELEASE, cli.NZTA)
    url = cli.infringement_link((FIXTURES / 'release.html').read_text(), meta)
    assert url == 'https://www.nzta.govt.nz/assets/synthetic-infringements.xlsx'
    assert meta['latest_data'] == '2026-05-31'
    newer = '<a href="/assets/synthetic-newer.xlsx">Safety camera infringement data to 31 August 2026 [XLSX]</a>'
    html = newer + (FIXTURES / 'release.html').read_text()
    assert cli.infringement_link(html, meta) == 'https://www.nzta.govt.nz/assets/synthetic-newer.xlsx'
    assert meta['latest_data'] == '2026-08-31'
    for bad in ('<p>No matching release</p>',
                newer + newer.replace('synthetic-newer.xlsx', 'ambiguous.xlsx'),
                newer.replace('/assets/synthetic-newer.xlsx', 'https://example.invalid/data.xlsx'),
                newer.replace('31 August', '32 August')):
        try: cli.infringement_link(bad, meta)
        except cli.SourceError as exc: assert exc.code == 6
        else: raise AssertionError('invalid or ambiguous infringement release accepted')
    with patch.object(cli, 'fetch', return_value=(html, meta)):
        try: cli.infringements()
        except cli.SourceError as exc:
            assert exc.code == 7 and 'not been verified' in str(exc)
            assert exc.meta['latest_data'] == '2026-08-31' and 'synthetic-newer.xlsx' in str(exc)
        else: raise AssertionError('unverified workbook filtering reported success')
    print('[PASS] fixture official workbook link discovery and explicit unverified schema gate')

    f = cameras[0]
    unavailable = cli.SourceError(4, 'network error: blocked', provenance(cli.CAMERAS, cli.NZTA))
    with patch.object(cli, 'incidents', return_value=([f], f['properties'])), \
         patch.object(cli, 'zones', return_value=([], meta)), \
         patch.object(cli, 'cameras', side_effect=unavailable), \
         patch.object(cli, 'infringements', side_effect=unavailable):
        rows, status = cli.corridor((174.74, -36.89), 500)
        assert len(rows) == 2 and len(status) == 6
        assert [s['status'] for s in status].count('unavailable') == 2
        assert all(r['properties']['distance_m'] == 0 for r in rows)
    print('[PASS] fixture corridor preserves unavailable sources beside available evidence')

    schema_error = cli.SourceError(6, 'Dated infringement workbook link missing', provenance(cli.RELEASE, cli.NZTA))
    with patch.object(cli, 'incidents', return_value=([], meta)), \
         patch.object(cli, 'zones', return_value=([], meta)), \
         patch.object(cli, 'cameras', return_value=([f], f['properties'])), \
         patch.object(cli, 'infringements', side_effect=schema_error):
        rows, status = cli.corridor((174.74, -36.89), 500)
        assert len(rows) == 1
        gate = next(s for s in status if s['source'] == 'nzta-infringements')
        assert gate['status'] == 'unavailable' and gate['error']['code'] == 6
        with patch.object(cli, 'cameras', side_effect=cli.SourceError(6, 'Camera schema changed', meta)):
            try: cli.corridor((174.74, -36.89), 500)
            except cli.SourceError as exc: assert exc.code == 6 and 'Camera schema' in str(exc)
            else: raise AssertionError('spatial source schema failure suppressed')
    print('[PASS] fixture corridor tolerates infringement schema failures and rejects spatial schema failures')


def live_probe(arguments):
    p = subprocess.run([sys.executable, str(Path(cli.__file__)), *arguments, '--json'],
                       capture_output=True, text=True, timeout=40)
    data = json.loads(p.stdout)
    assert data['meta']['source_url'] and data['meta']['retrieved_at'].endswith('Z')
    if p.returncode in (4, 5):
        assert data['results'] == [] and data['error']['code'] == p.returncode
        print('[SKIP] live ' + ' '.join(arguments) + ': ' + data['error']['message'])
        return
    if p.returncode == 7 and arguments[0] == 'infringements':
        assert data['error']['type'] == 'unsupported_operation'
        print('[SKIP] live infringements: workbook schema unverified')
        return
    assert p.returncode == 0, p.stdout + p.stderr
    if data.get('type') == 'FeatureCollection':
        assert isinstance(data['features'], list)
        rows = data['features']
        assert all(r['type'] == 'Feature' and r['properties']['source_url'] for r in rows)
    else:
        rows = data['results']; assert isinstance(rows, list)
    if arguments[0] == 'corridor':
        assert data['complete'] is False and len(data['source_status']) == 6
        assert all(r['properties']['distance_m'] <= 500 for r in rows)
    print('\n[PASS] live ' + ' '.join(arguments) + f': {len(rows)} records')


def main():
    fixture_checks()
    commands = [ ['incidents', '--kind', 'nearmiss'], ['incidents', '--kind', 'collision', '--format', 'geojson'],
                 ['cameras', '--bbox', '174.4,-37.2,175.2,-36.4'], ['infringements'], ['alerts'],
                 ['camera-zones', '--format', 'geojson'], ['corridor', '--near', '174.740,-36.890', '--radius', '500'] ]
    # Bounded concurrent probes keep the whole smoke within the repository timeout.
    with ThreadPoolExecutor(max_workers=7) as pool:
        list(pool.map(live_probe, commands))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
