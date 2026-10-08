#!/usr/bin/env python3
"""Deterministic assertions using trimmed public source responses."""
import argparse
import io
import json
from pathlib import Path
import tempfile
import zipfile

import cli

FIXTURES = Path(__file__).resolve().parents[1] / 'tests' / 'fixtures'


def run():
    traffic_body = (FIXTURES/'C0032-trimmed.xlsx').read_bytes()
    name, traffic, epoch = next(cli.sheets(traffic_body))
    assert name == 'July 2012 to June 2026'
    assert traffic[1]['G'] == 'Count Start Date'
    assert traffic[1]['I'] == '7 Day ADT'
    assert cli.excel_date('41054',epoch) == '2012-05-25'
    try:
        cli.parse_traffic(traffic_body)
    except cli.SkillError as exc:
        assert str(exc) == 'No AT traffic survey rows parsed'
    else:
        raise AssertionError('Header-only workbook must not become an empty success')
    print('[PASS] fixture traffic workbook schema, date conversion and empty-data failure')

    cycle = cli.parse_active((FIXTURES/'S0207-trimmed.xlsx').read_bytes())
    assert len({r['site_id'] for r in cycle}) == 83
    albany = [r for r in cycle if r['site_id'] == 'Albany Highway Cyclist']
    assert [r['count'] for r in albany] == [92, 71, 71]
    assert albany[0]['date'] == '2026-07-01'
    assert next(r for r in cycle if r['site_id'] == 'Great North Rd')['count'] is None
    print('[PASS] fixture cycle counters, missing observations and daily values')

    hot = cli.parse_active((FIXTURES/'hotcity-trimmed.xlsx').read_bytes(), True)
    assert len({r['site_id'] for r in hot}) == 24
    quay = [r for r in hot if r['site_id'] == '107 Quay Street']
    assert [(r['date'], r['interval'], r['count']) for r in quay] == [('2026-01-01', '6:00-6:59', 162), ('2026-01-01', '7:00-7:59', 248)]
    print('[PASS] fixture pedestrian hourly observations and expanded camera network')

    daily = json.loads((FIXTURES/'nzta-daily.json').read_text())['features']
    records = [cli.arc_normalise(f, 'nzta-tms', cli.TMS, '2026-10-08T00:00:00Z') for f in daily]
    assert len(records) == 8 and {r['date'] for r in records} == {'2018-01-01'}
    assert {r['vehicle_class'] for r in records} == {'Light', 'Heavy'}
    assert len({(r['lane'],r['direction'],r['vehicle_class']) for r in records}) == 4
    assert cli.local_day(1514721600000) == '2018-01-01'
    print('[PASS] fixture NZTA local dates preserve separate lane and class counts')

    at = json.loads((FIXTURES/'at-adt.json').read_text())['features'][0]
    row = cli.arc_normalise(at, 'at-adt', cli.AT, '2026-10-08T00:00:00Z')
    assert row['site_id'] == '23788:522' and row['adt'] == 451
    assert abs(row['longitude']-174.88287627714192) < 1e-10
    assert {'source_url','publisher','licence','retrieved_at','latest_data'} <= row.keys()
    assert cli.distance(174.76,-36.85,174.76,-36.85) == 0
    print('[PASS] fixture AT site identity, WGS84 location and provenance')
    nzta_site = json.loads((FIXTURES/'nzta-sites.json').read_text())['features'][0]
    site = cli.arc_normalise(nzta_site,'nzta-tms',cli.TMS_SITES,'2026-10-08T00:00:00Z',True)
    assert site['site_id'] == '01000007' and 'longitude' in site


    # Exercise date bounds against actual downloaded records without contacting upstream.
    args = cli.build_parser().parse_args(['counts','--source','nzta-tms','--site','00200444','--from','2018-01-01','--to','2018-01-01'])
    old_arc, old_wb = cli.arc_rows, cli.workbook_records
    try:
        def arc(base, a, where):
            assert "2017-12-31 11:00:00" in where and "2018-01-01 11:00:00" in where
            return [(f,cli.TMS,'2026-10-08T00:00:00Z') for f in daily], []
        cli.arc_rows = arc
        counts, warnings = cli.get_counts(args)
        assert len(counts) == 8 and warnings and all(r['duplicate_daily_key'] for r in counts)
        args = cli.build_parser().parse_args(['counts','--source','at-cycle-monthly','--site','Albany Highway Cyclist'])
        cli.workbook_records = lambda a: [{**r,**cli.provenance(a.source)} for r in cycle]
        monthly = cli.get_counts(args)[0][0]
        assert monthly['count'] == 234 and monthly['observed_days'] == 3
        args = cli.build_parser().parse_args(['sites','--source','at-adt','--format','geojson','--json'])
        out = cli.envelope([row],args,[])
        assert out['features'][0]['geometry']['coordinates'] == [row['longitude'],row['latitude']]
        assert out['features'][0]['properties']['source_url'] == cli.AT
    finally:
        cli.arc_rows, cli.workbook_records = old_arc, old_wb
    print('[PASS] fixture bounded date queries, monthly observed-day totals and GeoJSON')

    # Cache reuses retrieval time, expires, and max-age=0 makes a fresh request.
    old_fetch = cli.nzfetch.fetch_bytes
    calls = []
    try:
        def fake_fetch(url, **kw):
            calls.append(url)
            assert kw['timeout'] == 10 and kw['max_bytes'] == 32*1024*1024
            return b'{}', 'application/json', url
        cli.nzfetch.fetch_bytes = fake_fetch
        with tempfile.TemporaryDirectory() as folder:
            a = argparse.Namespace(cache_dir=Path(folder),max_age=86400)
            first = cli.fetch(cli.AT,a)
            assert cli.fetch(cli.AT,a) == first and len(calls) == 1
            meta = next(Path(folder).glob('*.json'))
            d = json.loads(meta.read_text());d['fetched_epoch'] = 0;meta.write_text(json.dumps(d))
            cli.fetch(cli.AT,a);assert len(calls) == 2
            a.max_age = 0;cli.fetch(cli.AT,a);assert len(calls) == 3
    finally:
        cli.nzfetch.fetch_bytes = old_fetch
    print('[PASS] fixture cache retrieval provenance, expiry and forced refresh')

    # Minimal synthetic date1904/shared-string case supplements real inline fixtures.
    with io.BytesIO() as stream:
        with zipfile.ZipFile(stream,'w') as z:
            z.writestr('xl/workbook.xml', '<workbook xmlns="'+cli.NS['s']+'" xmlns:r="'+cli.REL+'"><workbookPr date1904="1"/><sheets><sheet name="test" r:id="r1"/></sheets></workbook>')
            z.writestr('xl/_rels/workbook.xml.rels','<Relationships><Relationship Id="r1" Target="worksheets/sheet1.xml"/></Relationships>')
            z.writestr('xl/sharedStrings.xml','<sst xmlns="'+cli.NS['s']+'"><si><r><t>Rich </t></r><r><t>text</t></r></si></sst>')
            z.writestr('xl/worksheets/sheet1.xml','<worksheet xmlns="'+cli.NS['s']+'"><sheetData><row><c r="D1" t="s"><v>0</v></c></row></sheetData></worksheet>')
        _,rows,epoch = next(cli.sheets(stream.getvalue()))
        assert rows == [{'D':'Rich text'}] and cli.excel_date('0',epoch) == '1904-01-01'
    print('[PASS] fixture sparse cells, rich shared strings and Excel 1904 epoch')


if __name__ == '__main__':
    run()
