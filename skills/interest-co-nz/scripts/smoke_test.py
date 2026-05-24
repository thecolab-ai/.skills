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
def rates():
 d=json.loads(run(['mortgage-rates','--limit','5','--json'])); assert d['rates']; assert any(r['rates'] for r in d['rates'])
ok.append(check('mortgage rates', rates))
def westpac():
 d=json.loads(run(['mortgage-rates','--bank','Westpac','--limit','3','--json'])); assert d['rates']
ok.append(check('bank filter', westpac))
if all(ok): print('All tests passed.'); sys.exit(0)
sys.exit(1)
