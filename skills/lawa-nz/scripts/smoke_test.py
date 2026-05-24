#!/usr/bin/env python3
import json, subprocess, sys
from pathlib import Path
CLI=Path(__file__).with_name('cli.py')
def run(args): return subprocess.check_output([sys.executable,str(CLI),*args],text=True,timeout=60)
def check(n,f):
    try: f(); print('[PASS]',n); return True
    except Exception as e: print('[FAIL]',n,e); return False
ok=[]
ok.append(check('help', lambda: subprocess.check_call([sys.executable,str(CLI),'--help'], stdout=subprocess.DEVNULL)))
def river():
    d=json.loads(run(['river-sites','--query','waikato','--limit','5','--json'])); assert d['sites']
ok.append(check('river-sites', river))
def swim():
    d=json.loads(run(['swim-sites','--query','beach','--limit','5','--json'])); assert d['total'] is not None and isinstance(d['sites'], list)
ok.append(check('swim-sites', swim))
def ind():
    d=json.loads(run(['indicators','--lawa-id','ARC-00001','--limit','5','--json'])); assert d['indicators']
ok.append(check('indicators', ind))
if all(ok): print('All tests passed.'); sys.exit(0)
sys.exit(1)
