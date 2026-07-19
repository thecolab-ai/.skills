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
def fixture_layer():
    import importlib.util
    spec=importlib.util.spec_from_file_location('linz_data_service_cli',CLI); assert spec and spec.loader
    module=importlib.util.module_from_spec(spec); sys.modules[spec.name]=module; spec.loader.exec_module(module)
    row=module.norm_layer({'id':123113,'title':'NZ Addresses','public_access':True,'num_views':123,'private_field':'secret'})
    assert row=={'id':123113,'title':'NZ Addresses','public_access':True,'num_views':123}
    print('[PASS] fixture LINZ layer response normalisation')
ok.append(check('fixture layer parser',fixture_layer))
def search():
    d=json.loads(run(['search','address','--limit','3','--json'])); assert d['layers']; assert any('Address' in x.get('title','') for x in d['layers'])
ok.append(check('search address', search))
def layer():
    d=json.loads(run(['layer','123113','--json'])); assert d['layer']['id']==123113 and 'Address' in d['layer']['title']
ok.append(check('layer 123113', layer))
def services():
    d=json.loads(run(['services','123113','--json'])); assert d['services']
ok.append(check('services 123113', services))
if all(ok): print("[PASS] live smoke assertions completed"); sys.exit(0)
sys.exit(1)
