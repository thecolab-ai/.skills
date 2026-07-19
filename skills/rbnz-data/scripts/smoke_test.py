#!/usr/bin/env python3
import io, json, subprocess, sys, zipfile
from pathlib import Path
CLI=Path(__file__).with_name('cli.py')
def run(a): return subprocess.check_output([sys.executable,str(CLI),*a],text=True,timeout=45)
def check(n,f):
 try: f(); print('[PASS]',n); return True
 except Exception as e: print('[FAIL]',n,e); return False
ok=[]
ok.append(check('help', lambda: subprocess.check_call([sys.executable,str(CLI),'--help'], stdout=subprocess.DEVNULL)))
def fixture_xlsx():
 import importlib.util
 spec=importlib.util.spec_from_file_location('rbnz_data_cli',CLI); assert spec and spec.loader
 module=importlib.util.module_from_spec(spec); sys.modules[spec.name]=module; spec.loader.exec_module(module)
 stream=io.BytesIO()
 with zipfile.ZipFile(stream,'w') as z:
  z.writestr('xl/workbook.xml','''<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Data" sheetId="1" r:id="rId1"/></sheets></workbook>''')
  z.writestr('xl/_rels/workbook.xml.rels','''<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>''')
  z.writestr('xl/worksheets/sheet1.xml','''<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c t="inlineStr"><is><t>Period</t></is></c><c t="inlineStr"><is><t>Value</t></is></c></row><row r="2"><c t="inlineStr"><is><t>2026-Q2</t></is></c><c><v>5.5</v></c></row></sheetData></worksheet>''')
 parsed=module.parse_xlsx(stream.getvalue()); assert parsed['sheet']=='Data'; assert parsed['rows'][1]==['2026-Q2','5.5']
 print('[PASS] fixture RBNZ XLSX parser')
ok.append(check('fixture XLSX parser',fixture_xlsx))
def search():
 d=json.loads(run(['search','interest rates','--limit','3','--json'])); assert d['datasets']
ok.append(check('search interest rates', search))
def dataset():
 d=json.loads(run(['dataset','exchange-rates','--json'])); assert d['dataset']['resource_list']
ok.append(check('dataset exchange-rates', dataset))
def download_preview():
 d=json.loads(run(['download','exchange-rates','--match','daily','--rows','3','--json'])); assert d['bytes'] > 10000; assert d['preview']['rows']
ok.append(check('direct XLSX download preview', download_preview))
def chart():
 d=json.loads(run(['chart','retail-rates','--limit','3','--json'])); assert d['data']; assert 'Column0' in d['data'][-1]
ok.append(check('direct chart cache JSON', chart))
if all(ok): print("[PASS] live smoke assertions completed"); sys.exit(0)
sys.exit(1)
