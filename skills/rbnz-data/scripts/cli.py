#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys,urllib.parse,urllib.request,urllib.error,zipfile,io,re,xml.etree.ElementTree as ET
from pathlib import Path
BASE='https://catalogue.data.govt.nz/api/3/action/'
ORG='reserve-bank-of-new-zealand'
EXCHANGE_RESOURCE='f16aa755-ba94-4679-8c5f-4c1cb6c2901a'
CHARTS={
 'twi':'{39B96144-129C-4D86-AEA9-DAB75CDE26F4}',
 'retail-rates':'{9E689530-C72C-493C-B41C-C9750BDD2C69}',
}
BROWSER_HEADERS={
 'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36',
 'Accept':'application/json, text/plain, application/vnd.openxmlformats-officedocument.spreadsheetml.sheet, */*',
 'Accept-Language':'en-US,en;q=0.9',
 'Referer':'https://www.rbnz.govt.nz/statistics',
 'Sec-Fetch-Dest':'empty',
 'Sec-Fetch-Mode':'cors',
 'Sec-Fetch-Site':'same-origin',
 'sec-ch-ua':'"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
 'sec-ch-ua-mobile':'?0',
 'sec-ch-ua-platform':'"Windows"',
}
def die(m,c=1): print(f'rbnz-data: {m}',file=sys.stderr); raise SystemExit(c)
def http_text(url, headers=None, timeout=30):
 try: return urllib.request.urlopen(urllib.request.Request(url,headers=headers or BROWSER_HEADERS),timeout=timeout).read().decode()
 except urllib.error.HTTPError as e: die(f'HTTP {e.code} from {url}: {e.read().decode("utf-8","replace")[:250]}')
 except Exception as e: die(f'failed calling {url}: {e}')
def http_bytes(url, timeout=60):
 try:
  with urllib.request.urlopen(urllib.request.Request(url,headers=BROWSER_HEADERS),timeout=timeout) as r: return r.read(), r.headers.get('content-type')
 except urllib.error.HTTPError as e: die(f'HTTP {e.code} from {url}: {e.read().decode("utf-8","replace")[:250]}')
 except Exception as e: die(f'failed downloading {url}: {e}')
def get(action, params):
 url=BASE+action+'?'+urllib.parse.urlencode({k:v for k,v in params.items() if v is not None})
 data=json.loads(http_text(url, {'User-Agent':BROWSER_HEADERS['User-Agent'],'Accept':'application/json'}))
 if not data.get('success'): die(f'API returned success=false: {data.get("error")}')
 return data['result'],url
def norm_pkg(p):
 return {'id':p.get('id'),'name':p.get('name'),'title':p.get('title'),'notes':p.get('notes'),'frequency_of_update':p.get('frequency_of_update'),'metadata_modified':p.get('metadata_modified'),'resources':len(p.get('resources') or []),'url':f"https://catalogue.data.govt.nz/dataset/{p.get('name')}"}
def resource_list(pkg):
 return [{k:r.get(k) for k in ['id','name','format','url','datastore_active','last_modified']} for r in pkg.get('resources',[])]
