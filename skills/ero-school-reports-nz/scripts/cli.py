#!/usr/bin/env python3
"""Find official ERO institution reports with section provenance."""
import argparse,json,re,sys
from pathlib import Path
from urllib.parse import quote_plus
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/"lib"))
import nzfetch  # noqa: E402
from ero_reports import parse_page,report_sections,require_report  # noqa: E402
from result_contract import result_envelope,utc_now  # noqa: E402
ALLOWED={"ero.govt.nz","www.ero.govt.nz"};WARN=["Do not turn ERO reports into numeric rankings.","Historical review frameworks and dates remain explicit.","Extracted findings retain HTML section provenance."]
def parser():
 r=argparse.ArgumentParser(description=__doc__);c=r.add_subparsers(dest="command",required=True)
 for name,pos in (("search","school"),("latest","school_id"),("report","id"),("actions","id"),("history","school_id")):
  x=c.add_parser(name);x.add_argument(pos);x.add_argument("--limit",type=int,default=50);x.add_argument("--json",action="store_true")
 return r
def school_id(value):
 m=re.search(r"(?:/institution/)?(\d+)",value);return m.group(1) if m else None
def main():
 a=parser().parse_args();stamp=utc_now()
 try:
  if not 1<=a.limit<=100:raise ValueError("--limit must be between 1 and 100")
  value=getattr(a,"school",None) or getattr(a,"school_id",None) or a.id
  ident=school_id(value)
  if a.command=="search" and not ident:url=f"https://www.ero.govt.nz/review-reports?search={quote_plus(value)}"
  elif ident:
   index_url=f"https://www.ero.govt.nz/review-reports?search={quote_plus(ident)}"
   index=parse_page(nzfetch.fetch_text(index_url,timeout=30,allowed_hosts=ALLOWED),index_url,stamp)
   url=next((row["source_url"] for row in index["institutions"] if f"/institution/{ident}/" in row["source_url"]),None)
   if not url:raise ValueError("ERO institution ID was not present in the official report search")
  else:raise ValueError("report/latest/history/actions requires a numeric ERO institution ID or URL")
  page=parse_page(nzfetch.fetch_text(url,timeout=30,allowed_hosts=ALLOWED),url,stamp)
  if a.command=="search":
   needle=value.casefold();data=[row for row in page["institutions"] if needle in row["title"].casefold()][:a.limit]
  else:
   reports=report_sections(page)
   if a.command=="latest":data=reports[:1]
   elif a.command=="history":data=reports[:a.limit]
   elif a.command=="report":
    data=require_report(reports,a.id)
   else:
    keys=("next step","action","improvement","where to next","priority","expected outcome")
    sections=require_report(reports,a.id)["sections"]
    data=[s for s in sections if any(k in s["heading"].casefold() for k in keys)][:a.limit]
  env=result_envelope(ok=True,source_name="Education Review Office",source_url=url,retrieved_at=stamp,freshness="publication-specific",query=vars(a),data=data,warnings=WARN,blocked=False)
  if a.json:print(json.dumps(env,indent=2,ensure_ascii=False))
  else:print(json.dumps(data,indent=2,ensure_ascii=False))
  return 0
 except ValueError as e:print(json.dumps({"error":"invalid_input_or_source_schema","message":str(e)}),file=sys.stderr);return 2 if str(e).startswith(("--","report/latest","requested report ID")) else 6
 except nzfetch.RateLimited as e:print(json.dumps({"error":"rate_limited","message":str(e),"retry_after":e.retry_after}),file=sys.stderr);return 4
 except nzfetch.Blocked as e:print(json.dumps({"error":"blocked","message":str(e)}),file=sys.stderr);return 4
 except nzfetch.FetchError as e:print(json.dumps({"error":"source_unavailable","message":str(e)}),file=sys.stderr);return 5
if __name__=="__main__":raise SystemExit(main())
