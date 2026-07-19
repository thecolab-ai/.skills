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
def fixture_quake():
 import importlib.util
 spec=importlib.util.spec_from_file_location('geonet_nz_cli',CLI); assert spec and spec.loader
 module=importlib.util.module_from_spec(spec); sys.modules[spec.name]=module; spec.loader.exec_module(module)
 row=module.norm_feature({'properties':{'publicID':'synthetic-1','magnitude':4.2,'depth':12.5,'mmi':3,'locality':'Example locality'},'geometry':{'coordinates':[174.76,-36.85]}})
 assert row['public_id']=='synthetic-1'; assert row['longitude']==174.76; assert row['latitude']==-36.85; assert row['depth_km']==12.5
 print('[PASS] fixture GeoNet GeoJSON feature normalisation')
ok.append(check('fixture quake feature parser',fixture_quake))
def quakes():
 d=json.loads(run(['quakes','--mmi','3','--limit','3','--json'])); assert isinstance(d['quakes'], list)
ok.append(check('quakes', quakes))
def volcanoes():
 d=json.loads(run(['volcanoes','--json'])); assert d['volcanoes']
ok.append(check('volcanoes', volcanoes))
def news():
 d=json.loads(run(['news','--limit','2','--json'])); assert d['items']
ok.append(check('news', news))
if all(ok): print("[PASS] live smoke assertions completed"); sys.exit(0)
sys.exit(1)
