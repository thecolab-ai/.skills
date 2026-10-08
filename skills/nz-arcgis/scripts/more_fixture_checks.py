#!/usr/bin/env python3
"""Additional council/service contracts; all new fixture values are synthetic."""
import contextlib
import io
import json
from pathlib import Path
from unittest.mock import patch

import cli
from curate_more_layers import candidates

FIXTURES = Path(__file__).resolve().parents[1] / 'tests/fixtures'
CCC = cli.REGISTRY['ccc']['roots'][0] + '/OpenData/Structure/FeatureServer/2'
PC120 = cli.REGISTRY['akl']['roots'][-1] + '/PC120Revised_PROD_Precincts/MapServer'
FLOODED = cli.REGISTRY['flooded']['roots'][0] + '/flooded_nz_gdb_v2_202603181308/FeatureServer/0'


def read(name):
    return json.loads((FIXTURES / (name + '.json')).read_text())


def run():
    for org, path in [('dcc', '/Public/Search/FeatureServer/0'), ('hcc', '/RoadHierarchy20260623/FeatureServer/0')]:
        url = cli.REGISTRY[org]['roots'][0] + path
        assert cli.validate_url(url)[0] == org
        assert cli.provenance(url, org)['publisher'] == cli.REGISTRY[org]['publisher']
    assert cli.validate_url(FLOODED)[0] == 'flooded'
    invalid = [FLOODED.replace('flooded_nz_gdb_v2_202603181308', 'Unrelated_Example_Project'),
               FLOODED.replace('eqbFSejuTufXDr0E', 'ANOTHER_TENANT'),
               PC120 + '/export', PC120.replace('n4yPwebTjJCmXB6W', 'ANOTHER_TENANT')]
    for url in invalid:
        with patch.object(cli.urllib.request, 'build_opener', side_effect=AssertionError('unsafe URL reached network')):
            try:
                cli.fetch(url, kind='service')
            except cli.ClientError as exc:
                assert exc.code == 7
            else:
                raise AssertionError('unapproved service accepted')
    with patch.object(cli, 'fetch', return_value=read('flooded-root')):
        services = cli.discover('flooded', 1)
    assert len(services['services']) == 1 and not services['truncated']
    assert services['services'][0]['source_url'] == FLOODED.rsplit('/', 1)[0]
    print('[PASS] fixture new council routes and Flooded service-only allowlist')

    for org in ['ccc', 'dcc', 'hcc', 'flooded']:
        args = cli.parser().parse_args(['layers', '--curated', 'nz', '--publisher', org, '--json'])
        selected = cli.execute(args)
        assert selected['results'] and all(r['org'] == org for r in selected['results'])
        assert all({'source_url', 'publisher', 'retrieved_at', 'verified_at', 'caveat'} <= r.keys() for r in selected['results'])
        assert all(r['retrieved_at'] == r['verified_at'] and r['retrieved_at'].endswith('Z') for r in selected['results'])
    all_nz = cli.execute(cli.parser().parse_args(['layers', '--curated', 'nz', '--json']))
    assert len({r['source_url'] for r in all_nz['results']}) == len(all_nz['results'])
    assert {r['source_url'] for r in cli.CURATED} <= {r['source_url'] for r in all_nz['results']}
    assert all_nz['meta']['source_url'] == cli.REPO_URL + 'layers-auckland.json'
    assert all_nz['meta']['source_urls'] == [cli.REPO_URL + filename for filename in ('layers-auckland.json', 'layers-nz.json')]
    assert all_nz['meta']['retrieved_at'] == max(r['verified_at'] for r in cli.CURATED + cli.NZ_CURATED)
    assert {'S1100', 'S1101', 'S1102', 'S1103', 'S1104', 'S2927', 'S2686', 'S0789', 'S0790', 'S0792'} <= {r['catalogue_id'] for r in cli.NZ_CURATED}
    assert len([r for r in cli.NZ_CURATED if r['catalogue_id'] == 'S2516']) == 8
    assert 'recommended_fields' in next(r for r in cli.NZ_CURATED if r['catalogue_id'] == 'S2686')
    for record in cli.NZ_CURATED:
        if record['kind'] == 'service':
            assert record['tile_only'] and record['operations'] == ['describe', 'layers']
        else:
            assert isinstance(record['verified_count'], int) and record['verified_count'] >= 0
    selected = cli.execute(cli.parser().parse_args(['layers', '--curated', 'nz', '--publisher', 'ccc', '--problem', 'F1', '--json']))
    assert selected['results'] and all('F1' in r['problem_tags'] and r['org'] == 'ccc' for r in selected['results'])
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = cli.main(['layers', 'ccc', 'OpenData/Structure/FeatureServer', '--publisher', 'ccc', '--json'])
    assert code == 2 and json.loads(out.getvalue())['error']['type'] == 'invalid_input'
    # Catalogue service landing pages must not hide the direct feature endpoint.
    row = {'id': 'S1099', 'url': cli.REGISTRY['hcc']['roots'][0] + '/Example/FeatureServer',
           'direct_endpoint': cli.REGISTRY['hcc']['roots'][0] + '/Example/FeatureServer/0/query?f=geojson'}
    assert next(candidates(row))[2] == 'layer'
    print('[PASS] fixture NZ curated filters, retained Auckland selection and provenance')

    allowed = ['objectid', 'obs_date', 'impact', 'impact_items', 'obs_depth', 'obs_depth_v2', 'historic', 'status']
    assert cli.REGISTRY['flooded']['field_allowlist'] == allowed
    private = ['email', 'phone', 'name', 'Creator', 'Editor']
    for value in ['*', *private, 'objectid,email', 'survey.impact', 'NoSuchField']:
        for machine in [False, True]:
            out, err = io.StringIO(), io.StringIO()
            with patch.object(cli, 'fetch', side_effect=AssertionError('private field request reached network')):
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    code = cli.main(['query', FLOODED, '--fields', value] + (['--json'] if machine else []))
            assert code == 2
            if machine:
                error = json.loads(out.getvalue())
                assert error['results'] == [] and error['error']['type'] == 'invalid_input'
                assert error['meta']['source_url'] == FLOODED and not err.getvalue()
                message = error['error']['message']
            else:
                assert not out.getvalue()
                message = err.getvalue()
            assert 'privacy restriction' in message and ','.join(allowed) in message
    metadata = {'type': 'Feature Layer', 'name': 'Synthetic flood observations',
                'objectIdField': 'objectid', 'geometryType': 'esriGeometryPoint',
                'fields': [{'name': name, 'type': 'esriFieldTypeString'} for name in allowed + private]}
    for fmt in ['json', 'geojson', 'csv']:
        for selected in [None, ' IMPACT , OBJECTID ', 'status']:
            expected = allowed if selected is None else (['impact', 'objectid'] if 'IMPACT' in selected else ['status', 'objectid'])
            def flood(url, params=None, **kwargs):
                assert url == FLOODED
                if params is None:
                    return metadata
                if params.get('returnIdsOnly'):
                    return {'objectIdFieldName': 'objectid', 'objectIds': [1]}
                assert params['outFields'] == ','.join(expected)
                key = 'properties' if fmt == 'geojson' else 'attributes'
                attributes = {name: 'synthetic' for name in allowed + private}
                attributes['objectid'] = 1
                return {'type': 'FeatureCollection', 'features': [{key: attributes, 'id': 1}]}
            argv = ['query', FLOODED, '--format', fmt, '--limit', '1', '--json']
            if selected is not None:
                argv += ['--fields', selected]
            with patch.object(cli, 'fetch', flood):
                result = cli.execute(cli.parser().parse_args(argv))
            feature = result['features' if fmt == 'geojson' else 'results'][0]
            assert set(feature['properties' if fmt == 'geojson' else 'attributes']) == set(expected)
            if fmt == 'csv':
                rendered = cli.csv_output(result)
                assert all(name not in rendered for name in private)
    with patch.object(cli, 'fetch', side_effect=[metadata, {'count': 1}]):
        described = cli.execute(cli.parser().parse_args(['describe', FLOODED, '--json']))
    assert [f['name'] for f in described['results'][0]['fields']] == allowed
    assert described['results'][0]['object_id_field'] == 'objectid'
    # A changed upstream OID must never be added outside the privacy allowlist.
    for command in ['query', 'describe']:
        with patch.object(cli, 'fetch', return_value=dict(metadata, objectIdField='Creator')) as fetch:
            try:
                cli.execute(cli.parser().parse_args([command, FLOODED]))
            except cli.ClientError as exc:
                assert exc.code == 6 and 'field allowlist' in str(exc)
            else:
                raise AssertionError('private OID accepted')
        assert fetch.call_count == 1
    assert cli.query_fields('at', None) == '*' and cli.query_fields('at', '*') == '*'
    cli.ACTIVE_BUDGET = None
    print('[PASS] fixture Flooded privacy defaults, field refusals, describe filtering and JSON/GeoJSON/CSV projection')

    args = cli.parser().parse_args(['query', CCC, '--bbox', '172.635,-43.535,172.64,-43.53', '--fields', 'Height', '--limit', '2', '--format', 'geojson'])
    def fence(url, params=None, **kwargs):
        assert url == CCC
        if params is None:
            return read('more-fence-metadata')
        if params.get('returnIdsOnly'):
            return {'objectIdFieldName': 'FenceID', 'objectIds': [13, 12, 11]}
        assert params['objectIds'] == '11,12' and params['outFields'] == 'Height,FenceID'
        assert params['inSR'] == 4326 and params['outSR'] == 4326
        return read('more-fence-geojson')
    with patch.object(cli, 'fetch', fence):
        result = cli.execute(args)
    assert result['type'] == 'FeatureCollection' and result['feature_count'] == 2
    assert result['matched_count'] == 3 and result['truncated'] and not result['incomplete']
    assert result['meta']['licence'] == 'CC BY 4.0' and result['meta']['publisher'] == 'Christchurch City Council'
    assert 'latest_data' not in result['meta']
    print('[PASS] fixture Christchurch non-OBJECTID key, bbox and GeoJSON')

    args = cli.parser().parse_args(['describe', PC120, '--json'])
    with patch.object(cli, 'fetch', return_value=read('pc120-service')) as fetch:
        result = cli.execute(args)
    assert fetch.call_count == 1 and fetch.call_args.kwargs['kind'] == 'service'
    record = result['results'][0]
    assert record['tile_only'] and record['extent']['spatialReference']['wkid'] == 2193
    assert record['layers'][0]['id'] == 0 and 'record_count' not in record
    assert result['meta']['source_url'] == PC120 and result['meta']['publisher'] == 'Auckland Council'
    assert 'licence' not in result['meta'] and result['meta']['licence_note']
    with patch.object(cli, 'fetch', return_value={'capabilities': 'Map,TilesOnly'}):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.main(['describe', PC120, '--json'])
    error = json.loads(out.getvalue())
    assert code == 6 and error['results'] == [] and error['meta']['source_url'] == PC120
    for command in ['count', 'query']:
        with patch.object(cli, 'fetch', side_effect=AssertionError('service query reached network')):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = cli.main([command, PC120, '--json'])
        assert code == 7
    tiled = cli.REGISTRY['akl']['roots'][1] + '/Synthetic_DEM/ImageServer'
    for url in [tiled, tiled + '/', tiled.replace('tiledimageservices1.arcgis.com', 'TILEDIMAGESERVICES1.ARCGIS.COM')]:
        for machine in [False, True]:
            out, err = io.StringIO(), io.StringIO()
            with patch.object(cli, 'fetch', side_effect=AssertionError('robots-disallowed metadata reached network')):
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    code = cli.main(['describe', url] + (['--json'] if machine else []))
            assert code == 7
            if machine:
                error = json.loads(out.getvalue())
                assert error['results'] == [] and error['error']['reason'] == 'robots_disallowed'
                assert not err.getvalue()
                message = error['error']['message']
            else:
                assert not out.getvalue()
                message = err.getvalue()
            assert 'robots.txt disallows all' in message
    cli.ACTIVE_BUDGET = None
    print('[PASS] fixture tiles-only service metadata, feature-operation and tiled-image robots refusals')


if __name__ == '__main__':
    run()
