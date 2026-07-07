#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,pathlib,re,sys,html
from html.parser import HTMLParser
from typing import Any
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "lib"))
import nzfetch  # noqa: E402
URL='https://www.interest.co.nz/borrowing'
UA='Mozilla/5.0'
TERMS=['variable_floating','6_months','1_year','2_years','3_years','4_years','5_years']
def die(m,c=1): print(f'interest-co-nz: {m}',file=sys.stderr); raise SystemExit(c)
class TableParser(HTMLParser):
 def __init__(self): super().__init__(); self.in_table=False; self.in_cell=False; self.cell_tag=''; self.buf=[]; self.row=[]; self.rows=[]; self.current_inst=''; self.current_product=''; self.current_alt=''; self.current_href=''
 def handle_starttag(self,tag,attrs):
  a=dict(attrs); cls=a.get('class','')
  if tag=='table' and a.get('id')=='interest_financial_datatable': self.in_table=True
  if self.in_table and tag=='tr': self.row=[]
  if self.in_table and tag in ('td','th'): self.in_cell=True; self.cell_tag=tag; self.buf=[]; self.current_alt=''; self.current_href=''
  if self.in_cell and tag=='img' and a.get('title'): self.current_alt=a.get('title','')
  if self.in_cell and tag=='a' and a.get('href') and not self.current_href: self.current_href=a.get('href')
 def handle_data(self,d):
  if self.in_cell: self.buf.append(d)
 def handle_endtag(self,tag):
  if self.in_table and tag in ('td','th') and self.in_cell:
   text=' '.join(html.unescape(' '.join(self.buf)).split()) or self.current_alt
   self.row.append({'text':text,'tag':self.cell_tag,'href':self.current_href})
   self.in_cell=False
  elif self.in_table and tag=='tr':
   if self.row: self.rows.append(self.row)
  elif self.in_table and tag=='table': self.in_table=False
def fetch():
 try: return nzfetch.fetch_text(URL, timeout=30)  # direct → rotating proxy on a block
 except nzfetch.Blocked as e: die(f'network error: {e}')
 except nzfetch.FetchError as e: die(str(e))
def num(s):
 s=(s or '').strip();
 if not s: return None
 m=re.search(r'\d+(?:\.\d+)?',s); return float(m.group(0)) if m else None
def parse_rows():
 p=TableParser(); p.feed(fetch())
 rows=[]; current_bank=''; current_link=''; current_product=''
 for r in p.rows:
  texts=[c['text'] for c in r]
  if not texts or texts[0]=='Institution': continue
  # special line with colspan normally parsed as blank bank/product + combined text
  if len(texts)<=3 and any('=' in t for t in texts):
   line=' '.join(t for t in texts if t)
   if rows: rows[-1].setdefault('special_lines',[]).append(line)
   continue
  bank=texts[0] or current_bank
  link=next((c.get('href') for c in r if c.get('href')), '') or current_link
  product=texts[1] if len(texts)>1 else current_product
  if texts[0]: current_bank=bank; current_link=link
  if product: current_product=product
  values=texts[2:9]
  if len(values)<7: values += ['']*(7-len(values))
  row={'institution':bank,'product':product,'url':link,'rates':{term:num(val) for term,val in zip(TERMS,values)},'raw_values':dict(zip(TERMS,values)),'special_lines':[]}
  if bank and product and any(v is not None for v in row['rates'].values()): rows.append(row)
 return rows
def out(d,j):
 if j: print(json.dumps(d,indent=2,ensure_ascii=False)); return
 print(f"interest.co.nz mortgage rates: {len(d['rates'])} rows shown")
 for r in d['rates']:
  rates=' | '.join(f"{k.replace('_',' ')} {v:.2f}%" for k,v in r['rates'].items() if v is not None)
  extra=('; '+', '.join(r.get('special_lines') or [])) if r.get('special_lines') else ''
  print(f"- {r['institution']} — {r['product']}: {rates}{extra}")
def cmd_mortgage(a):
 rows=parse_rows()
 if a.bank: rows=[r for r in rows if a.bank.lower() in r['institution'].lower()]
 if a.product: rows=[r for r in rows if a.product.lower() in r['product'].lower()]
 if a.specials_only: rows=[r for r in rows if 'special' in r['product'].lower() or r.get('special_lines')]
 out({'kind':'mortgage-rates','source':'interest-co-nz','source_url':URL,'bank':a.bank,'product':a.product,'rates':rows[:a.limit]},a.json)
def main():
 p=argparse.ArgumentParser(description='Parse interest.co.nz mortgage rates')
 sub=p.add_subparsers(dest='cmd',required=True)
 s=sub.add_parser('mortgage-rates'); s.add_argument('--bank'); s.add_argument('--product'); s.add_argument('--specials-only',action='store_true'); s.add_argument('--limit',type=int,default=30); s.add_argument('--json',action='store_true'); s.set_defaults(func=cmd_mortgage)
 a=p.parse_args(); a.func(a)
if __name__=='__main__': main()
