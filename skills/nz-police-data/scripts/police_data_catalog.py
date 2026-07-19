"""Parse New Zealand Police's official policedata.nz report catalogue."""
import re
from html import unescape
from urllib.parse import urljoin,urlparse
def clean(s):return " ".join(unescape(re.sub(r"<[^>]+>"," ",s)).split())
def parse_catalog(html,source_url,retrieved_at):
 decoded=unescape(unescape(html));host=urlparse(source_url).hostname;rows=[]
 for href,body in re.findall(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',decoded,re.I|re.S):
  url=urljoin(source_url,unescape(href));title=clean(body)
  if urlparse(url).hostname!=host or "/policedatanz/" not in urlparse(url).path or not title:continue
  key=urlparse(url).path.rstrip("/").split("/")[-1]
  measure="proceedings" if "proceed" in key else "victimisations" if "victim" in key else "other"
  rows.append({"id":key,"title":title,"measure":measure,"report_url":url,"source_url":source_url,"retrieved_at":retrieved_at,"row_retrieval_supported":False})
 rows=list({r["report_url"]:r for r in rows}.values())
 if not rows:raise ValueError("Police Data NZ catalogue contained no recognisable report links")
 return rows
def parse_tableau(html,report_url,retrieved_at):
 decoded=unescape(unescape(html)).replace("&#47;","/")
 m=re.search(r'https://public\.tableau\.com/(?:views|static/images)/([^"\' <]+)',decoded,re.I)
 if not m:raise ValueError("Police report page contained no public Tableau workbook reference")
 path=m.group(1);parts=path.split("/")
 if len(parts)>2 and len(parts[0])==2:parts=parts[1:]
 workbook=parts[0];view=parts[1] if len(parts)>1 else None
 return {"workbook":workbook,"view":view,"tableau_url":f"https://public.tableau.com/views/{workbook}/{view or ''}","report_url":report_url,"source_url":report_url,"retrieved_at":retrieved_at,"row_retrieval_supported":False,"blocked_reason":"Tableau workbook exposes an interactive view but no stable documented row-query API"}
