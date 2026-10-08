#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys,pathlib,urllib.parse
import datetime as dt
import math
from typing import Any
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "lib"))
import nzfetch  # noqa: E402
BASE='https://data.linz.govt.nz/services/api/v1/'
UA='Mozilla/5.0'
MIRROR = 'https://services.arcgis.com/xdsHIIxuCWByZiCB/arcgis/rest/services/'
FEATURE_LAYERS = {
    'primary-parcels': 'LINZ_NZ_Primary_Parcels/FeatureServer/0',
    'building-outlines': 'LINZ_NZ_Building_Outlines/FeatureServer/0',
}
MAX_LIMIT = 2000
PAGE_SIZE = 1000
TIMEOUT = 10
def die(m,c=1): print(f'linz-data-service: {m}',file=sys.stderr); raise SystemExit(c)
def get(path, params=None):
    url=BASE+path
    if params: url+='?'+urllib.parse.urlencode({k:v for k,v in params.items() if v is not None})
    try:
        return nzfetch.fetch_json(url,timeout=TIMEOUT,accept='application/json'), url
    except nzfetch.Blocked as e: die(f'network error calling {url}: {e}')
    except nzfetch.FetchError as e: die(str(e))
    except Exception as e: die(f'failed calling {url}: {e}')
def norm_layer(x):
    return {k:x.get(k) for k in ['id','type','title','first_published_at','published_at','featured_at','public_access','user_permissions','user_capabilities','url','url_html','url_canonical','thumbnail_url','services','num_views','num_downloads'] if k in x}
def out(d,j):
    d.setdefault('publisher', 'Toitū Te Whenua LINZ')
    d.setdefault('retrieved_at', dt.datetime.now(dt.timezone.utc).isoformat().replace('+00:00', 'Z'))
    if j: print(json.dumps(d,indent=2,ensure_ascii=False)); return
    if d['kind']=='search':
        print(f"LINZ layers for {d['query']!r}: {len(d['layers'])} shown")
        for x in d['layers']: print(f"- {x.get('id')} {x.get('title')} | access: {x.get('public_access')} | published: {str(x.get('published_at',''))[:10]}")
    elif d['kind']=='layer':
        x=d['layer']; print(f"{x.get('id')} {x.get('title')}"); print(f"access: {x.get('public_access')} | permissions: {', '.join(x.get('user_permissions') or [])}"); print((x.get('description') or '')[:700].replace('\n',' '))
    elif d['kind']=='services':
        print(f"LINZ services for layer {d['layer_id']}: {len(d['services'])}")
        for s in d['services']: print(f"- {s.get('key')} ({s.get('short_name')}): auth={','.join(s.get('auth_method') or []) or 'none'} advertised={s.get('advertised')}")
    elif d['kind']=='features':
        print(f"LINZ {d['dataset']}: {d['returned']} of {d['total_matching']} intersecting features (truncated: {d['truncated']})")
        for feature in d['records']: print(json.dumps(feature['properties'],ensure_ascii=False))
    elif d['kind']=='feature-layers':
        for layer in d['layers']: print(f"- {layer['dataset']}: {layer['status']} | {layer.get('source_url') or layer.get('note')}")
def cmd_search(a):
    arr,url=get('layers/',{'q':a.query}); arr=arr[:a.limit]
    out({'kind':'search','source':'linz-data-service','query':a.query,'source_url':url,'layers':[norm_layer(x) for x in arr]},a.json)
def cmd_layer(a):
    x,url=get(f'layers/{a.id}/'); y=norm_layer(x); y.update({k:x.get(k) for k in ['description','license','tags','categories','metadata','group','data'] if k in x})
    payload={'kind':'layer','source':'linz-data-service','source_url':url,'layer':y}
    if x.get('license'): payload['licence']=x['license']
    if x.get('published_at'): payload['latest_data']=x['published_at']
    out(payload,a.json)
def cmd_services(a):
    arr,url=get(f'layers/{a.id}/services/');
    sv=[{k:s.get(k) for k in ['id','authority','key','short_name','label','auth_method','auth_scopes','domain','template_urls','advertised','enabled']} for s in arr]
    out({'kind':'services','source':'linz-data-service','source_url':url,'layer_id':a.id,'services':sv},a.json)


def bbox_value(raw):
    try:
        values=tuple(float(x) for x in raw.split(','))
    except ValueError as exc:
        raise argparse.ArgumentTypeError('--bbox requires comma-separated numbers') from exc
    if len(values)!=4 or not all(math.isfinite(x) for x in values):
        raise argparse.ArgumentTypeError('--bbox requires four finite numbers: minLon,minLat,maxLon,maxLat')
    west,south,east,north=values
    if not (-180<=west<east<=180 and -90<=south<north<=90):
        raise argparse.ArgumentTypeError('--bbox requires ordered WGS84 longitude/latitude bounds')
    if east-west>1 or north-south>1:
        raise argparse.ArgumentTypeError('--bbox must be at most 1 degree wide/high; split larger areas')
    return values


def feature_limit(raw):
    try: value=int(raw)
    except ValueError as exc: raise argparse.ArgumentTypeError('--limit must be an integer') from exc
    if not 1<=value<=MAX_LIMIT: raise argparse.ArgumentTypeError(f'--limit must be between 1 and {MAX_LIMIT}')
    return value


