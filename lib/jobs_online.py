"""Parse MBIE Jobs Online consolidated quarterly CSV."""
import csv,io
from datetime import datetime
INDUSTRIES={"agriculture, forestry and fishing","construction","manufacturing","mining","retail trade","accommodation and food services","education and training","health care and social assistance","public administration and safety","transport, postal and warehousing","professional, scientific and technical services","financial and insurance services","administrative and support services","arts and recreation services","other services","wholesale trade","information media and telecommunications","electricity, gas, water and waste services","rental, hiring and real estate services"}
OCCUPATIONS={"managers","professionals","technicians and trades workers","community and personal service workers","clerical and administrative workers","sales workers","machinery operators and drivers","labourers"}
SKILL_LEVELS={"highly-skilled","skilled","semi-skilled","low-skilled","unskilled"}
def classify_series(value):
 normal=value.strip().casefold()
 if normal in INDUSTRIES:return "industry"
 if normal in OCCUPATIONS:return "occupation"
 if normal in SKILL_LEVELS:return "skill_level"
 return "unknown"
def parse_jobs_csv(text,source_url,retrieved_at):
 reader=csv.DictReader(io.StringIO(text.lstrip("\ufeff")));required={"ACTUAL_DATE","KEYA","KEYBB","AVI_SUM"}
 if not reader.fieldnames or not required.issubset(reader.fieldnames):raise ValueError("Jobs Online CSV schema changed")
 rows=[]
 for raw in reader:
  try:period=datetime.strptime(raw["ACTUAL_DATE"],"%d/%m/%Y").date().isoformat();value=float(raw["AVI_SUM"])
  except (TypeError,ValueError):continue
  series=raw["KEYBB"].strip()
  rows.append({"period":period,"geography":raw["KEYA"].strip(),"series":series,"dimension":classify_series(series),"avi":value,"unit":"index","seasonal_adjustment":"unadjusted","source_url":source_url,"retrieved_at":retrieved_at})
 if not rows:raise ValueError("Jobs Online CSV contained no valid rows")
 return rows
