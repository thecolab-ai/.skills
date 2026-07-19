#!/usr/bin/env python3
import importlib.util, json, subprocess, sys
from pathlib import Path
CLI=Path(__file__).with_name('cli.py')
def run(args): return subprocess.check_output([sys.executable, str(CLI), *args], text=True, timeout=45)
def check(name, fn):
    try: fn(); print('[PASS]', name); return True
    except Exception as e: print('[FAIL]', name, e); return False
ok=[]
def fixture():
    spec=importlib.util.spec_from_file_location('data_govt_cli', CLI)
    cli=importlib.util.module_from_spec(spec); assert spec.loader is not None
    sys.modules[spec.name]=cli; spec.loader.exec_module(cli)
    row=cli.norm_pkg({'id':'abc','title':'Water data','organization':{'title':'Council'},'resources':[{'url':'https://catalogue.data.govt.nz/data.csv','format':'CSV'}]})
    assert row['id']=='abc' and row['organization']=='Council' and row['resource_count']==1
ok.append(check('fixture CKAN package normalization', fixture))
ok.append(check('help', lambda: subprocess.check_call([sys.executable,str(CLI),'--help'], stdout=subprocess.DEVNULL)))
def search():
    d=json.loads(run(['search','water','--limit','2','--json'])); assert d['count']>0 and d['datasets']
ok.append(check('search water', search))
def orgs():
    d=json.loads(run(['orgs','--limit','3','--json'])); assert len(d['organisations'])>=3
ok.append(check('orgs', orgs))
if all(ok): print("[PASS] live smoke assertions completed"); sys.exit(0)
sys.exit(1)
