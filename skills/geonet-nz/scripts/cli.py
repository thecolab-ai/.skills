#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,re,sys,urllib.parse
import pathlib
from typing import Any
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "lib"))
import nzfetch  # noqa: E402
BASE='https://api.geonet.org.nz/'
TILDE='https://tilde.geonet.org.nz/v4/'
TILDE_WINDOWS=('30m','6h','1d','2d','7d','30d')
UA='Mozilla/5.0'
def die(m,c=1): print(f'geonet-nz: {m}',file=sys.stderr); raise SystemExit(c)
def get(path, params=None):
    url=BASE+path
    if params: url+='?'+urllib.parse.urlencode({k:v for k,v in params.items() if v is not None})
    try:
        return nzfetch.fetch_json(url,timeout=30,accept='application/json,application/vnd.geo+json'), url
    except nzfetch.Blocked as e: die(f'network error: {e}')
    except nzfetch.FetchError as e: die(str(e))
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
    elif d['kind']=='tilde-domains':
        print(f"Tilde data domains: {len(d['domains'])}")
        for r in d['domains']: print(f"- {r['domain']}: {r['description']} ({r['stations']} stations, latest {r['latest_record']})")
    elif d['kind']=='tilde-stations':
        print(f"Tilde {d['domain']} stations: {len(d['stations'])}")
        for r in d['stations']: print(f"- {r['station']} {r['locality']} ({r['latitude']}, {r['longitude']}) series: {', '.join(r['names'])}")
    elif d['kind']=='tilde-latest':
        print(f"{d['station']} {d['name']} ({d['domain']}, {d['method']}): {d['latest_value']} at {d['latest_time']} UTC")
        print(f"  last {d['window']}: min {d['window_min']} max {d['window_max']} over {d['observations']} observations")
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
def tilde_get(path):
    url=TILDE+path
    try:
        return nzfetch.fetch_json(url,timeout=30,accept='application/json'), url
    except nzfetch.Blocked as e: die(f'network error: {e}',4)
    except nzfetch.FetchError as e: die(f'upstream unavailable: {e}',5)
def tilde_domain_arg(raw):
    if not re.fullmatch(r'[a-z0-9-]+',raw or ''): die(f'invalid Tilde domain {raw!r}; list domains with tilde-domains',2)
    return raw
def tilde_station_rows(domain_summary):
    rows=[]
    for st in (domain_summary.get('stations') or {}).values():
        names=sorted({n for sc in (st.get('sensorCodes') or {}).values() for n in (sc.get('names') or {})})
        rows.append({'station':st.get('station'),'locality':st.get('stationLocality'),'latitude':st.get('latitude'),'longitude':st.get('longitude'),'names':names})
    return sorted(rows,key=lambda r:r['station'] or '')
def tilde_first_series(domain_summary,station,name):
    """Pick the series with the freshest data (DART water-height only exists during events)."""
    st=(domain_summary.get('stations') or {}).get(station)
    if not st: die(f'unknown station {station!r}; list stations with tilde-stations',2)
    best=None
    for code in sorted(st.get('sensorCodes') or {}):
        for n,series in sorted((st['sensorCodes'][code].get('names') or {}).items()):
            if name and n!=name: continue
            for method,mrec in sorted((series.get('methods') or {}).items()):
                for aspect,arec in sorted((mrec.get('aspects') or {}).items()):
                    candidate={'name':n,'sensor_code':code,'method':method,'aspect':aspect,'series_latest_record':(arec or {}).get('latestRecord') or ''}
                    if best is None or candidate['series_latest_record']>best['series_latest_record']: best=candidate
    if best is None:
        die(f'station {station!r} has no series named {name!r}; list names with tilde-stations',2)
    return best
