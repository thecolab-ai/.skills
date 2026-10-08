#!/usr/bin/env python3
"""Deterministic behaviour checks using trimmed public responses captured live."""
import argparse
import contextlib
import csv
import io
import json
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
    def page(url, params, **kwargs):
        recorded.append(params)
        features=read('roadworks-json')['features'][params['resultOffset']:params['resultOffset']+params['resultRecordCount']]
        return dict(features=features, exceededTransferLimit=True)
    with patch.object(cli,'fetch',page): result=cli.query_layer(args,AT,m)
    assert result['feature_count']==5 and result['truncated']
    assert result['result_offsets']==[0,2,4]
    assert [r['resultRecordCount'] for r in recorded]==[2,2,1]
    assert all(r['inSR']==4326 and r['outSR']==4326 and r['outFields']=='Status,OBJECTID' for r in recorded)
    assert recorded[0]['orderByFields']=='OBJECTID ASC'
    print('[PASS] fixture bounded resultOffset paging, bbox and object-ID ordering')
    m['advancedQueryCapabilities']['supportsPagination']=False
    with patch.object(cli,'fetch',page): result=cli.query_layer(args,AT,m)
    assert result['feature_count']==2 and result['truncated'] and result['result_offsets']==[0]
    m['advancedQueryCapabilities']['supportsPagination']=True
    def repeat(url,params,**kwargs): return dict(features=read('roadworks-json')['features'][:2],exceededTransferLimit=True)
    with patch.object(cli,'fetch',repeat):
        try:cli.query_layer(args,AT,m)
        except cli.ClientError as e:assert e.category=='paging_failure'
        else:raise AssertionError('repeated page accepted')
    with patch.object(cli,'fetch',return_value={}):
        try:cli.record_count(AT)
        except cli.ClientError as e:assert e.code==6
        else:raise AssertionError('missing count accepted')
    print('[PASS] fixture unsupported paging, repeated records and malformed counts')
    good=cli.REGISTRY['at']['roots'][0]
    assert cli.validate_url(AT)[0]=='at'
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
    result=dict(features=read('roadworks-json')['features'],**source)
    rows=list(csv.DictReader(io.StringIO(cli.csv_output(result))))
    assert len(rows)==5 and rows[0]['provenance_source_url']==AT and rows[0]['Status']=='Active'
    selected=cli.execute(cli.parser().parse_args(['layers','--curated','akl','--problem','F1','--json']))
    assert selected['layers'] and all('F1' in r['problem_tags'] for r in selected['layers'])
    assert all({'source_url','publisher','licence','retrieved_at','caveat'} <= r.keys() for r in selected['layers'])
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
    assert len(partial['inaccessible_directories'])==1
    assert partial['inaccessible_directories'][0]['source_url'].endswith('/AllInOne')
    search_args=cli.parser().parse_args(['search','road','--org','at','--max-services','1','--json'])
    with patch.object(cli,'discover',return_value=partial), patch.object(cli,'service_layers',side_effect=cli.ClientError('ArcGIS error: Token Required',4,'access_blocked')):
        search=cli.execute(search_args)
    assert search['truncated'] and search['scanned_services']==1 and len(search['inaccessible_services'])==1
    print('[PASS] fixture gated discovery reports partial results with provenance')
    print('[PASS] fixture service discovery, curated filtering, CSV and provenance')


if __name__=='__main__':run()
