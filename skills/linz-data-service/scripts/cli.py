#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys,pathlib,urllib.parse
from typing import Any
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "lib"))
import nzfetch  # noqa: E402
BASE='https://data.linz.govt.nz/services/api/v1/'
UA='Mozilla/5.0'
def die(m,c=1): print(f'linz-data-service: {m}',file=sys.stderr); raise SystemExit(c)
def get(path, params=None):
    url=BASE+path
    if params: url+='?'+urllib.parse.urlencode({k:v for k,v in params.items() if v is not None})
    try:
        return nzfetch.fetch_json(url,timeout=30,accept='application/json'), url
    except nzfetch.Blocked as e: die(f'network error calling {url}: {e}')
    except nzfetch.FetchError as e: die(str(e))
    except Exception as e: die(f'failed calling {url}: {e}')
def norm_layer(x):
    return {k:x.get(k) for k in ['id','type','title','first_published_at','published_at','featured_at','public_access','user_permissions','user_capabilities','url','url_html','url_canonical','thumbnail_url','services','num_views','num_downloads'] if k in x}
def out(d,j):
    if j: print(json.dumps(d,indent=2,ensure_ascii=False)); return
    if d['kind']=='search':
        print(f"LINZ layers for {d['query']!r}: {len(d['layers'])} shown")
        for x in d['layers']: print(f"- {x.get('id')} {x.get('title')} | access: {x.get('public_access')} | published: {str(x.get('published_at',''))[:10]}")
    elif d['kind']=='layer':
        x=d['layer']; print(f"{x.get('id')} {x.get('title')}"); print(f"access: {x.get('public_access')} | permissions: {', '.join(x.get('user_permissions') or [])}"); print((x.get('description') or '')[:700].replace('\n',' '))
    elif d['kind']=='services':
        print(f"LINZ services for layer {d['layer_id']}: {len(d['services'])}")
        for s in d['services']: print(f"- {s.get('key')} ({s.get('short_name')}): auth={','.join(s.get('auth_method') or []) or 'none'} advertised={s.get('advertised')}")
def cmd_search(a):
    arr,url=get('layers/',{'q':a.query}); arr=arr[:a.limit]
    out({'kind':'search','source':'linz-data-service','query':a.query,'source_url':url,'layers':[norm_layer(x) for x in arr]},a.json)
def cmd_layer(a):
    x,url=get(f'layers/{a.id}/'); y=norm_layer(x); y.update({k:x.get(k) for k in ['description','license','tags','categories','metadata','group','data'] if k in x})
    out({'kind':'layer','source':'linz-data-service','source_url':url,'layer':y},a.json)
def cmd_services(a):
    arr,url=get(f'layers/{a.id}/services/');
    sv=[{k:s.get(k) for k in ['id','authority','key','short_name','label','auth_method','auth_scopes','domain','template_urls','advertised','enabled']} for s in arr]
    out({'kind':'services','source':'linz-data-service','source_url':url,'layer_id':a.id,'services':sv},a.json)
def main():
    p=argparse.ArgumentParser(description='Query LINZ Data Service public catalogue')
    sub=p.add_subparsers(dest='cmd',required=True)
    s=sub.add_parser('search'); s.add_argument('query'); s.add_argument('--limit',type=int,default=10); s.add_argument('--json',action='store_true'); s.set_defaults(func=cmd_search)
    s=sub.add_parser('layer'); s.add_argument('id'); s.add_argument('--json',action='store_true'); s.set_defaults(func=cmd_layer)
    s=sub.add_parser('services'); s.add_argument('id'); s.add_argument('--json',action='store_true'); s.set_defaults(func=cmd_services)
    a=p.parse_args(); a.func(a)
if __name__=='__main__': main()