def tilde_series_summary(points):
    numeric=[p for p in points if isinstance(p.get('val'),(int,float))]
    if not numeric: return None
    vals=[p['val'] for p in numeric]; latest=numeric[-1]
    return {'latest_value':latest['val'],'latest_time':latest.get('ts'),'window_min':min(vals),'window_max':max(vals),'observations':len(vals)}
def cmd_tilde_domains(a):
    data,url=tilde_get('dataSummary/')
    rows=[{'domain':d.get('domain'),'description':d.get('description'),'stations':d.get('stationCount'),'latest_record':d.get('latestRecord')} for d in (data.get('domains') or {}).values()]
    out({'kind':'tilde-domains','source':'geonet-nz','source_url':url,'domains':sorted(rows,key=lambda r:r['domain'] or '')},a.json)
def cmd_tilde_stations(a):
    data,url=tilde_get('dataSummary/'+tilde_domain_arg(a.domain))
    summary=(data.get('domain') or {}).get(a.domain)
    if not summary: die(f'unknown Tilde domain {a.domain!r}; list domains with tilde-domains',2)
    out({'kind':'tilde-stations','source':'geonet-nz','source_url':url,'domain':a.domain,'stations':tilde_station_rows(summary)},a.json)
def cmd_tilde_latest(a):
    if a.window not in TILDE_WINDOWS: die(f'invalid --window {a.window!r}; allowed: {", ".join(TILDE_WINDOWS)}',2)
    data,_=tilde_get('dataSummary/'+tilde_domain_arg(a.domain))
    summary=(data.get('domain') or {}).get(a.domain)
    if not summary: die(f'unknown Tilde domain {a.domain!r}; list domains with tilde-domains',2)
    series=tilde_first_series(summary,a.station,a.name)
    path=f"data/{a.domain}/{a.station}/{series['name']}/{series['sensor_code']}/{series['method']}/{series['aspect']}/latest/{a.window}"
    rows,url=tilde_get(path)
    points=(rows[0].get('data') or []) if isinstance(rows,list) and rows else []
    stats=tilde_series_summary(points)
    if not stats:
        hint='another --name' if a.window=='30d' else 'a wider --window or another --name'
        die(f'no observations for {a.station} {series["name"]} in the last {a.window} (series last recorded {series["series_latest_record"] or "never"}); try {hint}',5)
    out({'kind':'tilde-latest','source':'geonet-nz','source_url':url,'domain':a.domain,'station':a.station,**series,'window':a.window,**stats},a.json)
def main():
    p=argparse.ArgumentParser(description='Query GeoNet public feeds')
    sub=p.add_subparsers(dest='cmd',required=True)
    s=sub.add_parser('quakes'); s.add_argument('--mmi',type=int,default=3); s.add_argument('--min-mag',type=float); s.add_argument('--limit',type=int,default=10); s.add_argument('--json',action='store_true'); s.set_defaults(func=cmd_quakes)
    s=sub.add_parser('quake'); s.add_argument('public_id'); s.add_argument('--json',action='store_true'); s.set_defaults(func=cmd_quake)
    s=sub.add_parser('volcanoes'); s.add_argument('--json',action='store_true'); s.set_defaults(func=cmd_volcanoes)
    s=sub.add_parser('news'); s.add_argument('--limit',type=int,default=10); s.add_argument('--json',action='store_true'); s.set_defaults(func=cmd_news)
    s=sub.add_parser('tilde-domains'); s.add_argument('--json',action='store_true'); s.set_defaults(func=cmd_tilde_domains)
    s=sub.add_parser('tilde-stations'); s.add_argument('domain'); s.add_argument('--json',action='store_true'); s.set_defaults(func=cmd_tilde_stations)
    s=sub.add_parser('tilde-latest'); s.add_argument('domain'); s.add_argument('station'); s.add_argument('--name'); s.add_argument('--window',default='6h'); s.add_argument('--json',action='store_true'); s.set_defaults(func=cmd_tilde_latest)
    a=p.parse_args(); a.func(a)
if __name__=='__main__': main()
