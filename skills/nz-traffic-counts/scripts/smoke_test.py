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
    stage, data = 'JSON decode', None
    try:
        data = json.loads(p.stdout)
        stage = 'error-free envelope with source_url and UTC retrieved_at'
        assert 'error' not in data and data['meta']['source_url'] and data['meta']['retrieved_at'].endswith('Z')
        stage = 'probe-specific value check'
        assert check(data)
        stage = 'per-row source_url provenance'
        rows = data.get('results', [f['properties'] for f in data.get('features',[])])
        assert all('source_url' in row for row in rows)
    except (AssertionError,ValueError,KeyError,TypeError) as exc:
        detail = f'{type(exc).__name__}: {exc}' if str(exc) else 'returned false'
        print(f'[FAIL] live {name}: response/schema assertion failed at {stage} ({detail}); {describe(data)}')
        return False
    print(f"[PASS] live {name}: {data['meta']['count']} returned, {data['meta']['matched_count']} matched")
    return True


def describe(data):
    """Compact evidence for a failed check, so a false predicate is never a blank message."""
    if not isinstance(data, dict):
        return 'no JSON payload'
    rows = data.get('results') or [f.get('properties', {}) for f in data.get('features') or []]
    meta = data.get('meta') or {}
    first = {k: v for k, v in rows[0].items() if k not in ('raw', 'source_url', 'publisher', 'retrieved_at')} if rows and isinstance(rows[0], dict) else None
    summary = {'count': meta.get('count'), 'matched_count': meta.get('matched_count'), 'latest_data': meta.get('latest_data'),
               'error': data.get('error'), 'first_result': first}
    return 'observed ' + json.dumps(summary, default=str)[:400]


def numeric_single_direction(rows):
    """First Christchurch counter publishing a numeric one-direction count, or None."""
    return next((r['site_id'] for r in rows if r.get('direction') == 'one'
                 and isinstance(r.get('count'), (int, float)) and not isinstance(r.get('count'), bool)), None)


def christchurch_check(d):
    return (d['results'] and isinstance(d['results'][0]['count'], (int,float)) and d['results'][0]['direction'] == 'one'
            and d['results'][0]['series_role'] == 'single_direction' and 'date' not in d['results'][0]
            and 'latest_data' not in d['meta'] and any('not additive' in w for w in d['meta']['warnings']))


def probe_christchurch_snapshot():
    """Pick a counter that currently publishes a number; individual counters can go null."""
    name = 'Christchurch cycle snapshot'
    try:
        p = subprocess.run([sys.executable, str(CLI), 'sites', '--source', 'christchurch-cycle', '--limit', '1000',
                            '--json', '--max-age', '0'], text=True, capture_output=True, timeout=35)
    except subprocess.TimeoutExpired:
        print(f'[SKIP] live {name}: network probe timed out')
        return True
    if p.returncode in (4, 5):
        print(f'[SKIP] live {name}: {p.stderr.strip()[:180]}')
        return True
    try:
        data = json.loads(p.stdout)
        assert p.returncode == 0 and 'error' not in data, f'sites exit {p.returncode}: {p.stderr.strip()[:180]}'
        site = numeric_single_direction(data['results'])
        assert site, f'no single-direction counter publishes a numeric count among {len(data["results"])} sites'
    except (AssertionError, ValueError, KeyError, TypeError) as exc:
        print(f'[FAIL] live {name}: counter discovery failed ({type(exc).__name__}: {exc})')
        return False
    return probe(f'{name} (site {site})', ['counts', '--source', 'christchurch-cycle', '--site', site], christchurch_check)


def probe_unknown_wellington():
    """An unknown numeric id must fail from the small metadata file, not a monthly CSV."""
    try:
        p = subprocess.run([sys.executable, str(CLI), 'counts', '--source', 'wellington-sensors',
                            '--site', '999999999', '--json', '--max-age', '0'],
                           text=True, capture_output=True, timeout=20)
    except subprocess.TimeoutExpired:
        print('[FAIL] live Wellington unknown site: timed out before metadata rejection')
        return False
    if p.returncode in (4, 5):
        print(f'[SKIP] live Wellington unknown site: {p.stderr.strip()[:180]}')
        return True
    try:
        data = json.loads(p.stdout)
        assert p.returncode == 2 and data['error']['code'] == 2 and data['error']['type'] == 'invalid_input'
        assert data['results'] == [] and '999999999' in data['error']['message']
    except (AssertionError, ValueError, KeyError, TypeError) as exc:
        print(f'[FAIL] live Wellington unknown site: {exc}; stderr={p.stderr.strip()[:180]}')
        return False
    print('[PASS] live Wellington unknown site: rejected before monthly CSV download')
    return True


