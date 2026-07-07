#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, pathlib, sys, urllib.parse
from typing import Any

# Shared fetch helper — browser UA + rotating-proxy retry to clear IP-reputation
# bot walls (data.govt.nz sits behind Incapsula). Repo lib/, three parents up
# from this scripts/ dir. See lib/nzfetch.py.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / 'lib'))
import nzfetch  # noqa: E402
BASE='https://catalogue.data.govt.nz/api/3/action/'

def die(msg, code=1): print(f'data-govt-nz: {msg}', file=sys.stderr); raise SystemExit(code)
def get(action: str, params: dict[str, Any]):
    url=BASE+action+'?'+urllib.parse.urlencode({k:v for k,v in params.items() if v is not None})
    try:
        data=nzfetch.fetch_json(url, timeout=30)  # direct → rotating proxy on a block
    except nzfetch.Blocked as e: die(f'network error: {e}')
    except nzfetch.FetchError as e: die(str(e))
    if not data.get('success'): die(f'API returned success=false from {url}: {data.get("error")}')
    return data.get('result'), url

def out(data, as_json):
    if as_json: print(json.dumps(data, indent=2, ensure_ascii=False)); return
    if data.get('kind')=='search':
        print(f"data.govt.nz datasets for {data['query']!r}: {data['count']} total")
        for d in data['datasets']:
            print(f"- {d['title']} ({d['name']})")
            print(f"  org: {d.get('organization') or '-'} | resources: {d.get('resource_count',0)} | modified: {d.get('metadata_modified','')[:10]}")
            if d.get('url'): print(f"  url: {d['url']}")
    elif data.get('kind')=='dataset':
        d=data['dataset']; print(f"{d.get('title')} ({d.get('name')})"); print(f"org: {d.get('organization') or '-'} | resources: {len(d.get('resources',[]))}"); print(d.get('notes','')[:500].replace('\n',' '))
        for r in d.get('resources',[])[:10]: print(f"- {r.get('name') or r.get('id')} [{r.get('format') or '-'}] {r.get('url') or ''}")
    elif data.get('kind')=='orgs':
        print(f"data.govt.nz organisations: {len(data['organisations'])} shown")
        for o in data['organisations']: print(f"- {o.get('title') or o.get('display_name') or o.get('name')} ({o.get('name')})")
    elif data.get('kind')=='resource':
        print(f"resource {data['resource_id']}: {data.get('total')} records total, {len(data.get('records',[]))} shown")
        for rec in data.get('records',[])[:5]: print('- '+json.dumps(rec, ensure_ascii=False)[:300])

def norm_pkg(p):
    org=p.get('organization') or {}
    return {'id':p.get('id'),'name':p.get('name'),'title':p.get('title'),'notes':p.get('notes'),'organization':org.get('title') or org.get('name') if isinstance(org,dict) else None,'metadata_modified':p.get('metadata_modified'),'resource_count':len(p.get('resources') or []),'url':f"https://catalogue.data.govt.nz/dataset/{p.get('name')}" if p.get('name') else None}

def cmd_search(a):
    res,url=get('package_search',{'q':a.query,'rows':a.limit})
    out({'kind':'search','source':'data-govt-nz','query':a.query,'count':res.get('count'), 'source_url':url,'datasets':[norm_pkg(p) for p in res.get('results',[])]}, a.json)
def cmd_dataset(a):
    p,url=get('package_show',{'id':a.id})
    d=norm_pkg(p); d['resources']=[{k:r.get(k) for k in ['id','name','description','format','mimetype','url','created','last_modified','datastore_active']} for r in p.get('resources',[])]
    out({'kind':'dataset','source':'data-govt-nz','source_url':url,'dataset':d}, a.json)
def cmd_orgs(a):
    orgs,url=get('organization_list',{'all_fields':'true'})
    orgs=orgs[:a.limit]
    out({'kind':'orgs','source':'data-govt-nz','source_url':url,'organisations':orgs}, a.json)
def cmd_resource(a):
    res,url=get('datastore_search',{'resource_id':a.resource_id,'limit':a.limit})
    out({'kind':'resource','source':'data-govt-nz','source_url':url,'resource_id':a.resource_id,'total':res.get('total'),'fields':res.get('fields'),'records':res.get('records',[])}, a.json)
def main():
    p=argparse.ArgumentParser(description='Query data.govt.nz public CKAN catalogue')
    sub=p.add_subparsers(dest='cmd', required=True)
    s=sub.add_parser('search'); s.add_argument('query'); s.add_argument('--limit',type=int,default=5); s.add_argument('--json',action='store_true'); s.set_defaults(func=cmd_search)
    s=sub.add_parser('dataset'); s.add_argument('id'); s.add_argument('--json',action='store_true'); s.set_defaults(func=cmd_dataset)
    s=sub.add_parser('orgs'); s.add_argument('--limit',type=int,default=20); s.add_argument('--json',action='store_true'); s.set_defaults(func=cmd_orgs)
    s=sub.add_parser('resource'); s.add_argument('resource_id'); s.add_argument('--limit',type=int,default=5); s.add_argument('--json',action='store_true'); s.set_defaults(func=cmd_resource)
    a=p.parse_args(); a.func(a)
if __name__=='__main__': main()
