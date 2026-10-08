#!/usr/bin/env python3
"""Synthetic city response fixtures: no copied council observations."""
import json
from copy import deepcopy
from io import StringIO
from contextlib import redirect_stdout, redirect_stderr
from urllib.error import HTTPError
from pathlib import Path
from unittest.mock import patch

import cli

FIXTURES = Path(__file__).resolve().parents[1] / 'tests' / 'fixtures'
STAMP = '2026-10-08T00:00:00Z'


def run():
    def args(*argv):
        return cli.build_parser().parse_args(list(argv))

    for source in cli.CITY_SOURCES:
        result = cli.execute(args('sources', '--source', source))
        assert len(result['results']) == 1 and result['results'][0]['source_id'] == source
        assert result['results'][0]['publisher'] and result['results'][0]['retrieved_at'].endswith('Z')
        if source in cli.DATE_DERIVED_SOURCES:
            assert result['meta']['latest_data'] is None and result['meta']['latest_data_note']
            assert result['results'][0]['latest_data'] is None
            assert result['results'][0]['latest_data_note'] in result['meta']['warnings']

    fixtures = {s: json.loads((FIXTURES / (s+'.json')).read_text())
                for s in ('hamilton-traffic', 'tauranga-traffic', 'christchurch-cycle')}
    for source, body in fixtures.items():
        if source == 'christchurch-cycle':
            rows = cli.parse_chch(body, cli.CHCH, STAMP)
            assert [r['count'] for r in rows] == [0, None]
            assert all('date' not in r and 'latest_data' not in r and 'licence' not in r for r in rows)
        else:
            rows = [cli.parse_city_arc(f, source, cli.SOURCES[source]['url'], STAMP) for f in body['features']]
        assert all(r['source_url'] and r['publisher'] and r['retrieved_at'] == STAMP for r in rows)
        assert all(-90 <= r['latitude'] <= 90 for r in rows)
    h = cli.parse_city_arc(fixtures['hamilton-traffic']['features'][0], 'hamilton-traffic', cli.HAMILTON, STAMP)
    years = cli.hamilton_years(h, args('counts', '--source', 'hamilton-traffic', '--site', '901'))
    assert [(r['date'], r['count']) for r in years] == [('2000', None), ('2022', 125), ('2023', 0)]
    selected = cli.hamilton_years(h, args('counts', '--source', 'hamilton-traffic', '--site', '901', '--from', '2023-07-01'))
    assert len(selected) == 1 and selected[0]['date'] == '2023' and selected[0]['period_start'] == '2023-01-01'

    lines = json.loads((FIXTURES/'wellington-lines.json').read_text())
    w = cli.parse_city_arc(lines['features'][0], 'wellington-sensors', cli.WCC, STAMP)
    assert w['site_id'] == '90001' and w['geometry']['type'] == 'MultiLineString'
    assert abs(w['longitude']-174.7705) < 1e-9
    body = (FIXTURES/'wellington-counts.csv').read_bytes()
    rows, latest, seen = cli.parse_wcc_csv(body, '90001', '2026-09-01', '2026-09-01')
    assert seen and latest == '2026-09-30' and [r['count'] for r in rows] == [0, 9, None]
    assert rows[1]['direction'] == 'S' and rows[1]['transport_class'] == 'Pedestrian'
    listing = (FIXTURES/'wellington-list.xml').read_bytes()
    months = cli.wcc_months(listing)
    assert list(months) == ['2026-09']
    with patch.object(cli, 'arc_rows', return_value=([(lines['features'][0], cli.WCC+'/query', STAMP)], [])), patch.object(cli, 'fetch', side_effect=[(listing, STAMP), (body, STAMP)]):
        result = cli.execute(args('counts', '--source', 'wellington-sensors', '--site', '90001', '--from', '2026-09-01', '--to', '2026-09-01', '--format', 'geojson'))
    assert result['meta']['source_url'] == months['2026-09'] and result['meta']['latest_data'] == '2026-09-01'
    assert result['meta']['downloads'][0]['latest_data'] == '2026-09-30'
    assert 'latest_data_note' not in result['meta']
    assert len(result['features']) == 3 and result['features'][0]['geometry']['type'] == 'MultiLineString'
    assert result['features'][0]['properties']['geometry_source_url'] == cli.WCC+'/query'

    for command in [('sites',), ('nearest', '--near', '174.7705,-41.32')]:
        with patch.object(cli, 'arc_rows', return_value=([(lines['features'][0], cli.WCC+'/query', STAMP)], [])):
            result = cli.execute(args(*command, '--source', 'wellington-sensors'))
        assert result['results'] and result['meta']['latest_data'] is None
        assert result['meta']['latest_data_note'] in result['meta']['warnings']

    with patch.object(cli, 'arc_rows', return_value=([(lines['features'][0], cli.WCC+'/query', STAMP)], [])), patch.object(cli, 'fetch', side_effect=[(listing, STAMP), (body, STAMP)]):
        result = cli.execute(args('counts', '--source', 'wellington-sensors', '--site', '90001', '--from', '2026-09-02', '--to', '2026-09-02'))
    assert result['results'] == [] and result['meta']['latest_data'] is None
    assert result['meta']['latest_data_note'] in result['meta']['warnings']

    tauranga = fixtures['tauranga-traffic']['features'][0]
    newer, undated = deepcopy(tauranga), deepcopy(tauranga)
    newer['attributes']['count_date'] = '2025-04-05T00:00:00'
    undated['attributes'].update(count_date=None, SDE_Load_Date='2026-10-08T00:00:00')
    raw = [(f, cli.TAURANGA+'/query', STAMP) for f in (tauranga, newer, undated)]
    for limit, expected in [('1', '2024-02-03'), ('3', '2025-04-05')]:
        with patch.object(cli, 'arc_rows', return_value=(raw, [])):
            result = cli.execute(args('sites', '--source', 'tauranga-traffic', '--limit', limit))
        assert result['meta']['latest_data'] == expected and 'latest_data_note' not in result['meta']
        assert result['results'][0]['latest_data'] == '2024-02-03'
    for command in [('sites',), ('nearest', '--near', '176.17,-37.69'),
                    ('counts', '--site', tauranga['attributes']['id'])]:
        with patch.object(cli, 'arc_rows', return_value=([raw[-1]], [])):
            result = cli.execute(args(*command, '--source', 'tauranga-traffic'))
        assert result['results'] and result['meta']['latest_data'] is None
        assert result['meta']['latest_data_note'] in result['meta']['warnings']
    with patch.object(cli, 'arc_rows', return_value=([raw[0]], [])):
        result = cli.execute(args('counts', '--source', 'tauranga-traffic', '--site', tauranga['attributes']['id'], '--from', '2025-01-01'))
    assert result['results'] == [] and result['meta']['latest_data'] is None
    assert result['meta']['latest_data_note'] in result['meta']['warnings']

    with patch.object(cli, 'fetch', return_value=(json.dumps(fixtures['christchurch-cycle']).encode(), STAMP)):
        result = cli.execute(args('nearest', '--source', 'christchurch-cycle', '--near', '172.63,-43.53', '--radius-km', '0.05', '--format', 'geojson'))
        assert len(result['features']) == 1 and result['features'][0]['properties']['distance_km'] == 0
        assert 'latest_data' not in result['meta']
        try:
            cli.execute(args('counts', '--source', 'christchurch-cycle', '--site', '901', '--from', '2026-09-01'))
        except cli.SkillError as exc:
            assert exc.code == 7
        else:
            raise AssertionError('Undated snapshot must reject date filters')

    for broken in (b'COUNTLINE_ID,Changed\n90001,x\n', body.replace(b',0,0,Car', b',24,0,Car'), body.replace(b'2026-09-01', b'not-a-date')):
        try:
            cli.parse_wcc_csv(broken, '90001')
        except cli.SkillError as exc:
            assert exc.code == 6
        else:
            raise AssertionError('Malformed CSV must fail')
    for malformed in (listing.replace(b'false', b'true'), b'<Changed/>'):
        try:
            cli.wcc_months(malformed)
        except cli.SkillError as exc:
            assert exc.code in (6, 7)
        else:
            raise AssertionError('Incomplete discovery must fail')
    for source, feature in [('hamilton-traffic', fixtures['hamilton-traffic']['features'][0]),
                            ('tauranga-traffic', fixtures['tauranga-traffic']['features'][0])]:
        with patch.object(cli, 'arc_rows', return_value=([(feature, cli.SOURCES[source]['url']+'/query', STAMP)], [])) as request:
            result = cli.execute(args('sites', '--source', source, '--bbox', '175,-38,177,-37', '--format', 'geojson'))
            assert request.call_args.args[3] == (175, -38, 177, -37)
            assert result['features'][0]['geometry']['type'] == 'Point'
        with patch.object(cli, 'arc_rows', return_value=([], [])):
            try:
                cli.execute(args('counts', '--source', source, '--site', '901' if source == 'hamilton-traffic' else '00000000-1111-2222-3333-444444444444'))
            except cli.SkillError as exc:
                assert exc.code == 2
            else:
                raise AssertionError('Unknown site must not become empty success')
    for flags, code in [(['--from', '2025-01-01', '--to', '2025-02-01'], 7),
                        (['--from', '2026-01-01', '--to', '2026-09-01'], 7)]:
        with patch.object(cli, 'arc_rows', return_value=([(lines['features'][0], cli.WCC+'/query', STAMP)], [])), patch.object(cli, 'fetch', return_value=(listing, STAMP)):
            try:
                cli.execute(args('counts', '--source', 'wellington-sensors', '--site', '90001', *flags))
            except cli.SkillError as exc:
                assert exc.code == code
            else:
                raise AssertionError('Missing or excessive archive requests must fail')
    export = months['2026-09']
    for headers, chunks, message in [({'Content-Length': str(64*1024*1024+1)}, [], 'exceeds'),
                                      ({'Content-Length': '5'}, [b'ab', b''], 'truncated')]:
        with patch.object(cli, 'build_opener') as opener:
            response = opener.return_value.open.return_value.__enter__.return_value
            response.status, response.headers = 200, headers
            response.read.side_effect = chunks
            try:
                cli.fetch_wcc_export(export)
            except cli.SkillError as exc:
                assert exc.code == 5 and message in str(exc)
            else:
                raise AssertionError('Oversized or truncated exports must fail')
    with patch.object(cli, 'build_opener') as opener:
        opener.return_value.open.side_effect = HTTPError(export, 429, 'rate limited', {'Retry-After': '60'}, None)
        try:
            cli.fetch_wcc_export(export)
        except cli.SkillError as exc:
            assert exc.code == 4 and exc.retry_after == '60'
            assert opener.return_value.open.call_args.kwargs['timeout'] == 10
        else:
            raise AssertionError('S3 rate limiting must remain a blocked result')
    output = StringIO()
    with patch.object(cli, 'arc_rows', return_value=([(lines['features'][0], cli.WCC+'/query', STAMP)], [])), patch.object(cli, 'fetch', side_effect=[(listing, STAMP), cli.SkillError('network error: synthetic timeout', 5)]), redirect_stdout(output), redirect_stderr(StringIO()):
        assert cli.main(['counts', '--source', 'wellington-sensors', '--site', '90001', '--from', '2026-09-01', '--to', '2026-09-01', '--json']) == 5
    error = json.loads(output.getvalue())
    assert error['meta']['source_url'] == export and error['results'] == []
    print('[PASS] fixture city registries, derived latest dates, unknown-date notes, annual nulls, snapshots, countlines, class/direction CSVs, provenance and schema errors')


if __name__ == '__main__':
    run()
