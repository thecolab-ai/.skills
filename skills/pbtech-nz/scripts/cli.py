#!/usr/bin/env python3
from __future__ import annotations
import argparse, html, json, re, sys, urllib.parse, urllib.request, urllib.error
from html.parser import HTMLParser
BASE='https://www.pbtech.co.nz'
HEADERS={
 'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36',
 'Accept':'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
 'Accept-Language':'en-US,en;q=0.9',
 'Referer':'https://www.pbtech.co.nz/',
 'Sec-Fetch-Dest':'document','Sec-Fetch-Mode':'navigate','Sec-Fetch-Site':'same-origin','Sec-Fetch-User':'?1',
 'Upgrade-Insecure-Requests':'1',
 'sec-ch-ua':'"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
 'sec-ch-ua-mobile':'?0','sec-ch-ua-platform':'"Windows"'
}
def die(m,c=1): print(f'pbtech-nz: {m}',file=sys.stderr); raise SystemExit(c)
def fetch(url):
 if url.startswith('/'): url=BASE+url
 try:
  with urllib.request.urlopen(urllib.request.Request(url,headers=HEADERS),timeout=40) as r:
   return r.read().decode('utf-8','replace'), r.geturl()
 except urllib.error.HTTPError as e: die(f'HTTP {e.code} from {url}: {e.read().decode("utf-8","replace")[:250]}')
 except Exception as e: die(f'failed fetching {url}: {e}')
def clean(s): return re.sub(r'\s+',' ',html.unescape(re.sub(r'<[^>]+>',' ',s or ''))).strip()
def abs_url(href):
 if not href: return None
 return href if href.startswith('http') else BASE+'/'+href.lstrip('/')
def price_from(block):
 # Prefer GST-inclusive ginc full price.
 m=re.search(r'<div class="ginc"[^>]*>.*?<span[^>]*class="[^"]*full-price[^"]*"[^>]*>(.*?)</span>', block, re.S)
 if not m: m=re.search(r'<span[^>]*class="[^"]*full-price[^"]*"[^>]*>(\$[0-9,]+(?:\.\d{2})?)</span>', block, re.S)
 if m: return clean(m.group(1))
 m=re.search(r'<span[^>]*class="[^"]*price-dollar[^"]*"[^>]*>(\$[0-9,]+)</span>\s*<span[^>]*class="[^"]*price-cents[^"]*"[^>]*>(\.[0-9]{2})</span>', block, re.S)
 return (m.group(1)+m.group(2)) if m else None
def numeric_price(p):
 if not p: return None
 m=re.search(r'([0-9][0-9,]*(?:\.\d+)?)',p)
 return float(m.group(1).replace(',','')) if m else None
def parse_cards(page, limit=20):
 items=[]; seen=set()
 for m in re.finditer(r'<a[^>]+data-product-code=["\']([^"\']+)["\'][^>]*>(.*?)</a>', page, re.S|re.I):
  code=m.group(1); start=max(0,m.start()-500); end=min(len(page),m.start()+18000); block=page[start:end]
  if code in seen: continue
  seen.add(code)
  href=re.search(r'href=["\']([^"\']*product/'+re.escape(code)+r'[^"\']*)["\']', m.group(0), re.I)
  title=clean(m.group(2)) or clean(re.search(r'title=["\']([^"\']+)',m.group(0)).group(1) if re.search(r'title=["\']([^"\']+)',m.group(0)) else '')
  if len(title)<4: continue
  subtitle=''
  hm=re.search(r'<h3[^>]*class="[^"]*np_title[^"]*"[^>]*>(.*?)</h3>', block, re.S|re.I)
  if hm: subtitle=clean(hm.group(1))
  img=re.search(r'<img[^>]+class="[^"]*product-image-thumb[^"]*"[^>]+src=["\']([^"\']+)', block, re.S|re.I)
  stock=re.search(r'<div[^>]+class="[^"]*js-stock-info[^"]*"([^>]*)>(.*?)</div>\s*</div>', block, re.S|re.I)
  attrs=stock.group(1) if stock else ''
  pb_stock=re.search(r'data-stock-pb=["\']([^"\']*)',attrs)
  other_stock=re.search(r'data-stock-other=["\']([^"\']*)',attrs)
  stock_text=clean(stock.group(2)) if stock else None
  price=price_from(block)
  items.append({'code':code,'title':title,'subtitle':subtitle or None,'price':price,'price_nzd':numeric_price(price),'url':abs_url(href.group(1) if href else f'/product/{code}'),'image':img.group(1) if img else None,'stock_pb':pb_stock.group(1) if pb_stock else None,'stock_other':other_stock.group(1) if other_stock else None,'stock_text':stock_text})
  if len(items)>=limit: break
 return items
