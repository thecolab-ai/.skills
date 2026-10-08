#!/usr/bin/env python3
import json, subprocess, sys
from pathlib import Path
CLI=Path(__file__).with_name('cli.py')
def run(args): return subprocess.check_output([sys.executable,str(CLI),*args],text=True,timeout=45,stderr=subprocess.PIPE)
def check(n,f):
    try: f(); print('[PASS]',n); return True
    except subprocess.CalledProcessError as e:
        detail=(e.stderr or '')+(e.output or '')
        if any(x in detail.lower() for x in ['network error','timed out','http 429','http 5','upstream']): print('[SKIP] live',n,detail[:250]); return None
        print('[FAIL] live',n,detail[:300]); return False
    except Exception as e: print('[FAIL]',n,e); return False
ok=[]
ok.append(check('contract help', lambda: subprocess.check_call([sys.executable,str(CLI),'--help'], stdout=subprocess.DEVNULL)))
def fixture_layer():
    import importlib.util
    spec=importlib.util.spec_from_file_location('linz_data_service_cli',CLI); assert spec and spec.loader
    module=importlib.util.module_from_spec(spec); sys.modules[spec.name]=module; spec.loader.exec_module(module)
    row=module.norm_layer({'id':123113,'title':'NZ Addresses','public_access':True,'num_views':123,'private_field':'secret'})
    assert row=={'id':123113,'title':'NZ Addresses','public_access':True,'num_views':123}
    print('[PASS] fixture LINZ layer response normalisation')
ok.append(check('fixture layer parser',fixture_layer))
from spatial_contract import run_spatial_tests
ok.append(check('fixture mirror spatial contracts',run_spatial_tests))
def search():
    d=json.loads(run(['search','address','--limit','3','--json'])); assert d['layers']; assert any('Address' in x.get('title','') for x in d['layers'])
ok.append(check('live search address', search))
def layer():
    d=json.loads(run(['layer','123113','--json'])); assert d['layer']['id']==123113 and 'Address' in d['layer']['title']
ok.append(check('live layer 123113', layer))
def services():
    d=json.loads(run(['services','123113','--json'])); assert d['services']
ok.append(check('live services 123113', services))
def features(dataset):
    d=json.loads(run(['features',dataset,'--bbox','174.735,-36.905,174.745,-36.875','--limit','3','--format','geojson']))
    assert d['type']=='FeatureCollection' and len(d['features'])==3 and d['total_matching']>=3
    assert d['latest_data'] and d['licence']=='CC BY 4.0'
    assert all(f['geometry']['type'] in ('Polygon','MultiPolygon') for f in d['features'])
    print(f"  {dataset}: total={d['total_matching']}; sample OBJECTID={d['features'][0]['properties']['OBJECTID']}")
for dataset in ['primary-parcels','building-outlines']:
    ok.append(check(f'live {dataset} bbox GeoJSON',lambda dataset=dataset: features(dataset)))
if all(x is not False for x in ok): print(f"All non-skipped tests passed ({ok.count(True)} passed, {ok.count(None)} skipped)."); sys.exit(0)
sys.exit(1)
