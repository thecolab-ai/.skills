#!/usr/bin/env python3
import json, subprocess, sys
from pathlib import Path
CLI=Path(__file__).with_name('cli.py')
def run(args): return subprocess.check_output([sys.executable, str(CLI), *args], text=True, timeout=45)
def check(name, fn):
    try: fn(); print('[PASS]', name); return True
    except Exception as e: print('[FAIL]', name, e); return False
ok=[]
ok.append(check('help', lambda: subprocess.check_call([sys.executable,str(CLI),'--help'], stdout=subprocess.DEVNULL)))
def search():
    d=json.loads(run(['search','water','--limit','2','--json'])); assert d['count']>0 and d['datasets']
ok.append(check('search water', search))
def orgs():
    d=json.loads(run(['orgs','--limit','3','--json'])); assert len(d['organisations'])>=3
ok.append(check('orgs', orgs))
if all(ok): print('All tests passed.'); sys.exit(0)
sys.exit(1)
