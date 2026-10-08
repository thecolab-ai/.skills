#!/usr/bin/env python3
"""Deterministic repo contract and synthetic AQUARIUS parser checks."""
from copy import deepcopy
from contextlib import redirect_stdout, redirect_stderr
import io
import json
from pathlib import Path
import sys
from unittest.mock import patch

import cli

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL.parents[1] / 'lib'))
from contract_test import run_contract_test  # noqa: E402

FIXTURES = SKILL / 'tests' / 'fixtures'


def fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding='utf-8'))


def expect_error(function, code=6):
    try:
        function()
    except cli.SkillError as exc:
        assert exc.code == code
    else:
        raise AssertionError('malformed input did not fail closed')


def fixture_checks():
    manifest = fixture('fixtures.json')
    assert manifest['synthetic'] is True
    assert 'source_url' not in manifest and 'retrieved_at' not in manifest
    when = '2024-02-20T02:00:00Z'
    catalogue = fixture('catalogue.json')
    rows = cli.parse_catalogue(catalogue)
    assert len(rows) == 7 and catalogue['Total'] == len(rows)
    assert {r['parameter'] for r in rows} == {'rainfall', 'level', 'flow'}
    assert len(cli.group_sites(rows)) == 5
    rain = cli.select_site([r for r in rows if r['parameter'] == 'rainfall'], '900001')
    assert rain['name'] == 'Synthetic Rain Garden'
    assert rain['end_of_record'] == '2024-02-20T13:00:00+12:00'
    assert rain['dataset'] == 'Rainfall.Continuous@900001'
    print('[PASS] fixture monitoring metadata, parameter routing and site grouping')

    bounds = cli.bbox_type('174.88,-36.99,174.89,-36.97')
    assert cli.in_bbox(rain, bounds)
    assert not cli.in_bbox({**rain, 'longitude': None}, bounds)
    assert not cli.in_bbox({**rain, 'latitude': -37.5}, bounds)
    for invalid in ['-1,2,3', 'nan,-37,175,-36', '175,-36,174,-37', '181,-37,182,-36', '174.88,-36.98,174.88,-36.98']:
        try:
            cli.bbox_type(invalid)
        except cli.argparse.ArgumentTypeError:
            pass
        else:
            raise AssertionError('invalid bbox accepted')
    geo = cli.as_geojson(cli.result_envelope(cli.group_sites([rain]), cli.provenance(cli.BASE, when)))
    assert geo['features'][0]['geometry']['coordinates'] == [174.885, -36.985]
    assert geo['meta']['publisher'] == 'Auckland Council'
    print('[PASS] fixture WGS84 bbox validation, filtering and GeoJSON coordinates')

    assert cli.timestamp('2026-01-01').utcoffset().total_seconds() == 43200
    assert cli.timestamp('2026-10-08T00:00Z').isoformat() == '2026-10-08T12:00:00+12:00'
    q = cli.export_params([rain], cli.timestamp('2026-10-07'), cli.timestamp('2026-10-08'), 'hour')
    assert (q['TimeZone'], q['Interval'], q['Datasets[0].Calculation'], q['Datasets[0].UnitId']) == (12, 'Hourly', 'Aggregate', 332)
    assert q['Datasets[0].DatasetName'] == rain['dataset']
    with patch.object(cli.nzfetch, 'fetch_json', return_value={}) as fetch:
        _, source_url = cli.request_json('/Export/BulkExportJsonFile', q, post=True)
        assert fetch.call_args.args[0] == cli.BASE + '/Export/BulkExportJsonFile'
        assert fetch.call_args.kwargs['method'] == 'POST'
        assert fetch.call_args.kwargs['timeout'] == 10
        assert b'Datasets%5B0%5D.DatasetName=' in fetch.call_args.kwargs['data']
        assert source_url == cli.BASE + '/Export/BulkExportJsonFile'
    print('[PASS] fixture fixed NZST, aggregation and bounded form POST requests')

    for filename, parameter, site, count, unit, last in [
        ('rainfall-hour.json', 'rainfall', '900001', 7, 'mm', 0.0),
        ('level-raw.json', 'level', '900003', 5, 'm', 0.57),
        ('flow-day.json', 'flow', '900003', 2, 'm^3/s', 0.82),
    ]:
        row = cli.select_site([r for r in rows if r['parameter'] == parameter], site)
        result = cli.parse_export(fixture(filename), {row['dataset']: row})[row['dataset']]
        assert len(result) == count and result[-1]['value'] == last
        assert result[-1]['units'] == unit and result[-1]['grade_name'] == 'Non Verified'
        assert not {'source_url', 'publisher', 'licence', 'retrieved_at', 'latest_data'} & result[-1].keys()
        if parameter != 'level':
            assert result[0]['value'] is None and result[0]['missing'] is True
            assert result[0]['source_missing_marker'] == 'NaN'
            assert result[0]['grade_name'] == 'UNDEF'
        print(f'[PASS] fixture {parameter} values, units, missing values, quality and compact records')

    bulk_rows = {r['dataset']: r for r in rows if r['parameter'] == 'rainfall' and r['site'] in ['900001', '900002']}
    bulk = fixture('rainfall-bulk-hour.json')
    parsed = cli.parse_export(bulk, bulk_rows)
    assert len(parsed) == 2 and all(len(p) == 7 for p in parsed.values())
    assert all(p[-1]['time'] == '2024-02-20T06:00:00+12:00' for p in parsed.values())
    print('[PASS] fixture time-aligned bulk dataset routing')

    for mutation in ['unit', 'dataset', 'count', 'value', 'timestamp', 'duplicate']:
        bad = deepcopy(fixture('rainfall-hour.json'))
        if mutation == 'unit': bad['Datasets'][0]['Unit'] = 'm'
        if mutation == 'dataset': bad['Datasets'][0]['Identifier'] = 'Unexpected'
        if mutation == 'count': bad['NumRows'] += 1
        if mutation == 'value': bad['Rows'][0]['Points'][0]['Value'] = 'broken'
        if mutation == 'timestamp': bad['Rows'][0]['Timestamp'] = 'broken'
        if mutation == 'duplicate': bad['Rows'][1]['Timestamp'] = bad['Rows'][0]['Timestamp']
        expect_error(lambda: cli.parse_export(bad, {rain['dataset']: rain}))
    expect_error(lambda: cli.parse_catalogue({'Data': [{}], 'Total': 1}))
    expect_error(lambda: cli.select_site(rows, 'no-such-site'), 2)
    print('[PASS] fixture malformed schema, mismatched units and unknown-site errors')

    def fake_request(path, params, post=False):
        if path == '/Data/Data_List':
            assert post and params['parameters[0]'] == 78
            data = [r for r in catalogue['Data'] if r['DatasetIdentifier'].startswith('Rainfall.')]
            return {'Data': data, 'Total': len(data)}, cli.BASE + path
        assert path == '/Export/BulkExportJsonFile'
        return fixture('rainfall-hour.json'), cli.BASE + path

    parser = cli.build_parser()
    args = parser.parse_args(['series', '--site', '900001', '--parameter', 'rainfall', '--from', '2024-02-20T02:00', '--to', '2024-02-20T04:00', '--interval', 'hour', '--json'])
    with patch.object(cli, 'request_json', fake_request):
        output = cli.command(args)
    assert output['meta']['count'] == 3 and output['results'][0]['time'] == '2024-02-20T02:00:00+12:00'
    assert output['meta']['aggregation'] == 'preceding interval total'
    with patch.object(cli, 'request_json', side_effect=AssertionError('invalid range reached network')):
        args.end = '2026-12-01'
        expect_error(lambda: cli.command(args), 2)
    print('[PASS] fixture series command clips source boundaries and validates range before HTTP')

    args = parser.parse_args(['latest', '--parameter', 'rainfall', '--bbox', '174.88,-36.99,174.89,-36.97', '--json'])
    anchor = cli.timestamp('2024-02-20T14:00')
    with patch.object(cli, 'request_json', fake_request), patch.object(cli, 'datetime', wraps=cli.datetime) as clock:
        clock.now.return_value = anchor
        output = cli.command(args)
    assert output['meta']['count'] == 1 and output['meta']['matching_sites'] == 1
    assert output['results'][0]['age_hours'] == 8
    assert output['results'][0]['value'] == 0.0 and output['results'][0]['missing'] is False
    assert output['results'][0]['grade_name'] == 'Non Verified'
    assert output['meta']['latest_data'] == '2024-02-20T06:00:00+12:00'
    print('[PASS] fixture latest ignores nulls and preserves observed timestamp, age and quality')
    assert output['results'][0]['source_url'] == cli.BASE + '/Export/BulkExportJsonFile'
    assert not {'publisher', 'licence', 'retrieved_at', 'latest_data'} & output['results'][0].keys()

    # Discovery retains record dates per dataset but shares publisher/retrieval metadata.
    args = parser.parse_args(['sites', '--json'])
    with patch.object(cli, 'request_json', return_value=(catalogue, cli.BASE + '/Data/Data_List')):
        output = cli.command(args)
    assert set(output) == {'meta', 'results'} and output['meta']['count'] == 5
    assert output['meta']['request'] == {'method': 'POST', 'form': {'page': 1, 'pageSize': 1000, 'parameters[0]': 78, 'parameters[1]': 40, 'parameters[2]': 82}}
    assert not {'source_url', 'publisher', 'licence', 'retrieved_at', 'latest_data'} & rows[0].keys()
    assert output['results'][0]['end_of_record']
    assert all('latest_data' not in dataset for site in output['results'] for dataset in site['datasets'])
    assert rows[1]['dataset'] == 'Rainfall.Continous@900002'
    assert not cli.in_bbox(rows[4], bounds)
    print('[PASS] fixture synthetic manifest, POST provenance and compact discovery envelope')

    args = parser.parse_args(['series', '--site', '900001', '--parameter', 'rainfall', '--from', '2024-02-20', '--to', '2024-02-21', '--interval', 'hour'])
    with patch.object(cli, 'request_json', fake_request):
        output = cli.command(args)
    assert output['results'][1]['period_start'] == '2024-02-20T00:00:00+12:00'
    assert output['results'][1]['period_end'] == output['results'][1]['time'] == '2024-02-20T01:00:00+12:00'
    flow = cli.select_site([r for r in rows if r['parameter'] == 'flow'], '900003')
    with patch.object(cli, 'request_json', return_value=(fixture('flow-day.json'), cli.BASE)):
        points, _ = cli.export([flow], cli.timestamp('2024-02-20'), cli.timestamp('2024-02-21'), 'day')
    assert points[flow['dataset']][1]['period_start'] == '2024-02-20T00:00:00+12:00'
    assert points[flow['dataset']][1]['period_end'] == '2024-02-21T00:00:00+12:00'
    args.interval = None
    # Use the real cap, with invented dense observations held only in memory.
    dense = [{'time': (cli.timestamp('2024-02-20') + cli.timedelta(seconds=i)).isoformat(), 'value': 1} for i in range(cli.MAX_RAW_POINTS + 1)]
    with patch.object(cli, 'request_json', fake_request), patch.object(cli, 'export', return_value=({rain['dataset']: dense}, cli.BASE)):
        expect_error(lambda: cli.command(args), 2)
    with patch.object(cli, 'request_json', fake_request), patch.object(cli, 'export', return_value=({rain['dataset']: dense[:-1]}, cli.BASE)):
        assert cli.command(args)['meta']['count'] == cli.MAX_RAW_POINTS
    args.start, args.end = '2025-01-01', '2025-01-02'
    with patch.object(cli, 'request_json', fake_request):
        output = cli.command(args)
    assert output['results'] == []
    assert any('outside this dataset' in warning for warning in output['meta']['warnings'])
    args = parser.parse_args(['latest', '--parameter', 'rainfall', '--json'])
    with patch.object(cli, 'catalogue', return_value=([rows[5]], [{'source_url': cli.BASE}])), patch.object(cli, 'export', side_effect=AssertionError('retired gauge fetched')), patch.object(cli, 'datetime', wraps=cli.datetime) as clock:
        clock.now.return_value = anchor
        output = cli.command(args)
    assert output['meta']['outside_lookback_sites'] == 1 and output['results'] == []
    print('[PASS] fixture hour/day attribution, raw point cap and out-of-record warnings')

    for argv in [['sites', '--bbox=bad', '--format=geojson'], ['sites', '--bbox=bad', '--format', 'geojson'], ['sites', '--bbox=bad', '--format=json'], ['sites', '--bbox=bad', '--json']]:
        stdout = io.StringIO()
        with patch.object(sys, 'argv', ['cli.py', *argv]), redirect_stdout(stdout), redirect_stderr(io.StringIO()):
            assert cli.main() == 2
        error = json.loads(stdout.getvalue())
        assert set(error) == {'meta', 'results', 'error'} and error['results'] == []
        assert error['error']['type'] == 'invalid_input'
    assert not cli.machine_mode(['series', '--site', 'geojson'])
    for code, kind in [(2, 'invalid_input'), (4, 'blocked'), (5, 'upstream_unavailable'), (6, 'schema_failure'), (7, 'unsupported_operation')]:
        stdout = io.StringIO()
        with patch.object(sys, 'argv', ['cli.py', 'sites', '--json']), patch.object(cli, 'command', side_effect=cli.SkillError('test failure', code, '60' if code == 4 else None)), redirect_stdout(stdout), redirect_stderr(io.StringIO()):
            assert cli.main() == code
        error = json.loads(stdout.getvalue())
        assert error['error']['type'] == kind and error['error']['code'] == code
        assert error['meta']['retrieved_at'].endswith('Z') and error['results'] == []
        if code == 4:
            assert error['error']['retry_after'] == '60'
    for argv in [['sites', '--format', 'json'], ['sites', '--format=json']]:
        stdout = io.StringIO()
        with patch.object(sys, 'argv', ['cli.py', *argv]), patch.object(cli, 'request_json', return_value=(catalogue, cli.BASE + '/Data/Data_List')), redirect_stdout(stdout):
            assert cli.main() == 0
        assert set(json.loads(stdout.getvalue())) == {'meta', 'results'}
    print('[PASS] fixture direct error envelopes, equals-format parsing and explicit JSON output')
    import smoke_test
    for value, skipped in [(None, True), ('empty', True), (1.2, False)]:
        stdout = io.StringIO()
        data = {'meta': {'count': 0 if value == 'empty' else 1}, 'results': [] if value == 'empty' else [{'value': value}]}
        with redirect_stdout(stdout):
            assert smoke_test.no_recent_data(data, '900001') is skipped
        if skipped:
            assert stdout.getvalue().strip() == '[SKIP] live gauge 900001 has no recent data (source health degraded)'
        else:
            assert stdout.getvalue() == ''
    for raw in ['0', '-1', '5001', 'nan']:
        try:
            parser.parse_args(['series', '--site', '900001', '--parameter', 'rainfall', '--from', '2024-02-20', '--to', '2024-02-21', '--max-points', raw])
        except cli.SkillError as exc:
            assert exc.code == 2
        else:
            raise AssertionError('unbounded or invalid --max-points accepted')
    args = parser.parse_args(['series', '--site', '900001', '--parameter', 'rainfall', '--from', '2024-02-20', '--to', '2024-02-21', '--max-points', '3'])
    with patch.object(cli, 'request_json', fake_request):
        expect_error(lambda: cli.command(args), 2)
    print('[PASS] fixture degraded-gauge smoke skips and configurable bounded raw output')
    return 14


if __name__ == '__main__':
    try:
        fixture_checks()
    except (AssertionError, cli.SkillError, KeyError, ValueError) as exc:
        print(f'[FAIL] fixture {exc}', file=sys.stderr)
        raise SystemExit(1)
    raise SystemExit(run_contract_test(SKILL))