def main():
    try:
        fixture_tests()
    except Exception as exc:
        print(f'[FAIL] fixture parser checks: {exc}')
        return 1
    # Counter 100045582 was hard-coded until it published count=null (Nov 2026); discovery must skip nulls.
    fixture_rows = cli.parse_chch(json.loads((CLI.parent.parent / 'tests' / 'fixtures' / 'christchurch-cycle.json').read_text()),
                                  cli.CHCH, '2026-10-08T00:00:00Z')
    assert numeric_single_direction(fixture_rows) == '901'
    assert numeric_single_direction([dict(r, count=None) for r in fixture_rows]) is None
    blank = describe({'meta': {'count': 1, 'matched_count': 1}, 'results': [{'site_id': '1', 'count': None, 'raw': {}}]})
    assert '"count": null' in blank and 'raw' not in blank
    print('[PASS] fixture Christchurch probe discovers a numeric counter and failed checks describe observed values')
    checks = [
        ('sources registry', ['sources'], lambda d: d['meta']['count'] == len(cli.SOURCES)),
        ('Hamilton annual traffic', ['counts','--source','hamilton-traffic','--site','02893','--from','2023-01-01','--to','2023-12-31'], lambda d: len(d['results']) == 1 and d['results'][0]['site_id'] == '2893' and d['results'][0]['count'] == 17000 and d['results'][0]['date'] == '2023' and d['results'][0]['series_role'] == 'both_directions' and d['meta']['latest_data'] == '2023'),
        ('Hamilton spatial sites', ['nearest','--source','hamilton-traffic','--near','175.27,-37.77','--radius-km','0.5','--format','geojson','--limit','2'], lambda d: d['features'] and d['features'][0]['geometry']['type'] == 'Point'),
        ('Tauranga latest survey', ['counts','--source','tauranga-traffic','--site','411d227d-8458-4677-88d2-6cb552094cc1'], lambda d: d['results'] and d['results'][0]['adt'] == 18290 and d['results'][0]['date'] == '2005-11-11' and d['meta']['latest_data'] == '2005-11-11'),
        ('Tauranga spatial sites', ['sites','--source','tauranga-traffic','--bbox','176.12,-37.74,176.13,-37.73','--format','geojson','--limit','2'], lambda d: d['features'] and d['features'][0]['geometry']['type'] == 'Point'),
        ('Christchurch nearby counters', ['nearest','--source','christchurch-cycle','--near','172.6277,-43.5335','--radius-km','0.1','--format','geojson','--limit','2'], lambda d: d['features'] and d['features'][0]['properties']['distance_km'] < 0.1),
        ('Wellington countline geometry', ['nearest','--source','wellington-sensors','--near','174.7754,-41.3199','--radius-km','0.1','--format','geojson','--limit','2'], lambda d: d['features'] and d['features'][0]['geometry']['type'] == 'MultiLineString' and d['meta']['latest_data'] is None and d['meta']['latest_data_note'] in d['meta']['warnings']),
        ('Wellington September hourly counts', ['counts','--source','wellington-sensors','--site','048346','--from','2026-09-01','--to','2026-09-01','--limit','2'], lambda d: d['results'] and d['results'][0]['site_id'] == '48346' and d['results'][0]['date'] == '2026-09-01' and d['results'][0]['hour'] == 0 and d['results'][0]['count'] == 0 and d['results'][1]['hour'] == 0 and d['meta']['latest_data'] == '2026-09-01' and d['meta']['matched_count'] == 280),
        ('Wellington latest-month freshness', ['counts','--source','wellington-sensors','--site','48346','--limit','2'], lambda d: d['results'] and d['results'][0]['date'] <= d['meta']['latest_data'] and d['meta']['latest_data'] >= '2026-10-09' and d['meta']['matched_count'] > d['meta']['count']),
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
    good = all([probe_cycle_links(), probe_unknown_wellington(), probe_christchurch_snapshot()])
    for name,args,check in checks:
        good = probe(name,args,check) and good
    return 0 if good else 1


if __name__ == '__main__':
    raise SystemExit(main())
