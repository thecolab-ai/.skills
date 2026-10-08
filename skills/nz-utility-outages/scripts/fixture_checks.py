#!/usr/bin/env python3
"""Deterministic source and CLI behaviour checks using synthetic fixtures only."""
import copy
import io
import json
import math
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import cli
import rail_calendar

FIXTURES = Path(__file__).resolve().parents[1] / 'tests' / 'fixtures'
NOW = datetime(2026, 10, 8, 4, tzinfo=timezone.utc)


def fixtures():
    return {
        'watercare': json.loads((FIXTURES / 'watercare.json').read_text()),
        'wellington': json.loads((FIXTURES / 'wellington.json').read_text()),
        'kiwirail': (FIXTURES / 'kiwirail.html').read_text(),
        'kiwirail-calendar': (FIXTURES / 'calendar.pdf').read_bytes(),
    }


def invoke(arguments, data=None, failure=None, fetch_allowed=True):
    data = fixtures() if data is None else data
    def fake_fetch(utility, **_kwargs):
        assert fetch_allowed, 'invalid or unsupported requests must fail before network access'
        if failure:
            raise failure
        return copy.deepcopy(data[utility])
    output = io.StringIO()
    with patch.object(cli, 'fetch', fake_fetch), redirect_stdout(output):
        code = cli.main(arguments)
    return code, json.loads(output.getvalue())


def assert_rejected(function):
    try:
        function()
    except (ValueError, TypeError, KeyError):
        return
    raise AssertionError('malformed source must not be an empty success')


