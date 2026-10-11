#!/usr/bin/env python3
"""Bounded live source/schema and CLI probes; outages skip, parser failures fail."""
import json
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cli  # noqa: E402


def probe(name, action):
    try:
        action()
    except cli.SourceError as exc:
        if exc.code in (4, 5):
            print(f'[SKIP] {name}: {exc}')
            return True
        print(f'[FAIL] live {name}: {exc}')
        return False
    except Exception as exc:
        print(f'[FAIL] live {name}: {type(exc).__name__}: {exc}')
        return False
    print(f'[PASS] live {name}')
    return True


def source_check(source):
    rows = cli.load_uncached(source)
    assert len(rows) > 0
    for row in rows[:3]:
        assert row['source'] == source
        assert row['name']
        assert row['source_url'].startswith('https://')
        assert row['publisher']
        assert row['retrieved_at'].endswith('Z')
        assert row.get('licence') is None
    if source in ('recyclemap', 'wasteminz', 'branz', 'ecycle', 'agrecovery', 'beautification',
                  'christchurch', 'habitat'):
        assert any(r['lon'] is not None and r['lat'] is not None for r in rows)
    if source == 'recyclemap':
        assert any(cli.material_matches(r, 'battery') for r in rows)
    if source == 'branz':
        assert any('Concrete' in r['materials'] for r in rows)
    if source == 'christchurch':
        assert any('Recycling' in r['materials'] for r in rows)
        assert all('outSR=4326' in r['source_url'] for r in rows)
    if source == 'habitat':
        assert all(r['materials'] == ['Reuse'] for r in rows)
        assert all(not cli.material_matches(r, 'clothing') for r in rows)
        assert sum(r['lon'] is not None for r in rows) >= len(rows) - 1
    if source == 'crc':
        assert all(r['address'] and r['display_address'] and r['lon'] is None for r in rows)
        distinct = [r for r in rows if r.get('address_forms_differ')]
        warnings = rows[0].get('source_warnings') or []
        assert bool(distinct) == bool(warnings)
        assert all(r['address'] != r['display_address'] or not r.get('address_forms_differ') for r in rows)
    print(f'  {source}: {len(rows)} directory entries')


def repair_check():
    urls = cli.repair_urls(cli.get(cli.SOURCES['repair']['url']))
    link = next(u for u in urls if 'auckland-central-city-library' in u)
    row = cli.parse_repair(cli.get(link), link, cli.utc_now())
    assert 'Lorne Street' in row['address']
    assert 'Saturday' in row['hours']
    assert row['lon'] is None
    print(f'  repair: {len(urls)} café URLs; {row["name"]}, {row["address"]}')


def cli_find_check():
    result = subprocess.run([sys.executable, str(Path(cli.__file__)), 'find', '--material', 'battery',
                             '--near=174.7633,-36.8485', '--radius', '10', '--source', 'wasteminz',
                             '--refresh', '--limit', '3', '--format', 'geojson', '--json'],
                            capture_output=True, text=True, timeout=20)
    payload = json.loads(result.stdout)
    if result.returncode:
        error = payload['error']
        raise cli.SourceError(error['message'], error['code'])
    assert payload['type'] == 'FeatureCollection'
    assert payload['meta']['publisher'] == 'WasteMINZ'
    assert len(payload['features']) > 0
    for feature in payload['features']:
        assert feature['geometry']['type'] == 'Point'
        assert feature['properties']['distance_km'] <= 10
        assert feature['properties']['source'] == 'wasteminz'
    print('  Auckland battery GeoJSON: ' + ', '.join(f['properties']['name'] for f in payload['features']))


def council_check():
    result = subprocess.run([sys.executable, str(Path(cli.__file__)), 'item', 'battery', '--json'],
                            capture_output=True, text=True, timeout=10)
    payload = json.loads(result.stdout)
    assert result.returncode == 7
    assert payload['error']['type'] == 'unsupported_operation'
    assert payload['meta']['source_url'] == cli.COUNCIL
    assert payload['results'] == []
    print('[PASS] contract Council item guidance is explicitly unsupported')


def unsupported_feed_check(source):
    with tempfile.TemporaryDirectory() as cache:
        env = {**os.environ, 'XDG_CACHE_HOME': cache}
        result = subprocess.run([sys.executable, str(Path(cli.__file__)), 'search', 'Sampletown',
                                 '--source', source, '--refresh', '--json'],
                                env=env, capture_output=True, text=True, timeout=10)
        payload = json.loads(result.stdout)
        assert result.returncode == 7
        assert payload['error']['type'] == 'unsupported_operation'
        assert payload['results'] == []
        assert payload['meta']['source_url'] == cli.SOURCES[source]['url']
        assert 'base44.app' not in result.stdout
        assert 'wp-json/wpgmza' not in result.stdout
        for key in ('seller_email', 'seller_name', 'created_by'):
            assert key not in result.stdout
        assert not (Path(cache) / 'nz-recycling-locator' / (source + '.json')).exists()
    print(f'  {source} search is unsupported, makes no cache file, and returns {cli.SOURCES[source]["url"]}')


def main():
    fixtures = Path(cli.ROOT) / 'tests' / 'fixtures'
    sentinel = json.loads((fixtures / 'contract.json').read_text())
    assert sentinel['skill'] == 'nz-recycling-locator'
    rows = cli.parse_recyclemap(json.loads((fixtures / 'recyclemap-markers.json').read_text()),
                               json.loads((fixtures / 'recyclemap-maps.json').read_text()),
                               json.loads((fixtures / 'recyclemap-categories.json').read_text()), '2026-10-08T00:00:00Z')
    assert rows[1]['materials'] == ['Batteries']
    print('[PASS] fixture synthetic RecycleMap marker/material join')
    stamp = '2026-10-08T00:00:00Z'
    depots = cli.parse_christchurch(json.loads((fixtures / 'christchurch.json').read_text()), stamp)
    assert depots[0]['materials'] == ['Recycling', 'Refuse']
    assert depots[0]['latest_data'] == '2026-01-01T00:00:00.123Z'
    assert depots[0]['lon'] == 172.61
    print('[PASS] fixture synthetic Christchurch acceptance, edit date and WGS84')
    shops = cli.parse_habitat((fixtures / 'habitat.html').read_text(), stamp)
    assert len(shops) == 4 and shops[0]['materials'] == ['Reuse']
    assert shops[2]['lon'] == 174.78 and shops[3]['lon'] is None
    print('[PASS] fixture synthetic Habitat reuse labels and edge-only coordinate noise')
    centres = cli.parse_crc((fixtures / 'crc.html').read_text(), stamp)
    assert len(centres) == 3 and centres[2]['address_forms_differ']
    assert centres[0]['address'] != centres[2]['display_address']
    print('[PASS] fixture synthetic CRC addresses kept as distinct publisher forms')
    sources = ('recyclemap', 'wasteminz', 'branz', 'ecycle', 'agrecovery', 'beautification',
               'tyrewise', 'christchurch', 'habitat', 'crc')
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda s: probe(s, lambda: source_check(s)), sources))
    results.append(probe('repair café sitemap and Auckland detail', repair_check))
    results.append(probe('find Auckland batteries with GeoJSON', cli_find_check))
    for source in ('trow', 'zerowaste'):
        try:
            unsupported_feed_check(source)
            print(f'[PASS] contract {source} feed is explicitly unsupported')
        except Exception as exc:
            print(f'[FAIL] contract {source} unsupported state: {type(exc).__name__}: {exc}')
            results.append(False)
    try:
        council_check()
    except cli.SourceError as exc:
        print(f'[SKIP] council: {exc}')
    return 0 if all(results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
