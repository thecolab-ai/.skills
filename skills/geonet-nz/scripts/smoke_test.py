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
def quakes():
 d=json.loads(run(['quakes','--mmi','3','--limit','3','--json'])); assert isinstance(d['quakes'], list)
ok.append(check('quakes', quakes))
def volcanoes():
 d=json.loads(run(['volcanoes','--json'])); assert d['volcanoes']
ok.append(check('volcanoes', volcanoes))
def news():
 d=json.loads(run(['news','--limit','2','--json'])); assert d['items']
ok.append(check('news', news))
if all(ok): print('All tests passed.'); sys.exit(0)
sys.exit(1)