def parse_xlsx(data, max_rows=8, sheet='Data'):
 z=zipfile.ZipFile(io.BytesIO(data))
 ns={'a':'http://schemas.openxmlformats.org/spreadsheetml/2006/main','r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
 shared=[]
 if 'xl/sharedStrings.xml' in z.namelist():
  root=ET.fromstring(z.read('xl/sharedStrings.xml'))
  for si in root.findall('.//a:si',ns): shared.append(''.join(t.text or '' for t in si.findall('.//a:t',ns)))
 wb=ET.fromstring(z.read('xl/workbook.xml'))
 rels=ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
 relmap={r.attrib['Id']:r.attrib['Target'] for r in rels}
 target=None; sheets=[]
 for s in wb.findall('.//a:sheet',ns):
  name=s.attrib.get('name'); rid=s.attrib.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
  path='xl/'+relmap.get(rid,'').lstrip('/')
  sheets.append(name)
  if name==sheet or target is None: target=path
 if not target or target not in z.namelist(): die(f'could not find worksheet {sheet!r}; sheets={sheets}')
 root=ET.fromstring(z.read(target))
 rows=[]
 for row in root.findall('.//a:sheetData/a:row',ns):
  vals=[]
  for c in row.findall('a:c',ns):
   t=c.attrib.get('t'); v=c.find('a:v',ns)
   text=''
   if t=='s' and v is not None:
    idx=int(v.text or 0); text=shared[idx] if idx < len(shared) else ''
   elif t=='inlineStr':
    text=''.join(x.text or '' for x in c.findall('.//a:t',ns))
   elif v is not None: text=v.text or ''
   vals.append(text)
  if any(x not in ('',None) for x in vals): rows.append(vals)
  if len(rows)>=max_rows: break
 return {'sheets':sheets,'sheet':sheet,'rows':rows}
def choose_resource(pkg, match):
 resources=pkg.get('resources',[])
 if match:
  m=match.lower(); resources=[r for r in resources if m in (r.get('name') or '').lower() or m in (r.get('id') or '').lower() or m in (r.get('url') or '').lower()]
 else:
  resources=[r for r in resources if 'xlsx' in (r.get('url') or '').lower() or 'xls' in (r.get('format') or '').lower()]
 if not resources: die('no matching resource found')
 return resources[0]
def out(d,j):
 if j: print(json.dumps(d,indent=2,ensure_ascii=False)); return
 if d['kind']=='search':
  print(f"RBNZ datasets for {d['query']!r}: {d['count']} total")
  for x in d['datasets']: print(f"- {x['name']}: {x['title']} | resources {x['resources']}")
 elif d['kind']=='dataset':
  x=d['dataset']; print(f"{x['name']}: {x['title']}"); print((x.get('notes') or '')[:500].replace('\n',' '));
  for r in x.get('resource_list',[])[:12]: print(f"- {r.get('id')} {r.get('name')} [{r.get('format') or '-'}] datastore={r.get('datastore_active')} {r.get('url')}")
 elif d['kind']=='exchange-rates':
  print(f"RBNZ exchange-rate datastore preview: {len(d['records'])} records")
  for r in d['records']: print('- '+json.dumps(r,ensure_ascii=False)[:300])
 elif d['kind']=='download':
  print(f"Downloaded {d['bytes']} bytes from {d['resource']['name']}")
  if d.get('output'): print(f"Saved: {d['output']}")
  if d.get('preview'):
   for row in d['preview']['rows']: print('- '+ ' | '.join(row[:8]))
 elif d['kind']=='chart':
  print(f"RBNZ chart {d['chart']}: {len(d['data'])} points")
  for row in d['data'][-d['limit']:]: print('- '+json.dumps(row,ensure_ascii=False))
def cmd_search(a):
 res,url=get('package_search',{'fq':'organization:'+ORG,'q':a.query,'rows':a.limit})
 out({'kind':'search','source':'rbnz-data','source_url':url,'query':a.query,'count':res.get('count'),'datasets':[norm_pkg(p) for p in res.get('results',[])]},a.json)
def cmd_dataset(a):
 p,url=get('package_show',{'id':a.id}); d=norm_pkg(p); d['resource_list']=resource_list(p)
 out({'kind':'dataset','source':'rbnz-data','source_url':url,'dataset':d},a.json)
def cmd_exchange(a):
 res,url=get('datastore_search',{'resource_id':EXCHANGE_RESOURCE,'limit':a.limit})
 rows=[r for r in res.get('records',[]) if any(v not in (None,'') for k,v in r.items() if k!='_id')]
 out({'kind':'exchange-rates','source':'rbnz-data','source_url':url,'resource_id':EXCHANGE_RESOURCE,'total':res.get('total'),'records':rows[:a.limit]},a.json)
def cmd_download(a):
 p,_=get('package_show',{'id':a.dataset}); r=choose_resource(p,a.match); data,ct=http_bytes(r['url']); preview=None
 if a.preview or (not a.output and r.get('url','').lower().endswith(('.xlsx','.xls'))): preview=parse_xlsx(data,a.rows,a.sheet)
 outpath=None
 if a.output:
  path=Path(a.output); path.write_bytes(data); outpath=str(path)
 out({'kind':'download','source':'rbnz-data','dataset':p.get('name'),'resource':{k:r.get(k) for k in ['id','name','format','url']},'content_type':ct,'bytes':len(data),'output':outpath,'preview':preview},a.json)
def cmd_chart(a):
 cid=CHARTS.get(a.chart,a.chart)
 url='https://www.rbnz.govt.nz/api/cache/chart/data/'+urllib.parse.quote(cid, safe='')
 data=json.loads(http_text(url)); rows=data.get('Data') or []
 out({'kind':'chart','source':'rbnz-data','source_url':url,'chart':a.chart,'chart_id':cid,'limit':a.limit,'data':rows},a.json)
def main():
 p=argparse.ArgumentParser(description='Discover and fetch RBNZ public data')
 sub=p.add_subparsers(dest='cmd',required=True)
 s=sub.add_parser('search'); s.add_argument('query'); s.add_argument('--limit',type=int,default=10); s.add_argument('--json',action='store_true'); s.set_defaults(func=cmd_search)
 s=sub.add_parser('dataset'); s.add_argument('id'); s.add_argument('--json',action='store_true'); s.set_defaults(func=cmd_dataset)
 s=sub.add_parser('exchange-rates'); s.add_argument('--limit',type=int,default=5); s.add_argument('--json',action='store_true'); s.set_defaults(func=cmd_exchange)
 s=sub.add_parser('download'); s.add_argument('dataset'); s.add_argument('--match',help='resource name/id/url substring, e.g. daily or B2'); s.add_argument('--output'); s.add_argument('--preview',action='store_true'); s.add_argument('--sheet',default='Data'); s.add_argument('--rows',type=int,default=8); s.add_argument('--json',action='store_true'); s.set_defaults(func=cmd_download)
 s=sub.add_parser('chart'); s.add_argument('chart',help='chart alias: twi, retail-rates, or raw chart GUID'); s.add_argument('--limit',type=int,default=5); s.add_argument('--json',action='store_true'); s.set_defaults(func=cmd_chart)
 a=p.parse_args(); a.func(a)
if __name__=='__main__': main()
