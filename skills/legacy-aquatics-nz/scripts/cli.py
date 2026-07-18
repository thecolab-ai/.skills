#!/usr/bin/env python3
"""Read-only Legacy Aquatics NZ WooCommerce public catalogue CLI."""
from __future__ import annotations
import argparse, datetime as dt, html, json, re, sys, urllib.error, urllib.parse, urllib.request
BASE="https://legacyaquatics.co.nz"; UA="TheColabSkills/1.0 (+https://github.com/thecolab-ai/.skills; read-only)"; MAX=50; MAX_BYTES=5_000_000
class CliError(Exception): pass
def allowed(url):
 try:p=urllib.parse.urlparse(url);port=p.port
 except ValueError:return False
 return p.scheme=="https" and p.hostname in {"legacyaquatics.co.nz","www.legacyaquatics.co.nz"} and p.username is None and p.password is None and port in (None,443)
class StorefrontRedirectHandler(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,req,fp,code,msg,headers,newurl):
  if not allowed(newurl):raise CliError("refusing redirect outside the Legacy Aquatics HTTPS storefront")
  return super().redirect_request(req,fp,code,msg,headers,newurl)
def stamp(): return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00","Z")
def number(v):
 try:n=int(v)
 except ValueError as e:raise argparse.ArgumentTypeError("must be an integer") from e
 if not 1<=n<=MAX:raise argparse.ArgumentTypeError(f"must be 1-{MAX}")
 return n
def get(url,timeout):
 if not allowed(url):raise CliError("refusing request outside the Legacy Aquatics HTTPS storefront")
 try:
  with urllib.request.build_opener(StorefrontRedirectHandler()).open(urllib.request.Request(url,headers={"User-Agent":UA,"Accept":"text/html,application/xhtml+xml"}),timeout=timeout) as r:
   if not allowed(r.url):raise CliError("refusing response outside the Legacy Aquatics HTTPS storefront")
   body=r.read(MAX_BYTES+1)
   if len(body)>MAX_BYTES:raise CliError("upstream response exceeded the 5 MB safety limit")
   return body.decode("utf-8","replace"),r.url
 except urllib.error.HTTPError as e:raise CliError(f"upstream returned HTTP {e.code} for {url}") from e
 except (urllib.error.URLError,TimeoutError,OSError) as e:raise CliError(f"network error for {url}: {getattr(e,'reason',str(e))}") from e
def clean(v):return re.sub(r"\s+"," ",html.unescape(re.sub(r"<[^>]+>"," ",v))).strip()
def product_links(page,base):
 rows=[];by_url={}
 for href,label in re.findall(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',page,re.I|re.S):
  url=urllib.parse.urljoin(base,html.unescape(href));path=urllib.parse.urlparse(url).path
  if allowed(url) and "/product/" in path:
   title=clean(label)
   if url not in by_url:
    by_url[url]={"title":title,"url":url};rows.append(by_url[url])
   elif title and not by_url[url]["title"]:
    by_url[url]["title"]=title
 return rows
def search(query,page,max_results,timeout):
 if not query.strip():raise CliError("search query must not be empty")
 url=BASE+"/?"+urllib.parse.urlencode({"s":query,"post_type":"product","paged":page})
 body,final=get(url,timeout);rows=[x for x in product_links(body,final) if query.casefold() in (x["title"]+" "+x["url"]).casefold()]
 return {"source":"woocommerce-public-html","source_url":final,"retrieved_at":stamp(),"query":query,"page":page,"limit":max_results,"results":rows[:max_results],"note":"Public aquarium/reptile catalogue snapshot only; product fitment and husbandry are not advice."}
def category(slug,page,max_results,timeout):
 if not re.fullmatch(r"[a-z0-9-]+",slug):raise CliError("category slug must use lowercase letters, numbers and hyphens")
 url=f"{BASE}/product-category/{slug}/page/{page}/" if page>1 else f"{BASE}/product-category/{slug}/"
 body,final=get(url,timeout);return {"source":"woocommerce-public-html","source_url":final,"retrieved_at":stamp(),"category":slug,"page":page,"limit":max_results,"results":product_links(body,final)[:max_results],"note":"Public catalogue snapshot only; product fitment and husbandry are not advice."}
def detail(value,timeout):
 url=urllib.parse.urljoin(BASE,value) if not value.startswith("http") else value
 if not allowed(url) or "/product/" not in urllib.parse.urlparse(url).path:raise CliError("provide a Legacy Aquatics HTTPS /product/ URL")
 body,final=get(url,timeout);m=re.search(r'<h1\b[^>]*>(.*?)</h1>',body,re.I|re.S) or re.search(r'<title>(.*?)</title>',body,re.I|re.S);price=clean(" ".join(re.findall(r'<[^>]*woocommerce-Price-amount[^>]*>(.*?)</[^>]+>',body,re.I|re.S)[:3]));desc=re.search(r'<meta\s+name=["\']description["\']\s+content=["\']([^"\']+)',body,re.I)
 return {"source":"woocommerce-public-html","source_url":final,"retrieved_at":stamp(),"product":{"title":clean(m.group(1)) if m else "","url":final,"price_text":price or None,"description":html.unescape(desc.group(1)) if desc else None},"note":"Public product data only; verify aquarium/reptile setup and care with an appropriate expert."}
def emit(data,as_json):
 if as_json:print(json.dumps(data,ensure_ascii=False,indent=2));return
 for r in data.get("results",[data.get("product")] if data.get("product") else []):print(f"{r.get('title','')} | {r.get('url','')}")
def main():
 ap=argparse.ArgumentParser(description="Read-only Legacy Aquatics NZ public WooCommerce catalogue CLI.");ap.add_argument("--timeout",type=number,default=10,help="network timeout seconds, 1-50 (default: 10)");sub=ap.add_subparsers(dest="cmd",required=True)
 s=sub.add_parser("search",help="search public WooCommerce product results");s.add_argument("query");s.add_argument("--page",type=number,default=1);s.add_argument("--limit",type=number,default=12);s.add_argument("--json",action="store_true")
 c=sub.add_parser("category",help="list public products in a WooCommerce category");c.add_argument("slug");c.add_argument("--page",type=number,default=1);c.add_argument("--limit",type=number,default=12);c.add_argument("--json",action="store_true")
 p=sub.add_parser("product",help="fetch a public product URL");p.add_argument("url");p.add_argument("--json",action="store_true")
 a=ap.parse_args()
 try:data=search(a.query,a.page,a.limit,a.timeout) if a.cmd=="search" else category(a.slug,a.page,a.limit,a.timeout) if a.cmd=="category" else detail(a.url,a.timeout);emit(data,a.json)
 except CliError as e:print(f"legacy-aquatics-nz: {e}",file=sys.stderr);return 1
 return 0
if __name__=="__main__":raise SystemExit(main())
