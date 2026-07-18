#!/usr/bin/env python3
"""Read-only Raw Essentials NZ public catalogue and store CLI."""
from __future__ import annotations
import argparse, datetime as dt, html, json, math, re, sys, urllib.error, urllib.parse, urllib.request
from html.parser import HTMLParser

BASE="https://rawessentials.co.nz"; UA="TheColabSkills/1.0 (+https://github.com/thecolab-ai/.skills; read-only)"; MAX=50; MAX_BYTES=5_000_000
class CliError(Exception): pass
def allowed(url):
 try:p=urllib.parse.urlparse(url);port=p.port
 except ValueError:return False
 return p.scheme=="https" and p.hostname in {"rawessentials.co.nz","www.rawessentials.co.nz"} and p.username is None and p.password is None and port in (None,443)
class StorefrontRedirectHandler(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,req,fp,code,msg,headers,newurl):
  if not allowed(newurl):raise CliError("refusing redirect outside the Raw Essentials HTTPS storefront")
  return super().redirect_request(req,fp,code,msg,headers,newurl)
def stamp(): return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00","Z")
def number(v):
 try: n=int(v)
 except ValueError as e: raise argparse.ArgumentTypeError("must be an integer") from e
 if not 1<=n<=MAX: raise argparse.ArgumentTypeError(f"must be 1-{MAX}")
 return n
def get(url, timeout):
 if not allowed(url): raise CliError("refusing request outside the Raw Essentials HTTPS storefront")
 try:
  with urllib.request.build_opener(StorefrontRedirectHandler()).open(urllib.request.Request(url,headers={"User-Agent":UA,"Accept":"text/html,application/xhtml+xml"}),timeout=timeout) as r:
   if not allowed(r.url): raise CliError("refusing response outside the Raw Essentials HTTPS storefront")
   body=r.read(MAX_BYTES+1)
   if len(body)>MAX_BYTES: raise CliError("upstream response exceeded the 5 MB safety limit")
   return body.decode("utf-8","replace"),r.url
 except urllib.error.HTTPError as e: raise CliError(f"upstream returned HTTP {e.code} for {url}") from e
 except (urllib.error.URLError,TimeoutError,OSError) as e: raise CliError(f"network error for {url}: {getattr(e,'reason',str(e))}") from e
def text(value): return re.sub(r"\s+"," ",html.unescape(re.sub(r"<[^>]+>"," ",value))).strip()
class ProductMetadataParser(HTMLParser):
 def __init__(self):super().__init__();self.meta={};self.json_ld=[];self._in_json_ld=False;self._script=[]
 def handle_starttag(self,tag,attrs):
  values={key.casefold():value for key,value in attrs if value is not None}
  if tag.casefold()=="meta":
   key=(values.get("property") or values.get("name") or "").casefold()
   if key and "content" in values:self.meta[key]=values["content"]
  if tag.casefold()=="script" and values.get("type","").casefold()=="application/ld+json":self._in_json_ld=True;self._script=[]
 def handle_data(self,data):
  if self._in_json_ld:self._script.append(data)
 def handle_endtag(self,tag):
  if tag.casefold()=="script" and self._in_json_ld:self.json_ld.append("".join(self._script));self._in_json_ld=False
def amount(value):
 raw=str(value).strip()
 if not re.fullmatch(r"(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)(?:\.[0-9]+)?",raw):return None
 try:price=float(raw.replace(",",""))
 except (TypeError,ValueError):return None
 return round(price,2) if math.isfinite(price) and price>=0 else None
def product_nodes(value):
 if isinstance(value,dict):
  kind=value.get("@type",[]);kinds=kind if isinstance(kind,list) else [kind]
  if any(str(item).casefold()=="product" for item in kinds):yield value
  for child in value.values():yield from product_nodes(child)
 elif isinstance(value,list):
  for child in value:yield from product_nodes(child)
def json_ld_products(raw):
 try:return list(product_nodes(json.loads(raw)))
 except (ValueError,RecursionError):return []
def product_price(page):
 parser=ProductMetadataParser();parser.feed(page)
 for raw in parser.json_ld:
  for product in json_ld_products(raw):
   offers=product.get("offers",[]);offers=offers if isinstance(offers,list) else [offers]
   for offer in offers:
    if not isinstance(offer,dict):continue
    price=amount(offer.get("price",offer.get("lowPrice")))
    if price is not None and str(offer.get("priceCurrency","")).upper()=="NZD":return price,f"NZ${price:.2f}"
 for prefix in ("product:price","og:price"):
  price=amount(parser.meta.get(prefix+":amount"));currency=parser.meta.get(prefix+":currency","")
  if price is not None and currency.upper()=="NZD":return price,f"NZ${price:.2f}"
 return None,None