def parse_product(page, url):
 code=re.search(r'/product/([A-Z0-9]+)',url)
 code=code.group(1) if code else None
 # Restrict extraction to the main product header/top section; detail pages also
 # contain combo/accessory cards that reuse product-card markup.
 h1pos=page.find('<h1')
 top=page[max(0,h1pos-15000):h1pos+90000] if h1pos!=-1 else page[:220000]
 h1=re.search(r'<h1[^>]*class="[^"]*np_title[^"]*"[^>]*>(.*?)</h1>',top,re.S|re.I)
 h3=re.search(r'<h3[^>]*class="[^"]*np_title[^"]*"[^>]*>(.*?)</h3>',top,re.S|re.I)
 title=clean((h1.group(1) if h1 else '')+' '+(h3.group(1) if h3 else ''))
 # Main detail price uses single-quoted ginc spans, unlike cards.
 price=None
 pm=re.search(r"<span class='ginc'[^>]*>.*?<span[^>]*>\$</span>\s*<span[^>]*>([0-9,]+)</span>\s*<span[^>]*>(\.[0-9]{2})</span>",page[:max(220000,h1pos+1000)],re.S|re.I)
 if pm: price='$'+pm.group(1)+pm.group(2)
 if not price:
  sm=re.search(r"<span class='sticky-price'>(\$[0-9,]+(?:\.\d{2})?)</span>",top,re.S|re.I)
  if sm: price=sm.group(1)
 facts={}
 for label,val in re.findall(r'<span class="fw-semibold">(Brand|MPN|Part #|UPC):?\s*</span>\s*(?:<a[^>]*>)?\s*<span>(.*?)</span>',top,re.S|re.I):
  facts[clean(label)]=clean(val)
 stock=re.search(r'<div[^>]+class="[^"]*js-stock-info[^"]*"([^>]*)>(.*?)</div>\s*</div>',top,re.S|re.I)
 attrs=stock.group(1) if stock else ''
 pb_stock=re.search(r'data-stock-pb=["\']([^"\']*)',attrs)
 other_stock=re.search(r'data-stock-other=["\']([^"\']*)',attrs)
 img=re.search(r"<meta property='og:image' content='([^']+)'",page,re.I)
 return {'code':code or facts.get('Part #'),'title':title or None,'price':price,'price_nzd':numeric_price(price),'url':url,'image':img.group(1) if img else None,'stock_pb':pb_stock.group(1) if pb_stock else None,'stock_other':other_stock.group(1) if other_stock else None,'stock_text':clean(stock.group(2)) if stock else None,'part_number':facts.get('Part #') or code,'mpn':facts.get('MPN'),'brand':facts.get('Brand')}
