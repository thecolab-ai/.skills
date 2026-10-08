#!/usr/bin/env python3
"""Bounded live public-source probes; fixture failures always fail."""
import json
from pathlib import Path
import subprocess
import sys

from parser_tests import run as fixture_tests

CLI = Path(__file__).with_name('cli.py')


def probe(name, arguments, check):
    try:
        p = subprocess.run([sys.executable,str(CLI),*arguments,'--json','--max-age','0'],text=True,capture_output=True,timeout=35)
    except subprocess.TimeoutExpired:
        print(f'[SKIP] live {name}: network probe timed out')
        return True
    if p.returncode:
        if p.returncode in (4,5):
            print(f'[SKIP] live {name}: {p.stderr.strip()[:180]}')
            return True
        print(f'[FAIL] live {name}: {p.stderr.strip()[:240]}')
        return False
    try:
        data = json.loads(p.stdout)
        assert data['ok'] and data['source_url'] and data['retrieved_at'].endswith('Z')
        assert check(data)
        rows = data.get('records', [f['properties'] for f in data.get('features',[])])
        assert all({'source_url','publisher','licence','retrieved_at','latest_data'} <= row.keys() for row in rows)
    except (AssertionError,ValueError,KeyError,TypeError) as exc:
        print(f'[FAIL] live {name}: response/schema assertion {exc}')
        return False
    print(f"[PASS] live {name}: {data['count']} returned, {data['matched_count']} matched")
    return True


def main():
    try:
        fixture_tests()
    except Exception as exc:
        print(f'[FAIL] fixture parser checks: {exc}')
        return 1
    checks = [
        ('sources registry', ['sources'], lambda d: d['count'] == 6),
        ('AT traffic workbook', ['sites','--source','at-traffic','--limit','2'], lambda d: d['matched_count'] > 20000 and d['records'][0]['name'] == 'Access Road #2'),
        ('AT traffic survey values', ['counts','--source','at-traffic','--site','6f28d534b38283b7'], lambda d: d['records'] and d['records'][0]['adt_7_day'] == 1603.4285714285716),
        ('AT ADT survey values', ['counts','--source','at-adt','--site','23788:522'], lambda d: d['records'] and any(r['adt'] == 451 for r in d['records'])),
        ('AT ADT spatial query', ['nearest','--source','at-adt','--near','174.76,-36.85','--radius-km','0.5','--limit','2','--format','geojson'], lambda d: d['features'] and d['features'][0]['geometry']['type'] == 'Point' and d['features'][0]['properties']['distance_km'] < .5),
        ('AT daily cycles', ['counts','--source','at-cycle-daily','--site','Albany Highway Cyclist','--limit','2'], lambda d: d['matched_count'] == 31 and d['records'][0]['count'] == 92),
        ('AT monthly cycles', ['counts','--source','at-cycle-monthly','--site','Albany Highway Cyclist'], lambda d: d['records'][0]['count'] == 1958 and d['records'][0]['observed_days'] == 31),
        ('NZTA monitoring sites', ['sites','--source','nzta-tms','--bbox','174.5,-37.2,175,-36.6','--limit','2'], lambda d: d['matched_count'] > 100 and 'longitude' in d['records'][0]),
        ('NZTA daily traffic', ['counts','--source','nzta-tms','--site','00200444','--from','2018-01-01','--to','2018-01-01'], lambda d: d['records'] and all(r['date'] == '2018-01-01' for r in d['records']) and any(r['count'] == 2468 for r in d['records'])),
        ('Heart of the City hourly counts', ['counts','--source','hotcity','--site','107 Quay Street','--from','2026-09-01','--to','2026-09-01'], lambda d: d['matched_count'] == 24 and d['records'][0]['count'] == 211 and d['latest_data'] == '2026-09-30'),
    ]
    good = True
    for name,args,check in checks:
        good = probe(name,args,check) and good
    return 0 if good else 1


if __name__ == '__main__':
    raise SystemExit(main())
