"""Parsers for labelled FENZ operational reports and annual incident downloads."""
import csv
import io
import re
import zipfile
from html.parser import HTMLParser
from html import unescape
from urllib.parse import urljoin, urlparse
PUBLISHER = "Fire and Emergency New Zealand"
LICENCE = "CC BY-NC-ND 4.0"
LABELS = {
    "Incident number": "incident_number", "Date and time": "date_and_time",
    "Location": "location", "Duration": "duration",
    "Attending Stations/Brigades": "attending_stations_brigades", "Stations": "stations",
    "Call Type": "call_type", "Call type": "call_type",
}


class IncidentText(HTMLParser):
    """Preserve visible labelled cells across dl and table page layouts."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.buffer = []
        self.skip = 0

    def flush(self):
        value = " ".join("".join(self.buffer).split())
        if value:
            self.parts.append(value)
        self.buffer = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript"}:
            self.skip += 1
        if tag in {"dt", "dd", "th", "td", "div", "p", "li", "h1", "h2", "h3", "br"}:
            self.flush()

    def handle_data(self, data):
        if not self.skip:
            self.buffer.append(data)

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"} and self.skip:
            self.skip -= 1
        if tag in {"dt", "dd", "th", "td", "div", "p", "li", "h1", "h2", "h3"}:
            self.flush()


def parse_incident_lines(lines, source, at):
    lines = [" ".join(line.split()) for line in lines if line.strip()]
    out, row = [], {}
    for index, label in enumerate(lines[:-1]):
        key = LABELS.get(label)
        if key is None:
            continue
        if key == "incident_number":
            if row:
                out.append(row)
            row = {}
        value = lines[index + 1]
        if value in LABELS:
            raise ValueError(f"FENZ incident record has no value for {label}")
        if key == "incident_number" or row:
            row[key] = value
    if row:
        out.append(row)
    if not out:
        raise ValueError("FENZ page contained no labelled incident records")
    for row in out:
        if not all(row.get(key) for key in ("incident_number", "date_and_time", "location", "call_type")):
            raise ValueError("FENZ incident record is missing required fields")
        row.update({"classification_status": "preliminary operational report", "source_url": source,
                    "publisher": PUBLISHER, "licence": LICENCE, "retrieved_at": at})
        date = re.match(r"(\d{2})/(\d{2})/(\d{4})", row["date_and_time"])
        if date:
            row["latest_data"] = f"{date[3]}-{date[2]}-{date[1]}"
    return out


def parse_incidents(text, source, at):
    parser = IncidentText()
    parser.feed(text)
    parser.flush()
    return parse_incident_lines(parser.parts, source, at)


def parse_annual_resources(document, source_url, retrieved_at):
 host=urlparse(source_url).hostname;rows=[]
 for href,body in re.findall(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',document,re.I|re.S):
  title=" ".join(re.sub(r"<[^>]+>"," ",unescape(body)).split());match=re.search(r"Incident Data\s+(20\d{2})[-/]([0-9]{2})",title,re.I)
  if not match:continue
  url=urljoin(source_url,unescape(href))
  if urlparse(url).hostname!=host:continue
  rows.append({"financial_year":f"{match.group(1)}-{match.group(2)}","title":title,"download_url":url,"source_url":source_url,"publisher":PUBLISHER,"licence":LICENCE,"retrieved_at":retrieved_at})
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
  output.append({"financial_year":financial_year,"regional_council":area,"incident_type":kind,"exposures":counts["exposures"],"incidents":len(counts["incidents"]),"unit_note":"source has one row per exposure; incidents are distinct Incident ID values","dataset_url":dataset_url,"metadata_url":metadata_url,"source_url":dataset_url,"publisher":PUBLISHER,"licence":LICENCE,"latest_data":financial_year,"retrieved_at":retrieved_at,"provenance":"FENZ annual tab-delimited incident table"})
 return sorted(output,key=lambda row:(-row["incidents"],row["regional_council"],row["incident_type"]))
