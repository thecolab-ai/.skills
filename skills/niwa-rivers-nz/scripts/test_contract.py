#!/usr/bin/env python3
"""Deterministic source parsers, spatial semantics, provenance and error contracts."""
from __future__ import annotations

import argparse
import copy
import json
import sys
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'lib'))
from contract_test import run_contract_test  # noqa: E402
import cli  # noqa: E402
import rivermaps  # noqa: E402

FIXTURES = Path(__file__).resolve().parents[1] / 'tests' / 'fixtures'


def fixture_checks():
    page = cli.parse_products((FIXTURES / 'products.html').read_text())
    assert page['total'] == 2 and page['page'] == 1 and len(page['products']) == 2
    hourly = cli.product_record({**page['products'][0], 'source_url': cli.SOURCE_URL}, 'hourly_series_metadata')
    assert hourly['station'] == '99901' and hourly['parameter'] == 'River flow [m3/s]'
    assert hourly['geometry']['coordinates'] == [174.75, -36.91]
    assert hourly['latest_data'] == '2026-01-02T00:00:00.000Z'
    assert hourly['latest_data'] != hourly['catalogue_updated_at']
    assert hourly['observations_available'] is False
    flood = cli.product_record({**page['products'][1], 'source_url': cli.FLOOD_URL}, 'flood_product_metadata')
    assert flood['geometry_role'] == 'product_coverage_bbox' and not flood['hazard_values_available']
    assert flood['latest_data'] == '2026-02-01T00:00:00.000Z'
    print('[PASS] fixture public Astro catalogue, hourly dates and flood coverage labels')

    for html in ('<html>Unavailable</html>', '<astro-island component-url="/_astro/SubcategoriesMain.x.js" props="{}">'):
        try:
            cli.parse_products(html)
        except cli.Failure as exc:
            assert exc.code == 6
        else:
            raise AssertionError('missing catalogue must fail, not return an empty success')
    with patch.object(cli, 'fetch', return_value='irrelevant'), patch.object(cli, 'parse_products', side_effect=[
            {'products': page['products'][:1], 'page': 1, 'total': 2},
            {'products': page['products'][1:], 'page': 2, 'total': 2}]):
        rows, total = cli.product_listing(cli.SOURCE_URL)
        assert total == 2 and len(rows) == 2 and rows[1]['source_url'].endswith('page=2')
    with patch.object(cli, 'fetch', return_value='irrelevant'), patch.object(cli, 'parse_products', side_effect=[
            {'products': page['products'][:1], 'page': 1, 'total': 2},
            {'products': page['products'][:1], 'page': 2, 'total': 2}]):
        try:
            cli.product_listing(cli.SOURCE_URL)
        except cli.Failure as exc:
            assert exc.code == 6
        else:
            raise AssertionError('duplicate pagination must fail')
    print('[PASS] fixture paging completeness and changed-source failures')

    regional = json.loads((FIXTURES / 'regions.json').read_text())
    with patch.object(cli, 'fetch', return_value=regional):
        geometry, url = cli.region_geometry('Auckland')
        assert 'regional_council_gen' in url
        assert cli.in_region([174.75, -36.91], geometry)
        assert not cli.in_region([174.71, -36.94], geometry), 'holes excluded'
        assert not cli.in_region([170, -40], geometry)
    assert cli.intersects_bbox(hourly['geometry'], (174.7, -37, 174.8, -36.9))
    assert not cli.intersects_bbox(hourly['geometry'], (170, -45, 171, -44))
    assert cli.region_name('Manawatū-Whanganui') == 'Manawatu-Whanganui'
    assert cli.region_name('Manawatu-Wanganui') == 'Manawatu-Whanganui'
    for value in ('0,0,0,1', 'nan,0,1,1', '170,-91,171,-90', '179,-40,-179,-39', '1,2,3'):
        try:
            cli.build_parser().parse_args(['stations', '--bbox=' + value])
        except cli.InputError:
            pass
        else:
            raise AssertionError('invalid box accepted: ' + value)
    print('[PASS] fixture bbox validation, region membership and polygon holes')

    data = json.loads((FIXTURES / 'fpat.json').read_text())
    features, total = cli.parse_features(data)
    assert total == 2 and len(features) == 1 and features[0]['properties']['structure_type'] == 'Culvert'
    url = cli.wfs_query(cli.WFS_URL, 'fpat:fpat_surveys', count=3, bbox=(174.6, -37, 174.9, -36.7), start=2)
    params = parse_qs(urlparse(url).query)
    assert params['bbox'] == ['174.6,-37,174.9,-36.7,urn:ogc:def:crs:OGC:1.3:CRS84']
    assert params['count'] == ['3'] and params['startIndex'] == ['2'] and params['sortBy'] == ['id']
    with patch.object(cli, 'fetch', return_value=data):
        result = cli.cmd_fish(SimpleNamespace(limit=1, offset=0, bbox=None, format='geojson'))
        assert result['type'] == 'FeatureCollection' and result['meta']['truncated']
        assert 'latest_data' not in result['meta'], 'WFS response time is not data freshness'
        assert result['features'][0]['geometry']['coordinates'] == [174.75, -36.91]
    invalid = copy.deepcopy(data)
    invalid['features'][0]['geometry']['coordinates'] = [-36.91, 174.75]
    try:
        cli.parse_features(invalid)
    except cli.Failure as exc:
        assert exc.code == 6
    else:
        raise AssertionError('invalid WGS84 latitude must fail')
    print('[PASS] fixture WFS parsing, explicit axes, pagination and freshness')

    transport = json.loads((FIXTURES / 'rivermaps.json').read_text())
    decoded = rivermaps.frames(transport['frame'])
    call = decoded[0]['custom']['leaflet-calls']['calls'][0]
    predictions, matched = rivermaps.parse_polylines(call, 'Mean Flow')
    assert matched and len(predictions) == 1
    assert predictions[0]['nzsegment'] == 9999999 and predictions[0]['value'] == 0.123
    assert predictions[0]['units'] == 'cumecs'
    assert predictions[0]['geometry']['coordinates'][0][0] == [174.7, -36.9]
    assert rivermaps.distance_km((174.71, -36.91), predictions[0]['geometry']) < 0.0001
    assert not rivermaps.parse_polylines(call, 'MALF')[1]
    grouped = copy.deepcopy(call)
    grouped['args'][4][0] = grouped['args'][4][0].replace('0.123', '1,234.500')
    assert rivermaps.parse_polylines(grouped, 'Mean Flow')[0][0]['value'] == 1234.5
    month = copy.deepcopy(call)
    month['args'][4] = ['nzsegment: 9999999<br>Catchment: Synthetic Creek<br>Month lowest mean flow: April ' ]
    assert rivermaps.parse_polylines(month, 'Month lowest mean flow')[0][0]['value'] == 'April'
    with patch.object(rivermaps, 'query', return_value=(predictions, 'Synthetic mean flow description', 'Stream order ≥ 1')):
        result = cli.cmd_rivers(SimpleNamespace(near=(174.71, -36.91), bbox=None, radius_km=5,
                                               metric='Mean Flow', limit=1, format='geojson'))
        assert len(result['features']) == 1
        assert result['meta']['data_kind'] == 'static_modelled_river_metric'
        assert 'latest_data' not in result['meta']
    invalid_call = copy.deepcopy(call)
    invalid_call['args'][1] = ['1']
    try:
        rivermaps.parse_polylines(invalid_call, 'Mean Flow')
    except rivermaps.RiverMapsError as exc:
        assert exc.code == 6
    else:
        raise AssertionError('reach ID mismatch must fail')
    print('[PASS] fixture River Maps transport, predictions, geometry and nearby ranking')
    def frame(message):
        return 'a' + json.dumps(['0|m|' + json.dumps(message)])
    first = {'values': {'ui_selectedvariable': {'html': '<option value="Mean Flow">Mean Flow</option>'}},
             'custom': {'leaflet-calls': {'calls': [{'method': 'addControl', 'args': ['Stream order ≥ 7']}]}}}
    stale = {'values': {'variableDescription_Hydro': 'Synthetic mean flow (cumecs)'},
             'custom': {'leaflet-calls': {'calls': [call, {'method': 'addControl', 'args': ['Stream order ≥ 7']}]}}}
    final = {'custom': {'leaflet-calls': {'calls': [{'method': 'clearGroup', 'args': ['MapLines']},
                                                  call, {'method': 'addControl', 'args': ['Stream order ≥ 1']}]}}}
    with patch.object(rivermaps.nzfetch, 'fetch_text', side_effect=['o', '', frame(first), '', frame(stale), frame(final), '']) as fetch_mock:
        actual, description, visibility = rivermaps.query((174.6, -37, 174.9, -36.7))
        assert len(actual) == 1 and visibility == 'Stream order ≥ 1'
        assert description == 'Synthetic mean flow (cumecs)'
        requests = fetch_mock.call_args_list
        assert all(req.kwargs['method'] == 'POST' and req.kwargs['timeout'] <= 10 for req in requests)
        updates = json.loads(requests[3].kwargs['data'])[0]
        assert 'SelectedVariable' in updates and 'HydroMap_bounds' in updates
        assert '|c|' in json.loads(requests[-1].kwargs['data'])[0], 'session must close'
    print('[PASS] fixture River Maps query ignores stale map, respects timeouts and closes session')


    for argv, code in [(['flow', '--station', '99901', '--json'], 4),
                       (['flow', '--station', '99901', '--from', '2026-02-02', '--to', '2026-01-01', '--json'], 2),
                       (['flow', '--station', 'x', '--json'], 2),
                       (['flow', '--station', '99901', '--from', '2026-02-02T00:00:00', '--json'], 2),
                       (['fish-passage', '--limit', '0', '--json'], 2),
                       (['fish-passage', '--offset', '-1', '--json'], 2),
                       (['stations', '--bbox=nan,0,1,1', '--format=geojson'], 2),
                       (['rivers', '--near', 'nan,-36.9', '--json'], 2),
                       (['rivers', '--near', '174.7,-36.9', '--radius-km', 'nan', '--json'], 2)]:
        out = StringIO()
        with patch.object(cli, 'fetch', side_effect=AssertionError('must reject before network')), redirect_stdout(out):
            assert cli.main(argv) == code
        result = json.loads(out.getvalue())
        assert result['results'] == [] and result['error']['code'] == code
        assert result['meta']['source_url'] and result['meta']['publisher'] and result['meta']['retrieved_at'].endswith('Z')
    with patch.object(cli.nzfetch, 'fetch_json', side_effect=cli.nzfetch.RateLimited('test', retry_after='17')):
        try:
            cli.fetch(cli.WFS_URL)
        except cli.Failure as exc:
            assert exc.code == 4 and exc.retry_after == '17'
        else:
            raise AssertionError('rate limiting must fail')
    with patch.object(cli.nzfetch, 'fetch_json', side_effect=AssertionError('unexpected network')):
        try:
            cli.fetch('http://' + 'localhost' + '/')
        except cli.Failure as exc:
            assert exc.code == 2
        else:
            raise AssertionError('host outside allowlist must fail')
    sources = cli.cmd_sources(None)
    assert len(sources['results']) == 4
    assert all(row['source_url'] and row['publisher'] and row['retrieved_at'].endswith('Z') and row['licence'] for row in sources['results'])
    print('[PASS] fixture gates, errors, provenance, Retry-After and outbound host bounds')


if __name__ == '__main__':
    try:
        fixture_checks()
    except Exception as exc:
        print(f'[FAIL] fixture NIWA freshwater contract: {exc}')
        raise SystemExit(1)
    raise SystemExit(run_contract_test(Path(__file__).resolve().parents[1]))
