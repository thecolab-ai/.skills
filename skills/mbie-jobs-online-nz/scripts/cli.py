#!/usr/bin/env python3
"""Query official MBIE Jobs Online advertised-vacancy indices."""
import argparse,json,sys
from datetime import date
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/"lib"))
import nzfetch  # noqa: E402
from jobs_online import parse_jobs_csv  # noqa: E402
from result_contract import result_envelope,utc_now  # noqa: E402
URL="https://www.mbie.govt.nz/assets/Data-Files/Business-employment/Employment-skills/Labour-market-reports/Jobs-online-quarterly/jobs-online-all-unadjusted-quarterly-data-consolidated-march-2026.csv";ALLOWED={"mbie.govt.nz","www.mbie.govt.nz"};WARN=["Advertised-vacancy indices are not employment, hiring or unique job-opening counts.","Quarterly series are unadjusted; prefer annual comparisons.","Do not combine with listing counts unless definitions and deduplication are explicit."]
def parser():
 r=argparse.ArgumentParser(description=__doc__);c=r.add_subparsers(dest="command",required=True)
 x=c.add_parser("latest");x.add_argument("--limit",type=int,default=50);x.add_argument("--json",action="store_true")
 for name,pos in (("occupation","query"),("industry","name"),("region","name")):
  x=c.add_parser(name);x.add_argument(pos);x.add_argument("--limit",type=int,default=50);x.add_argument("--json",action="store_true")
 x=c.add_parser("skill-level");x.add_argument("number",type=int);x.add_argument("--limit",type=int,default=50);x.add_argument("--json",action="store_true")
 x=c.add_parser("trend");x.add_argument("--from",dest="from_date",required=True);x.add_argument("--to",dest="to_date",required=True);x.add_argument("--limit",type=int,default=50);x.add_argument("--json",action="store_true")
 x=c.add_parser("definitions");x.add_argument("--limit",type=int,default=50);x.add_argument("--json",action="store_true")
 return r
def parse_input_date(value,option):
 try:parsed=date.fromisoformat(value)
 except ValueError as exc:raise LookupError(f"{option} must be a valid YYYY-MM-DD date") from exc
 if parsed.isoformat()!=value:raise LookupError(f"{option} must be a valid YYYY-MM-DD date")
 return parsed
def main():
 a=parser().parse_args();stamp=utc_now()
 try:
  if not 1<=a.limit<=100:raise LookupError("--limit must be between 1 and 100")
  start=end=None
  if a.command=="trend":
   start=parse_input_date(a.from_date,"--from");end=parse_input_date(a.to_date,"--to")
   if start>end:raise LookupError("--from must not be after --to")
  if a.command=="skill-level" and a.number not in {1,2,3,4,5}:raise LookupError("skill level must be 1 to 5")
  body,_,_=nzfetch.fetch_bytes(URL,timeout=45,allowed_hosts=ALLOWED);rows=parse_jobs_csv(body.decode("utf-8-sig"),URL,stamp)
  if a.command=="definitions":data={"AVI":"All Vacancies Index based on raw unweighted advertisements from four job boards","unit":"index, not a vacancy count","seasonal_adjustment":"quarterly series are unadjusted","deduplication":"duplicates within and across job boards and months are removed","source_url":URL,"retrieved_at":stamp}
  else:
   if a.command=="latest":
    latest=max(r["period"] for r in rows);rows=[r for r in rows if r["period"]==latest]
   elif a.command in {"occupation","industry"}:needle=(a.query if a.command=="occupation" else a.name).casefold();rows=[r for r in rows if r["dimension"]==a.command and needle in r["series"].casefold()]
   elif a.command=="region":rows=[r for r in rows if a.name.casefold() in r["geography"].casefold()]
   elif a.command=="skill-level":
    labels={1:"Highly-Skilled",2:"Skilled",3:"Semi-Skilled",4:"Low-Skilled",5:"Unskilled"}
    rows=[r for r in rows if r["dimension"]=="skill_level" and r["series"]==labels[a.number]]
   else:
    rows=[r for r in rows if start<=date.fromisoformat(r["period"])<=end]
   data=rows[:a.limit]
  env=result_envelope(ok=True,source_name="MBIE Jobs Online",source_url=URL,retrieved_at=stamp,freshness="quarterly consolidated file; page updated 15 July 2026",query=vars(a),data=data,warnings=WARN,blocked=False)
  if a.json:print(json.dumps(env,indent=2,ensure_ascii=False))
  else:print(json.dumps(data,indent=2,ensure_ascii=False))
  return 0
 except LookupError as e:print(json.dumps({"error":"invalid_input","message":str(e)}),file=sys.stderr);return 2
 except ValueError as e:print(json.dumps({"error":"source_schema_failure","message":str(e)}),file=sys.stderr);return 6
 except nzfetch.RateLimited as e:print(json.dumps({"error":"rate_limited","message":str(e),"retry_after":e.retry_after}),file=sys.stderr);return 4
 except nzfetch.Blocked as e:print(json.dumps({"error":"blocked","message":str(e)}),file=sys.stderr);return 4
 except nzfetch.FetchError as e:print(json.dumps({"error":"source_unavailable","message":str(e)}),file=sys.stderr);return 5
if __name__=="__main__":raise SystemExit(main())