def parse_stores(page, limit=100, query=None):
 rows=[]
 for m in re.finditer(r'<div class="[^"]*stores[^"]*"[^>]*data-coord="\[([^\]]*)\]"[^>]*>(.*?)(?=<div class="col-12 col-xl-3 col-lg-4 col-sm-6 mb-4 stores |</div>\s*</div>\s*</div>\s*<footer)', page, re.S|re.I):
  block=m.group(2); coords=[x.strip() for x in m.group(1).split(',')]
  name=clean(re.search(r'<h3[^>]*class="[^"]*store-name[^"]*"[^>]*>(.*?)</h3>',block,re.S|re.I).group(1) if re.search(r'<h3[^>]*class="[^"]*store-name[^"]*"[^>]*>(.*?)</h3>',block,re.S|re.I) else '')
  addr=clean(re.search(r'<h4[^>]*class="[^"]*card-subtitle[^"]*"[^>]*>(.*?)</h4>',block,re.S|re.I).group(1) if re.search(r'<h4[^>]*class="[^"]*card-subtitle[^"]*"[^>]*>(.*?)</h4>',block,re.S|re.I) else '')
  phone=clean(re.search(r'href="tel:([^"]+)"[^>]*>(.*?)</a>',block,re.S|re.I).group(2) if re.search(r'href="tel:([^"]+)"[^>]*>(.*?)</a>',block,re.S|re.I) else '')
  link=re.search(r'href="(stores/[^"]+)"',block)
  maps=re.search(r'href="(https://www\.google\.com/maps/[^"]+)"',block)
  txt=clean(block)
  hours='; '.join(re.findall(r'(Monday - Friday\s*:\s*[^<]+|Saturday\s*:\s*[^<]+|Sunday\s*:\s*[^<]+)',block,re.I))
  row={'name':name,'address':addr,'phone':phone or None,'hours':clean(hours) or None,'latitude':float(coords[0]) if coords and coords[0] else None,'longitude':float(coords[1]) if len(coords)>1 and coords[1] else None,'url':abs_url(link.group(1) if link else None),'maps_url':maps.group(1) if maps else None}
  hay=(name+' '+addr+' '+txt).lower()
  if name and (not query or query.lower() in hay): rows.append(row)
  if len(rows)>=limit: break
 return rows
def output(data, as_json):
 if as_json: print(json.dumps(data,indent=2,ensure_ascii=False)); return
 if data['kind']=='search':
  print(f"PB Tech products for {data['query']!r}: {len(data['products'])} shown")
  for p in data['products']: print(f"- {p['code']} {p['title']} — {p.get('price') or 'price n/a'} — {p.get('stock_text') or ''} {p['url']}")
 elif data['kind']=='product':
  p=data['product']; print(f"{p.get('code')}: {p.get('title')} — {p.get('price') or 'price n/a'}"); print(p.get('url'))
  if p.get('stock_text'): print('Stock:',p['stock_text'])
 elif data['kind']=='stores':
  print(f"PB Tech stores: {len(data['stores'])} shown")
  for s in data['stores']: print(f"- {s['name']}: {s['address']} {s.get('phone') or ''} {s.get('url') or ''}")
def cmd_search(a):
 page,url=fetch(BASE+'/search?'+urllib.parse.urlencode({'sf':a.query}))
 products=parse_cards(page,a.limit)
 output({'kind':'search','source':'pbtech-nz','source_url':url,'query':a.query,'products':products},a.json)
def cmd_product(a):
 target=a.code_or_url
 url=target if target.startswith('http') else BASE+'/product/'+target
 page,final=fetch(url)
 output({'kind':'product','source':'pbtech-nz','source_url':final,'product':parse_product(page,final)},a.json)
def cmd_stores(a):
 page,url=fetch(BASE+'/stores')
 output({'kind':'stores','source':'pbtech-nz','source_url':url,'query':a.query,'stores':parse_stores(page,a.limit,a.query)},a.json)
def main():
 p=argparse.ArgumentParser(description='Query PB Tech NZ public product and store pages')
 sub=p.add_subparsers(dest='cmd',required=True)
 s=sub.add_parser('search'); s.add_argument('query'); s.add_argument('--limit',type=int,default=10); s.add_argument('--json',action='store_true'); s.set_defaults(func=cmd_search)
 s=sub.add_parser('product'); s.add_argument('code_or_url'); s.add_argument('--json',action='store_true'); s.set_defaults(func=cmd_product)
 s=sub.add_parser('stores'); s.add_argument('--query'); s.add_argument('--limit',type=int,default=20); s.add_argument('--json',action='store_true'); s.set_defaults(func=cmd_stores)
 a=p.parse_args(); a.func(a)
if __name__=='__main__': main()
