#!/usr/bin/env python3
"""Deterministic repository contract and real-fixture GTFS behaviour checks."""
import argparse
import csv
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest.mock as mock
import urllib.error
import zipfile

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / 'lib'))
from contract_test import run_contract_test  # noqa: E402
import cli  # noqa: E402

SKILL = Path(__file__).resolve().parents[1]
FIXTURES = SKILL / 'tests' / 'fixtures'
PROVENANCE = ('source_url', 'publisher', 'licence', 'retrieved_at', 'latest_data')


def args(command, *flags):
    return cli.parser().parse_args([command, '--feed', 'at', *flags])


def modified_zip(path, changes):
    """Explicit synthetic edge cases derived from the real, licensed AT capture."""
    with zipfile.ZipFile(FIXTURES / 'at-sample.zip') as source, zipfile.ZipFile(path, 'w') as target:
        for name in source.namelist():
            if name in changes and changes[name] is None:
                continue
            if name in changes:
                rows = changes[name]
                fields = next(csv.reader(io.StringIO(source.read(name).decode('utf-8-sig'))))
                buf = io.StringIO(newline='')
                writer = csv.DictWriter(buf, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
                target.writestr(name, buf.getvalue())
            else:
                target.writestr(name, source.read(name))


def fixture_checks():
    source = json.loads((FIXTURES / 'source-sample.json').read_text())
    f = cli.Feed(FIXTURES / 'at-sample.zip', 'at', source['retrieved_at'], cached=True)
    assertions = 0

    def check(condition, message):
        nonlocal assertions
        assert condition, message
        assertions += 1
        print('[PASS] fixture ' + message)

    try:
        check(all(sum(1 for _ in f.rows(n)) == count for n, count in source['table_rows'].items()),
              'real ZIP table selection counts')
        check(f.provenance()['latest_data'] == source['latest_data'], 'feed_info dates/version are source values')
        stop_args = args('stops', '--limit', '2')
        out = cli.stops(f, stop_args)
        check(out['total'] == 27 and out['returned'] == 2 and out['truncated'], 'limits count all matches')
        check(all(all(k in row for k in PROVENANCE) for row in out['records']) and
              out['retrieved_at'] == source['retrieved_at'], 'record provenance and cached retrieval time')
        stop = next(f.rows('stops.txt'))
        near_args = args('stops', '--near', f"{stop['stop_lon']},{stop['stop_lat']}", '--radius', '1', '--format', 'geojson')
        nearby = cli.stops(f, near_args)
        check(nearby['features'] and nearby['features'][0]['properties']['distance_m'] == 0 and
              nearby['features'][0]['geometry']['coordinates'] == [float(stop['stop_lon']), float(stop['stop_lat'])],
              'nearby GeoJSON uses longitude,latitude and provenance')
        empty = cli.stops(f, args('stops', '--bbox', '0,0,1,1'))
        check(empty['total'] == 0 and empty['records'] == [], 'bbox filters outside NZ')
        check(cli.routes(f, args('routes', '--type', 'bus'))['total'] == 1 and
              cli.routes(f, args('routes', '--type', 'rail'))['total'] == 0 and
              cli.mode('712') == 'bus' and cli.mode('100') == 'rail' and cli.mode('1200') == 'ferry',
              'standard and extended route type filters')
        check(cli.trips(f, args('trips', '--route', '101'))['total'] == 3, 'route short name resolves real trips')
        dep = cli.departures(f, args('departures', '--stop', source['stop_id'], '--date', source['service_date']))
        raw = [r for r in f.rows('stop_times.txt') if r['stop_id'] == source['stop_id'] and r.get('pickup_type') != '1']
        check(dep['total'] == len(raw) == 3 and all(r['scheduled'] for r in dep['records']) and
              [r['scheduled_seconds'] for r in dep['records']] == sorted(cli.seconds(r['departure_time']) for r in raw),
              'real departures join calendars/trips and sort by scheduled time')
        shape = cli.shapes(f, args('shapes', '--route', source['route_id']))
        check(len(shape['features']) == 1 and all(len(r['geometry']['coordinates']) >= 2 and
              all(k in r['properties'] for k in PROVENANCE) for r in shape['features']),
              'real route shapes form provenance-bearing LineStrings')
        check(cli.intersects([[-2, 0], [2, 0]], [-1, -1, 1, 1]) and
              not cli.intersects([[-2, 2], [2, 2]], [-1, -1, 1, 1]),
              'bbox tests crossing segments without interior vertices')
        with tempfile.TemporaryDirectory(dir=SKILL) as tmp:
            tmp = Path(tmp)
            all_trips = list(f.rows('trips.txt'))
            first = all_trips[0]
            calendar = [r for r in f.rows('calendar.txt') if r['service_id'] == first['service_id']][:1]
            check(bool(calendar), 'captured trip has a base calendar')
            exceptions = [dict(service_id=first['service_id'], date='20261008', exception_type='2'),
                          dict(service_id='synthetic-added', date='20261008', exception_type='1')]
            changed = tmp / 'calendar.zip'
            modified_zip(changed, {'calendar.txt': calendar, 'calendar_dates.txt': exceptions})
            test = cli.Feed(changed, 'at', source['retrieved_at'])
            try:
                active = cli.active_services(test, cli.date(2026, 10, 8))
                check(first['service_id'] not in active and 'synthetic-added' in active,
                      'calendar exception additions/removals override weekday service')
            finally:
                test.close()
            modified_zip(changed, {'calendar.txt': None, 'calendar_dates.txt': [exceptions[1]]})
            test = cli.Feed(changed, 'at', source['retrieved_at'])
            try:
                check(cli.active_services(test, cli.date(2026, 10, 8)) == {'synthetic-added'} and
                      cli.active_services(test, cli.date(2026, 10, 9)) == set(), 'calendar_dates-only feed')
            finally:
                test.close()
            selected = [r for r in f.rows('stop_times.txt') if r['stop_id'] == source['stop_id']]
            # All three captured trips are active on this date. Make overnight/no-pickup/untimed cases.
            selected[0]['departure_time'] = '25:10:00'
            selected[1]['pickup_type'] = '1'
            selected[2]['departure_time'] = ''
            modified_zip(changed, {'stop_times.txt': selected})
            test = cli.Feed(changed, 'at', source['retrieved_at'])
            try:
                result = cli.departures(test, args('departures', '--stop', source['stop_id'], '--date', '2026-10-08', '--time', '24:00'))
                check(result['total'] == 1 and result['records'][0]['departure_time'] == '25:10:00' and
                      result['records'][0]['service_date'] == '2026-10-08' and result['untimed_stop_times'] == 1,
                      'overnight service-date time, no-pickup exclusion and untimed warning')
            finally:
                test.close()
            # Header is copied from the upstream empty frequencies table.
            frequency = dict(trip_id=first['trip_id'], start_time='08:00:00', end_time='09:00:00', headway_secs='600', exact_times='0')
            modified_zip(changed, {'frequencies.txt': [frequency]})
            test = cli.Feed(changed, 'at', source['retrieved_at'])
            try:
                try:
                    cli.departures(test, args('departures', '--stop', source['stop_id'], '--date', '2026-10-08'))
                except cli.GTFSFailure as exc:
                    check(exc.code == 7, 'frequency service fails explicitly rather than inventing departures')
                else:
                    raise AssertionError('frequencies must fail')
            finally:
                test.close()
            shape_rows = list(f.rows('shapes.txt'))[:2]
            shape_rows[0]['shape_pt_sequence'] = '10'
            shape_rows[1]['shape_pt_sequence'] = '2'
            modified_zip(changed, {'shapes.txt': shape_rows})
            test = cli.Feed(changed, 'at', source['retrieved_at'])
            try:
                geometry = cli.shapes(test, args('shapes', '--route', '101'))['features'][0]['geometry']
                check(geometry['coordinates'][0] == [float(shape_rows[1]['shape_pt_lon']), float(shape_rows[1]['shape_pt_lat'])],
                      'shape point sequence sorts numerically, including unsorted input')
            finally:
                test.close()
            stop_rows = list(f.rows('stops.txt'))
            parent = dict(stop_rows[0])
            parent.update(stop_id='synthetic-station', stop_code='synthetic-station', location_type='1')
            next(r for r in stop_rows if r['stop_id'] == source['stop_id'])['parent_station'] = parent['stop_id']
            stop_rows.append(parent)
            modified_zip(changed, {'stops.txt': stop_rows})
            test = cli.Feed(changed, 'at', source['retrieved_at'])
            try:
                result = cli.departures(test, args('departures', '--stop', parent['stop_id'], '--date', '2026-10-08'))
                check(result['total'] == 3 and source['stop_id'] in result['included_stop_ids'],
                      'parent station includes child platform departures')
            finally:
                test.close()
            stop_rows[0]['stop_name'] = 'Synthetic Māori stop, "platform"'
            modified_zip(changed, {'stops.txt': stop_rows})
            # Add a BOM to the real-format CSV header while retaining CSV-escaped values.
            with zipfile.ZipFile(changed) as z:
                tables = {n: z.read(n) for n in z.namelist()}
            with zipfile.ZipFile(changed, 'w') as z:
                for n, content in tables.items():
                    z.writestr(n, b'\xef\xbb\xbf' + content if n == 'stops.txt' else content)
            test = cli.Feed(changed, 'at', source['retrieved_at'])
            try:
                check(next(test.rows('stops.txt'))['stop_name'] == stop_rows[0]['stop_name'],
                      'UTF-8 BOM, Māori text and quoted CSV fields')
            finally:
                test.close()
            # Malformed headers and row widths must fail, not become an empty success.
            for content in (b'stop_id,invented_column\n1,wrong\n', tables['stops.txt'].splitlines()[0] + b'\n1,short\n'):
                with zipfile.ZipFile(changed, 'w') as z:
                    for n, data in tables.items():
                        z.writestr(n, content if n == 'stops.txt' else data)
                try:
                    cli.Feed(changed, 'at', source['retrieved_at'])
                except cli.GTFSFailure as exc:
                    check(exc.code == 6, 'malformed CSV headers or row widths fail explicitly')
                else:
                    raise AssertionError('malformed CSV must fail')
            # Seed fresh cache with a real fixture and exercise expiry using a mocked network transport.
            cached = tmp / 'cache'; cached.mkdir()
            (cached / 'at.zip').write_bytes((FIXTURES / 'at-sample.zip').read_bytes())
            retrieved = cli.utc_now()
            (cached / 'at.json').write_text(json.dumps({'source_url': cli.FEEDS['at']['source_url'], 'retrieved_at': retrieved}))
            with mock.patch.object(cli.urllib.request, 'urlopen', side_effect=AssertionError('fresh cache must not request')):
                test = cli.get_feed('at', cached)
                try:
                    check(test.cached and test.retrieved_at == retrieved, 'fresh cache is reused without network')
                finally:
                    test.close()
            with mock.patch.object(cli.urllib.request, 'urlopen', return_value=io.BytesIO((FIXTURES / 'at-sample.zip').read_bytes())) as http:
                test = cli.get_feed('at', cached, max_age=0)
                try:
                    check(not test.cached and http.call_args.kwargs['timeout'] == 10, 'expired cache downloads with 10 s timeout')
                finally:
                    test.close()
            with mock.patch.object(cli.urllib.request, 'urlopen', side_effect=urllib.error.URLError('synthetic outage')):
                try:
                    cli.get_feed('at', cached, max_age=0)
                except cli.GTFSFailure as exc:
                    check(exc.code == 5, 'failed refresh does not silently use stale data')
                else:
                    raise AssertionError('outage must fail')
            error = urllib.error.HTTPError(cli.FEEDS['at']['source_url'], 429, 'rate limit', {'Retry-After': '60'}, None)
            with mock.patch.object(cli.urllib.request, 'urlopen', side_effect=error):
                try:
                    cli.get_feed('at', cached, refresh=True)
                except cli.GTFSFailure as exc:
                    check(exc.code == 4 and exc.retry_after == '60', 'rate limit retains Retry-After')
                else:
                    raise AssertionError('429 must fail')
            with zipfile.ZipFile(tmp / 'invalid.zip', 'w') as z:
                z.writestr('stops.txt', 'invented_column\nwrong\n')
            try:
                cli.Feed(tmp / 'invalid.zip', 'at', retrieved)
            except cli.GTFSFailure as exc:
                check(exc.code == 6, 'invalid archive tables fail as schema errors')
            else:
                raise AssertionError('invalid source must fail')
            # Check the documented CLI surface through real fixture-backed subprocesses.
            for command, flags in [('stops', []), ('routes', []), ('trips', ['--route', '101']),
                                   ('departures', ['--stop', source['stop_id'], '--date', source['service_date']]),
                                   ('shapes', ['--route', '101', '--format', 'geojson'])]:
                run = subprocess.run([sys.executable, str(SKILL / 'scripts' / 'cli.py'), command,
                                      '--feed', 'at', '--cache-dir', str(cached), '--json', *flags],
                                     capture_output=True, text=True, timeout=5)
                payload = json.loads(run.stdout)
                check(run.returncode == 0 and payload['ok'] and payload['retrieved_at'], f'{command} CLI returns JSON from cached real ZIP')
            for flags in [['departures', '--stop', source['stop_id'], '--date', '2026-13-01'],
                          ['departures', '--stop', source['stop_id'], '--time', '12:99'],
                          ['routes', '--limit', '0'], ['stops', '--bbox', 'nan,0,1,1'],
                          ['stops', '--radius', '-1']]:
                run = subprocess.run([sys.executable, str(SKILL / 'scripts' / 'cli.py'), *flags,
                                      '--feed', 'at', '--cache-dir', str(cached), '--json'],
                                     capture_output=True, text=True, timeout=5)
                check(run.returncode == 2 and 'Traceback' not in run.stdout + run.stderr,
                      'invalid input exits 2: ' + ' '.join(flags))
    finally:
        f.close()
    return assertions


if __name__ == '__main__':
    result = run_contract_test(SKILL)
    if result == 0:
        try:
            count = fixture_checks()
            print(f'[PASS] contract {count} GTFS fixture checks')
        except Exception as exc:
            print('[FAIL] fixture ' + str(exc))
            raise SystemExit(1)
    raise SystemExit(result)