def links(page, base):
 by_url={}; rows=[]
 for href,label in re.findall(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',page,re.I|re.S):
  url=urllib.parse.urljoin(base,html.unescape(href)); title=text(label)
  if allowed(url) and urllib.parse.urlparse(url).path.startswith("/product/"):
   if url not in by_url:
    by_url[url]={"title":title,"url":url}; rows.append(by_url[url])
   elif title and not by_url[url]["title"]:
    by_url[url]["title"]=title
 return [row for row in rows if row["title"]]
def search(query, pet_type, page, max_results, timeout):
 if not query.strip(): raise CliError("search query must not be empty")
 url=BASE+"/products?"+urllib.parse.urlencode({"petType":pet_type,"search":query,"page":page})
 body,final=get(url,timeout); needle=query.casefold(); rows=[r for r in links(body,final) if needle in r["title"].casefold() or needle in r["url"].casefold()]
 return {"source":"raw-essentials-public-html","source_url":final,"retrieved_at":stamp(),"query":query,"pet_type":pet_type,"page":page,"limit":max_results,"results":rows[:max_results],"note":"Public catalogue snapshot only; raw feeding and supplement suitability are not veterinary advice."}
def detail(value, timeout):
 url=urllib.parse.urljoin(BASE,value) if not value.startswith("http") else value
 if not allowed(url) or not urllib.parse.urlparse(url).path.startswith("/product/"): raise CliError("provide a Raw Essentials HTTPS /product/ URL")
 body,final=get(url,timeout); title=re.search(r'<h1\b[^>]*>(.*?)</h1>',body,re.I|re.S) or re.search(r'<title>(.*?)</title>',body,re.I|re.S); description=re.search(r'<meta\s+name=["\']description["\']\s+content=["\']([^"\']+)',body,re.I);price,price_text=product_price(body)
 return {"source":"raw-essentials-public-html","source_url":final,"retrieved_at":stamp(),"product":{"title":text(title.group(1)) if title else "","url":final,"description":html.unescape(description.group(1)) if description else None,"price_nzd":price,"price_text":price_text,"price_note":"Advertised Product offer; variants and unit pricing may differ." if price is not None else None},"note":"Public product page snapshot only; verify variants, pack sizes and unit pricing on the product page. Product suitability is not veterinary advice."}
def stores(timeout):
 body,final=get(BASE+"/stores",timeout); matches=[]
 for name,address in re.findall(r'<h[2-4][^>]*>(.*?)</h[2-4]>(.{0,1200})',body,re.I|re.S):
  clean=text(name)
  if clean and ("store" in clean.casefold() or "raw essentials" in clean.casefold()): matches.append({"name":clean,"context":text(address)[:350]})
 return {"source":"raw-essentials-public-html","source_url":final,"retrieved_at":stamp(),"results":matches[:MAX]}
def emit(data,as_json):
 if as_json: print(json.dumps(data,ensure_ascii=False,indent=2));return
 for r in data.get("results", [data.get("product")] if data.get("product") else []): print(f"{r.get('title',r.get('name',''))} | {r.get('url','')}")
def main():
 ap=argparse.ArgumentParser(description="Read-only Raw Essentials NZ public catalogue, detail and store CLI."); ap.add_argument("--timeout",type=number,default=10,help="network timeout seconds, 1-50 (default: 10)"); sub=ap.add_subparsers(dest="cmd",required=True)
 s=sub.add_parser("search",help="search public product listing HTML");s.add_argument("query");s.add_argument("--pet-type",choices=("dog","cat"),default="dog");s.add_argument("--page",type=number,default=1);s.add_argument("--limit",type=number,default=12);s.add_argument("--json",action="store_true")
 p=sub.add_parser("product",help="fetch a public product URL");p.add_argument("url");p.add_argument("--json",action="store_true")
 t=sub.add_parser("stores",help="list public store-page headings");t.add_argument("--json",action="store_true")
 a=ap.parse_args()
 try: data=search(a.query,a.pet_type,a.page,a.limit,a.timeout) if a.cmd=="search" else detail(a.url,a.timeout) if a.cmd=="product" else stores(a.timeout);emit(data,a.json)
 except CliError as e: print(f"raw-essentials-nz: {e}",file=sys.stderr);return 1
 return 0
if __name__=="__main__":raise SystemExit(main())
