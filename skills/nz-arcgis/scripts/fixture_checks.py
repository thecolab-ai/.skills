#!/usr/bin/env python3
"""Deterministic behaviour checks using trimmed public responses captured live."""
import argparse
import contextlib
import csv
import io
import json
import time
import urllib.error
from curate_layers import restricts_reuse
from pathlib import Path
from unittest.mock import patch
import cli

FIXTURES = Path(__file__).resolve().parents[1] / 'tests/fixtures'
AT = cli.REGISTRY['at']['roots'][0] + '/PJ_Roadworks_MS/FeatureServer/0'
AKL = cli.REGISTRY['akl']['roots'][0] + '/Stormwater_Pipe/FeatureServer/0'


def read(name):
    return json.loads((FIXTURES / (name + '.json')).read_text())


def run():
    for key in ['roadworks', 'stormwater']:
        m = read(key + '-metadata')
        assert m['objectIdField'] == 'OBJECTID'
        assert m['editingInfo']['lastEditDate'] > 0
        assert any(f['name'] == 'OBJECTID' for f in cli.list_value(m, 'fields'))
        assert read(key+'-count')['count'] > 0
        for fmt in ['json','geojson']:
            rows = cli.list_value(read(key+'-'+fmt), 'features')
            assert len(rows) == 5
            assert len({f['id'] if fmt == 'geojson' else f['attributes']['OBJECTID'] for f in rows}) == 5
    print('[PASS] fixture real metadata, counts and JSON/GeoJSON features')
    args=cli.parser().parse_args(['query',AT,'--bbox','174.60,-37.05,174.95,-36.70','--limit','5','--fields','Status','--json'])
    m=read('roadworks-metadata'); m['maxRecordCount']=2
    recorded=[]
    # Synthetic dropped-row server: IDs survive, projected features may disappear.
    def page(url, params, **kwargs):
        recorded.append(params)
        if params.get('returnIdsOnly'):
            return dict(objectIds=[5, 4, 3, 2, 1], objectIdFieldName='OBJECTID')
        ids = set(map(int, params['objectIds'].split(',')))
        return dict(features=[f for f in read('roadworks-json')['features'] if f['attributes']['OBJECTID'] in ids], exceededTransferLimit=True)
    with patch.object(cli,'fetch',page): result=cli.query_layer(args,AT,m)
    assert result['feature_count']==5 and not result['truncated'] and not result['incomplete']
    assert result['result_offsets']==[0,2,4]
    batches=recorded[1:]
    assert [r['objectIds'] for r in batches]==['1,2','3,4','5']
    assert all(r['inSR']==4326 and r['outSR']==4326 and r['outFields']=='Status,OBJECTID' for r in batches)
    def drop(url,params,**kwargs):
        data=page(url,params,**kwargs)
        if 'features' in data:
            data['features']=[f for f in data['features'] if f['attributes']['OBJECTID']!=2]
        return data
    with patch.object(cli,'fetch',drop): result=cli.query_layer(args,AT,m)
    assert result['feature_count']==4 and result['truncated'] and result['incomplete'] and result['missing_object_ids_count']==1
    # Synthetic dense selection: a small sample must work without a bbox.
    for fmt in ['json', 'geojson', 'csv']:
        dense_args=cli.parser().parse_args(['query',AT,'--limit','5','--format',fmt,'--json'])
        def dense(url,params,**kwargs):
            if params.get('returnIdsOnly'):
                assert 'geometry' not in params
                return dict(objectIds=list(range(1,2440)),objectIdFieldName='OBJECTID')
            ids=set(map(int,params['objectIds'].split(',')))
            fixture=read('roadworks-'+('geojson' if fmt=='geojson' else 'json'))
            return dict(fixture,features=[f for f in fixture['features'] if (f['id'] if fmt=='geojson' else f['attributes']['OBJECTID']) in ids])
        with patch.object(cli,'fetch',dense): result=cli.query_layer(dense_args,AT,m)
        assert result['feature_count']==dense_args.limit and result['truncated'] and not result['incomplete']
        assert result['matched_count']==2439 and result['missing_object_ids_count']==0
        def capped_ids(url,params,**kwargs):
            data=dense(url,params,**kwargs)
            if params.get('returnIdsOnly'): data['exceededTransferLimit']=True
            return data
        with patch.object(cli,'fetch',capped_ids): result=cli.query_layer(dense_args,AT,m)
        assert result['feature_count']==5 and result['truncated'] and result['incomplete']
        assert 'server truncated object ID selection' in result['truncation_reasons']
    csv_args=cli.parser().parse_args(['query',AT,'--limit','5','--format','csv','--json'])
    recorded.clear()
    with patch.object(cli,'fetch',page): csv_result=cli.query_layer(csv_args,AT,m)
    assert csv_result['feature_count']==5 and all(r['returnGeometry']=='false' for r in recorded)
    print('[PASS] fixture ID batches detect dropped projected rows without offset drift')
    def repeat(url,params,**kwargs):
        if params.get('returnIdsOnly'): return dict(objectIds=[1,2,3,4,5])
        return dict(features=read('roadworks-json')['features'][:2],exceededTransferLimit=True)
    with patch.object(cli,'fetch',repeat):
        try: cli.query_layer(args,AT,m)
        except cli.ClientError as e: assert e.code==6
        else: raise AssertionError('repeated page accepted')
    no_oid=dict(m, objectIdField=None, fields=[])
    def fallback(url, params, **kwargs):
        if params.get('returnCountOnly'): return dict(count=5)
        return dict(features=read('roadworks-json')['features'][:1],exceededTransferLimit=False)
    with patch.object(cli,'fetch',fallback): result=cli.query_layer(args,AT,no_oid)
    assert result['truncated'] and result['incomplete'] and result['ordering']=='unordered' and result['warnings']
    with patch.object(cli,'fetch',return_value={}):
        try: cli.record_count(AT)
        except cli.ClientError as e: assert e.code==6
        else: raise AssertionError('missing count accepted')
    def limit(url,params,**kwargs):
        if params.get('returnIdsOnly'): return dict(objectIds=[1,2,3,4,5])
        if params['objectIds']=='1,2': return page(url,params,**kwargs)
        raise cli.ClientError('aggregate cap',6,'resource_limit')
    with patch.object(cli,'fetch',limit): result=cli.query_layer(args,AT,m)
    assert result['feature_count']==2 and result['truncated'] and result['missing_object_ids_count']==3 and result['truncation_reasons']
    print('[PASS] fixture unsupported ordering, repeated IDs, count validation and partial resource limits')
    good=cli.REGISTRY['at']['roots'][0]
    assert cli.validate_url(AT)[0]=='at'
    assert cli.validate_url(AT+'/')[1]==AT
    assert cli.validate_url(AT.replace('/arcgis/','/ArcGIS/'))[0]=='at'
    assert cli.validate_url(cli.REGISTRY['at']['roots'][1]+'/FutureConnect/FutureConnect_DeficiencyIndicators/MapServer/46')[0]=='at'
    invalid=[AT.replace('https:','http:'), AT.replace('JkPEgZJGxhSjYOo0','OTHER_TENANT'), AT.replace('services2.arcgis.com','services2.arcgis.com.evil.invalid'), AT+'?token=no', AT+'#fragment', AT+'/query',AT.replace('/PJ_', '/../PJ_'),AT.replace('/PJ_','/%2e%2e/PJ_'), AT.replace('/PJ_','/%252e%252e/PJ_'),AT.replace('/PJ_','/x%2fPJ_'),AT.replace('https://','https://user@'),AT.replace('.com/','.com:443/'), AT.replace('/PJ_','//PJ_'),good+'/PJ_Roadworks_MS/FeatureServer/deleteFeatures']
    with patch.object(cli.urllib.request,'build_opener',side_effect=AssertionError('unsafe URL reached network')):
        for u in invalid:
            try:cli.fetch(u)
            except cli.ClientError as e:assert e.code==7
            else:raise AssertionError('unsafe route accepted')
    try:cli.NoRedirect().redirect_request(None,None,302,'',{},AT.replace('JkPEgZJGxhSjYOo0','OTHER_TENANT'))
    except cli.ClientError as e:assert e.category=='blocked_redirect'
    else:raise AssertionError('redirect accepted')
    for b in ['nan,-37,175,-36','174,-37,inf,-36','175,-37,174,-36','174,-37,175,-91','1,2,3','1,2,3,4,5']:
        try:cli.bbox(b)
        except argparse.ArgumentTypeError:pass
        else:raise AssertionError('bad bbox accepted')
    print('[PASS] fixture host/tenant/path/redirect restrictions and bbox validation')
    with patch.object(cli,'fetch',return_value=read('roadworks-service')):
        layers=cli.service_layers(AT.rsplit('/',1)[0])
    assert layers[0]['name']=='Roadworks' and layers[0]['source_url']==AT
    with patch.object(cli,'fetch',return_value=read('at-root')):
        discovered=cli.discover('at',1,0)
    assert discovered['requests']==1 and discovered['services']
    assert all(r['publisher']=='Auckland Transport' for r in discovered['services'])
    source=cli.provenance(AT,'at',read('roadworks-metadata'))
    assert source['latest_data']=='2026-10-07T12:01:32Z' and source['retrieved_at'].endswith('Z')
    assert {'source_url','publisher','licence','retrieved_at'} <= source.keys()
    result=dict(results=read('roadworks-json')['features'],meta=source)
    rows=list(csv.DictReader(io.StringIO(cli.csv_output(result))))
    assert len(rows)==5 and rows[0]['provenance_source_url']==AT and rows[0]['Status']=='Active'
    selected=cli.execute(cli.parser().parse_args(['layers','--curated','akl','--problem','F1','--json']))
    assert selected['results'] and all('F1' in r['problem_tags'] for r in selected['results'])
    assert all({'source_url','publisher','retrieved_at','caveat'} <= r.keys() for r in selected['results'])
    directory_calls=[]
    def gated_directory(url, params=None, **kwargs):
        directory_calls.append(url)
        if url==cli.REGISTRY['at']['roots'][0]:
            return read('at-root')
        if url==cli.REGISTRY['at']['roots'][1]:
            return read('mahere-root')
        raise cli.ClientError('ArcGIS error: Token Required',4,'access_blocked')
    with patch.object(cli,'fetch',gated_directory):
        partial=cli.discover('at',3)
    assert partial['services'] and partial['truncated'] and partial['requests']==3
    assert len(partial['failed_directories'])==1
    assert partial['failed_directories'][0]['source_url'].endswith('/AllInOne')
    search_args=cli.parser().parse_args(['search','road','--org','at','--max-services','1','--json'])
    with patch.object(cli,'discover',return_value=dict(partial)), patch.object(cli,'service_layers',side_effect=cli.ClientError('ArcGIS error: Token Required',4,'access_blocked')):
        search=cli.execute(search_args)
    assert search['truncated'] and search['scanned_services']==1 and len(search['failed_services'])==1
    for error in [cli.ClientError('HTTP 404',2,'upstream_http_failure'),
                  cli.ClientError('Invalid URL',2,'upstream_arcgis_failure'),
                  cli.ClientError('redirect refused',7,'blocked_redirect')]:
        def stale_directory(url,params=None,**kwargs):
            if url==cli.REGISTRY['at']['roots'][0]: return dict(read('at-root'),folders=['Stale'])
            raise error
        with patch.object(cli,'fetch',stale_directory): stale=cli.discover('at',2,0)
        assert stale['services'] and stale['truncated'] and len(stale['failed_directories'])==1
        with patch.object(cli,'discover',return_value=dict(stale)), patch.object(cli,'service_layers',side_effect=error):
            search=cli.execute(search_args)
        assert search['truncated'] and len(search['failed_services'])==1
    with patch.object(cli,'discover',return_value=dict(partial)), patch.object(cli,'service_layers',side_effect=cli.ClientError('invalid local route',2)):
        try: cli.execute(search_args)
        except cli.ClientError as e: assert e.code==2
        else: raise AssertionError('local invalid input tolerated')
    print('[PASS] fixture gated discovery reports partial results with provenance')
    assert all(not restricts_reuse(r) for r in cli.CURATED)
    assert {'S0470','S0723','S0777'} <= {r['catalogue_id'] for r in cli.CURATED}
    assert 'nema' not in cli.REGISTRY
    assert all(not r.get('licence') or not cli.UNKNOWN_LICENCE.search(r['licence']) for r in cli.CURATED)
    assert not cli.UNKNOWN_LICENCE.search('Creative Commons Attribution (version not specified on MfE page)')
    for note in ['Not specified; source credit is Example Council', 'Metadata does not state a licence', 'No explicit licence', 'No open reuse license', 'No specific licence']:
        assert cli.UNKNOWN_LICENCE.search(note)
    for catalogue_id in ['C0094','S2235']:
        record=next(r for r in cli.CURATED if r['catalogue_id']==catalogue_id)
        assert record['licence_note'] and 'licence' not in cli.provenance(record['source_url'],record['org'])
    assert all(r['org']!='nema' for r in cli.VERIFICATION)
    for fmt,key in [('json','attributes'),('geojson','properties')]:
        assert all('PrincipalOrganisation' not in f[key] for f in read('roadworks-'+fmt)['features'])
    assert all(r['retrieved_at']==next(x['retrieved_at'] for x in cli.CURATED if x['source_url']==r['source_url']) for r in selected['results'])
    registry=cli.execute(cli.parser().parse_args(['orgs','--json']))
    assert registry['meta']['source_url'].endswith('/references/orgs.json')
    assert registry['meta']['retrieved_at']==max(r['verified_at'] for r in cli.VERIFICATION if r['org'] in cli.REGISTRY and r.get('ok'))
    formula=cli.result_envelope([{'attributes': {'value': '=1+1', 'other': '  @SUM(A1)'}}],source)
    escaped=list(csv.DictReader(io.StringIO(cli.csv_output(formula))))[0]
    assert escaped['value']=="'=1+1" and escaped['other'].startswith("'")
    print('[PASS] fixture curated reuse terms, cached timestamps, unknown licences and safe CSV')
    # Synthetic ArcGIS and HTTP errors; no upstream data is redistributed here.
    cli.ACTIVE_BUDGET=None
    for upstream, expected in [(400,2),(404,2),(403,4),(498,4),(499,4),(500,5)]:
        response=io.BytesIO(json.dumps({'error': {'code': upstream, 'message': '', 'details': ['Invalid field NoSuchField']}}).encode())
        with patch.object(cli.urllib.request,'build_opener') as opener:
            opener.return_value.open.return_value=response
            try: cli.fetch(AT)
            except cli.ClientError as e:
                assert e.code==expected and 'NoSuchField' in str(e)
            else: raise AssertionError('upstream error accepted')
        http_error=urllib.error.HTTPError(AT,upstream,'synthetic',{'Retry-After': '30'},None)
        with patch.object(cli.urllib.request,'build_opener') as opener:
            opener.return_value.open.side_effect=http_error
            try: cli.fetch(AT)
            except cli.ClientError as e: assert e.code==expected and e.details['retry_after']=='30'
            else: raise AssertionError('HTTP error accepted')
    for timeout in ['0','61','nan']:
        try: cli.parser().parse_args(['query',AT,'--timeout',timeout])
        except cli.ClientError as e: assert e.code==2
        else: raise AssertionError('bad timeout accepted')
    with patch.object(cli.urllib.request,'build_opener') as opener:
        opener.return_value.open.side_effect=TimeoutError()
        cli.ACTIVE_BUDGET=cli.RequestBudget(30)
        try: cli.fetch(AT,query=True)
        except cli.ClientError as e: assert e.code==5 and 'after 30s' in str(e) and 'narrow --bbox' in str(e)
        else: raise AssertionError('timeout accepted')
        for url,kind in [(cli.REGISTRY['at']['roots'][0],'directory'),(AT.rsplit('/',1)[0],'service')]:
            try: cli.fetch(url,kind=kind)
            except cli.ClientError as e: assert e.code==5 and 'retry later' in str(e) and '--' not in str(e)
            else: raise AssertionError('directory/service timeout accepted')
    response=io.BytesIO(json.dumps({'error':{'code':499,'message':'Token Required','details':['Token Required','Token Required']}}).encode())
    with patch.object(cli.urllib.request,'build_opener') as opener:
        opener.return_value.open.return_value=response
        try: cli.fetch(AT)
        except cli.ClientError as e: assert str(e)=='ArcGIS error: Token Required'
        else: raise AssertionError('ArcGIS error accepted')
    now=time.monotonic()
    assert now+54 < cli.RequestBudget().deadline <= time.monotonic()+55
    for bound in ['bytes','deadline']:
        cli.ACTIVE_BUDGET=cli.RequestBudget()
        if bound=='bytes': cli.ACTIVE_BUDGET.bytes=64*1024*1024
        else: cli.ACTIVE_BUDGET.deadline=time.monotonic()-1
        with patch.object(cli.urllib.request,'build_opener',side_effect=AssertionError('bound reached network')):
            try: cli.fetch(AT)
            except cli.ClientError as e: assert e.category=='resource_limit'
            else: raise AssertionError('resource bound accepted')
    cli.ACTIVE_BUDGET=None
    cli.ACTIVE_BUDGET=cli.RequestBudget()
    sample=json.dumps({'count':5}).encode()
    with patch.object(cli.urllib.request,'build_opener') as opener:
        opener.return_value.open.side_effect=[io.BytesIO(sample),io.BytesIO(sample)]
        cli.fetch(AT); cli.fetch(AT)
    assert cli.ACTIVE_BUDGET.bytes==len(sample)*2
    cli.ACTIVE_BUDGET=None
    print('[PASS] fixture error codes/details, timeout and aggregate/deadline bounds')
    def root_failure(url,params=None,**kwargs):
        if url==cli.REGISTRY['at']['roots'][0]: raise cli.ClientError('synthetic outage',5)
        return read('at-root')
    with patch.object(cli,'fetch',root_failure): partial=cli.discover('at',2)
    assert partial['services'] and partial['truncated'] and len(partial['failed_directories'])==1
    with patch.object(cli,'fetch',side_effect=cli.ClientError('all roots down',5)):
        try: cli.discover('at',2)
        except cli.ClientError as e: assert e.code==5
        else: raise AssertionError('all roots failed as success')
    for bad in [dict(services=None),dict(services=[],folders=['../unsafe'])]:
        with patch.object(cli,'fetch',return_value=bad):
            if bad['services'] is None:
                try: cli.discover('at',2)
                except cli.ClientError as e: assert e.code==6
                else: raise AssertionError('malformed roots accepted')
            else:
                try: cli.discover('at',2)
                except cli.ClientError as e: assert e.code==7
                else: raise AssertionError('unsafe folder accepted')
    with patch.object(cli,'fetch',return_value={'type':'Group Layer','fields':None}):
        out=io.StringIO()
        with contextlib.redirect_stdout(out): code=cli.main(['describe',AT,'--json'])
        assert code==7 and json.loads(out.getvalue())['error']['type']=='unsupported_operation'
    for metadata in [{'type':'Table'},{'type':'Feature Layer','geometryType':None}]:
        for command in ['count','query']:
            with patch.object(cli,'fetch',return_value=metadata) as fetch:
                out=io.StringIO()
                with contextlib.redirect_stdout(out): code=cli.main([command,AT,'--bbox','174,-37,175,-36','--json'])
                data=json.loads(out.getvalue())
                assert code==2 and data['error']['message']=='bbox not supported on tables; use --where'
                assert fetch.call_count==1
    for argv in [['count',AT,'--json'],['query',AT,'--format','geojson']]:
        with patch.object(cli,'execute',side_effect=cli.ClientError('bad field',2)):
            out,err=io.StringIO(),io.StringIO()
            with contextlib.redirect_stdout(out),contextlib.redirect_stderr(err): code=cli.main(argv)
            data=json.loads(out.getvalue())
            assert code==2 and data['results']==[] and data['meta']['source_url']==AT and data['error']['type']=='invalid_input' and not err.getvalue()
    print('[PASS] fixture partial/all-root failures, unsafe folders, unsupported layer and stdout errors')
    print('[PASS] fixture service discovery, curated filtering, CSV and provenance')
    from more_fixture_checks import run as run_more
    run_more()


if __name__=='__main__':run()
