#!/usr/bin/env python3
"""Bounded live public-source probes; fixture failures always fail."""
import json
import calendar
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from urllib.parse import unquote, urlparse

import cli

from parser_tests import run as fixture_tests

CLI = Path(__file__).with_name('cli.py')


def probe_cycle_links():
    """Scan the full live page for monthly filename candidates, independent of discovery."""
    try:
        with tempfile.TemporaryDirectory(dir=CLI.parent.parent) as folder:
            args = cli.build_parser().parse_args(['sites', '--source', 'at-cycle-daily',
                                                  '--max-age', '0', '--cache-dir', folder])
            body, _ = cli.fetch(cli.CYCLE_PAGE, args, binary=True)
        parser = cli.DownloadLinks()
        parser.feed(body.decode('utf-8'))
        names = [n.lower() for n in (*calendar.month_name, *calendar.month_abbr) if n] + ['sept']
        checked = 0
        for link in parser.links:
            filename = unquote(urlparse(link).path.rsplit('/', 1)[-1]).lower()
            if 'cycle' not in filename:
                continue
            months = re.findall(r'(?<![a-z0-9])(' + '|'.join(names) + r')(?![a-z0-9])', filename)
            years = re.findall(r'(?<!\d)((?:19|20)\d{2})(?!\d)', filename)
            if len(months) == len(years) == 1:
                assert cli.download_period(link) is not None, link
                checked += 1
        assert checked > 0, 'No monthly cycle XLSX links checked'
    except cli.SkillError as exc:
        if exc.code in (4, 5):
            print(f'[SKIP] live cycle archive links: {exc}')
            return True
        print(f'[FAIL] live cycle archive links: {exc}')
        return False
    except (AssertionError, ValueError) as exc:
        print(f'[FAIL] live cycle archive links: {exc}')
        return False
    print(f'[PASS] live cycle archive links: all {checked} monthly XLSX candidates map to periods')
    return True


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
        assert 'error' not in data and data['meta']['source_url'] and data['meta']['retrieved_at'].endswith('Z')
        assert check(data)
        rows = data.get('results', [f['properties'] for f in data.get('features',[])])
        assert all('source_url' in row for row in rows)
    except (AssertionError,ValueError,KeyError,TypeError) as exc:
        print(f'[FAIL] live {name}: response/schema assertion {exc}')
        return False
    print(f"[PASS] live {name}: {data['meta']['count']} returned, {data['meta']['matched_count']} matched")
    return True


