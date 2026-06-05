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
if all(ok): print('All tests passed.'); sys.exit(0)
sys.exit(1)
