#!/usr/bin/env python3
"""Captured response checks and four bounded outage-aware live ArcGIS probes."""
import json
from pathlib import Path
import subprocess
import sys
from fixture_checks import AKL, AT, run

CLI = Path(__file__).with_name('cli.py')


def coordinate_pairs(coords):
    if len(coords)>=2 and all(isinstance(v,(int,float)) for v in coords[:2]):
        yield coords[:2]
    else:
        for child in coords:
            yield from coordinate_pairs(child)


def main():
    try:
        run()
    except Exception as exc:
        print(f'[FAIL] fixture captured responses: {exc}')
        return 1
    failures=0
    for name,url,box in [('AT roadworks',AT,'174.738,-36.895,174.741,-36.888'),('Council stormwater pipe',AKL,'174.919,-37.024,174.922,-37.021')]:
        for mode in ['count','query']:
            args=[mode,url,'--json']
            if mode=='query': args+=['--bbox',box,'--limit','5','--format','geojson']
            try:
                result=subprocess.run([sys.executable,str(CLI),*args],capture_output=True,text=True,timeout=35,check=False)
                if result.returncode:
                    error=json.loads(result.stdout)['error']
                    if result.returncode in {4,5}:
                        print(f"[SKIP] live {name} {mode}: {error['message']}")
                        continue
                    raise AssertionError(result.stdout.strip() or result.stderr.strip())
                data=json.loads(result.stdout)
                meta=data['meta']
                assert meta['source_url']==url and meta['publisher']
                assert meta['retrieved_at'].endswith('Z') and meta['latest_data'].endswith('Z')
                assert 'licence' in meta
                if mode=='count':
                    assert data['results'][0]['count']>0
                    detail=f"count={data['results'][0]['count']} latest_data={meta['latest_data']}"
                else:
                    assert data['type']=='FeatureCollection'
                    if data['feature_count']==0:
                        print(f'[SKIP] live {name} {mode}: no current features in bbox')
                        continue
                    assert 1<=data['feature_count']<=5
                    assert len({f['id'] for f in data['features']})==data['feature_count']
                    assert all(f['geometry'] and f['properties'] for f in data['features'])
                    geometry=data['features'][0]['geometry']
                    points=list(coordinate_pairs(geometry['coordinates']))
                    assert points
                    xmin,ymin,xmax,ymax=map(float,box.split(','))
                    assert min(p[0] for p in points)<=xmax and max(p[0] for p in points)>=xmin
                    assert min(p[1] for p in points)<=ymax and max(p[1] for p in points)>=ymin
                    point=points[0]
                    detail=f"features={data['feature_count']} geometry={geometry['type']} first_id={data['features'][0]['id']} point={point} truncated={data['truncated']}"
                print(f'[PASS] live {name} {mode}: {detail}')
            except Exception as exc:
                print(f'[FAIL] live {name} {mode}: {exc}')
                failures+=1
    return 1 if failures else 0


if __name__=='__main__':raise SystemExit(main())