def run():
    data = fixtures()
    water = cli.parse_watercare(data['watercare'], cli.source_meta('watercare'), NOW)
    assert [row['status'] for row in water] == ['planned', 'current']
    assert water[0]['geometry']['coordinates'] == [174.76, -36.85]
    assert water[1]['end'] is None and water[1]['affected_count'] is None
    assert water[0]['latest_data'] == data['watercare'][0]['updatedAt']
    old = copy.deepcopy(data['watercare'][0]); old.update(start_time='2020-01-01T00:00:00Z', estimated_resolution_time='2020-01-02T00:00:00Z')
    assert cli.parse_watercare([old], cli.source_meta('watercare'), NOW)[0]['status'] == 'unknown'
    print('[PASS] fixture Watercare planned/current, WGS84, updates and expired estimated windows')

    wellington = cli.parse_wellington(data['wellington'], cli.source_meta('wellington'), NOW)
    assert [row['status'] for row in wellington] == ['planned', 'resolved']
    assert wellington[0]['start'] == '2099-01-14T21:00:00Z'  # NZ daylight saving
    assert wellington[1]['affected_count'] == 9 and wellington[1]['latest_data'] == '2026-10-01 12:00:00'
    winter = cli.iso_time('2026-07-01 10:00:00', local=True)
    assert winter == '2026-06-30T22:00:00Z'
    altered = copy.deepcopy(data['wellington']); altered['plannedOutages'][0]['useAlternateDate'] = 1
    alternate = cli.parse_wellington(altered, cli.source_meta('wellington'), NOW)[0]
    assert alternate['start'] == '2099-01-21T21:00:00Z' and alternate['alternate_date_used'] is True
    altered['plannedOutages'][0]['status'] = 'Cancelled'
    assert cli.parse_wellington(altered, cli.source_meta('wellington'), NOW)[0]['status'] == 'cancelled'
    print('[PASS] fixture Wellington resolution, counts, summer/winter offsets, alternate dates and cancellation')

    work = cli.parse_works(data['kiwirail'], cli.source_meta('kiwirail'))
    assert len(work) == 4 and work[0]['start'] == '2099-01-12' and work[0]['end'] == '2099-01-16'
    assert work[1]['description'].endswith('Monday to Saturday.') and work[1]['area'] == 'Sample Station'
    assert work[-1]['kind'] == 'rail_notice' and work[-1]['status'] == 'unknown'
    assert all(row['geometry'] is None and not row['passenger_closure_confirmed'] for row in work)
    no_year = data['kiwirail'].replace('January-2099.pdf', 'January.pdf')
    assert cli.parse_works(no_year, cli.source_meta('kiwirail'))[0]['start'] is None
    print('[PASS] fixture KiwiRail notice grouping, explicit year extraction and absence of invented locations/closures')

    parsed = rail_calendar.parse_pdf(data['kiwirail-calendar'])
    assert parsed['coverage_start'] == '2026-01-01' and parsed['coverage_end'] == '2026-01-31'
    assert parsed['latest_data'] == '2025-12-01'
    assert parsed['closures'] == [{'date': '2026-01-03', 'kind': 'full_network_closure'}, {'date': '2026-01-04', 'kind': 'partial_closure_or_reduced_frequency'}]
    content = rail_calendar.page_content(data['kiwirail-calendar'])
    assert_rejected(lambda: rail_calendar.parse_content(content.replace('(31)Tj', '(30)Tj')))
    assert_rejected(lambda: rail_calendar.parse_content(content.replace('0.64 0.12 0.12 0 k', '0.2 0.3 0.4 0 k')))
    assert_rejected(lambda: rail_calendar.parse_pdf(b'<html>blocked</html>'))
    assert_rejected(lambda: rail_calendar.parse_content(content.replace('Full Network Closure', 'Different legend')))
    print('[PASS] fixture PDF compressed streams, colours, complete month grid, publication and fail-closed layout checks')

    assert_rejected(lambda: cli.parse_watercare({}, cli.source_meta('watercare'), NOW))
    assert_rejected(lambda: cli.parse_watercare([{'id': 1}], cli.source_meta('watercare'), NOW))
    assert_rejected(lambda: cli.parse_wellington({}, cli.source_meta('wellington'), NOW))
    assert_rejected(lambda: cli.parse_works('<main><p>Changed page</p></main>', cli.source_meta('kiwirail')))
    assert_rejected(lambda: cli.point({'lng': math.nan, 'lat': 0}))
    print('[PASS] fixture schema changes and non-finite coordinates fail without empty-success fallbacks')

    code, payload = invoke(['outages', '--utility', 'watercare', '--bbox', '174.75,-36.86,174.77,-36.84', '--json'])
    assert code == 0 and [row['id'] for row in payload['results']] == ['101']
    assert {'source_url', 'publisher', 'retrieved_at'} <= payload['meta'].keys()
    code, spatial = invoke(['near', '--near', '174.76,-36.85', '--radius', '1', '--format', 'geojson'])
    assert code == 0 and spatial['type'] == 'FeatureCollection' and len(spatial['features']) == 1
    assert spatial['features'][0]['properties']['distance_km'] == 0
    assert spatial['meta']['retrieved_at'].endswith('Z')
    assert cli.distance_km((180, 0), (-180, 0)) < 1e-9
    print('[PASS] fixture local bbox/near filtering, boundary distance and GeoJSON provenance')

    code, mixed = invoke(['near', '--near', '174.76,-36.85', '--radius', '1000', '--utility', 'all', '--json'])
    assert code == 0 and {row['utility'] for row in mixed['results']} == {'watercare', 'wellington'}
    assert all({'source_url', 'publisher', 'retrieved_at'} <= row.keys() for row in mixed['results'])
    code, dates = invoke(['rail-closures', '--from', '2026-01-04', '--to', '2026-01-04', '--json'])
    assert code == 0 and len(dates['results']) == 1 and dates['results'][0]['start'] == '2026-01-04'
    code, dates = invoke(['rail-closures', '--from', '2026-10-01', '--json'])
    assert code == 0 and dates['results'] == [] and dates['meta']['coverage_end'] == '2026-01-31'
    print('[PASS] fixture mixed-source provenance, inclusive date filters and coverage for out-of-range queries')

    invalid_cases = [
        ['near', '--near', 'nan,-36', '--json'],
        ['near', '--near', '181,-36', '--format', 'geojson'],
        ['near', '--near', '174,-36', '--radius', 'nan', '--json'],
        ['outages', '--utility', 'watercare', '--bbox', '175,-37,174,-36', '--json'],
        ['outages', '--utility', 'watercare', '--bbox=170,-91,175,-36', '--json'],
        ['rail-closures', '--from', '2026-10-09', '--to', '2026-10-08', '--json'],
        ['rail-closures', '--from', '2026-02-30', '--json'],
    ]
    for arguments in invalid_cases:
        code, error = invoke(arguments, fetch_allowed=False)
        assert code == 2 and error['error']['type'] == 'invalid_input' and error['results'] == []
    for utility, expected in [('vector', 7), ('powernet', 7), ('counties', 4)]:
        code, error = invoke(['outages', '--utility', utility, '--json'], fetch_allowed=False)
        assert code == expected and error['error']['code'] == expected and error['results'] == []
    code, error = invoke(['outages', '--utility', 'kiwirail', '--bbox', '174,-37,175,-36', '--json'])
    assert code == 7 and error['error']['type'] == 'unsupported_operation'
    print('[PASS] fixture invalid arguments, skipped sources and unsupported spatial filters use stable JSON errors')

    broken = copy.deepcopy(data); broken['watercare'] = {'unexpected': []}
    code, error = invoke(['outages', '--utility', 'watercare', '--json'], broken)
    assert code == 6 and error['error']['type'] == 'schema_failure'
    code, error = invoke(['near', '--near', '174,-37', '--utility', 'all', '--json'], failure=cli.SourceError(4, 'network error: rate limited', '30'))
    assert code == 4 and error['error']['retry_after'] == '30' and error['results'] == []
    with patch.object(cli.nzfetch, 'fetch_bytes', side_effect=cli.nzfetch.Blocked('synthetic blocked')):
        try:
            cli.fetch('watercare')
        except cli.SourceError as exc:
            assert exc.code == 4
        else:
            raise AssertionError('blocked requests must fail')
    print('[PASS] fixture schema errors, rate limiting and access blocks retain provenance and no partial-success data')


if __name__ == '__main__':
    run()
