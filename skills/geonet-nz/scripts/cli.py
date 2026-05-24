#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys,urllib.parse,urllib.request,urllib.error
from typing import Any
BASE='https://api.geonet.org.nz/'
UA='Mozilla/5.0'
def die(m,c=1): print(f'geonet-nz: {m}',file=sys.stderr); raise SystemExit(c)
def get(path, params=None):
    url=BASE+path
    if params: url+='?'+urllib.parse.urlencode({k:v for k,v in params.items() if v is not None})
    try:
        with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':UA,'Accept':'application/json,application/vnd.geo+json'}),timeout=30) as r: return json.loads(r.read().decode()), url
    except urllib.error.HTTPError as e: die(f'HTTP {e.code} from {url}: {e.read().decode("utf-8","replace")[:250]}')
    except Exception as e: die(f'failed calling {url}: {e}')
def norm_feature(f):
    p=f.get('properties') or {}; coords=(f.get('geometry') or {}).get('coordinates') or []
    return {'public_id':p.get('publicID'),'time':p.get('time'),'magnitude':p.get('magnitude'),'depth_km':p.get('depth'),'mmi':p.get('mmi'),'locality':p.get('locality'),'quality':p.get('quality'),'longitude':coords[0] if len(coords)>0 else None,'latitude':coords[1] if len(coords)>1 else None}
def out(d,j):
    if j: print(json.dumps(d,indent=2,ensure_ascii=False)); return
    if d['kind']=='quakes':
        print(f"GeoNet earthquakes: {len(d['quakes'])} shown")
        for q in d['quakes']: print(f"- {q.get('public_id')} M{q.get('magnitude'):.1f} MMI {q.get('mmi')} {q.get('locality')} {q.get('time')}")
    elif d['kind']=='quake':
        qs=d['quakes']; print(f"GeoNet quake {d['public_id']}: {len(qs)} result(s)")
        for q in qs: print(f"- M{q.get('magnitude'):.1f} depth {q.get('depth_km')}km {q.get('locality')} {q.get('time')}")
    elif d['kind']=='volcanoes':
        print(f"GeoNet volcano alert levels: {len(d['volcanoes'])}")
        for v in d['volcanoes']: print(f"- {v.get('title')}: level {v.get('level')} {v.get('acc')} — {v.get('activity')}")
    elif d['kind']=='news':
        print(f"GeoNet news: {len(d['items'])} shown")
        for n in d['items']: print(f"- {n.get('published')} {n.get('title')} ({n.get('tag')}) {n.get('link')}")
def cmd_quakes(a):
    data,url=get('quake',{'MMI':a.mmi})
    qs=[norm_feature(f) for f in data.get('features',[])]
    if a.min_mag is not None: qs=[q for q in qs if q.get('magnitude') is not None and q['magnitude']>=a.min_mag]
    out({'kind':'quakes','source':'geonet-nz','source_url':url,'mmi':a.mmi,'min_mag':a.min_mag,'quakes':qs[:a.limit]},a.json)
def cmd_quake(a):
    data,url=get('quake/'+a.public_id)
    qs=[norm_feature(f) for f in data.get('features',[])]
    out({'kind':'quake','source':'geonet-nz','source_url':url,'public_id':a.public_id,'quakes':qs},a.json)
def cmd_volcanoes(a):
    data,url=get('volcano/val')
    rows=[]
    for f in data.get('features',[]):
        p=f.get('properties') or {}; c=(f.get('geometry') or {}).get('coordinates') or []
        rows.append({'id':p.get('volcanoID'),'title':p.get('volcanoTitle'),'level':p.get('level'),'acc':p.get('acc'),'activity':p.get('activity'),'hazards':p.get('hazards'),'longitude':c[0] if len(c)>0 else None,'latitude':c[1] if len(c)>1 else None})
    out({'kind':'volcanoes','source':'geonet-nz','source_url':url,'volcanoes':rows},a.json)
def cmd_news(a):
    data,url=get('news/geonet')
    out({'kind':'news','source':'geonet-nz','source_url':url,'total':data.get('total'),'items':(data.get('feed') or [])[:a.limit]},a.json)
def main():
    p=argparse.ArgumentParser(description='Query GeoNet public feeds')
    sub=p.add_subparsers(dest='cmd',required=True)
    s=sub.add_parser('quakes'); s.add_argument('--mmi',type=int,default=3); s.add_argument('--min-mag',type=float); s.add_argument('--limit',type=int,default=10); s.add_argument('--json',action='store_true'); s.set_defaults(func=cmd_quakes)
    s=sub.add_parser('quake'); s.add_argument('public_id'); s.add_argument('--json',action='store_true'); s.set_defaults(func=cmd_quake)
    s=sub.add_parser('volcanoes'); s.add_argument('--json',action='store_true'); s.set_defaults(func=cmd_volcanoes)
    s=sub.add_parser('news'); s.add_argument('--limit',type=int,default=10); s.add_argument('--json',action='store_true'); s.set_defaults(func=cmd_news)
    a=p.parse_args(); a.func(a)
if __name__=='__main__': main()
