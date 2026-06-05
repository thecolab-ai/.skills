#!/usr/bin/env python3
import json, subprocess, sys
from pathlib import Path
CLI=Path(__file__).with_name('cli.py')
def run(args): return subprocess.check_output([sys.executable,str(CLI),*args],text=True,timeout=45)
def check(n,f):
    try: f(); print('[PASS]',n); return True
    except Exception as e: print('[FAIL]',n,e); return False
ok=[]
ok.append(check('help', lambda: subprocess.check_call([sys.executable,str(CLI),'--help'], stdout=subprocess.DEVNULL)))
def search():
    d=json.loads(run(['search','address','--limit','3','--json'])); assert d['layers']; assert any('Address' in x.get('title','') for x in d['layers'])
ok.append(check('search address', search))
def layer():
    d=json.loads(run(['layer','123113','--json'])); assert d['layer']['id']==123113 and 'Address' in d['layer']['title']
ok.append(check('layer 123113', layer))
def services():
    d=json.loads(run(['services','123113','--json'])); assert d['services']
ok.append(check('services 123113', services))
if all(ok): print('All tests passed.'); sys.exit(0)
sys.exit(1)
