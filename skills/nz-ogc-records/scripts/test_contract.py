#!/usr/bin/env python3
"""Captured OGC and synthetic CKAN checks plus the shared repository contract."""
from __future__ import annotations

import contextlib
import copy
import io
import importlib.util
from urllib.error import HTTPError
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
import smoke_test  # noqa: E402

FIXTURES = SKILL_DIR / 'tests' / 'fixtures'
STAMP = '2026-10-08T00:00:00Z'
PROVENANCE = {'source_url', 'publisher', 'retrieved_at'}


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
            self.assertNotIn('latest_data', rec)
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
            self.assertNotIn('latest_data', r)
            self.assertIsNotNone(r['updated_at'])
        f = fixture('niwa-get.json')
        f['properties'].pop('license')
        r = cli.normalise_ogc(f, 'niwa', f['links'][0]['href'], STAMP)
        self.assertIn('NonCommercial', r['licence'])
        f['properties'].pop('licenseInfo')
        r = cli.normalise_ogc(f, 'niwa', f['links'][0]['href'], STAMP)
        self.assertNotIn('licence', r)
        for d in r['distributions']:
            self.assertNotIn('licence', d)
            self.assertNotIn('latest_data', d)

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
        self.assertEqual(len(payload['results']), 1)
        self.assertEqual(payload['meta']['catalogues'][0]['next_urls'],
                         [l['href'] for l in fixture('niwa.json')['links'] if l['rel'] == 'next'])
        self.assertTrue(PROVENANCE <= payload['meta'].keys())
        self.assertFalse(payload['meta']['partial'])
        self.assertEqual(payload['meta']['publisher'], cli.CATALOGUES['niwa']['publisher'])
        self.assertEqual(payload['meta']['source_url'], cli.CATALOGUES['niwa']['source_url'])

    def test_partial_search_reports_blocked_ckan_without_crashing(self):
        def fetch(url):
            if urlsplit(url).hostname == urlsplit(cli.CATALOGUES['data-govt-nz']['source_url']).hostname:
                raise cli.SourceError('network error: blocked', 4)
            return fixture('niwa.json')
        code, p = self.invoke(['search', 'water', '--catalogue', 'niwa', '--catalogue',
                              'data-govt-nz', '--json'], fetch)
        self.assertEqual(code, 0)
        self.assertNotIn('error', p)
        self.assertTrue(p['meta']['partial'])
        self.assertTrue(p['results'])
        self.assertEqual(p['meta']['catalogues'][1]['status'], 'unavailable')
        self.assertEqual(p['meta']['catalogues'][1]['error_code'], 4)
        self.assertTrue(p['meta']['warnings'])
        code, p = self.invoke(['search', 'water', '--catalogue', 'data-govt-nz', '--json'], fetch)
        self.assertEqual(code, 4)
        self.assertIn('error', p)
        self.assertEqual(p['results'], [])
        self.assertIn('error', p)

    def test_catalogue_probe_reports_all_statuses(self):
        def fetch(url):
            for cat, meta in cli.CATALOGUES.items():
                if url.startswith(meta['source_url']):
                    if cat == 'data-govt-nz':
                        raise cli.SourceError('network error: blocked', 4)
                    return fixture(cat + '.json')
            self.fail('Unknown outbound catalogue')
        code, p = self.invoke(['catalogues', '--json'], fetch)
        self.assertEqual(code, 0)
        self.assertEqual(len(p['meta']['catalogues']), 5)
        for c in p['meta']['catalogues']:
            self.assertTrue(PROVENANCE <= c.keys())
        self.assertEqual(sum(c['available'] for c in p['meta']['catalogues']), 4)

    def test_geojson_search_and_get_preserve_null_coverage(self):
        code, p = self.invoke(['search', 'impervious', '--catalogue', 'auckland-council',
                              '--limit', '1', '--format', 'geojson'],
                             lambda url, **kwargs: fixture('auckland-council.json'))
        self.assertEqual(code, 0)
        self.assertEqual(p['type'], 'FeatureCollection')
        self.assertIsNone(p['features'][0]['geometry'])
        self.assertTrue(PROVENANCE <= p['features'][0]['properties'].keys())
        code, p = self.invoke(['get', 'auckland-transport', fixture('auckland-transport.json')['features'][0]['id'],
                              '--format', 'geojson'], lambda url, **kwargs: fixture('auckland-transport-get.json'))
        self.assertEqual(code, 0)
        self.assertEqual(p['features'][0]['geometry']['type'], 'Polygon')
        self.assertTrue(p['features'][0]['id'].endswith('_0'))

    def test_malformed_response_is_failure_and_empty_search_is_valid(self):
        for data in ({}, {'type': 'FeatureCollection', 'features': [], 'numberMatched': 'unknown'},
                     {'type': 'FeatureCollection', 'features': [None], 'numberMatched': 1}):
            code, p = self.invoke(['search', 'water', '--catalogue', 'niwa', '--json'], lambda url, **kwargs: data)
            self.assertEqual(code, 6)
            self.assertIn('error', p)
            self.assertEqual(p['meta']['catalogues'][0]['error_category'], 'schema_failure')
        data = copy.deepcopy(fixture('niwa.json'))
        data.update(features=[], numberMatched=0, numberReturned=0, links=[])
        code, p = self.invoke(['search', 'water', '--catalogue', 'niwa', '--json'], lambda url, **kwargs: data)
        self.assertEqual(code, 0)
        self.assertNotIn('error', p)
        self.assertEqual(p['meta']['returned'], 0)
        for key in ('type', 'license', 'source', 'url'):
            malformed = copy.deepcopy(fixture('niwa-get.json'))
            malformed['properties'][key] = {}
            code, p = self.invoke(['get', 'niwa', malformed['id'], '--json'], lambda url, **kwargs: malformed)
            self.assertEqual(code, 6)
            self.assertEqual(p['error']['type'], 'schema_failure')
        code, p = self.invoke(['get', 'niwa', 'missing', '--json'], lambda url, **kwargs: {})
        self.assertEqual(code, 6)
        self.assertIn('error', p)
        self.assertTrue(PROVENANCE <= p['meta'].keys())

    def test_ckan_fixtures_bbox_geometry_and_pagination(self):
        raw = fixture('data-govt-nz.json')
        rows, count, _ = cli.ckan_result(raw)
        self.assertEqual(count, raw['result']['count'])
        self.assertEqual(len(rows), 3)
        url = cli.query_url('data-govt-nz', 'water', [174, -37, 175, -36], 2)
        r = cli.normalise_ckan(rows[0], 'data-govt-nz', url, STAMP)
        self.assertEqual(r['publisher'], rows[0]['organization']['title'])
        self.assertEqual(r['licence'], rows[0]['license_title'])
        self.assertEqual(r['distribution_urls'], [d['url'] for d in rows[0]['resources']])
        self.assertEqual(r['formats'], ['CSV'])
        self.assertEqual(r['geometry'], json.loads(rows[0]['spatial']))
        self.assertEqual(r['updated_at'], '2022-03-05T02:19:21Z')
        self.assertNotIn('latest_data', r)
        self.assertEqual(r['description'], 'Synthetic water metadata.')
        for d in r['distributions']:
            self.assertTrue(PROVENANCE <= d.keys())
            self.assertNotIn('latest_data', d)
        for spatial in (json.loads(rows[0]['spatial']), None):
            mutated = dict(rows[0], spatial=spatial)
            self.assertEqual(cli.normalise_ckan(mutated, 'data-govt-nz', url, STAMP)['geometry'], spatial)
        for spatial in ('', '  \t\n'):
            record = cli.normalise_ckan(dict(rows[0], spatial=spatial), 'data-govt-nz', url, STAMP)
            self.assertIsNone(record['geometry'])
            self.assertNotIn('geometry_warning', record)
        for spatial in ('{bad', '[]', {}, {'type': 4}, ['Polygon']):
            with self.assertRaises(cli.SourceError) as caught:
                cli.normalise_ckan(dict(rows[0], spatial=spatial), 'data-govt-nz', url, STAMP)
            self.assertEqual(caught.exception.code, 6)
        record = cli.normalise_ckan(rows[2], 'data-govt-nz', url, STAMP)
        self.assertIsNone(record['geometry'])
        self.assertEqual(record['publisher'], 'data.govt.nz')
        self.assertNotIn('licence', record)
        self.assertNotIn('licence', record['distributions'][0])
        self.assertEqual(record['distributions'][0]['updated_at'], '2026-10-02T03:04:05Z')
        blank_date = cli.normalise_ckan(rows[1], 'data-govt-nz', url, STAMP)
        self.assertIsNone(blank_date['geometry'])
        self.assertIsNone(blank_date['distributions'][0]['updated_at'])
        calls = []
        def fetch(url):
            calls.append(url)
            return raw
        code, p = self.invoke(['search', 'water', '--catalogue', 'data-govt-nz', '--limit', '2',
                              '--bbox', '174,-37,175,-36', '--format', 'json'], fetch)
        self.assertEqual(code, 0)
        self.assertFalse(p['meta']['partial'])
        self.assertEqual(parse_qs(urlsplit(calls[0]).query)['ext_bbox'], ['174.0,-37.0,175.0,-36.0'])
        next_url = p['meta']['catalogues'][0]['next_urls'][0]
        self.assertEqual(parse_qs(urlsplit(next_url).query),
                         {'q': ['water'], 'rows': ['2'], 'start': ['2'], 'ext_bbox': ['174.0,-37.0,175.0,-36.0']})
        code, p = self.invoke(['get', 'data-govt-nz', rows[2]['name'], '--json'],
                             lambda url, **kwargs: fixture('data-govt-nz-get.json'))
        self.assertEqual(code, 0)
        self.assertEqual(p['results'][0]['id'], rows[2]['id'])
        self.assertIsNone(p['results'][0]['geometry'])
        self.assertNotIn('licence', p['meta'])
        self.assertEqual(len(p['results']), 1)

    def test_ckan_malformed_coverage_preserves_search_page_but_get_fails(self):
        for spatial in ('{bad', '[]', {}, {'type': 4}):
            raw = fixture('data-govt-nz.json')
            raw['result']['results'][1]['spatial'] = spatial
            code, payload = self.invoke(['search', 'water', '--catalogue', 'data-govt-nz', '--json'],
                                        lambda url, **kwargs: raw)
            self.assertEqual(code, 0)
            self.assertEqual(len(payload['results']), 3)
            self.assertFalse(payload['meta']['partial'])
            self.assertTrue(payload['meta']['catalogues'][0]['available'])
            self.assertIsNotNone(payload['results'][0]['geometry'])
            self.assertIsNone(payload['results'][1]['geometry'])
            self.assertIn('geometry_warning', payload['results'][1])
            self.assertIn(raw['result']['results'][1]['id'], payload['meta']['warnings'][0])
            code, payload = self.invoke(['get', 'data-govt-nz', 'record', '--json'],
                                        lambda url, **kwargs: {'success': True, 'result': raw['result']['results'][1]})
            self.assertEqual(code, 6)
            self.assertEqual(payload['error']['type'], 'schema_failure')

    def test_shared_runner_accepts_success_and_error_shapes(self):
        spec = importlib.util.spec_from_file_location('records_run_skill', SKILL_DIR.parents[1] / 'scripts/run_skill.py')
        runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runner)
        for fetch, expected in ((lambda url, **kwargs: fixture('niwa-get.json'), 0),
                                (lambda url, **kwargs: {}, 6)):
            code, p = self.invoke(['get', 'niwa', 'record', '--json'], fetch)
            self.assertEqual(code, expected)
            self.assertFalse(runner.looks_like_result_envelope(p))
            self.assertEqual(set(p), {'meta', 'results'} | ({'error'} if expected else set()))
            self.assertTrue(PROVENANCE <= p['meta'].keys())
            self.assertNotIn('latest_data', p['meta'])
            if expected:
                self.assertEqual(p['results'], [])
                self.assertNotIn('licence', p['meta'])

    def test_fetch_error_causes_and_get_not_found(self):
        for status in (404, 410):
            err = cli.nzfetch.FetchError('unavailable')
            err.__cause__ = HTTPError(cli.query_url('niwa'), status, 'not found', {}, None)
            with patch.object(cli.nzfetch, 'fetch_json', side_effect=err):
                with self.assertRaises(cli.SourceError) as caught:
                    cli.fetch_json(cli.query_url('niwa'))
                self.assertEqual(caught.exception.code, 5)
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    code = cli.main(['get', 'niwa', 'missing', '--json'])
                p = json.loads(out.getvalue())
                self.assertEqual(code, 2)
                self.assertEqual(p['error']['type'], 'invalid_input')
        with patch.object(cli.nzfetch, 'fetch_bytes', return_value=(b'{not json', 'application/json', cli.query_url('niwa'))):
            with self.assertRaises(cli.SourceError) as caught:
                cli.fetch_json(cli.query_url('niwa'))
            self.assertEqual(caught.exception.code, 6)
            self.assertEqual(caught.exception.category, 'schema_failure')

    def test_all_failed_catalogues_and_order_independent_codes(self):
        def failed(url):
            raise cli.SourceError('network error: unavailable', 5)
        code, p = self.invoke(['catalogues', '--json'], failed)
        self.assertEqual(code, 5)
        self.assertEqual(p['error']['type'], 'upstream_unavailable')
        self.assertEqual(len(p['meta']['catalogues']), 5)
        for codes, expected in (((4, 5), 4), ((7, 5), 5), ((4, 6), 6)):
            for ordered in (codes, tuple(reversed(codes))):
                def fetch(url):
                    code = ordered[0 if 'data-niwa' in url else 1]
                    raise cli.SourceError('failure', code, retry_after='60' if code == 4 else None)
                code, p = self.invoke(['search', 'x', '--catalogue', 'niwa', '--catalogue', 'data-govt-nz',
                                      '--format', 'geojson'], fetch)
                self.assertEqual(code, expected)
                self.assertEqual(set(p), {'meta', 'results', 'error'})
                self.assertEqual(p['results'], [])
                if code == 4:
                    self.assertEqual(p['error']['retry_after'], '60')
        def limited(url):
            raise cli.SourceError('rate limited', 4, retry_after='120')
        code, p = self.invoke(['catalogues', '--json'], limited)
        self.assertEqual(p['error']['retry_after'], '120')

    def test_custom_none_licences_and_invalid_dates(self):
        for marker in ('custom', 'none', ''):
            f = fixture('auckland-council-get.json')
            f['properties']['license'] = marker
            f['properties']['licenseInfo'] = '<p>Terms &amp; conditions ' + 'licence clause ' * 30 + '</p>'
            r = cli.normalise_ogc(f, 'auckland-council', 'https://example.invalid/', STAMP)
            self.assertTrue(r['licence_info'].startswith(r['licence'][:-1]))
            self.assertTrue(r['licence'].endswith('licence…'))
            self.assertLessEqual(len(r['licence']), 301)
            self.assertTrue(r['licence'].endswith('…'))
            self.assertFalse(r['licence'][:-1].endswith(' '))
            self.assertGreater(len(r['licence_info']), 300)
            self.assertNotIn('<p>', r['licence'])
            f['properties'].pop('licenseInfo')
            r = cli.normalise_ogc(f, 'auckland-council', 'https://example.invalid/', STAMP)
            self.assertNotIn('licence', r)
            for d in r['distributions']:
                self.assertNotIn('licence', d)
        self.assertEqual(cli.iso_date('2022-03-05T02:19:21.805308'), '2022-03-05T02:19:21Z')
        self.assertEqual(cli.iso_date('2022-03-05T03:19:21+01:00'), '2022-03-05T02:19:21Z')
        for value in (None, '', ' \t\n'):
            self.assertIsNone(cli.iso_date(value))
        with self.assertRaises(cli.SourceError):
            cli.iso_date('invalid date')

    def test_smoke_cli_traceback_and_invalid_json_are_clean_failures(self):
        raw = fixture('data-govt-nz.json')
        rows, _, _ = cli.ckan_result(raw)
        record = cli.normalise_ckan(rows[0], 'data-govt-nz', cli.query_url('data-govt-nz'), STAMP)
        for returncode in (1, 0):
            run = smoke_test.subprocess.CompletedProcess([], returncode, '', 'synthetic traceback tail')
            out = io.StringIO()
            with patch.object(smoke_test, 'live', return_value='[SKIP] synthetic live probe'), \
                 patch.object(smoke_test.subprocess, 'run', return_value=run), \
                 patch.object(cli, 'catalogue_request', return_value=({'available': True, 'number_matched': 3}, [record])), \
                 contextlib.redirect_stdout(out):
                self.assertEqual(smoke_test.main(), 1)
            self.assertIn('[FAIL] CLI GeoJSON:', out.getvalue())
            self.assertIn('synthetic traceback tail', out.getvalue())

    def test_live_ckan_smoke_fetches_detail_and_searches_twenty_rows(self):
        raw = fixture('data-govt-nz.json')
        records = [cli.normalise_ckan(r, 'data-govt-nz', cli.query_url('data-govt-nz'), STAMP)
                   for r in raw['result']['results']]
        # Put blank coverage first so the smoke detail parser must accept it.
        records = [records[2], *records[:2]]
        with patch.object(cli, 'catalogue_request', return_value=({'available': True, 'number_matched': 3}, records)) as search, \
             patch.object(cli, 'fetch_json', return_value=fixture('data-govt-nz-get.json')) as get:
            result = smoke_test.live('data-govt-nz', 'roads')
        search.assert_called_once_with('data-govt-nz', 'roads', None, 20)
        get.assert_called_once_with(cli.query_url('data-govt-nz', record_id=records[0]['id']))
        self.assertIn('[PASS] live data-govt-nz get:', result)
        for code in (4, 5):
            with patch.object(cli, 'catalogue_request', return_value=({'available': True, 'number_matched': 3}, records)), \
                 patch.object(cli, 'fetch_json', side_effect=cli.SourceError('network error', code)):
                result = smoke_test.live('data-govt-nz', 'roads')
            self.assertIn('[PASS] live data-govt-nz search:', result)
            self.assertIn('[SKIP] data-govt-nz get:', result)

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
