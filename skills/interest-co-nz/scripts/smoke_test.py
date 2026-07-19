#!/usr/bin/env python3
import json, subprocess, sys
from pathlib import Path
CLI=Path(__file__).with_name('cli.py')
def run(a): return subprocess.check_output([sys.executable,str(CLI),*a],text=True,timeout=45)
def check(n,f):
 try: f(); print('[PASS]',n); return True
 except Exception as e: print('[FAIL]',n,e); return False
ok=[]
ok.append(check('help', lambda: subprocess.check_call([sys.executable,str(CLI),'--help'], stdout=subprocess.DEVNULL)))
def fixture_table():
 import importlib.util
 spec=importlib.util.spec_from_file_location('interest_co_nz_cli',CLI); assert spec and spec.loader
 module=importlib.util.module_from_spec(spec); sys.modules[spec.name]=module; spec.loader.exec_module(module)
 parser=module.TableParser(); parser.feed('''<table id="interest_financial_datatable"><tr><th>Institution</th><th>Product</th><th>Variable</th></tr><tr><td><img title="Example Bank"></td><td>Standard</td><td>6.49%</td></tr></table>''')
 assert parser.rows[1][0]['text']=='Example Bank'; assert parser.rows[1][2]['text']=='6.49%'; assert module.num(parser.rows[1][2]['text'])==6.49
 print('[PASS] fixture interest.co.nz mortgage table parser')
ok.append(check('fixture mortgage table parser',fixture_table))
def rates():
 d=json.loads(run(['mortgage-rates','--limit','5','--json'])); assert d['rates']; assert any(r['rates'] for r in d['rates'])
ok.append(check('mortgage rates', rates))
def westpac():
 d=json.loads(run(['mortgage-rates','--bank','Westpac','--limit','3','--json'])); assert d['rates']
ok.append(check('bank filter', westpac))
if all(ok): print("[PASS] live smoke assertions completed"); sys.exit(0)
sys.exit(1)
