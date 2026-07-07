#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,re,sys,pathlib,urllib.parse,html
from html.parser import HTMLParser
from typing import Any
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "lib"))
import nzfetch  # noqa: E402
BASE='https://www.lawa.org.nz'
UA='Mozilla/5.0'
def die(m,c=1): print(f'lawa-nz: {m}',file=sys.stderr); raise SystemExit(c)
def get(path, params=None):
    url=BASE+path
    if params: url+='?'+urllib.parse.urlencode({k:v for k,v in params.items() if v is not None})
    try:
        return nzfetch.fetch_json(url,timeout=45,accept='application/json,text/plain,*/*'), url
    except nzfetch.Blocked as e: die(f'network error calling {url}: {e}')
    except nzfetch.FetchError as e: die(str(e))
    except Exception as e: die(f'failed calling {url}: {e}')
def clean(s): return ' '.join(html.unescape(re.sub('<[^>]+>',' ',s or '')).split())
class CardParser(HTMLParser):
    def __init__(self): super().__init__(); self.cards=[]; self.cur=None; self.in_h=False; self.in_p=False; self.in_grade=False; self.buf=[]
    def handle_starttag(self, tag, attrs):
        a=dict(attrs)
        cls=a.get('class','')
        if tag=='a' and a.get('href'):
            self.cur={'url':urllib.parse.urljoin(BASE,a['href']),'title':'','subtitle':'','grade':''}
        if self.cur is not None and tag=='h6': self.in_h=True; self.buf=[]
        if self.cur is not None and tag=='p': self.in_p=True; self.buf=[]
        if self.cur is not None and tag=='span' and 'grade-icon--label' in cls: self.in_grade=True; self.buf=[]
    def handle_data(self,d):
        if self.in_h or self.in_p or self.in_grade: self.buf.append(d)
    def handle_endtag(self, tag):
        if self.cur is not None and tag=='h6' and self.in_h: self.cur['title']=clean(' '.join(self.buf)); self.in_h=False
        elif self.cur is not None and tag=='p' and self.in_p and not self.cur.get('subtitle'): self.cur['subtitle']=clean(' '.join(self.buf)); self.in_p=False
        elif self.cur is not None and tag=='span' and self.in_grade: self.cur['grade']=clean(' '.join(self.buf)); self.in_grade=False
        elif tag=='a' and self.cur is not None:
            self.cards.append(self.cur); self.cur=None

def out(d,j):
    if j: print(json.dumps(d,indent=2,ensure_ascii=False)); return
    if d['kind']=='river-sites':
        print(f"LAWA river sites for {d.get('query') or 'all'}: {len(d['sites'])} shown")
        for x in d['sites']: print(f"- {x.get('name')} ({x.get('code') or x.get('lawa_id') or x.get('id')}) {x.get('url') or ''}")
    elif d['kind']=='swim-sites':
        print(f"LAWA swim sites for {d.get('query') or 'all'}: {d.get('total')} total, {len(d['sites'])} shown")
        for x in d['sites']: print(f"- {x.get('title')} — {x.get('subtitle')} | {x.get('grade') or '-'} | {x.get('url')}")
    elif d['kind']=='indicators':
        print(f"LAWA indicators: {len(d['indicators'])} shown")
        for x in d['indicators']: print(f"- {x.get('LawaId')} {x.get('Parameter')}: median={x.get('Median')} band={x.get('NofBand')} trend10={x.get('TrendScore10Year')}")

def norm_site(x):
    return {'id':x.get('Id'),'lawa_id':x.get('ParentLawaId') or x.get('Code'),'name':x.get('Name'),'code':x.get('Code'),'latitude':x.get('Latitude'),'longitude':x.get('Longitude'),'url':urllib.parse.urljoin(BASE,x.get('Url') or ''),'site_type':x.get('SiteType'),'data_type':x.get('DataType'),'has_scientific_data':x.get('HasScientificData'),'has_ecology_data':x.get('HasEcologyData'),'is_background':x.get('IsBackground')}
def cmd_river(a):
    arr,url=get('/umbraco/api/mapservice/RiverQualitySites')
    sites=[norm_site(x) for x in arr if isinstance(x,dict)]
    if a.query:
        q=a.query.lower(); sites=[s for s in sites if q in (s.get('name') or '').lower() or q in (s.get('code') or '').lower() or q in (s.get('url') or '').lower()]
    out({'kind':'river-sites','source':'lawa-nz','source_url':url,'query':a.query,'sites':sites[:a.limit]},a.json)
def cmd_swim(a):
    data,url=get('/umbraco/api/swimservice/getswimsites',{'regionid':'','sitetype':'','sortby':'status','siteName':a.query or ''})
    parser=CardParser()
    for frag in data.get('ResultList',[]): parser.feed(frag)
    out({'kind':'swim-sites','source':'lawa-nz','source_url':url,'query':a.query,'total':data.get('TotalResultCount'),'next_index':data.get('NextIndex'),'sites':parser.cards[:a.limit]},a.json)
def cmd_ind(a):
    n,url1=get('/umbraco/api/commonapi/GetNonMciIndicatorDataForAllLocations'); m,url2=get('/umbraco/api/commonapi/GetMciIndicatorDataForAllLocations')
    rows=[x for x in (n+m) if isinstance(x,dict)]
    if a.lawa_id: rows=[r for r in rows if str(r.get('LawaId','')).lower()==a.lawa_id.lower()]
    if a.parameter: rows=[r for r in rows if str(r.get('Parameter','')).lower()==a.parameter.lower()]
    out({'kind':'indicators','source':'lawa-nz','source_url':[url1,url2],'lawa_id':a.lawa_id,'parameter':a.parameter,'indicators':rows[:a.limit]},a.json)
def main():
    p=argparse.ArgumentParser(description='Query LAWA public environmental data')
    sub=p.add_subparsers(dest='cmd',required=True)
    s=sub.add_parser('river-sites'); s.add_argument('--query'); s.add_argument('--limit',type=int,default=20); s.add_argument('--json',action='store_true'); s.set_defaults(func=cmd_river)
    s=sub.add_parser('swim-sites'); s.add_argument('--query'); s.add_argument('--limit',type=int,default=20); s.add_argument('--json',action='store_true'); s.set_defaults(func=cmd_swim)
    s=sub.add_parser('indicators'); s.add_argument('--lawa-id'); s.add_argument('--parameter'); s.add_argument('--limit',type=int,default=20); s.add_argument('--json',action='store_true'); s.set_defaults(func=cmd_ind)
    a=p.parse_args(); a.func(a)
if __name__=='__main__': main()
