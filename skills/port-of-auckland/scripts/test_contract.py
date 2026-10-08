#!/usr/bin/env python3
"""Deterministic CLI, parser, caching and provenance contracts."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / 'scripts'))
sys.path.insert(0, str(SKILL_DIR.parents[1] / 'lib'))
import cli
from contract_test import run_contract_test

FIXTURES = SKILL_DIR / 'tests' / 'fixtures'


def fixture(name):
    return (FIXTURES / name).read_text(encoding='utf-8')


class FixtureTests(unittest.TestCase):
    def test_csv_shape_and_repeated_vessel(self):
        rows, latest = cli.parse_arrivals(fixture('arrivals.csv'))
        self.assertEqual(len(rows), 3)
        self.assertEqual(len({r['vessel'] for r in rows}), 2)
        self.assertEqual(rows[0]['arrival'], '2026-10-08T09:00+13:00')
        self.assertEqual(rows[0]['receivals_start'], 'Refer to Line')
        self.assertIsNone(latest)

    def test_auckland_turns_midnight_and_latest_data(self):
        rows, latest = cli.parse_trucks(fixture('trucks.html'))
        self.assertEqual([r['turn_seconds'] for r in rows], [667, 189])
        self.assertEqual(rows[0]['observed_at'], '2026-10-07T23:58+13:00')
        self.assertEqual(latest, '2026-10-08T00:01+13:00')

    def test_tauranga_expected_table_only(self):
        rows, latest = cli.parse_tauranga_arrivals(fixture('tauranga.html'))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['agent'], 'Example & Co')
        self.assertEqual(rows[0]['arrival'], '2026-10-09T08:30+13:00')
        self.assertEqual(latest, '2026-10-08T12:34+13:00')

    def test_tauranga_queue_is_not_turn_seconds(self):
        rows, latest = cli.parse_tauranga_queue(fixture('tauranga-queue.html'))
        self.assertEqual(rows[0]['queue_trucks'], 7)
        self.assertNotIn('turn_seconds', rows[0])
        self.assertEqual(latest, rows[0]['observed_at'])

    def test_schema_failures_are_not_empty_successes(self):
        for parser, source in [(cli.parse_arrivals, 'Vessel,Arrival\n'),
                               (cli.parse_trucks, '<html>No metrics</html>'),
                               (cli.parse_tauranga_arrivals, '<table></table>'),
                               (cli.parse_tauranga_queue, '<html>No queue</html>')]:
            with self.assertRaises(cli.SkillError) as exc:
                parser(source)
            self.assertEqual(exc.exception.code, 6)
        with self.assertRaises(cli.SkillError):
            cli.parse_arrivals(fixture('arrivals.csv').replace('8 Oct 2026 09:00', 'bad date'))

    def test_inclusive_date_and_vessel_filters(self):
        args = cli.build_parser().parse_args(['arrivals', '--from', '2026-10-08', '--to', '2026-10-09', '--vessel', 'explorer'])
        rows, _ = cli.parse_arrivals(fixture('arrivals.csv'))
        self.assertEqual(len(cli.filter_records(rows, args, 'arrival')), 2)
        args = cli.build_parser().parse_args(['truck-turns', '--from', '2026-10-08', '--to', '2026-10-08'])
        rows, _ = cli.parse_trucks(fixture('trucks.html'))
        self.assertEqual(len(cli.filter_records(rows, args, 'observed_at')), 1)
        args.start = cli.date_arg('2030-01-01')
        self.assertEqual(cli.filter_records(rows, args, 'observed_at'), [])

    def test_json_input_errors(self):
        for argv in [['arrivals', '--from', '2026-99-08'], ['truck-turns', '--from', '2026-10-09', '--to', '2026-10-08'],
                     ['arrivals', '--max-age', '-1'], ['arrivals', '--max-age', '3601'], ['unknown']]:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                status = cli.main(argv + ['--json'])
            payload = json.loads(out.getvalue())
            self.assertEqual(status, 2)
            self.assertEqual(payload['error']['type'], 'invalid_input')
            self.assertEqual(payload['results'], [])
            self.assertTrue(payload['meta']['retrieved_at'].endswith('Z'))

    def test_cache_preserves_timestamp_and_expires(self):
        with tempfile.TemporaryDirectory(dir=FIXTURES) as temporary:
            path = Path(temporary) / 'cache.json'
            payload = cli.result_envelope([{'synthetic': True}], cli.provenance(*cli.FEEDS['auckland', 'arrivals']))
            cli.write_cache(path, payload)
            self.assertEqual(cli.read_cache(path, 300), payload)
            self.assertIsNone(cli.read_cache(path, 0))
            payload['meta']['retrieved_at'] = '2000-01-01T00:00:00Z'
            cli.write_cache(path, payload)
            self.assertIsNone(cli.read_cache(path, 300))
            path.write_text('{bad json')
            self.assertIsNone(cli.read_cache(path, 300))

    def test_refresh_and_block_do_not_return_stale_data(self):
        with tempfile.TemporaryDirectory(dir=FIXTURES) as temporary, patch.object(cli, 'CACHE_DIR', Path(temporary)):
            with patch.object(cli, 'check_robots'), patch.object(cli, 'fetch_text', return_value=fixture('arrivals.csv')) as fetch:
                first = cli.load_feed('auckland', 'arrivals', 300)
                second = cli.load_feed('auckland', 'arrivals', 300)
                self.assertEqual(first, second)
                self.assertEqual(fetch.call_count, 1)
            with patch.object(cli, 'check_robots'), patch.object(cli, 'fetch_text', side_effect=cli.SkillError('network error', 5)):
                with self.assertRaises(cli.SkillError):
                    cli.load_feed('auckland', 'arrivals', 0)

    def test_robots_disallow(self):
        with tempfile.TemporaryDirectory(dir=FIXTURES) as temporary, patch.object(cli, 'CACHE_DIR', Path(temporary)), \
                patch.object(cli, 'fetch_text', return_value='User-agent: *\nDisallow: /operations/\n'):
            with self.assertRaises(cli.SkillError) as exc:
                cli.check_robots(cli.FEEDS['auckland', 'arrivals'][0])
            self.assertEqual(exc.exception.code, 4)

    def test_mixed_summary_provenance(self):
        def feed(port, command, age):
            parser, name = (cli.parse_arrivals, 'arrivals.csv') if command == 'arrivals' else (cli.parse_trucks, 'trucks.html')
            rows, latest = parser(fixture(name))
            return cli.result_envelope(rows, cli.provenance(*cli.FEEDS[port, command], latest_data=latest))
        with patch.object(cli, 'load_feed', side_effect=feed):
            payload = cli.execute(cli.build_parser().parse_args(['summary']))
        self.assertEqual(payload['results'][0]['vessel_calls'], 3)
        self.assertEqual(payload['results'][0]['distinct_vessels'], 2)
        self.assertNotEqual(payload['results'][0]['source_url'], payload['results'][1]['source_url'])
        self.assertEqual(payload['results'][1]['latest_data'], '2026-10-08T00:01+13:00')

    def test_rate_limit_retry_after(self):
        with patch.object(cli.nzfetch, 'fetch_text', side_effect=cli.nzfetch.RateLimited('limited', retry_after='60')):
            with self.assertRaises(cli.SkillError) as exc:
                cli.fetch_text(cli.FEEDS['auckland', 'arrivals'][0])
        self.assertEqual(exc.exception.code, 4)
        self.assertEqual(exc.exception.retry_after, '60')

    def test_summary_upstream_error_provenance(self):
        with tempfile.TemporaryDirectory(dir=FIXTURES) as temporary, patch.object(cli, 'CACHE_DIR', Path(temporary)), \
                patch.object(cli, 'check_robots'), patch.object(cli, 'fetch_text',
                    side_effect=[fixture('arrivals.csv'), cli.SkillError('network error: limited', 4, '60')]):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                status = cli.main(['summary', '--max-age', '0', '--json'])
        payload = json.loads(out.getvalue())
        self.assertEqual(status, 4)
        self.assertEqual(payload['meta']['source_url'], cli.FEEDS['auckland', 'truck-turns'][0])
        self.assertEqual(payload['error']['retry_after'], '60')


def run_fixture_tests():
    result = unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromTestCase(FixtureTests))
    if result.wasSuccessful():
        print(f'[PASS] fixture parsers, filters, provenance, robots and cache: {result.testsRun} tests')
    return result.wasSuccessful()


if __name__ == '__main__':
    contract_status = run_contract_test(SKILL_DIR)
    raise SystemExit(0 if run_fixture_tests() and contract_status == 0 else 1)
