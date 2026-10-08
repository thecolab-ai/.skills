#!/usr/bin/env python3
"""Real-fixture capability checks plus the shared repository contract."""
from __future__ import annotations

import contextlib
import copy
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR.parents[1] / 'lib'))
from contract_test import run_contract_test  # noqa: E402
import cli  # noqa: E402

FIXTURES = SKILL_DIR / 'tests' / 'fixtures'
STAMP = '2026-10-08T00:00:00Z'
PROVENANCE = {'source_url', 'publisher', 'licence', 'retrieved_at', 'latest_data'}


def fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding='utf-8'))


class RecordsTests(unittest.TestCase):
    def invoke(self, args, fetch):
        stdout = io.StringIO()
        with patch.object(cli, 'fetch_json', side_effect=fetch), contextlib.redirect_stdout(stdout):
            code = cli.main(args)
        return code, json.loads(stdout.getvalue())

    def test_real_search_and_detail_fixtures(self):
        for cat in ('auckland-council', 'auckland-transport', 'waka-kotahi', 'niwa'):
            data = fixture(cat + '.json')
            features, count, next_urls = cli.ogc_page(data)
            self.assertEqual(count, data['numberMatched'])
            self.assertEqual(len(features), 2)
            rec = cli.normalise_ogc(features[0], cat, cli.CATALOGUES[cat]['source_url'], STAMP)
            self.assertEqual(rec['title'], features[0]['properties']['title'])
            self.assertEqual(rec['licence'], features[0]['properties']['license'])
            self.assertTrue(PROVENANCE <= rec.keys())
            self.assertIsNone(rec['latest_data'])
            self.assertTrue(rec['updated_at'].endswith('Z'))
            self.assertEqual(rec['geometry'], features[0]['geometry'])
            self.assertTrue(rec['distribution_urls'])
            for dist in rec['distributions']:
                self.assertTrue(PROVENANCE <= dist.keys())
            detail = fixture(cat + '-get.json')
            row = cli.normalise_ogc(detail, cat, detail['links'][0]['href'], STAMP)
            self.assertEqual(row['id'], detail['id'])
            self.assertEqual(row['title'], rec['title'])
            if cat == 'auckland-transport':
                self.assertTrue(row['id'].endswith('_0'))
                self.assertIn('/FeatureServer', row['distribution_urls'][0])
                self.assertIn('geojson', row['formats'])
            if cat == 'niwa':
                self.assertEqual(row['licence'], 'CC-BY-NC-4.0')
                self.assertIn('/ImageServer', row['distribution_urls'][0])

    def test_zip_distribution_and_dates_do_not_claim_fresh_data(self):
        for cat in ('auckland-council', 'waka-kotahi'):
            f = fixture(cat + '-get.json')
            r = cli.normalise_ogc(f, cat, f['links'][0]['href'], STAMP)
            self.assertTrue(r['distributions'][0]['derived'])
            self.assertTrue(r['distribution_urls'][0].endswith('/' + f['id'] + '/data'))
            self.assertIsNone(r['latest_data'])
            self.assertIsNotNone(r['updated_at'])
        f = fixture('niwa-get.json')
        f['properties'].pop('license')
        r = cli.normalise_ogc(f, 'niwa', f['links'][0]['href'], STAMP)
        self.assertIn('NonCommercial', r['licence'])
        f['properties'].pop('licenseInfo')
        r = cli.normalise_ogc(f, 'niwa', f['links'][0]['href'], STAMP)
        self.assertIsNone(r['licence'])

    def test_search_forwards_bbox_and_keeps_pagination_and_provenance(self):
        calls = []
        def fetch(url):
            calls.append(url)
            return fixture('niwa.json')
        code, payload = self.invoke(['search', 'bathymetry', '--catalogue', 'niwa', '--bbox',
                                    '174.4,-37.2,175.3,-36.4', '--limit', '1', '--json'], fetch)
        self.assertEqual(code, 0)
        self.assertEqual(len(calls), 1)
        params = parse_qs(urlsplit(calls[0]).query)
        self.assertEqual(params['q'], ['bathymetry'])
        self.assertEqual(params['bbox'], ['174.4,-37.2,175.3,-36.4'])
        self.assertEqual(params['limit'], ['1'])
        self.assertEqual(len(payload['records']), 1)
        self.assertEqual(payload['catalogues'][0]['next_urls'],
                         [l['href'] for l in fixture('niwa.json')['links'] if l['rel'] == 'next'])
        self.assertTrue(PROVENANCE <= payload.keys())
        self.assertFalse(payload['partial'])
        self.assertEqual(payload['publisher'], 'NIWA')
        self.assertEqual(payload['source_url'], cli.CATALOGUES['niwa']['source_url'])

    def test_partial_search_reports_blocked_ckan_without_crashing(self):
        def fetch(url):
            if urlsplit(url).hostname == urlsplit(cli.CATALOGUES['data-govt-nz']['source_url']).hostname:
                raise cli.SourceError('network error: blocked', 4, 'blocked')
            return fixture('niwa.json')
        code, p = self.invoke(['search', 'water', '--catalogue', 'niwa', '--catalogue',
                              'data-govt-nz', '--json'], fetch)
        self.assertEqual(code, 0)
        self.assertTrue(p['ok'])
        self.assertTrue(p['partial'])
        self.assertTrue(p['records'])
        self.assertEqual(p['catalogues'][1]['status'], 'unavailable')
        self.assertEqual(p['catalogues'][1]['error_code'], 4)
        self.assertTrue(p['warnings'])
        code, p = self.invoke(['search', 'water', '--catalogue', 'data-govt-nz', '--json'], fetch)
        self.assertEqual(code, 4)
        self.assertFalse(p['ok'])
        self.assertEqual(p['records'], [])
        self.assertIn('error', p)

    def test_catalogue_probe_reports_all_statuses(self):
        def fetch(url):
            for cat, meta in cli.CATALOGUES.items():
                if url.startswith(meta['source_url']):
                    if cat == 'data-govt-nz':
                        raise cli.SourceError('network error: blocked', 4, 'blocked')
                    return fixture(cat + '.json')
            self.fail('Unknown outbound catalogue')
        code, p = self.invoke(['catalogues', '--json'], fetch)
        self.assertEqual(code, 0)
        self.assertEqual(len(p['catalogues']), 5)
        for c in p['catalogues']:
            self.assertTrue(PROVENANCE <= c.keys())
        self.assertEqual(sum(c['available'] for c in p['catalogues']), 4)

    def test_geojson_search_and_get_preserve_null_coverage(self):
        code, p = self.invoke(['search', 'impervious', '--catalogue', 'auckland-council',
                              '--limit', '1', '--format', 'geojson'],
                             lambda url: fixture('auckland-council.json'))
        self.assertEqual(code, 0)
        self.assertEqual(p['type'], 'FeatureCollection')
        self.assertIsNone(p['features'][0]['geometry'])
        self.assertTrue(PROVENANCE <= p['features'][0]['properties'].keys())
        code, p = self.invoke(['get', 'auckland-transport', fixture('auckland-transport.json')['features'][0]['id'],
                              '--format', 'geojson'], lambda url: fixture('auckland-transport-get.json'))
        self.assertEqual(code, 0)
        self.assertEqual(p['features'][0]['geometry']['type'], 'Polygon')
        self.assertTrue(p['features'][0]['id'].endswith('_0'))

    def test_malformed_response_is_failure_and_empty_search_is_valid(self):
        for data in ({}, {'type': 'FeatureCollection', 'features': [], 'numberMatched': 'unknown'},
                     {'type': 'FeatureCollection', 'features': [None], 'numberMatched': 1}):
            code, p = self.invoke(['search', 'water', '--catalogue', 'niwa', '--json'], lambda url: data)
            self.assertEqual(code, 6)
            self.assertFalse(p['ok'])
            self.assertEqual(p['catalogues'][0]['error_category'], 'schema_error')
        data = copy.deepcopy(fixture('niwa.json'))
        data.update(features=[], numberMatched=0, numberReturned=0, links=[])
        code, p = self.invoke(['search', 'water', '--catalogue', 'niwa', '--json'], lambda url: data)
        self.assertEqual(code, 0)
        self.assertTrue(p['ok'])
        self.assertEqual(p['returned'], 0)
        for key in ('type', 'license', 'source', 'url'):
            malformed = copy.deepcopy(fixture('niwa-get.json'))
            malformed['properties'][key] = {}
            code, p = self.invoke(['get', 'niwa', malformed['id'], '--json'], lambda url: malformed)
            self.assertEqual(code, 6)
            self.assertEqual(p['error']['category'], 'schema_error')
        code, p = self.invoke(['get', 'niwa', 'missing', '--json'], lambda url: {})
        self.assertEqual(code, 6)
        self.assertFalse(p['ok'])
        self.assertTrue(PROVENANCE <= p.keys())

    def test_ckan_bbox_is_explicitly_unsupported(self):
        with patch.object(cli, 'fetch_json') as fetch:
            code, p = self.invoke(['search', 'water', '--catalogue', 'data-govt-nz',
                                  '--bbox', '174,-37,175,-36', '--json'], lambda url: self.fail('Must not fetch'))
        self.assertEqual(code, 7)
        self.assertEqual(p['catalogues'][0]['status'], 'unsupported_bbox')
        fetch.assert_not_called()

    def test_input_rejected_before_network(self):
        for argv in (['search', 'x', '--limit', '0'], ['search', 'x', '--limit', '101'],
                     ['search', 'x', '--bbox', '175,-37,174,-36'],
                     ['search', 'x', '--bbox', '174,-91,175,-36'],
                     ['search', 'x', '--bbox', 'NaN,-37,175,-36'],
                     ['search', 'x', '--bbox', '174,-37,175'],
                     ['search', ' '], ['get', 'niwa', '../file'],
                     ['get', 'niwa', 'https://example.com']):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
                cli.parse_args(argv)
            self.assertEqual(caught.exception.code, 2)

    def test_bounded_allowlisted_fetch_and_rate_limit(self):
        with patch.object(cli.nzfetch, 'fetch_json', return_value=fixture('niwa.json')) as fetch:
            cli.fetch_json(cli.query_url('niwa'))
            self.assertEqual(fetch.call_args.kwargs['timeout'], 10)
            self.assertEqual(fetch.call_args.kwargs['allowed_hosts'], cli.ALLOWED_HOSTS)
        with patch.object(cli.nzfetch, 'fetch_json', side_effect=cli.nzfetch.RateLimited('slow', retry_after='60')):
            with self.assertRaises(cli.SourceError) as caught:
                cli.fetch_json(cli.query_url('niwa'))
            self.assertEqual(caught.exception.code, 4)
            self.assertEqual(caught.exception.retry_after, '60')


def main():
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(RecordsTests))
    if not result.wasSuccessful():
        return 1
    return run_contract_test(SKILL_DIR)


if __name__ == '__main__':
    raise SystemExit(main())
