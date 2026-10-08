#!/usr/bin/env python3
"""Bounded, outage-aware real GTFS downloads and timetable query checks."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

import cli
from test_contract import fixture_checks

SKILL = Path(__file__).resolve().parents[1]


def main():
    try:
        fixture_checks()
    except Exception as exc:
        print('[FAIL] fixture ' + str(exc))
        return 1
    failed = False
    with tempfile.TemporaryDirectory(prefix='gtfs-smoke-') as directory:
        try:
            result = subprocess.run([sys.executable, str(SKILL / 'scripts' / 'cli.py'),
                                     'feeds', '--cache-dir', directory, '--json'],
                                    capture_output=True, text=True, timeout=65)
        except subprocess.TimeoutExpired:
            print('[SKIP] registry network error: live download exceeded the 65 s smoke bound')
            return 0
        if result.returncode in (4, 5):
            print('[SKIP] registry network error: ' + result.stdout + result.stderr)
            return 0
        if result.returncode:
            print('[FAIL] live feeds command: ' + result.stdout + result.stderr)
            return 1
        try:
            status = json.loads(result.stdout)
            assert status['meta']['total'] == len(cli.FEEDS)
            assert all(isinstance(status['meta'].get(k), str) for k in ('source_url', 'publisher', 'retrieved_at'))
            print('[PASS] contract feeds CLI returns registry and provenance JSON')
        except (ValueError, AssertionError) as exc:
            print('[FAIL] schema feed registry: ' + str(exc))
            return 1
        for row in status['results']:
            key = row['feed']
            if row['status'] != 'available':
                if row['error']['code'] in (4, 5):
                    print(f"[SKIP] {key} network error: {row['error']['message']}")
                    continue
                print(f"[FAIL] schema {key}: {row['error']['message']}")
                failed = True
                continue
            feed = None
            try:
                feed = cli.Feed(Path(directory) / (key + '.zip'), key, row['retrieved_at'])
                assert row['zip_bytes'] > 0
                assert all(isinstance(row.get(k), str) for k in ('source_url', 'publisher', 'retrieved_at'))
                if key == 'busit':
                    assert 'latest_data' not in row and row['warnings']
                else:
                    assert isinstance(row['latest_data'], str) and '/' in row['latest_data']
                print(f"[PASS] live {key} ZIP={row['zip_bytes']} bytes; feed_info={row.get('latest_data', 'not published')}")
                routes = cli.routes(feed, cli.parser().parse_args(['routes', '--feed', key, '--limit', '1']))
                stops = cli.stops(feed, cli.parser().parse_args(['stops', '--feed', key, '--limit', '1']))
                assert routes['meta']['total'] > 0 and stops['meta']['total'] > 0 and stops['results'][0]['stop_name']
                print(f"[PASS] live {key} routes={routes['meta']['total']} stops={stops['meta']['total']}; sample stop={stops['results'][0]['stop_id']} {stops['results'][0]['stop_name']}")
                if feed.info and feed.info[0].get('feed_start_date'):
                    day = cli.gtfs_date(feed.info[0]['feed_start_date'])
                else:
                    day = cli.gtfs_date(next(feed.rows('calendar.txt'))['start_date'])
                active = cli.active_services(feed, day)
                trip = next(r for r in feed.rows('trips.txt') if r['service_id'] in active and r.get('shape_id'))
                time_row = next(r for r in feed.rows('stop_times.txt') if r['trip_id'] == trip['trip_id']
                                and r['departure_time'] and r.get('pickup_type') != '1')
                trip_out = cli.trips(feed, cli.parser().parse_args(['trips', '--feed', key, '--route', trip['route_id']]))
                dep_out = cli.departures(feed, cli.parser().parse_args(['departures', '--feed', key,
                                          '--stop', time_row['stop_id'], '--date', day.isoformat()]))
                assert trip_out['meta']['total'] > 0 and dep_out['meta']['total'] > 0
                assert all(r['scheduled'] and r['service_date'] == day.isoformat() for r in dep_out['results'])
                print(f"[PASS] live {key} route={trip['route_id']} trips={trip_out['meta']['total']}; stop={time_row['stop_id']} service_date={day} departures={dep_out['meta']['total']} first={dep_out['results'][0]['departure_time']}")
                shape = cli.shapes(feed, cli.parser().parse_args(['shapes', '--feed', key,
                                       '--route', trip['route_id'], '--format', 'geojson']))
                assert shape['type'] == 'FeatureCollection' and shape['features']
                assert all(f['geometry']['type'] == 'LineString' and len(f['geometry']['coordinates']) >= 2
                           and shape['meta']['source_url'] == row['source_url'] for f in shape['features'])
                print(f"[PASS] live {key} route shape LineStrings={shape['meta']['total']}")
            except Exception as exc:
                print(f'[FAIL] parser {key}: {exc}')
                failed = True
            finally:
                if feed is not None:
                    feed.close()
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
