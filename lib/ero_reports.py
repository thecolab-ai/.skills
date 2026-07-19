"""Parse Education Review Office institution pages with section provenance."""
from __future__ import annotations
import re
from datetime import datetime
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urljoin,urlparse

class Extract(HTMLParser):
 def __init__(self):
  super().__init__(convert_charrefs=True);self.depth=0;self.heading=None;self.heading_parts=[];self.sections=[];self.current=None;self.links=[];self.active_link=None;self.ignored=[]
 def handle_starttag(self,tag,attrs):
  self.depth+=1; a=dict(attrs)
  if tag in {"nav","footer","script","style","form"}:self.ignored.append((tag,self.depth))
  if self.ignored:return
  if tag in {"h1","h2","h3","h4","h5"}:self.heading=(tag,self.depth);self.heading_parts=[]
  if tag=="a" and a.get("href"):
   self.active_link={"href":a["href"],"depth":self.depth,"parts":[]}
  if tag in {"p","li","br","tr"} and self.current:self.current["parts"].append("\n")
 def handle_data(self,data):
  if self.ignored:return
  if self.heading:self.heading_parts.append(data)
  elif self.current:self.current["parts"].append(data)
  if self.active_link:self.active_link["parts"].append(data)
 def handle_endtag(self,tag):
  if self.ignored and self.ignored[-1]==(tag,self.depth):self.ignored.pop()
  if self.ignored:self.depth-=1;return
  if tag=="a" and self.active_link and self.active_link["depth"]==self.depth:
   self.links.append([self.active_link["href"],"".join(self.active_link["parts"])])
   self.active_link=None
  if self.heading and self.heading[0]==tag and self.heading[1]==self.depth:
   title=" ".join("".join(self.heading_parts).split())
   if title:
    self.current={"level":int(tag[1]),"heading":title,"parts":[]};self.sections.append(self.current)
   self.heading=None;self.heading_parts=[]
  self.depth-=1

def _institution_title(title,url):
 title=" ".join(title.split())
 if title and not re.match(r"^(?:view|read)\b",title,re.I):return title
 slug=urlparse(url).path.rstrip("/").rsplit("/",1)[-1]
 return " ".join(part.capitalize() for part in slug.split("-") if part)

def parse_page(html,source_url,retrieved_at):
 if re.search(r"captcha|access denied",html,re.I):raise ValueError("ERO source returned an access challenge")
 p=Extract();p.feed(html); host=urlparse(source_url).hostname
 links={};link_scores={}
 for href,title in p.links:
  url=urljoin(source_url,href);title=" ".join(title.split());generic=not title or bool(re.match(r"^(?:view|read)\b",title,re.I))
  if urlparse(url).hostname==host and re.search(r"/institution/\d+",url):
   candidate={"title":_institution_title(title,url),"source_url":url,"retrieved_at":retrieved_at}
   score=0 if generic else 1
   if score>link_scores.get(url,-1):links[url]=candidate;link_scores[url]=score
 sections=[]
 for index,s in enumerate(p.sections):
  text=" ".join("".join(s["parts"]).split())
  sections.append({"section_index":index,"heading":s["heading"],"level":s["level"],"text":text,"source_url":source_url,"retrieved_at":retrieved_at,"provenance":{"format":"html","section_heading":s["heading"],"section_index":index}})
 if not sections and not links:raise ValueError("ERO page contained no recognisable institutions or report sections")
 return {"institutions":list(links.values()),"sections":sections}

def report_sections(page):
 sections=page["sections"];out=[]; current_date=None; current_school=None;markers=[]
 for index,s in enumerate(sections):
  if s["level"]==1:current_school=s["heading"]
  date_match=re.search(r"\b(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4})\b",s["text"] or s["heading"],re.I)
  if date_match:
   try:current_date=datetime.strptime(date_match.group(1),"%d %b %Y").date().isoformat()
   except ValueError:
    try:current_date=datetime.strptime(date_match.group(1),"%d %B %Y").date().isoformat()
    except ValueError:pass
  heading=s["heading"].casefold()
  if s["level"] in {2,3} and not heading.startswith("reports for ") and ("report" in heading or any(k in heading for k in ("evaluation","assurance","profile"))):markers.append((index,current_school,current_date))
 marker_indices={item[0] for item in markers}
 for marker,(index,school,published) in enumerate(markers):
  s=sections[index];end=len(sections)
  for cursor in range(index+1,len(sections)):
   if cursor in marker_indices or sections[cursor]["level"]<s["level"] or (s["level"]==2 and sections[cursor]["level"]==2):
    end=cursor;break
  report_content=sections[index:end]
  slug=re.sub(r"[^a-z0-9]+","-",s["heading"].casefold()).strip("-")
  institution=re.search(r"/institution/(\d+)",s["source_url"])
  stable_id=f"{institution.group(1) + '/' if institution else ''}{published or 'date-unknown'}:{slug}"
  out.append({"id":stable_id,"school":school,"report_type":s["heading"],"published_on":published,"source_url":s["source_url"],"retrieved_at":s["retrieved_at"],"section":s,"sections":report_content})
 return sorted(out,key=lambda item:(item["published_on"] or "",item["id"]),reverse=True)

def require_report(reports,requested):
 report=next((item for item in reports if item["id"]==requested),None)
 if report is None:raise ValueError("requested report ID was not found on the official institution page")
 return report