def arcgis_get(url,params=None):
    if params: url+='?'+urllib.parse.urlencode(params)
    try:
        data=nzfetch.fetch_json(url,timeout=TIMEOUT,max_bytes=8*1024*1024,accept='application/json')
    except nzfetch.Blocked as exc: die(f'network error calling LINZ mirror: {exc}')
    except nzfetch.FetchError as exc: die(f'LINZ mirror fetch failed: {exc}')
    if not isinstance(data,dict): die('invalid LINZ mirror response: expected an object',6)
    if data.get('error'):
        error=data['error']; die(f"LINZ mirror query failed: {error.get('message')} ({error.get('details')})",5)
    return data


def feature_provenance(layer_url,metadata):
    result={'source_url':layer_url,'publisher':'Toitū Te Whenua LINZ','licence':'CC BY 4.0',
            'retrieved_at':dt.datetime.now(dt.timezone.utc).isoformat().replace('+00:00','Z')}
    latest=(metadata.get('editingInfo') or {}).get('dataLastEditDate')
    if latest:
        result['latest_data']=dt.datetime.fromtimestamp(latest/1000,dt.timezone.utc).isoformat().replace('+00:00','Z')
    return result


def cmd_features(a):
    if a.dataset=='parcels':
        die('NZ Parcels is not published in the verified LINZ public ArcGIS mirror. Use primary-parcels for current primary parcels only; it excludes non-primary, historic and pending parcels. Catalogue metadata remains available via layer 51571.',7)
    layer_url=MIRROR+FEATURE_LAYERS[a.dataset]
    metadata=arcgis_get(layer_url,{'f':'json'})
    if metadata.get('geometryType')!='esriGeometryPolygon' or not metadata.get('objectIdField'):
        die('LINZ mirror schema changed: expected a polygon layer with an object ID field',6)
    params={'where':'1=1','geometry':','.join(map(str,a.bbox)),
            'geometryType':'esriGeometryEnvelope','inSR':4326,
            'spatialRel':'esriSpatialRelIntersects'}
    count=arcgis_get(layer_url+'/query',{**params,'f':'json','returnCountOnly':'true'})
    total=count.get('count')
    if not isinstance(total,int) or total<0: die('invalid LINZ mirror response: missing integer count',6)
    records=[]
    page_size=min(PAGE_SIZE,metadata.get('maxRecordCount') or PAGE_SIZE)
    while len(records)<min(total,a.limit):
        page=arcgis_get(layer_url+'/query',{**params,'f':'geojson','outFields':'*',
            'returnGeometry':'true','outSR':4326,'orderByFields':metadata['objectIdField']+' ASC',
            'resultOffset':len(records),'resultRecordCount':min(page_size,a.limit-len(records))})
        features=page.get('features')
        if page.get('type')!='FeatureCollection' or not isinstance(features,list) or not features:
            die('invalid LINZ mirror response: expected a non-empty GeoJSON feature page',6)
        if any(not isinstance(f,dict) or f.get('type')!='Feature' or not isinstance(f.get('properties'),dict) for f in features):
            die('invalid LINZ mirror response: malformed GeoJSON feature',6)
        records.extend(features[:a.limit-len(records)])
    provenance=feature_provenance(layer_url,metadata)
    for feature in records: feature['properties'].update(provenance)
    payload={'kind':'features','dataset':a.dataset,'bbox':a.bbox,'returned':len(records),
             'total_matching':total,'limit':a.limit,'truncated':len(records)<total,**provenance,
             'notes':['Features intersect the bbox; polygon boundaries are not clipped.',
                      'latest_data is the mirror data edit time, not an imagery capture date.']}
    if a.format=='geojson':
        payload['query_bbox']=payload.pop('bbox')
        payload.update({'type':'FeatureCollection','features':records})
        out(payload,True)
    else:
        payload['records']=records
        out(payload,a.json)


def cmd_feature_layers(a):
    layers=[]
    for dataset,path in FEATURE_LAYERS.items():
        url=MIRROR+path; metadata=arcgis_get(url,{'f':'json'})
        layers.append({'dataset':dataset,'name':metadata['name'],'status':'available',
                       **feature_provenance(url,metadata)})
    layers.append({'dataset':'parcels','status':'unsupported',
                   'note':'No NZ Parcels service is published in the verified public mirror; primary parcels are a different dataset.'})
    out({'kind':'feature-layers','source_url':MIRROR,'layers':layers},a.json)


def main():
    p=argparse.ArgumentParser(description='Query LINZ Data Service public catalogue')
    sub=p.add_subparsers(dest='cmd',required=True)
    s=sub.add_parser('search'); s.add_argument('query'); s.add_argument('--limit',type=int,default=10); s.add_argument('--json',action='store_true'); s.set_defaults(func=cmd_search)
    s=sub.add_parser('layer'); s.add_argument('id'); s.add_argument('--json',action='store_true'); s.set_defaults(func=cmd_layer)
    s=sub.add_parser('services'); s.add_argument('id'); s.add_argument('--json',action='store_true'); s.set_defaults(func=cmd_services)
    s=sub.add_parser('features',help='Query keyless LINZ mirror polygons intersecting a bbox')
    s.add_argument('dataset',choices=(*FEATURE_LAYERS,'parcels'))
    s.add_argument('--bbox',type=bbox_value,required=True,help='minLon,minLat,maxLon,maxLat (WGS84), at most 1 degree wide/high')
    s.add_argument('--limit',type=feature_limit,default=100,help=f'maximum features, 1-{MAX_LIMIT}')
    s.add_argument('--format',choices=('json','geojson'),default='json')
    s.add_argument('--json',action='store_true'); s.set_defaults(func=cmd_features)
    s=sub.add_parser('feature-layers',help='Inspect verified public mirror layer availability')
    s.add_argument('--json',action='store_true'); s.set_defaults(func=cmd_feature_layers)
    a=p.parse_args(); a.func(a)
if __name__=='__main__': main()
