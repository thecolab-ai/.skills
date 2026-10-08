#!/usr/bin/env python3
"""Synthetic source fixtures and deterministic filtering, caching and error checks."""
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from zipfile import BadZipFile

import cli
from transport import download_links, parse_inventory, parse_metlink, parse_patronage, parse_punctuality

FIXTURES = Path(__file__).resolve().parents[1] / 'tests' / 'fixtures'


def check_fixtures():
    daily = (FIXTURES / 'daily.xlsx').read_bytes()
    monthly = (FIXTURES / 'monthly.xlsx').read_bytes()
    punctuality = (FIXTURES / 'punctuality.xlsx').read_bytes()
    metlink = (FIXTURES / 'metlink.csv').read_bytes()
    inventory = (FIXTURES / 'inventory.json').read_bytes()
    rows = parse_patronage(daily, 'daily')
    assert len(rows) == 6 and rows[0]['period'] == '2026-09-27'
    assert next(r for r in rows if r['mode'] == 'ferry' and r['period'] == '2026-09-26')['boardings'] == 0
    assert parse_patronage((FIXTURES / 'epoch1904.xlsx').read_bytes(), 'daily')[0]['period'] == '1904-01-01'
    print('[PASS] fixture daily sparse XLSX, shared/inline strings, formula values, zero counts and 1904 epoch')
    rows = parse_patronage(monthly, 'monthly', True)
    assert len(rows) == 5 and rows[0]['route'] == '007'
    assert {r['period'] for r in rows} == {'2026-07', '2026-08'}
    assert parse_patronage(monthly, 'monthly')[0]['boardings'] == 200
    print('[PASS] fixture monthly route/mode XLSX excludes totals and future blank columns')
    rows = parse_punctuality(punctuality)
    assert len(rows) == 4 and rows[0]['punctuality'] == 0.8 and rows[0]['reliability'] == 0.95
    assert next(r for r in rows if r['route'] == 'TEST' and r['month'] == '2026-08')['punctuality'] is None
    print('[PASS] fixture punctuality and reliability join preserves missing measurements')
    rows = parse_metlink(metlink)
    assert len(rows) == 2 and rows[0]['route'] == 'AX' and rows[1]['route'] == '007'
    assert rows[0]['patronage'] == 27 and rows[0]['mean_departure_time_variance'] == -4.5
    assert rows[0]['peak_mean_departure_time_variance'] is None
    print('[PASS] fixture Metlink tidy CSV retains route identifiers, integer capacity and null measures')
    rows = parse_inventory(json.loads(inventory))
    assert rows[0]['available_spaces'] == 0 and rows[1]['available_spaces'] is None
    print('[PASS] fixture parking distinguishes zero vacancy from absent availability')
    for parser, body in [(lambda b: parse_patronage(b, 'monthly'), daily),
                         (parse_punctuality, monthly), (parse_metlink, b'day,route\n2026-09-27,AX\n')]:
        try:
            parser(body)
        except (ValueError, BadZipFile):
            pass
        else:
            raise AssertionError('schema change incorrectly accepted')
    try:
        parse_inventory({'features': [], 'exceededTransferLimit': True})
    except ValueError:
        pass
    else:
        raise AssertionError('truncated inventory accepted')
    print('[PASS] fixture schema drift and truncated inventory fail closed')
    html = (FIXTURES / 'downloads.html').read_text()
    assert len(download_links(html, cli.AT_PAGE, 'monthly')) == 1
    print('[PASS] fixture download discovery excludes off-host links')
    stamp = '2026-10-01T01:02:03Z'
    samples = {'daily': daily, 'monthly': monthly, 'punctuality': punctuality, 'metlink': metlink}
    def load(kind, *_):
        yield samples[kind], cli.meta_for(cli.METLINK_PAGE if kind == 'metlink' else cli.AT_PAGE,
                                          'metlink' if kind == 'metlink' else 'at', stamp)
    def run(arguments, expected=0):
        out = io.StringIO()
        with redirect_stdout(out):
            code = cli.main(arguments)
        assert code == expected, out.getvalue()
        result = json.loads(out.getvalue())
        assert result['meta']['source_url'] and result['meta']['publisher'] and result['meta']['retrieved_at'].endswith('Z')
        return result
    with patch.object(cli, 'load_download', load), patch.object(cli, 'get_bytes', return_value=(inventory, stamp)):
        payload = run(['patronage', '--mode', 'bus', '--route', '007', '--from', '2026-08-15', '--to', '2026-08-16', '--json'])
        assert len(payload['results']) == 1 and payload['results'][0]['boardings'] == 200
        assert payload['meta']['retrieved_at'] == stamp
        assert run(['patronage', '--mode', 'ferry', '--from', '2026-09-26', '--to', '2026-09-26', '--json'])['results'][0]['boardings'] == 0
        assert run(['punctuality', '--route', '007', '--month', '2026-08', '--json'])['results'][0]['reliability'] == 0.98
        assert len(run(['metlink', '--route', 'ax', '--date', '2026-09-27', '--json'])['results']) == 1
        assert run(['metlink', '--route', 'missing', '--json'])['results'] == []
        spatial = run(['carparks', '--inventory', '--bbox', '174.7,-36.87,174.8,-36.8', '--format', 'geojson'])
        assert spatial['type'] == 'FeatureCollection' and len(spatial['features']) == 1
        assert spatial['features'][0]['geometry']['coordinates'] == [174.76, -36.85]
    print('[PASS] fixture full command filters, monthly interval intersection, cached provenance and GeoJSON containment')
    def load_archive(kind, max_age, archive):
        assert kind == 'daily' and archive
        for filename in ('daily.xlsx', 'epoch1904.xlsx'):
            yield (FIXTURES / filename).read_bytes(), cli.meta_for(
                'https://at.govt.nz/' + filename, stamp=stamp)
    with patch.object(cli, 'load_download', load_archive):
        payload = run(['patronage', '--mode', 'bus', '--to', '2026-09', '--json'])
        assert {r['period'] for r in payload['results']} == {'1904-01-01', '2026-09-26', '2026-09-27'}
        assert payload['meta']['coverage_from'] == '1904-01-01'
        assert len(payload['meta']['queried_sources']) == 2
        for upper_bound in ([], ['--to', '2026-09']):
            payload = run(['patronage', '--mode', 'bus', '--from', '2026-09-26', *upper_bound, '--json'])
            assert {r['period'] for r in payload['results']} == {'2026-09-26', '2026-09-27'}
            assert len(payload['meta']['queried_sources']) == 1
    print('[PASS] fixture upper-bound-only patronage includes older workbooks; lower bounds stop when covered')
    for args in [ ['patronage', '--mode', 'bus', '--route', '007', '--frequency', 'daily'],
                  ['patronage', '--mode', 'bus', '--from', '2026-09', '--to', '2026-08'],
                  ['punctuality', '--month', '2026-99'], ['metlink', '--date', 'bad'],
                  ['metlink', '--max-age', '-1'], ['carparks', '--inventory', '--bbox', 'nan,0,1,1'] ]:
        result = run([*args, '--json'], 2)
        assert result['results'] == [] and result['error']['type'] == 'invalid_input'
    with patch.object(cli.nzfetch, 'fetch_bytes', side_effect=AssertionError('restricted endpoint must not be fetched')):
        assert run(['carparks', '--json'], 4)['error']['type'] == 'blocked'
    print('[PASS] fixture invalid input errors and robots restriction emit structured errors without network access')
    with TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as directory:
        with patch.object(cli, 'CACHE', Path(directory)), patch.object(cli.nzfetch, 'fetch_bytes', return_value=(b'synthetic', '', cli.AT_PAGE)) as fetch:
            first = cli.get_bytes(cli.AT_PAGE, 86400)
            assert cli.get_bytes(cli.AT_PAGE, 86400) == first and fetch.call_count == 1
            cli.get_bytes(cli.AT_PAGE, 0)
            assert fetch.call_count == 2
            cache = next(Path(directory).glob('*.json'))
            value = json.loads(cache.read_text());value['retrieved_at'] = stamp;cache.write_text(json.dumps(value))
            cli.get_bytes(cli.AT_PAGE, 1)
            assert fetch.call_count == 3
    print('[PASS] fixture cache hit retains original timestamp, max-age zero bypasses and expired entries refresh')
