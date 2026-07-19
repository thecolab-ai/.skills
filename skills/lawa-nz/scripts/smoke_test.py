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
def fixture_swim_card():
    import importlib.util
    spec=importlib.util.spec_from_file_location('lawa_nz_cli',CLI); assert spec and spec.loader
    module=importlib.util.module_from_spec(spec); sys.modules[spec.name]=module; spec.loader.exec_module(module)
    parser=module.CardParser(); parser.feed('''<a href="/explore-data/swimming/example-beach"><h6>Example Beach</h6><p>Wellington</p><span class="grade-icon--label">Good</span></a>''')
    assert len(parser.cards)==1; assert parser.cards[0]['title']=='Example Beach'; assert parser.cards[0]['subtitle']=='Wellington'; assert parser.cards[0]['grade']=='Good'
    print('[PASS] fixture LAWA swim-site card parser')
ok.append(check('fixture swim-site parser',fixture_swim_card))
def river():
    d=json.loads(run(['river-sites','--query','waikato','--limit','5','--json'])); assert d['sites']
ok.append(check('river-sites', river))
def swim():
    d=json.loads(run(['swim-sites','--query','beach','--limit','5','--json'])); assert d['total'] is not None and isinstance(d['sites'], list)
ok.append(check('swim-sites', swim))
def ind():
    d=json.loads(run(['indicators','--lawa-id','ARC-00001','--limit','5','--json'])); assert d['indicators']
ok.append(check('indicators', ind))
if all(ok): print("[PASS] live smoke assertions completed"); sys.exit(0)
sys.exit(1)