def main():
    try:
        fixture_tests()
    except Exception as exc:
        print(f'[FAIL] fixture parser checks: {exc}')
        return 1
    checks = [
        ('sources registry', ['sources'], lambda d: d['meta']['count'] == len(cli.SOURCES)),
        ('Hamilton annual traffic', ['counts','--source','hamilton-traffic','--site','2893','--from','2023-01-01','--to','2023-12-31'], lambda d: len(d['results']) == 1 and d['results'][0]['count'] == 17000 and d['results'][0]['date'] == '2023'),
        ('Hamilton spatial sites', ['nearest','--source','hamilton-traffic','--near','175.27,-37.77','--radius-km','0.5','--format','geojson','--limit','2'], lambda d: d['features'] and d['features'][0]['geometry']['type'] == 'Point'),
        ('Tauranga latest survey', ['counts','--source','tauranga-traffic','--site','411d227d-8458-4677-88d2-6cb552094cc1'], lambda d: d['results'] and d['results'][0]['adt'] == 18290 and d['results'][0]['date'] == '2005-11-11' and d['meta']['latest_data'] == '2005-11-11'),
        ('Tauranga spatial sites', ['sites','--source','tauranga-traffic','--bbox','176.12,-37.74,176.13,-37.73','--format','geojson','--limit','2'], lambda d: d['features'] and d['features'][0]['geometry']['type'] == 'Point'),
        ('Christchurch cycle snapshot', ['counts','--source','christchurch-cycle','--site','100045582'], lambda d: d['results'] and isinstance(d['results'][0]['count'], (int,float)) and 'date' not in d['results'][0] and 'latest_data' not in d['meta']),
        ('Christchurch nearby counters', ['nearest','--source','christchurch-cycle','--near','172.6277,-43.5335','--radius-km','0.1','--format','geojson','--limit','2'], lambda d: d['features'] and d['features'][0]['properties']['distance_km'] < 0.1),
        ('Wellington countline geometry', ['nearest','--source','wellington-sensors','--near','174.7754,-41.3199','--radius-km','0.1','--format','geojson','--limit','2'], lambda d: d['features'] and d['features'][0]['geometry']['type'] == 'MultiLineString' and d['meta']['latest_data'] is None and d['meta']['latest_data_note'] in d['meta']['warnings']),
        ('Wellington September hourly counts', ['counts','--source','wellington-sensors','--site','48346','--from','2026-09-01','--to','2026-09-01','--limit','2'], lambda d: d['results'] and d['results'][0]['date'] == '2026-09-01' and d['results'][0]['hour'] == 0 and d['results'][0]['count'] == 0 and d['meta']['latest_data'] == '2026-09-01'),
        ('AT traffic workbook', ['sites','--source','at-traffic','--limit','2'], lambda d: d['meta']['matched_count'] > 20000 and d['results'][0]['name'] == 'Access Road #2'),
        ('AT traffic survey values', ['counts','--source','at-traffic','--site','6f28d534b38283b7'], lambda d: d['results'] and d['results'][0]['adt_7_day'] == 1603.4285714285716),
        ('AT ADT survey values', ['counts','--source','at-adt','--site','23788:522'], lambda d: d['results'] and any(r['adt'] == 451 for r in d['results'])),
        ('AT ADT spatial query', ['nearest','--source','at-adt','--near','174.76,-36.85','--radius-km','0.5','--limit','2','--format','geojson'], lambda d: d['features'] and d['features'][0]['geometry']['type'] == 'Point' and d['features'][0]['properties']['distance_km'] < .5),
        ('AT daily cycles', ['counts','--source','at-cycle-daily','--site','Albany Highway Cyclist','--from','2026-07-01','--to','2026-07-31','--limit','2'], lambda d: d['meta']['matched_count'] == 31 and d['results'][0]['count'] == 92),
        ('AT monthly cycles', ['counts','--source','at-cycle-monthly','--site','Albany Highway Cyclist','--from','2026-07-01','--to','2026-07-31'], lambda d: d['results'][0]['count'] == 1958 and d['results'][0]['observed_days'] == 31),
        ('AT May 2026 cycles', ['counts','--source','at-cycle-monthly','--site','Albany Highway Cyclist','--from','2026-05-01','--to','2026-05-31'], lambda d: len(d['results']) == 1 and d['results'][0]['date'] == '2026-05-01' and d['results'][0]['published_days'] == 31),
        ('NZTA monitoring sites', ['sites','--source','nzta-tms','--bbox','174.5,-37.2,175,-36.6','--limit','2'], lambda d: d['meta']['matched_count'] > 100 and 'longitude' in d['results'][0]),
        ('NZTA daily traffic', ['counts','--source','nzta-tms','--site','00200444','--from','2018-01-01','--to','2018-01-01'], lambda d: d['results'] and all(r['date'] == '2018-01-01' for r in d['results']) and any(r['count'] == 2468 for r in d['results'])),
        ('Heart of the City hourly counts', ['counts','--source','hotcity','--site','107 Quay Street','--from','2026-09-01','--to','2026-09-01'], lambda d: d['meta']['matched_count'] == 24 and d['results'][0]['count'] == 211 and d['meta']['latest_data'] >= '2026-09-30'),
    ]
    good = probe_cycle_links()
    for name,args,check in checks:
        good = probe(name,args,check) and good
    return 0 if good else 1


if __name__ == '__main__':
    raise SystemExit(main())
