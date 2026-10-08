#!/usr/bin/env python3
"""Deterministic repository and directory parser contracts using synthetic source structures."""
import argparse
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT.parents[1] / 'lib'))
import cli  # noqa: E402
from contract_test import audit_skill  # noqa: E402

FIXTURES = ROOT / 'tests' / 'fixtures'
STAMP = '2026-10-08T00:00:00Z'


def fixture(name):
    return json.loads((FIXTURES / (name + '.json')).read_text())


class Parsers(unittest.TestCase):
    def assert_record(self, row):
        self.assertEqual(row['retrieved_at'], STAMP)
        for key in ('name', 'address', 'lon', 'lat', 'materials', 'hours', 'source', 'provenance'):
            self.assertIn(key, row)
        for key in ('source_url', 'publisher', 'retrieved_at'):
            self.assertIn(key, row)
            self.assertEqual(row[key], row['provenance'][key])

    def test_material_join_uses_maps_not_shop_categories(self):
        rows = cli.parse_recyclemap(fixture('recyclemap-markers'), fixture('recyclemap-maps'), fixture('recyclemap-categories'), STAMP)
        self.assertEqual(rows[1]['materials'], ['Batteries'])
        self.assertEqual(rows[1]['name'], 'Example Household Collection')
        self.assertIn('Free to drop off', rows[1]['categories'])
        self.assertNotIn('Free to drop off', rows[1]['materials'])
        self.assertIn('Monday', rows[1]['hours'])
        self.assertTrue(cli.material_matches(rows[1], 'battery'))
        for row in rows:
            self.assert_record(row)
        damaged = fixture('recyclemap-markers')
        damaged[0]['map_id'] = 'unpublished'
        with self.assertRaises(cli.SourceError):
            cli.parse_recyclemap(damaged, fixture('recyclemap-maps'), fixture('recyclemap-categories'), STAMP)

    def test_kml_keeps_acceptance_conditions_and_lon_lat(self):
        rows = cli.parse_kml((FIXTURES / 'wasteminz.kml').read_text(), STAMP)
        self.assertEqual(rows[0]['name'], 'Example Battery Recovery Park')
        self.assertAlmostEqual(rows[0]['lon'], 171.245)
        self.assertAlmostEqual(rows[0]['lat'], -44.415)
        self.assertIn('damaged batteries', rows[0]['details'])
        self.assertIsNone(rows[0]['address'])
        self.assert_record(rows[0])
        with self.assertRaises(cli.SourceError):
            cli.parse_kml('<kml/>', STAMP)

    def test_branz_material_flags_and_truncation(self):
        latest = cli.branz_latest(fixture('branz-metadata'))
        self.assertEqual(latest, '2026-01-01T00:00:00.123Z')
        rows = cli.parse_branz(fixture('branz'), STAMP, latest)
        self.assertEqual(len(rows), 2)
        self.assertFalse(any(r.get('status') == 'Planned' for r in rows))
        self.assertEqual(rows[0]['name'], 'Example Concrete Recovery')
        self.assertIn('Concrete', rows[0]['materials'])
        self.assertNotIn('Glass', rows[0]['materials'])
        self.assertAlmostEqual(rows[0]['lon'], 174.76)
        self.assertIn('latest_data', rows[0]['provenance'])
        status = {'source': 'branz', 'status': 'ok', **rows[0]['provenance']}
        output = cli.envelope(rows, argparse.Namespace(command='search'), [status])
        self.assertEqual(output['meta']['latest_data'], rows[0]['latest_data'])
        self.assertEqual(output['meta']['publisher'], 'BRANZ')
        self.assert_record(rows[0])
        damaged = fixture('branz')
        damaged['exceededTransferLimit'] = True
        with self.assertRaises(cli.SourceError):
            cli.parse_branz(damaged, STAMP)

    def test_ecycle_hours(self):
        row = cli.parse_ecycle(fixture('ecycle'), STAMP)[0]
        self.assertEqual(row['name'], 'Example Electronic Recovery Hub')
        self.assertIn('Tuesday Closed', row['hours'])
        self.assertIn('Polystyrene', row['materials'])
        self.assert_record(row)

    def test_agrecovery_schemes_and_inactive(self):
        data = fixture('agrecovery')
        rows = cli.parse_agrecovery(data, STAMP)
        self.assertEqual(rows[0]['name'], 'Example Agricultural Collection')
        self.assertEqual(rows[0]['materials'], ['small-bags'])
        self.assertIn('sat: closed', rows[0]['hours'])
        self.assert_record(rows[0])
        data[0]['acf']['ag_site_active'] = False
        self.assertEqual(len(cli.parse_agrecovery(data, STAMP)), len(rows) - 1)

    def test_beautification_categories_and_unlabelled_drafts(self):
        rows = cli.parse_beautification(fixture('beautification'), STAMP)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]['name'], 'Example Community Recycling Centre')
        self.assertIn('Household batteries', rows[0]['materials'])
        self.assertIn('Sample Road', rows[0]['address'])
        self.assertIn('Wednesday', rows[0]['hours'])
        self.assert_record(rows[0])

    def test_repair_address_schedule_without_head_office_coords(self):
        row = cli.parse_repair((FIXTURES / 'repair.html').read_text(), cli.SOURCES['repair']['url'], STAMP)
        self.assertEqual(row['name'], 'Example Library Repair Café')
        self.assertIn('110 Sample Road', row['address'])
        self.assertIn('third Saturday', row['hours'])
        self.assertIsNone(row['lon'])
        self.assertIsNone(row['lat'])
        self.assert_record(row)

    def test_tyrewise_pagination_and_null_coordinates(self):
        rows, nxt = cli.parse_tyrewise((FIXTURES / 'tyrewise.html').read_text(), cli.SOURCES['tyrewise']['url'], STAMP)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]['name'], 'Example Tyre Collection 1-1')
        self.assertTrue(all(r['region'] == 'Auckland' for r in rows))
        self.assertIsNone(rows[0]['address'])
        self.assertIsNone(rows[0]['lon'])
        self.assertTrue(nxt.endswith('/page/2/'))
        self.assert_record(rows[0])
        last_rows, nxt = cli.parse_tyrewise((FIXTURES / 'tyrewise-last.html').read_text(), cli.SOURCES['tyrewise']['url'], STAMP)
        self.assertEqual(len(last_rows), 3)
        self.assertIsNone(nxt)

    def test_council_is_deterministically_unsupported(self):
        with patch.object(cli, 'get') as fetch, redirect_stdout(io.StringIO()) as out:
            self.assertEqual(cli.main(['item', '541', '--json']), 7)
        fetch.assert_not_called()
        self.assertNotIn('www.aucklandcouncil.govt.nz', cli.FETCH_HOSTS)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload['error']['type'], 'unsupported_operation')
        self.assertEqual(payload['results'], [])
        self.assertEqual(payload['meta']['source_url'], cli.COUNCIL)
        self.assertNotIn('retry_after', payload['error'])

    def test_spatial_filters_and_geojson(self):
        rows = cli.parse_kml((FIXTURES / 'wasteminz.kml').read_text(), STAMP)
        origin = [rows[0]['lon'], rows[0]['lat']]
        filtered = cli.spatial_filter(rows, [171.24, -44.42, 171.25, -44.41], origin, 0.001)
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]['distance_km'], 0)
        args = argparse.Namespace(command='find', format='geojson')
        geo = cli.envelope(filtered, args)
        self.assertEqual(geo['type'], 'FeatureCollection')
        self.assertIn('meta', geo)
        self.assertEqual(geo['features'][0]['geometry']['coordinates'], origin)
        self.assertEqual(geo['features'][0]['properties']['publisher'], 'WasteMINZ')
        for invalid in ('nan,-36', '181,-36', '174,-91', '174,-36,1'):
            with self.assertRaises(argparse.ArgumentTypeError):
                cli.coordinates(invalid)
        for invalid in ('175,-37,174,-36', '174,-37,174,-36', '174,-37,175,-37'):
            with self.assertRaises(argparse.ArgumentTypeError):
                cli.coordinates(invalid, 4)

    def test_partial_and_all_failed_sources(self):
        rows = cli.parse_ecycle(fixture('ecycle'), STAMP)
        args = argparse.Namespace(source=['ecycle', 'council'], refresh=True)
        def load(source, refresh):
            if source == 'council':
                raise cli.SourceError('blocked', 4)
            return rows, False
        with patch.object(cli, 'load', side_effect=load):
            actual, statuses = cli.combined(args)
        self.assertEqual(actual, rows)
        self.assertEqual(statuses[1]['code'], 4)
        with patch.object(cli, 'load', side_effect=cli.SourceError('blocked', 4)):
            with self.assertRaises(cli.SourceError):
                cli.combined(args)

    def test_cache_preserves_retrieval_time(self):
        rows = cli.parse_ecycle(fixture('ecycle'), STAMP)
        with tempfile.TemporaryDirectory(dir=ROOT / 'tests') as temp, patch.object(cli, 'CACHE', Path(temp)), patch.object(cli, 'load_uncached', return_value=rows) as fetch:
            first, cached = cli.load('ecycle')
            second, cached_again = cli.load('ecycle')
            self.assertFalse(cached)
            self.assertTrue(cached_again)
            self.assertEqual(second[0]['retrieved_at'], STAMP)
            self.assertEqual(fetch.call_count, 1)
            cli.load('ecycle', refresh=True)
            self.assertEqual(fetch.call_count, 2)
            self.assertEqual(first, second)
            saved = json.loads((Path(temp) / 'ecycle.json').read_text())
            saved['version'] = 1
            (Path(temp) / 'ecycle.json').write_text(json.dumps(saved))
            cli.load('ecycle')
            self.assertEqual(fetch.call_count, 3)

    def test_rate_limit_preserves_retry_after(self):
        # Use a mock exception instance so the test does not depend on helper internals.
        error = cli.nzfetch.RateLimited('rate limited', retry_after='120')
        with patch.object(cli.nzfetch, 'fetch_json', side_effect=error):
            with self.assertRaises(cli.SourceError) as caught:
                cli.get(cli.SOURCES['ecycle']['url'], True)
        self.assertEqual(caught.exception.retry_after, '120')
        self.assertEqual(caught.exception.code, 4)


    def invoke(self, argv, loads=None, error=None):
        # Resolve mocks by source; worker scheduling must not assign an outcome
        # to a different directory through a shared side-effect iterator.
        outcomes = dict(zip(cli.selected(cli.build_parser().parse_args(argv)), loads)) if loads else {}
        def load(source, refresh):
            outcome = error or outcomes[source]
            if isinstance(outcome, Exception):
                raise outcome
            return outcome
        with patch.object(cli, 'load', side_effect=load), redirect_stdout(io.StringIO()) as out:
            code = cli.main(argv)
        payload = json.loads(out.getvalue())
        self.assertIn('meta', payload)
        self.assertNotIn('licence', payload['meta'])
        for key in ('schema_version', 'ok', 'blocked', 'provenance', 'publisher', 'source_url'):
            self.assertNotIn(key, payload)
        # Direct CLI output must be wrapped, never mistaken for a runner envelope.
        sys.path.insert(0, str(ROOT.parents[1] / 'scripts'))
        import run_skill
        from result_contract import result_envelope, validate_result_envelope
        self.assertFalse(run_skill.looks_like_result_envelope(payload))
        self.assertFalse(code == 0 and run_skill.payload_advertises_failure(payload))
        wrapped = result_envelope(ok=code == 0, source_name=payload['meta']['publisher'],
                                  source_url=payload['meta']['source_url'], retrieved_at=payload['meta']['retrieved_at'],
                                  query={'argv': argv}, data=payload, blocked=code == 4,
                                  error=payload.get('error'))
        self.assertEqual(validate_result_envelope(wrapped), [])
        return code, payload

    def test_cli_success_find_search_materials_and_sources(self):
        rows = cli.parse_recyclemap(fixture('recyclemap-markers'), fixture('recyclemap-maps'), fixture('recyclemap-categories'), STAMP)
        for argv in (['find', '--material', 'battery', '--near=174.76,-36.85'],
                     ['search', 'Sampletown'], ['materials']):
            code, payload = self.invoke(argv + ['--source', 'recyclemap', '--json'], [(rows, True)])
            self.assertEqual(code, 0)
            self.assertGreater(len(payload['results']), 0)
            self.assertEqual(payload['meta']['retrieved_at'], STAMP)
        with patch.object(cli, 'load_uncached', return_value=rows):
            code, payload = self.invoke(['sources', '--source', 'recyclemap', '--json'])
        self.assertEqual(code, 0)
        self.assertEqual(payload['results'][0]['status'], 'ok')

    def test_cli_geojson_and_machine_errors(self):
        rows = cli.parse_ecycle(fixture('ecycle'), STAMP)
        argv = ['find', '--material', 'ewaste', '--near=174.76,-36.85', '--source', 'ecycle', '--format', 'geojson']
        code, payload = self.invoke(argv, [(rows, False)])
        self.assertEqual(code, 0)
        self.assertEqual(payload['type'], 'FeatureCollection')
        self.assertEqual(len(payload['features']), 1)
        self.assertNotIn('results', payload)
        code, payload = self.invoke(argv, error=cli.SourceError('not supported', 7))
        self.assertEqual(code, 7)
        self.assertEqual(payload['results'], [])
        self.assertEqual(payload['error']['type'], 'unsupported_operation')
        for tail in (['--limit', '-1'], ['--radius', 'nan'], ['--bbox=174,-37,174,-36']):
            code, payload = self.invoke(argv + tail)
            self.assertEqual(code, 2)
            self.assertEqual(payload['error']['type'], 'invalid_input')
            self.assertEqual(payload['meta']['source_url'], cli.PRIMARY_URL)
            self.assertEqual(payload['meta']['publisher'], 'Multiple NZ collection directories')
        for argv in (['search', '', '--json'], ['find', '--material', '', '--near=174,-36', '--json'],
                     ['find', '--near=bad', '--material', 'glass', '--json'], ['unknown', '--json']):
            code, payload = self.invoke(argv)
            self.assertEqual(code, 2)
            self.assertEqual(payload['meta']['source_url'], cli.PRIMARY_URL)
            self.assertEqual(payload['meta']['publisher'], 'Multiple NZ collection directories')

    def test_cli_partial_all_failed_and_filtered_empty_failure(self):
        rows = cli.parse_ecycle(fixture('ecycle'), STAMP)
        argv = ['find', '--material', 'ewaste', '--near=174.76,-36.85', '--source', 'ecycle', '--source', 'recyclemap', '--json']
        code, payload = self.invoke(argv, [(rows, True), cli.SourceError('blocked upstream', 4)])
        self.assertEqual(code, 0)
        self.assertEqual(payload['result_status'], 'partial')
        self.assertTrue(any('recyclemap unavailable (code 4)' in w for w in payload['warnings']))
        self.assertEqual(payload['meta']['retrieved_at'], STAMP)
        self.assertEqual(payload['meta']['source_url'], 'https://www.recyclemap.co.nz/')
        self.assertEqual(payload['meta']['publisher'], 'Multiple NZ collection directories')
        code, payload = self.invoke(argv, error=cli.SourceError('blocked upstream', 4))
        self.assertEqual(code, 4)
        self.assertEqual(payload['error']['type'], 'blocked')
        self.assertEqual(payload['results'], [])
        empty_argv = [a if a != 'ewaste' else 'battery' for a in argv]
        code, payload = self.invoke(empty_argv, [(rows, False), cli.SourceError('blocked upstream', 4)])
        self.assertEqual(code, 4)
        self.assertEqual(payload['results'], [])
        no_materials = [{**rows[0], 'materials': []}]
        code, payload = self.invoke(['materials', '--source', 'ecycle', '--source', 'recyclemap', '--json'], [(no_materials, False), cli.SourceError('blocked upstream', 4)])
        self.assertEqual(code, 4)
        code, payload = self.invoke(argv, [(rows, False), cli.SourceError('rate limited', 4, '120')])
        self.assertEqual(code, 0)
        self.assertEqual(payload['source_status'][1]['retry_after'], '120')

    def test_battery_alias_does_not_include_car_batteries(self):
        car = {'materials': ['Car Batteries']}
        self.assertFalse(cli.material_matches(car, 'battery'))
        self.assertFalse(cli.material_matches(car, 'batteries'))
        self.assertTrue(cli.material_matches(car, 'car battery'))
        self.assertTrue(cli.material_matches({'materials': ['Household batteries']}, 'battery'))
        self.assertTrue(cli.material_matches({'materials': ['Batteries']}, 'battery'))

    def test_clothing_alias_includes_both_acceptance_labels(self):
        for label in ('Clothing (resalable)', 'Clothing (not resalable)', 'Op Shops', 'Textiles'):
            self.assertTrue(cli.material_matches({'materials': [label]}, 'clothing'), label)
        self.assertFalse(cli.material_matches({'materials': ['Car Batteries']}, 'battery'))

    def test_combined_concurrent_sources_preserve_order_and_provenance(self):
        sources = ['repair', 'branz', 'recyclemap', 'wasteminz', 'ecycle']
        barrier = threading.Barrier(4)
        lock = threading.Lock()
        active = peak = 0
        records = {s: [cli.record(s, 'Example ' + s, materials=['Repair café'], retrieved=STAMP,
                                 url=cli.SOURCES[s]['url'] + '/synthetic-detail')] for s in sources}
        def load(source, refresh):
            nonlocal active, peak
            self.assertTrue(refresh)
            with lock:
                active += 1
                peak = max(peak, active)
            try:
                if source in sources[:4]:
                    barrier.wait(timeout=5)
                if source == 'branz':
                    raise cli.SourceError('synthetic schema change', 6)
                return records[source], False
            finally:
                with lock:
                    active -= 1
        with patch.object(cli, 'load', side_effect=load):
            rows, health = cli.combined(argparse.Namespace(source=sources, refresh=True))
        self.assertEqual(peak, 4)
        self.assertEqual([s['source'] for s in health], sources)
        self.assertEqual([r['source'] for r in rows], [s for s in sources if s != 'branz'])
        self.assertEqual(health[1]['code'], 6)
        self.assertEqual(health[0]['source_url'], cli.SOURCES['repair']['url'])
        self.assertEqual(rows[0]['source_url'], records['repair'][0]['source_url'])
        self.assertEqual(health[0]['retrieved_at'], STAMP)

    def test_sources_skipped_entries_do_not_make_healthy_status_partial(self):
        rows = [cli.record('repair', 'Example café', retrieved=STAMP,
                           url='https://www.repairnetworkaotearoa.org.nz/localrepaircafes/example')]
        def load(source, probe):
            self.assertTrue(probe)
            if source != 'repair':
                raise cli.SourceError('synthetic unsupported source', 7)
            return rows
        with patch.object(cli, 'load_uncached', side_effect=load) as fetch:
            code, payload = self.invoke(['sources', '--source', 'repair', '--source', 'council', '--source', 'techcollect', '--source', 'repair', '--json'])
        self.assertEqual(fetch.call_count, 3)
        self.assertEqual(code, 0)
        self.assertEqual(payload['result_status'], 'ok')
        self.assertEqual([s['status'] for s in payload['source_status']], ['ok', 'skipped', 'skipped'])
        self.assertEqual(payload['source_status'][0]['source_url'], cli.SOURCES['repair']['url'])
        with patch.object(cli, 'load_uncached', side_effect=cli.SourceError('synthetic outage', 5)):
            code, payload = self.invoke(['sources', '--source', 'repair', '--json'])
        self.assertEqual(payload['result_status'], 'partial')

    def test_unlocated_warning_only_for_spatial_queries(self):
        rows = [cli.record('repair', 'Example café', materials=['Repair café'], retrieved=STAMP,
                           url='https://www.repairnetworkaotearoa.org.nz/localrepaircafes/example')]
        for argv in (['search', 'Example'], ['materials'], ['search', 'Example', '--bbox=174,-37,175,-36']):
            code, payload = self.invoke(argv + ['--source', 'repair', '--json'], [(rows, True)])
            self.assertEqual(code, 0)
            self.assertEqual(payload['meta']['source_url'], cli.SOURCES['repair']['url'])
            self.assertEqual(payload['meta']['retrieved_at'], STAMP)
            excluded = any('excluded from spatial filters' in w for w in payload['warnings'])
            self.assertEqual(excluded, '--bbox=174,-37,175,-36' in argv)

    def test_unsupported_data_selection_alone_and_combined(self):
        rows = cli.parse_ecycle(fixture('ecycle'), STAMP)
        for source in ('council', 'techcollect'):
            argv = ['materials', '--source', source, '--json']
            code, payload = self.invoke(argv, error=cli.SourceError('synthetic unsupported selection', 7))
            self.assertEqual(code, 7)
            self.assertEqual(payload['error']['type'], 'unsupported_operation')
            code, payload = self.invoke(argv + ['--source', 'ecycle'],
                                        [cli.SourceError('synthetic unsupported selection', 7), (rows, True)])
            self.assertEqual(code, 0)
            self.assertEqual(payload['result_status'], 'partial')
            self.assertEqual(payload['source_status'][0]['code'], 7)

    def test_hours_inline_and_unknown(self):
        self.assertEqual(cli.hours_from('<p>Hours: Monday - Friday 0800-1600</p><p>Restrictions: public access</p>'), 'Monday - Friday 0800-1600')
        self.assertIsNone(cli.hours_from('<p>Opening hours unknown.</p><p>Website unknown.</p>'))
        self.assertEqual(cli.hours_from('<p>Opening hours: Saturday 9am to 12pm</p><p>Closed on holidays.</p>'), 'Saturday 9am to 12pm Closed on holidays.')

    def test_schema_drift_remains_a_source_failure(self):
        malformed = '<kml xmlns="http://www.opengis.net/kml/2.2"><Placemark><Point><coordinates>174.7</coordinates></Point></Placemark></kml>'
        with self.assertRaises(cli.SourceError):
            cli.parse_kml(malformed, STAMP)
        self.assertEqual(cli.parse_agrecovery([{'id': 1, 'acf': False}], STAMP), [])
        rows = cli.parse_ecycle(fixture('ecycle'), STAMP)
        argv = ['search', 'Example', '--source', 'ecycle', '--source', 'agrecovery', '--json']
        for error in (IndexError('bad coordinate'), AttributeError('bad acf')):
            code, payload = self.invoke(argv, [(rows, False), error])
            self.assertEqual(code, 0)
            self.assertEqual(payload['result_status'], 'partial')
            self.assertEqual(payload['source_status'][1]['code'], 6)
            code, payload = self.invoke(argv, error=error)
            self.assertEqual(code, 6)

    def test_spatial_defaults_skip_unlocated_sources(self):
        rows = cli.parse_ecycle(fixture('ecycle'), STAMP)
        for argv in (['find', '--material', 'ewaste', '--near=174.76,-36.85', '--json'],
                     ['search', 'Example', '--bbox=174,-37,175,-36', '--json']):
            with patch.object(cli, 'load', return_value=(rows, True)) as load, redirect_stdout(io.StringIO()) as out:
                self.assertEqual(cli.main(argv), 0)
            called = [c.args[0] for c in load.call_args_list]
            self.assertNotIn('repair', called)
            self.assertNotIn('tyrewise', called)
            self.assertTrue(any('use search <town>' in w for w in json.loads(out.getvalue())['warnings']))
        with patch.object(cli, 'load', return_value=(rows, True)) as load, redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(['find', '--material', 'ewaste', '--near=174.76,-36.85', '--source', 'repair', '--json']), 0)
        load.assert_called_once_with('repair', False)

    def test_materials_groups_do_not_misattribute_multiple_sources(self):
        rows = [cli.record('recyclemap', 'Example One', materials=['Batteries'], retrieved=STAMP)]
        other = [cli.record('wasteminz', 'Example Two', materials=['Batteries'], retrieved='2026-10-07T00:00:00Z')]
        code, payload = self.invoke(['materials', '--source', 'recyclemap', '--source', 'wasteminz', '--json'], [(rows, True), (other, True)])
        self.assertEqual(code, 0)
        self.assertEqual(payload['meta']['retrieved_at'], '2026-10-07T00:00:00Z')
        group = payload['results'][0]
        self.assertEqual(len(group['provenance']), 2)
        self.assertNotIn('publisher', group)
        self.assertNotIn('source_url', group)

    def test_branz_service_warning_and_human_fields(self):
        rows = cli.parse_branz(fixture('branz'), STAMP)
        code, payload = self.invoke(['search', 'Example', '--source', 'branz', '--json'], [(rows, False)])
        self.assertEqual(code, 0)
        self.assertTrue(any('service contractors' in w for w in payload['warnings']))
        with patch.object(cli, 'load', return_value=(rows, True)), redirect_stdout(io.StringIO()) as out:
            self.assertEqual(cli.main(['search', 'Example', '--source', 'branz']), 0)
        self.assertIn('type: Service; status: unknown', out.getvalue())

    def test_agrecovery_exact_multiple_and_crawl_delay(self):
        from urllib.error import HTTPError
        http = HTTPError(cli.SOURCES['agrecovery']['url'], 400, 'Bad Request', {}, io.BytesIO(b'{"code":"rest_post_invalid_page_number"}'))
        fetch = cli.nzfetch.FetchError('HTTP 400')
        fetch.__cause__ = http
        error = cli.SourceError('network error: HTTP 400', 5)
        error.__cause__ = fetch
        data = [fixture('agrecovery')[0]] * 100
        with patch.object(cli, 'get', side_effect=[data, error]), patch.object(cli.time, 'sleep') as sleep:
            rows = cli.load_uncached('agrecovery')
        self.assertEqual(len(rows), 100)
        sleep.assert_called_once_with(10)
        with patch.object(cli, 'get', side_effect=[data, cli.SourceError('network error: HTTP 400', 5)]), patch.object(cli.time, 'sleep'):
            with self.assertRaises(cli.SourceError):
                cli.load_uncached('agrecovery')

    def test_repair_page_failure_preserves_source_with_warning(self):
        urls = ['https://www.repairnetworkaotearoa.org.nz/localrepaircafes/synthetic-' + str(n) for n in range(3)]
        text = (FIXTURES / 'repair.html').read_text()
        def get(url):
            if url == cli.SOURCES['repair']['url']:
                return '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + ''.join('<url><loc>' + u + '</loc></url>' for u in urls) + '</urlset>'
            if url == urls[0]:
                raise cli.SourceError('page changed')
            return text
        with patch.object(cli, 'get', side_effect=get), patch.object(cli.time, 'sleep'):
            rows = cli.load_uncached('repair')
        self.assertEqual(len(rows), 2)
        self.assertIn(urls[0], rows[0]['source_warnings'][0])
        with patch.object(cli, 'get', side_effect=lambda url: get(url) if url == cli.SOURCES['repair']['url'] else '<html/>'), patch.object(cli.time, 'sleep'):
            with self.assertRaises(cli.SourceError):
                cli.load_uncached('repair')

    def test_tyrewise_legacy_card_and_pagination_guard(self):
        rows, nxt = cli.parse_tyrewise((FIXTURES / 'tyrewise-loop.html').read_text(), cli.SOURCES['tyrewise']['url'], STAMP)
        self.assertEqual(rows[0]['name'], 'Example Legacy Tyre Collection')
        self.assertIsNone(nxt)
        hostile = (FIXTURES / 'tyrewise.html').read_text().replace(cli.SOURCES['tyrewise']['url'] + 'page/2/', 'https://example.invalid/page/2/')
        with patch.object(cli, 'get', return_value=hostile) as get:
            with self.assertRaises(cli.SourceError):
                cli.load_uncached('tyrewise')
        get.assert_called_once()


def main():
    audit = audit_skill(ROOT)
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Parsers)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if result.wasSuccessful():
        print(f'[PASS] fixture {result.testsRun} parser, provenance, spatial and failure tests')
    return 0 if audit['ok'] and result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
