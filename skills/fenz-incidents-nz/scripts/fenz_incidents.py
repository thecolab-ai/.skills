"""Parsers for labelled FENZ operational reports and annual incident downloads."""
import csv
import io
import re
import zipfile
from html.parser import HTMLParser
from html import unescape
from urllib.parse import urljoin, urlparse
class P(HTMLParser):
 def __init__(self):super().__init__(convert_charrefs=True);self.tag=None;self.buf=[];self.pairs=[];self.pending=None
 def handle_starttag(self,t,a):
  if t in {"dt","dd","th","td"}:self.tag=t;self.buf=[]
 def handle_data(self,d):
  if self.tag:self.buf.append(d)
 def handle_endtag(self,t):
  if t==self.tag:
   x=" ".join("".join(self.buf).split());self.tag=None
   if t in {"dt","th"}:self.pending=x
   elif self.pending:self.pairs.append((self.pending,x));self.pending=None
def parse_incidents(text,source,at):
 p=P();p.feed(text);out=[];row={}
 for k,v in p.pairs:
  key=re.sub(r"[^a-z0-9]+","_",k.lower()).strip("_")
  if key=="incident_number" and row:out.append(row);row={}
  if key:row[key]=v
 if row:out.append(row)
 out=[r for r in out if r.get("incident_number")]
 for r in out:r.update({"classification_status":"preliminary operational report","source_url":source,"retrieved_at":at})
 if not out:raise ValueError("FENZ page contained no labelled incident records")
 return out


def parse_annual_resources(document, source_url, retrieved_at):
 host=urlparse(source_url).hostname;rows=[]
 for href,body in re.findall(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',document,re.I|re.S):
  title=" ".join(re.sub(r"<[^>]+>"," ",unescape(body)).split());match=re.search(r"Incident Data\s+(20\d{2})[-/]([0-9]{2})",title,re.I)
  if not match:continue
  url=urljoin(source_url,unescape(href))
  if urlparse(url).hostname!=host:continue
  rows.append({"financial_year":f"{match.group(1)}-{match.group(2)}","title":title,"download_url":url,"source_url":source_url,"retrieved_at":retrieved_at})
 rows=list({row["financial_year"]:row for row in rows}.values())
 if not rows:raise ValueError("FENZ annual data page contained no incident dataset links")
 return sorted(rows,key=lambda row:row["financial_year"])


def _tabular_bytes(body, dataset_url):
 if body[:4]==b"PK\x03\x04":
  try:
   archive=zipfile.ZipFile(io.BytesIO(body));names=[name for name in archive.namelist() if name.lower().endswith((".txt",".tsv",".csv")) and not name.endswith("/")]
   if not names:raise ValueError("FENZ incident archive contained no tabular file")
   return archive.read(sorted(names)[0])
  except (zipfile.BadZipFile,OSError) as exc:raise ValueError(f"FENZ incident archive could not be opened: {exc}") from exc
 return body


def aggregate_annual(body, dataset_url, retrieved_at, financial_year, *, region=None, incident_type=None, metadata_url=None):
 raw=_tabular_bytes(body,dataset_url)
 try:
  text=raw.decode("utf-16") if raw.startswith((b"\xff\xfe",b"\xfe\xff")) else raw.decode("utf-8-sig")
 except UnicodeDecodeError:text=raw.decode("cp1252")
 reader=csv.DictReader(io.StringIO(text),delimiter="\t")
 if not reader.fieldnames:raise ValueError("FENZ incident table has no header")
 columns={re.sub(r"[^a-z0-9]","",name.casefold()):name for name in reader.fieldnames}
 def find(*names):return next((columns[name] for name in names if name in columns),None)
 incident_col=find("incidentid");region_col=find("regionalcouncil","regionalcouncilname","region");type_col=find("incidentname","incidenttypename","incidenttype","incidentgroupname","groupname","incidentdescription")
 if not incident_col or not region_col or not type_col:raise ValueError("FENZ incident table is missing Incident ID, Regional Council or Incident Type")
 groups={}
 for row in reader:
  area=" ".join((row.get(region_col) or "Unknown").split());kind=" ".join((row.get(type_col) or "Unknown").split());incident=" ".join((row.get(incident_col) or "").split())
  if region and region.casefold() not in area.casefold():continue
  if incident_type and incident_type.casefold() not in kind.casefold():continue
  group=groups.setdefault((area,kind),{"exposures":0,"incidents":set()});group["exposures"]+=1
  if incident:group["incidents"].add(incident)
 output=[]
 for (area,kind),counts in groups.items():
  output.append({"financial_year":financial_year,"regional_council":area,"incident_type":kind,"exposures":counts["exposures"],"incidents":len(counts["incidents"]),"unit_note":"source has one row per exposure; incidents are distinct Incident ID values","dataset_url":dataset_url,"metadata_url":metadata_url,"source_url":dataset_url,"retrieved_at":retrieved_at,"provenance":"FENZ annual tab-delimited incident table"})
 return sorted(output,key=lambda row:(-row["incidents"],row["regional_council"],row["incident_type"]))
