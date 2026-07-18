#!/usr/bin/env python3
"""Read-only Raw Essentials NZ public catalogue and store CLI."""
from __future__ import annotations
import argparse, datetime as dt, html, json, re, sys, urllib.error, urllib.parse, urllib.request

BASE="https://rawessentials.co.nz"; UA="TheColabSkills/1.0 (+https://github.com/thecolab-ai/.skills; read-only)"; MAX=50; MAX_BYTES=5_000_000
class CliError(Exception): pass
def allowed(url):
 p=urllib.parse.urlparse(url);return p.scheme=="https" and p.hostname in {"rawessentials.co.nz","www.rawessentials.co.nz"}
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
def links(page, base):
 seen=set(); rows=[]
 for href,label in re.findall(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',page,re.I|re.S):
  url=urllib.parse.urljoin(base,html.unescape(href)); title=text(label)
  if allowed(url) and "/products/" in urllib.parse.urlparse(url).path and title and url not in seen:
   seen.add(url); rows.append({"title":title,"url":url})
 return rows
def search(query, pet_type, page, max_results, timeout):
 if not query.strip(): raise CliError("search query must not be empty")
 url=BASE+"/products?"+urllib.parse.urlencode({"petType":pet_type,"search":query,"page":page})
 body,final=get(url,timeout); needle=query.casefold(); rows=[r for r in links(body,final) if needle in r["title"].casefold() or needle in r["url"].casefold()]
 return {"source":"raw-essentials-public-html","source_url":final,"retrieved_at":stamp(),"query":query,"pet_type":pet_type,"page":page,"limit":max_results,"results":rows[:max_results],"note":"Public catalogue snapshot only; raw feeding and supplement suitability are not veterinary advice."}
def detail(value, timeout):
 url=urllib.parse.urljoin(BASE,value) if not value.startswith("http") else value
 if not allowed(url) or "/products/" not in urllib.parse.urlparse(url).path: raise CliError("provide a Raw Essentials HTTPS /products/ URL")
 body,final=get(url,timeout); title=re.search(r'<h1\b[^>]*>(.*?)</h1>',body,re.I|re.S) or re.search(r'<title>(.*?)</title>',body,re.I|re.S); description=re.search(r'<meta\s+name=["\']description["\']\s+content=["\']([^"\']+)',body,re.I)
 prices=[text(x) for x in re.findall(r'<[^>]+(?:price|Price)[^>]*>(.*?)</[^>]+>',body,re.I|re.S)][:8]
 return {"source":"raw-essentials-public-html","source_url":final,"retrieved_at":stamp(),"product":{"title":text(title.group(1)) if title else "","url":final,"description":html.unescape(description.group(1)) if description else None,"price_text":prices},"note":"Public product page snapshot only; product suitability is not veterinary advice."}
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
