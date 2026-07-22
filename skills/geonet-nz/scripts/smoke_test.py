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
def fixture_tilde():
 import importlib.util
 spec=importlib.util.spec_from_file_location('geonet_nz_cli_tilde',CLI); assert spec and spec.loader
 module=importlib.util.module_from_spec(spec); sys.modules[spec.name]=module; spec.loader.exec_module(module)
 summary={'stations':{'WLGT':{'station':'WLGT','stationLocality':'Wellington','latitude':-41.28,'longitude':174.78,'sensorCodes':{'40':{'names':{'water-height':{'methods':{'15s':{'aspects':{'nil':{'latestRecord':'2026-07-22T00:00:00Z'}}}}},'water-temperature':{'methods':{'raw':{'aspects':{'nil':{'latestRecord':'2021-01-01T00:00:00Z'}}}}}}}}}}}
 rows=module.tilde_station_rows(summary)
 assert rows[0]['station']=='WLGT' and rows[0]['names']==['water-height','water-temperature']
 series=module.tilde_first_series(summary,'WLGT',None)
 assert series['name']=='water-height' and series['method']=='15s', 'freshest series must win'
 stats=module.tilde_series_summary([{'val':1.0,'ts':'a'},{'val':3.0,'ts':'b'},{'val':2.0,'ts':'c'}])
 assert stats['latest_value']==2.0 and stats['window_min']==1.0 and stats['window_max']==3.0 and stats['observations']==3
 print('[PASS] fixture Tilde summary parsing and freshest-series pick')
ok.append(check('fixture tilde parsers',fixture_tilde))
def quakes():
 d=json.loads(run(['quakes','--mmi','3','--limit','3','--json'])); assert isinstance(d['quakes'], list)
ok.append(check('quakes', quakes))
def volcanoes():
 d=json.loads(run(['volcanoes','--json'])); assert d['volcanoes']
ok.append(check('volcanoes', volcanoes))
def news():
 d=json.loads(run(['news','--limit','2','--json'])); assert d['items']
ok.append(check('news', news))
def tilde_stations():
 d=json.loads(run(['tilde-stations','coastal','--json'])); assert any(s['station']=='WLGT' for s in d['stations'])
ok.append(check('tilde coastal stations', tilde_stations))
if all(ok): print("[PASS] live smoke assertions completed"); sys.exit(0)
sys.exit(1)
