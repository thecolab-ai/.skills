#!/usr/bin/env python3
"""Captured response checks and four bounded outage-aware live ArcGIS probes."""
import json
from pathlib import Path
import subprocess
import sys
from fixture_checks import AKL, AT, run

CLI = Path(__file__).with_name('cli.py')


def main():
    try:
        run()
    except Exception as exc:
        print(f'[FAIL] fixture captured responses: {exc}')
        return 1
    failures=0
    for name,url in [('AT roadworks',AT),('Council stormwater pipe',AKL)]:
        for mode in ['count','query']:
            args=[mode,url,'--json']
            if mode=='query': args+=['--bbox','174.60,-37.05,174.95,-36.70','--limit','5','--format','geojson']
            try:
                result=subprocess.run([sys.executable,str(CLI),*args],capture_output=True,text=True,timeout=35,check=False)
                if result.returncode:
                    error=json.loads(result.stderr)['error']
                    if error['code'] in {4,5} and error['category'] in {'upstream_http_failure','rate_limited','access_blocked'}:
                        print(f"[SKIP] live {name} {mode}: {error['message']}")
                        continue
                    raise AssertionError(result.stderr.strip())
                data=json.loads(result.stdout)
                assert data['source_url']==url and data['publisher']
                assert data['retrieved_at'].endswith('Z') and data['latest_data'].endswith('Z')
                assert 'licence' in data
                if mode=='count':
                    assert data['count']>0
                    detail=f"count={data['count']} latest_data={data['latest_data']}"
                else:
                    assert data['type']=='FeatureCollection' and data['feature_count']==5
                    assert len({f['id'] for f in data['features']})==5
                    assert all(f['geometry'] and f['properties'] for f in data['features'])
                    geometry=data['features'][0]['geometry']
                    coords=geometry['coordinates']
                    point=coords[0][0] if geometry['type']=='Polygon' else coords[0]
                    assert 174.60<=point[0]<=174.95 and -37.05<=point[1]<=-36.70
                    detail=f"features=5 geometry={geometry['type']} first_id={data['features'][0]['id']} point={point} truncated={data['truncated']}"
                print(f'[PASS] live {name} {mode}: {detail}')
            except Exception as exc:
                print(f'[FAIL] live {name} {mode}: {exc}')
                failures+=1
    return 1 if failures else 0


if __name__=='__main__':raise SystemExit(main())
