#!/usr/bin/env python3
"""Discover official Police Data NZ statistical reports and definitions."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/"lib"))
import nzfetch  # noqa: E402
from police_data_catalog import parse_catalog,parse_tableau  # noqa: E402
from result_contract import result_envelope,utc_now  # noqa: E402
SOURCE="https://www.police.govt.nz/about-us/publications-statistics/data-and-statistics/policedatanz";ALLOWED={"police.govt.nz","www.police.govt.nz","public.tableau.com"};WARN=["Recorded crime is not a direct measure of total underlying crime prevalence.","Preserve suppression, rounding and small-cell rules from the selected report.","Do not use these descriptors for person-level, address-level or predictive-policing outputs.","Interactive Tableau rows are not returned because Police publishes no stable documented row-query API."]
def parser():
 r=argparse.ArgumentParser(description=__doc__);c=r.add_subparsers(dest="command",required=True)
 for name in ("victimisations","proceedings","datasets","definitions"):
  x=c.add_parser(name);x.add_argument("--limit",type=int,default=50);x.add_argument("--json",action="store_true")
 x=c.add_parser("trend");x.add_argument("--offence",required=True);x.add_argument("--limit",type=int,default=50);x.add_argument("--json",action="store_true")
 x=c.add_parser("area");x.add_argument("name");x.add_argument("--limit",type=int,default=50);x.add_argument("--json",action="store_true")
 x=c.add_parser("demographics");x.add_argument("--measure",required=True);x.add_argument("--limit",type=int,default=50);x.add_argument("--json",action="store_true")
 return r
def main():
 a=parser().parse_args();stamp=utc_now()
 try:
  if not 1<=a.limit<=100:raise ValueError("--limit must be between 1 and 100")
  if a.command in {"trend","area","demographics"}:
   print(json.dumps({"error":"unsupported_operation","code":7,"message":"The official Tableau surface has no stable documented row-query API, so this requested statistical filter cannot be applied honestly. Use `datasets` to open the official report."}),file=sys.stderr);return 7
  html=nzfetch.fetch_text(SOURCE,timeout=30,allowed_hosts=ALLOWED);reports=parse_catalog(html,SOURCE,stamp)
  if a.command=="victimisations":reports=[r for r in reports if r["measure"]=="victimisations"]
  elif a.command=="proceedings":reports=[r for r in reports if r["measure"]=="proceedings"]
  if a.command=="definitions":
   data={"RCVS":"Recorded Crime Victims Statistics: crimes with an identified victim; introduced 2014-15","RCOS":"Recorded Crime Offenders Statistics: includes crimes without a clear victim; introduced 2014-15","update_cadence":"last working day of each month","licence":"Creative Commons Attribution 4.0 International","source_url":SOURCE,"retrieved_at":stamp,"warnings":WARN}
  else:
   data=[]
   for report in reports[:a.limit]:
    try:report["tableau"]=parse_tableau(nzfetch.fetch_text(report["report_url"],timeout=25,allowed_hosts=ALLOWED),report["report_url"],stamp)
    except nzfetch.RateLimited:raise
    except nzfetch.Blocked:raise
    except (nzfetch.FetchError,ValueError):report["tableau"]={"status":"unavailable_or_schema_changed"}
    report["requested_filters"]={k:v for k,v in vars(a).items() if k not in {"json","limit","command"}};data.append(report)
  env=result_envelope(ok=True,source_name="New Zealand Police - Police Data NZ",source_url=SOURCE,retrieved_at=stamp,freshness="updated on the last working day of each month",query=vars(a),data=data,warnings=WARN,blocked=False)
  if a.json:print(json.dumps(env,indent=2,ensure_ascii=False))
  else:print(json.dumps(data,indent=2,ensure_ascii=False))
  return 0
 except ValueError as e:print(json.dumps({"error":"invalid_input_or_source_schema","message":str(e)}),file=sys.stderr);return 2 if str(e).startswith("--") else 6
 except nzfetch.RateLimited as e:print(json.dumps({"error":"rate_limited","message":str(e),"retry_after":e.retry_after}),file=sys.stderr);return 4
 except nzfetch.Blocked as e:print(json.dumps({"error":"blocked","message":str(e)}),file=sys.stderr);return 4
 except nzfetch.FetchError as e:print(json.dumps({"error":"source_unavailable","message":str(e)}),file=sys.stderr);return 5
if __name__=="__main__":raise SystemExit(main())
