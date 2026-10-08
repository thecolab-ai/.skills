#!/usr/bin/env python3
"""Bounded real catalogue search and detail probes; outages report skips."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys

import cli

FIXTURES = Path(__file__).resolve().parents[1] / 'tests' / 'fixtures'
PROVENANCE = {'source_url', 'publisher', 'retrieved_at'}


def live(cat, term):
    status, records = cli.catalogue_request(cat, term, [174.4, -37.2, 175.3, -36.4], 2)
    if not status['available']:
        if status.get('error_code') in (4, 5):
            return f"[SKIP] {cat}: {status['error']}"
        raise AssertionError(f"{cat}: {status['error']}")
    assert status['number_matched'] > 0 and records
    assert all(PROVENANCE <= r.keys() for r in records)
    assert any(r['distribution_urls'] for r in records)
    # Resolve an actual returned record, not a hard-coded smoke item.
    url = cli.query_url(cat, record_id=records[0]['id'])
    try:
        raw = cli.fetch_json(url)
    except cli.SourceError as exc:
        if exc.code in (4, 5):
            return f"[PASS] live {cat} search: {status['number_matched']} matched\n[SKIP] {cat} get: {exc}"
        raise
    detail = cli.normalise_ogc(raw, cat, url, cli.now())
    assert detail['title'] == records[0]['title']
    assert detail['distribution_urls']
    assert PROVENANCE <= detail.keys()
    geo = cli.make_geojson({'results': [detail], 'meta': cli.provenance(url, detail['publisher'], cli.now())})
    assert geo['type'] == 'FeatureCollection' and len(geo['features']) == 1
    return (f"[PASS] live {cat} search: {status['number_matched']} matched; {len(records)} returned; {records[0]['title']}\n"
            f"[PASS] live {cat} get: {detail['id']}; {detail.get('licence', 'unknown')}; {detail['distribution_urls'][0]}")


def main():
    for cat in ('auckland-council', 'auckland-transport', 'waka-kotahi', 'niwa'):
        data = json.loads((FIXTURES / (cat + '.json')).read_text())
        rows, count, links = cli.ogc_page(data)
        record = cli.normalise_ogc(rows[0], cat, cli.CATALOGUES[cat]['source_url'], cli.now())
        assert count > 0 and record['distribution_urls'] and PROVENANCE <= record.keys()
        print(f'[PASS] fixture {cat}: Records response shape and distributions')
    ckan_fixture = json.loads((FIXTURES / 'data-govt-nz.json').read_text())
    rows, count, _ = cli.ckan_result(ckan_fixture)
    assert count == ckan_fixture['result']['count'] and len(rows) == 2
    record = cli.normalise_ckan(rows[0], 'data-govt-nz', cli.query_url('data-govt-nz'), cli.now())
    assert PROVENANCE <= record.keys() and record['distribution_urls']
    assert record['publisher'] == rows[0]['organization']['title']
    assert record['licence'] == rows[0]['license_title']
    assert record['geometry'] == json.loads(rows[0]['spatial'])
    assert 'latest_data' not in record
    print('[PASS] fixture data-govt-nz: synthetic CKAN search, provenance and geometry')
    ckan_detail = json.loads((FIXTURES / 'data-govt-nz-get.json').read_text())
    detail = cli.normalise_ckan(cli.ckan_result(ckan_detail, detail=True), 'data-govt-nz',
                                cli.query_url('data-govt-nz', record_id=rows[0]['id']), cli.now())
    assert detail['id'] == rows[0]['id'] and detail['distribution_urls'] == record['distribution_urls']
    print('[PASS] fixture data-govt-nz get: synthetic CKAN detail and distributions')
    jobs = [('auckland-council', 'flood'), ('auckland-transport', 'Future Connect'),
            ('waka-kotahi', 'traffic'), ('niwa', 'bathymetry')]
    failed = False
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [(cat, pool.submit(live, cat, term)) for cat, term in jobs]
        for cat, future in futures:
            try:
                print(future.result())
            except (AssertionError, cli.SourceError) as exc:
                print(f'[FAIL] live {cat}: {exc}')
                failed = True
    # Exercise the public executable surface with one bounded live request.
    run = subprocess.run([sys.executable, str(Path(__file__).with_name('cli.py')), 'search',
                          'bathymetry', '--catalogue', 'niwa', '--limit', '1', '--format', 'geojson'],
                         text=True, capture_output=True, timeout=50)
    if run.returncode in (4, 5):
        print('[SKIP] CLI GeoJSON: network error')
    elif run.returncode != 0:
        print('[FAIL] CLI GeoJSON: ' + run.stderr[-300:].strip())
        failed = True
    else:
        try:
            result = json.loads(run.stdout)
            assert result['type'] == 'FeatureCollection' and result['features']
            assert PROVENANCE <= result['meta'].keys() and PROVENANCE <= result['features'][0]['properties'].keys()
        except (ValueError, KeyError, TypeError, AssertionError):
            print('[FAIL] CLI GeoJSON: invalid output; ' + run.stderr[-300:].strip())
            failed = True
        else:
            print('[PASS] live CLI GeoJSON: provenance and catalogue coverage geometry')
    ckan, records = cli.catalogue_request('data-govt-nz', limit=1)
    if ckan['available']:
        assert records and PROVENANCE <= records[0].keys()
        print(f"[PASS] live CKAN: {ckan['number_matched']} matched")
    elif ckan.get('error_code') in (4, 5):
        print(f"[SKIP] data-govt-nz: {ckan['error']}")
    else:
        print(f"[FAIL] schema CKAN: {ckan['error']}")
        failed = True
    return int(failed)


if __name__ == '__main__':
    raise SystemExit(main())
