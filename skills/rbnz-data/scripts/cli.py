#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys,urllib.parse,urllib.request,urllib.error
from typing import Any
BASE='https://catalogue.data.govt.nz/api/3/action/'
ORG='reserve-bank-of-new-zealand'
EXCHANGE_RESOURCE='f16aa755-ba94-4679-8c5f-4c1cb6c2901a'
UA='Mozilla/5.0'
def die(m,c=1): print(f'rbnz-data: {m}',file=sys.stderr); raise SystemExit(c)
def get(action, params):
 url=BASE+action+'?'+urllib.parse.urlencode({k:v for k,v in params.items() if v is not None})
 try:
  data=json.loads(urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':UA,'Accept':'application/json'}),timeout=30).read().decode())
 except urllib.error.HTTPError as e: die(f'HTTP {e.code} from {url}: {e.read().decode("utf-8","replace")[:250]}')
 except Exception as e: die(f'failed calling {url}: {e}')
 if not data.get('success'): die(f'API returned success=false: {data.get("error")}')
 return data['result'],url
def norm_pkg(p):
 return {'id':p.get('id'),'name':p.get('name'),'title':p.get('title'),'notes':p.get('notes'),'frequency_of_update':p.get('frequency_of_update'),'metadata_modified':p.get('metadata_modified'),'resources':len(p.get('resources') or []),'url':f"https://catalogue.data.govt.nz/dataset/{p.get('name')}"}
def out(d,j):
 if j: print(json.dumps(d,indent=2,ensure_ascii=False)); return
 if d['kind']=='search':
  print(f"RBNZ datasets for {d['query']!r}: {d['count']} total")
  for x in d['datasets']: print(f"- {x['name']}: {x['title']} | resources {x['resources']}")
 elif d['kind']=='dataset':
  x=d['dataset']; print(f"{x['name']}: {x['title']}"); print((x.get('notes') or '')[:500].replace('\n',' '));
  for r in x.get('resource_list',[])[:12]: print(f"- {r.get('name')} [{r.get('format') or '-'}] datastore={r.get('datastore_active')} {r.get('url')}")
 elif d['kind']=='exchange-rates':
  print(f"RBNZ exchange-rate datastore preview: {len(d['records'])} records")
  for r in d['records']: print('- '+json.dumps(r,ensure_ascii=False)[:300])
def cmd_search(a):
 res,url=get('package_search',{'fq':'organization:'+ORG,'q':a.query,'rows':a.limit})
 out({'kind':'search','source':'rbnz-data','source_url':url,'query':a.query,'count':res.get('count'),'datasets':[norm_pkg(p) for p in res.get('results',[])]},a.json)
def cmd_dataset(a):
 p,url=get('package_show',{'id':a.id}); d=norm_pkg(p); d['resource_list']=[{k:r.get(k) for k in ['id','name','format','url','datastore_active','last_modified']} for r in p.get('resources',[])]
 out({'kind':'dataset','source':'rbnz-data','source_url':url,'dataset':d},a.json)
def cmd_exchange(a):
 res,url=get('datastore_search',{'resource_id':EXCHANGE_RESOURCE,'limit':a.limit})
 rows=[r for r in res.get('records',[]) if any(v not in (None,'') for k,v in r.items() if k!='_id')]
 out({'kind':'exchange-rates','source':'rbnz-data','source_url':url,'resource_id':EXCHANGE_RESOURCE,'total':res.get('total'),'records':rows[:a.limit]},a.json)
def main():
 p=argparse.ArgumentParser(description='Discover RBNZ public data via data.govt.nz')
 sub=p.add_subparsers(dest='cmd',required=True)
 s=sub.add_parser('search'); s.add_argument('query'); s.add_argument('--limit',type=int,default=10); s.add_argument('--json',action='store_true'); s.set_defaults(func=cmd_search)
 s=sub.add_parser('dataset'); s.add_argument('id'); s.add_argument('--json',action='store_true'); s.set_defaults(func=cmd_dataset)
 s=sub.add_parser('exchange-rates'); s.add_argument('--limit',type=int,default=5); s.add_argument('--json',action='store_true'); s.set_defaults(func=cmd_exchange)
 a=p.parse_args(); a.func(a)
if __name__=='__main__': main()
