#!/usr/bin/env python3
"""Deterministic catalogue, parser, routing, network and repository contracts."""
from __future__ import annotations
import argparse
import io
import json
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import urllib.parse
from pathlib import Path
from unittest.mock import MagicMock, patch

import build_catalogue
import cli

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'tests/fixtures'
PROVENANCE = {'source_url', 'publisher', 'licence', 'retrieved_at', 'latest_data'}

def fixture_checks():
    rows = json.loads((FIXTURES / 'source-sample.json').read_text())
    data = build_catalogue.build(rows, 'source-sample.json', 'fixture')
    records = data['records']
    assert len(records) == 8
    assert data['metadata']['excluded'] == {'duplicate_of': 1, 'broken': 1}
    assert len({r['id'] for r in records}) == len(records)
    assert all('Evidence' not in r and 'Agent check notes' not in r for r in records)
    assert any(r['not_data'] and r['agent_check'] == 'Not data' for r in records)
    assert next(r for r in records if r['id'] == 'C0001')['problem_tags'] == ['T1', 'T3']
    print('[PASS] fixture export deduplication, exclusion, flags and problem ticks')
    live = json.loads((FIXTURES / 'live-samples.json').read_text())
    assert all(PROVENANCE <= r.keys() and r['http_status'] == 200 for r in live)
    count = next(r for r in live if r['id'] == 'C0002')
    assert count['body']['count'] == 14108
    stac = next(r for r in live if r['id'] == 'C0064')
    assert stac['body']['type'] == 'Collection' and stac['body']['license'] == 'CC-BY-4.0'
    assert len(stac['body']['extent']['spatial']['bbox'][0]) == 4
    for fixture in live:
        assert cli.inspect_sample(json.dumps(fixture['body']).encode(), fixture['content_type']) == ('reachable', None)
    print('[PASS] fixture real ArcGIS count and licensed STAC response samples')
    return data

class CatalogueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = fixture_checks()
        cls.catalogue = cli.load_catalogue()
        cls.rows = {r['id']: r for r in cls.catalogue['records']}
        cls.skill_map = json.loads((ROOT / 'references/skill-map.json').read_text())

    def test_snapshot_counts_and_no_long_notes(self):
        self.assertEqual(len(self.rows), 3168)
        self.assertEqual(self.catalogue['metadata']['retained_rows'], len(self.rows))
        self.assertTrue(all(r['agent_check'] != 'Broken' for r in self.rows.values()))
        self.assertEqual(sum(r['not_data'] for r in self.rows.values()), 278)
        self.assertEqual(self.catalogue['metadata']['input_rows'], 3238)
        self.assertTrue(all(set(r) == set(build_catalogue.FIELDS) | {'problem_tags', 'not_data', 'credential_redacted'} for r in self.rows.values()))
        for row in self.rows.values():
            for field in ('url', 'direct_endpoint'):
                self.assertEqual(build_catalogue.redact_url(row[field]), (row[field], False))

    def test_reproducible_build_and_validation(self):
        with tempfile.TemporaryDirectory(dir=FIXTURES) as temp:
            a, b = Path(temp) / 'a.gz', Path(temp) / 'b.gz'
            build_catalogue.write_catalogue(self.data, a)
            build_catalogue.write_catalogue(self.data, b)
            self.assertEqual(a.read_bytes(), b.read_bytes())
            self.assertEqual(cli.load_catalogue(a), self.data)
        row = json.loads((FIXTURES / 'source-sample.json').read_text())[0]
        for mutation in (dict(row, **{'Score (0-5)': float('nan')}), dict(row, Grade='Z')):
            with self.assertRaises(ValueError):
                build_catalogue.build([mutation], 'bad.json', 'fixture')
        with self.assertRaises(ValueError):
            build_catalogue.build([row, row], 'duplicate.json', 'fixture')
        missing = dict(row)
        del missing['URL']
        with self.assertRaises(ValueError):
            build_catalogue.build([missing], 'missing.json', 'fixture')
        redacted, changed = build_catalogue.redact_url('https://example.org/api?token=synthetic-fixture&limit=1')
        self.assertTrue(changed)
        self.assertNotIn('synthetic-fixture', redacted)
        self.assertIn('{credential}', redacted)

    def test_search_ranking_case_and_all_terms(self):
        results = cli.ranked_search(list(self.rows.values()), 'Roadworks')
        self.assertTrue(results)
        self.assertEqual([r['id'] for r in results], [r['id'] for r in cli.ranked_search(list(self.rows.values()), 'ROADWORKS')])
        self.assertTrue(all(results[i]['relevance'] >= results[i+1]['relevance'] for i in range(len(results)-1)))
        self.assertIn('C0001', [r['id'] for r in cli.ranked_search(list(self.rows.values()), 'AT Roadworks')])
        self.assertEqual(cli.ranked_search(list(self.rows.values()), 'roadworks nonexistentword123'), [])
        with self.assertRaises(cli.CatalogueError):
            cli.ranked_search(list(self.rows.values()), '!!!')

    def test_filters_conjunction_and_planned_routes(self):
        args = cli.parser().parse_args(['filter', '--problem', 't3', '--grade', 'A', '--auckland', '--category', 'traffic', '--scope', 'Auckland', '--access', 'open', '--type', 'gis', '--owner', 'auckland transport'])
        selected = cli.filter_records(list(self.rows.values()), args)
        self.assertIn('C0001', [r['id'] for r in selected])
        self.assertTrue(all('T3' in r['problem_tags'] and r['grade'] == 'A' and r['covers_auckland'] == 'yes' for r in selected))
        def route(id, skill, status, auth):
            result = next(r for r in cli.mapped_skills(self.rows[id], self.skill_map) if r['skill'] == skill)
            self.assertEqual((result['status'], result['auth']), (status, auth))
        route('C0024', 'nzta-highway-info', 'existing', 'none')
        route('C0029', 'at-transport', 'existing', 'api-key')
        route('S0351', 'charities-services-nz', 'existing', 'none')
        route('S1589', 'nz-road-closures', 'existing', 'none')
        route('S1186', 'statsnz-classifications-nz', 'existing', 'none')
        for id, skill in [('C0064','nz-stac'),('C0028','gtfs-nz'),('S1213','nz-ogc-records'),('C0043','akl-rainfall'),('C0106','nz-recycling-locator')]:
            route(id, skill, 'planned', 'none')
        for id in ('C0001', 'C0012', 'S0131', 'S0618', 'S1098', 'S2932', 'S2686', 'S1097'):
            route(id, 'nz-arcgis', 'existing', 'none')
        for id in ('S0312', 'S0754', 'S0790', 'S0791', 'S0792', 'C0073'):
            routed = next(r for r in cli.mapped_skills(self.rows[id], self.skill_map) if r['skill'] == 'nz-arcgis')
            self.assertEqual(routed['relationship'], 'related')
            self.assertNotIn('need a numeric', routed['note'])
        self.assertIn('numeric layer', next(r for r in cli.mapped_skills(self.rows['C0073'], self.skill_map) if r['skill'] == 'nz-arcgis')['note'])
        self.assertEqual(next(r for r in cli.mapped_skills(self.rows['C0061'], self.skill_map) if r['skill'] == 'nz-arcgis')['relationship'], 'exact')
        for id in ('S2687', 'C0070', 'C0102', 'C0072', 'S0122', 'S0444', 'C0069', 'S0789'):
            # Unlisted Flooded service, refused tiled-image host, unlisted organisation,
            # SceneServer, VectorTileServer, and MapServers whose describe exits 6.
            self.assertNotIn('nz-arcgis', [s['skill'] for s in cli.mapped_skills(self.rows[id], self.skill_map)])
        for id in ('C0002', 'C0018', 'C0019', 'C0032', 'C0033', 'S0207', 'S0182'):
            route(id, 'nz-traffic-counts', 'existing', 'none')
        overseas = dict(self.rows['C0001'], scope='Overseas')
        self.assertNotIn('nz-arcgis', [s['skill'] for s in cli.mapped_skills(overseas, self.skill_map)])
        other = dict(self.rows['C0064'], url='https://zenodo.org/records/123', direct_endpoint=None, name='Unrelated research')
        self.assertEqual(cli.mapped_skills(other, self.skill_map), [])
        cross_url = dict(self.rows['C0024'], direct_endpoint='https://trafficnz.info/some-other-path', url='https://github.com/service/traffic/rest/4/events')
        self.assertEqual(cli.mapped_skills(cross_url, self.skill_map), [])

    def test_arcgis_routes_stay_within_runtime_allowlist(self):
        orgs_path = ROOT.parent / 'nz-arcgis/references/orgs.json'
        self.assertTrue(orgs_path.is_file(), 'nz-arcgis must be present in this repository')
        orgs = json.loads(orgs_path.read_text())
        roots = {(urllib.parse.urlsplit(root).hostname, urllib.parse.urlsplit(root).path + '/'): (code, org)
                 for code, org in orgs.items() for root in org['roots']}
        routed = set()
        server_types = {'FeatureServer', 'MapServer', 'ImageServer', 'SceneServer', 'VectorTileServer'}
        for rule in (r for r in self.skill_map['rules'] if r['skill'] == 'nz-arcgis'):
            self.assertEqual(rule['status'], 'existing')
            hosts, paths = rule['match']['hosts'], rule['match']['url_contains']
            self.assertEqual(len(hosts), 1)
            self.assertTrue(paths)
            matched = set()
            for path in paths:
                root = next((key for key in roots if key[0] == hosts[0] and path.casefold().startswith(key[1].casefold())), None)
                self.assertIsNotNone(root, (hosts[0], path))
                matched.add(root)
                kind = path.rstrip('/').rsplit('/', 1)[-1]
                if kind in server_types:
                    self.assertIn(kind, {'FeatureServer', 'MapServer', 'ImageServer'})
            self.assertEqual(len(matched), 1)
            root = next(iter(matched))
            code, org = roots[root]
            self.assertIn(f'`{code}`', rule['note'])
            for service in org.get('service_allowlist') or []:
                self.assertTrue(any(f'/{service}/'.casefold() in path.casefold() for path in paths), service)
            routed.add(root)
        self.assertEqual(set(roots) - routed, {('tiledimageservices1.arcgis.com', '/n4yPwebTjJCmXB6W/arcgis/rest/services/')})
        self.assertEqual(len(self.skill_map['rules']), 83)

    def test_arcgis_routes_match_allowlisted_operations(self):
        import importlib.util
        arc_dir = ROOT.parent / 'nz-arcgis/scripts'
        self.assertTrue((arc_dir / 'cli.py').is_file(), 'nz-arcgis CLI must be present in this repository')
        sys.path.insert(0, str(arc_dir))
        spec = importlib.util.spec_from_file_location('nz_arcgis_cli', arc_dir / 'cli.py')
        arc = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(arc)
        operational_query = {'f', 'where', 'outFields', 'returnGeometry', 'returnCountOnly', 'resultOffset', 'resultRecordCount', 'maxAllowableOffset', 'outSR'}
        identity_query = {'id', 'itemid', 'item', 'token', 'key', 'access_token', 'apikey', 'layerid'}
        seen_query = set()
        needs_query_strip = 0

        def invocation_url(url):
            parsed = urllib.parse.urlsplit(url.strip())
            path = parsed.path
            if path.rstrip('/').endswith('/query'):
                path = path.rstrip('/')[:-len('/query')]
            if '/tile/' in path:
                path = path.split('/tile/')[0]
            return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, path, '', ''))

        def accepts(url):
            found = {}
            for kind in ('layer', 'service'):
                try:
                    found[kind] = arc.validate_url(url, kind)
                except arc.ClientError:
                    pass
            return found

        for row in self.rows.values():
            skills = cli.mapped_skills(row, self.skill_map)
            hit = next((item for item in skills if item['skill'] == 'nz-arcgis'), None)
            if hit is None:
                continue
            matched = None
            for rule in self.skill_map['rules']:
                if rule.get('skill') != 'nz-arcgis' or rule.get('note') != hit.get('note'):
                    continue
                match = rule['match']
                for url in (row.get('direct_endpoint'), row.get('url')):
                    if not url:
                        continue
                    host = urllib.parse.urlsplit(url).hostname
                    if match.get('hosts') and host not in match['hosts']:
                        continue
                    if match.get('url_contains') and not any(part.casefold() in url.casefold() for part in match['url_contains']):
                        continue
                    matched = url
                    break
                if matched:
                    break
            self.assertIsNotNone(matched, row['id'])
            self.assertNotIn(';', matched, row['id'])
            if hit['relationship'] == 'exact':
                self.assertNotIn('/tile/', matched)
            parsed = urllib.parse.urlsplit(matched)
            keys = {key for key, _ in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)}
            seen_query.update(keys)
            self.assertFalse(keys & identity_query, row['id'])
            if parsed.query or parsed.path.rstrip('/').endswith('/query'):
                needs_query_strip += 1
            found = accepts(invocation_url(matched))
            self.assertTrue(found, row['id'])
            code = next(iter(found.values()))[0]
            self.assertIn(f'`{code}`', hit['note'])
            if row['id'] in {'S0312', 'S0754', 'S0790', 'S0791', 'S0792'}:
                self.assertEqual(set(found), {'service'})
                self.assertIn('not successful', hit['note'])
            if row['id'] == 'C0073':
                self.assertIn('service', found)
                self.assertNotIn('layer', found)
                self.assertIn('/tile/', matched)
        self.assertTrue(seen_query <= operational_query)
        self.assertEqual(needs_query_strip, 198)
        related = sorted(row['id'] for row in self.rows.values()
                         if any(item['skill'] == 'nz-arcgis' and item['relationship'] == 'related' for item in cli.mapped_skills(row, self.skill_map)))
        self.assertEqual(related, ['C0073', 'S0312', 'S0754', 'S0790', 'S0791', 'S0792'])
        routed_count = sum(any(item['skill'] == 'nz-arcgis' for item in cli.mapped_skills(row, self.skill_map)) for row in self.rows.values())
        self.assertEqual(routed_count, 226)
        precincts = 'https://tiles.arcgis.com/tiles/n4yPwebTjJCmXB6W/arcgis/rest/services/PC120Revised_PROD_Precincts/MapServer'
        base = self.rows['S0790']
        for url in (
            precincts.replace('PC120Revised_PROD_Precincts/MapServer', 'Other/SceneServer'),
            precincts.replace('PC120Revised_PROD_Precincts/MapServer', 'Other/VectorTileServer'),
            precincts.replace('PC120Revised_PROD_Precincts/MapServer', 'AucklandInfraredImagery2024/MapServer'),
            'https://services-ap1.arcgis.com/eqbFSejuTufXDr0E/arcgis/rest/services/Other_Project/FeatureServer/0',
        ):
            synthetic = dict(base, url=url, direct_endpoint=url)
            self.assertNotIn('nz-arcgis', [item['skill'] for item in cli.mapped_skills(synthetic, self.skill_map)])
        kept = dict(base, url=precincts + '/tile/{level}/{row}/{column}', direct_endpoint=None)
        self.assertEqual(next(item['relationship'] for item in cli.mapped_skills(kept, self.skill_map) if item['skill'] == 'nz-arcgis'), 'related')
        scene = precincts.replace('PC120Revised_PROD_Precincts/MapServer', 'Akl_CBD_to_Airport_3D_Mesh_Zone1B/SceneServer')
        with self.assertRaises(arc.ClientError) as refused:
            arc.validate_url(scene, 'service')
        self.assertEqual(refused.exception.code, 7)

    def test_json_commands_and_provenance(self):
        for args in (['search','roadworks'], ['filter','--problem','F1'], ['get','c0001'], ['stats'], ['top','--problem','F1','--n','10']):
            result = subprocess.run([sys.executable, str(ROOT/'scripts/cli.py'), *args, '--json'], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(result.stdout)
            self.assertTrue(data['ok'])
            self.assertTrue(PROVENANCE <= data.keys())
            self.assertTrue(data['retrieved_at'].endswith('Z'))
            for row in data['data'].get('records', []):
                self.assertTrue(PROVENANCE <= row.keys())
                self.assertIsInstance(row['fetch_skills'], list)
            if args[0] == 'top':
                self.assertEqual(data['data']['returned'], 10)
                self.assertTrue(all('F1' in r['problem_tags'] and not r['not_data'] for r in data['data']['records']))
            sys.path.insert(0, str(ROOT.parents[1] / 'lib'))
            from result_contract import validate_result_envelope
            self.assertEqual(validate_result_envelope(data), [])
        result = subprocess.run([sys.executable, str(ROOT/'scripts/cli.py'), 'get', 'unknown', '--json'], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertFalse(json.loads(result.stdout)['ok'])
        result = subprocess.run([sys.executable, str(ROOT/'scripts/cli.py'), 'top', '--problem', 'BAD', '--json'], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertTrue(PROVENANCE <= json.loads(result.stdout).keys())
        result = subprocess.run([sys.executable, str(ROOT.parents[1]/'scripts/run_skill.py'), 'nz-data-catalogue', 'get', 'C0001'], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)['data']['records'][0]['id'], 'C0001')

    def test_domains_and_template_private_rejection(self):
        sys.path.insert(0, str(ROOT.parents[1] / 'lib'))
        from skill_metadata import load_skill, split_csv
        self.assertEqual(set(split_csv(load_skill(ROOT).metadata['thecolab.allowed_domains'])), set(self.catalogue['metadata']['allowed_domains']))
        with self.assertRaises(cli.CatalogueError):
            cli.validated_url(self.rows['C0037']['direct_endpoint'], {'basemaps.linz.govt.nz'})
        with self.assertRaises(cli.CatalogueError):
            cli.validated_url('https://outside.example/api', {'trafficnz.info'})
        with patch.object(cli.socket, 'getaddrinfo', return_value=[(None,None,None,None,('127.0.0.1',443))]):
            with self.assertRaises(cli.CatalogueError):
                cli.validated_url('https://trafficnz.info/api', {'trafficnz.info'})
        with self.assertRaises(cli.CatalogueError):
            cli.CheckedRedirect({'trafficnz.info'}).redirect_request(None,None,302,'',{},'https://outside.example/api')

    def test_live_get_contract_and_common_failure_states(self):
        response = MagicMock()
        response.status = 200
        response.headers = {'Content-Type': 'application/json'}
        response.geturl.return_value = self.rows['C0024']['url']
        response.read.return_value = b'{"count": 1}'
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value = response
        with patch.object(cli, 'validated_url'), patch.object(cli.urllib.request, 'build_opener', return_value=opener):
            result, code = cli.check_endpoint(self.rows['C0024'], {'trafficnz.info'})
        self.assertEqual(code, 0)
        self.assertTrue(PROVENANCE <= result.keys())
        self.assertEqual(result['http_status'], 200)
        self.assertEqual(opener.open.call_args.kwargs['timeout'], 10)
        self.assertEqual(opener.open.call_args.args[0].get_method(), 'GET')
        response.read.assert_called_once_with(65536)
        error = urllib.error.HTTPError(self.rows['C0024']['url'], 429, 'Too many requests', {'Retry-After':'60'}, io.BytesIO())
        with patch.object(cli, 'validated_url'), patch.object(cli.urllib.request, 'build_opener', return_value=opener):
            opener.open.side_effect = error
            result, code = cli.check_endpoint(self.rows['C0024'], {'trafficnz.info'})
        self.assertEqual((code, result['status'], result['retry_after']), (4, 'blocked', '60'))
        self.assertEqual(cli.inspect_sample(b'{"error":{"code":400}}','application/json')[0], 'api_error')
        self.assertEqual(cli.inspect_sample(b'<title>Just a moment</title>','text/html')[0], 'blocked')

if __name__ == '__main__':
    outcome = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(CatalogueTests))
    if not outcome.wasSuccessful():
        raise SystemExit(1)
    sys.path.insert(0, str(ROOT.parents[1] / 'lib'))
    from contract_test import run_contract_test
    raise SystemExit(run_contract_test(ROOT))
