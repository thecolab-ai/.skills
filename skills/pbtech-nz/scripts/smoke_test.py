#!/usr/bin/env python3
import json, subprocess, sys
from pathlib import Path
CLI=Path(__file__).with_name('cli.py')
def run(args): return subprocess.check_output([sys.executable,str(CLI),*args],text=True,timeout=90)
def check(name, fn):
 try: fn(); print('[PASS]',name); return True
 except Exception as e: print('[FAIL]',name,e); return False
ok=[]
ok.append(check('help', lambda: subprocess.check_call([sys.executable,str(CLI),'--help'], stdout=subprocess.DEVNULL)))
def search():
 d=json.loads(run(['search','ssd','--limit','3','--json'])); assert d['products']; assert any(p.get('code') and p.get('price') for p in d['products'])
ok.append(check('search ssd returns priced products', search))
def product():
 d=json.loads(run(['product','HDDTGM0050','--json'])); p=d['product']; assert p.get('code')=='HDDTGM0050'; assert p.get('title'); assert p.get('price')
ok.append(check('product detail by code', product))
def stores():
 d=json.loads(run(['stores','--query','auckland','--limit','5','--json'])); assert d['stores']; assert any('Auckland' in (s.get('address') or '') for s in d['stores'])
ok.append(check('stores auckland', stores))
if all(ok): print('All tests passed.'); sys.exit(0)
sys.exit(1)
