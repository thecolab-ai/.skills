#!/usr/bin/env python3
"""Deterministic assertions using trimmed public source responses."""
import argparse
import io
import os
import json
from pathlib import Path
import tempfile
import subprocess
import sys
from unittest.mock import patch
from contextlib import redirect_stdout, redirect_stderr
import zipfile

import cli

FIXTURES = Path(__file__).resolve().parents[1] / 'tests' / 'fixtures'


def run():
    from city_tests import run as city_tests
    city_tests()
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
    assert row['source_url'] == cli.AT
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
            assert kw['timeout'] == 10 and kw['max_bytes'] == 32*1024*1024 and kw['allowed_hosts'] == cli.ALLOWED
            return b'{}', 'application/json', url
        cli.nzfetch.fetch_bytes = fake_fetch
        with tempfile.TemporaryDirectory() as folder:
            a = argparse.Namespace(cache_dir=Path(folder),max_age=86400)
            first = cli.fetch(cli.AT,a)
            assert cli.fetch(cli.AT,a) == first and len(calls) == 1
            meta = next((Path(folder)/'nz-traffic-counts-v1').glob('*.json'))
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
    regressions(cycle, row)
    re_review_regressions()


def synthetic_workbook(rows, name='test'):
    """Synthetic cells only: exercise edge cases without redistributing restricted data."""
    from xml.sax.saxutils import escape
    with io.BytesIO() as stream:
        with zipfile.ZipFile(stream, 'w') as z:
            z.writestr('xl/workbook.xml', '<workbook xmlns="'+cli.NS['s']+'" xmlns:r="'+cli.REL+'"><sheets><sheet name="'+name+'" r:id="r1"/></sheets></workbook>')
            z.writestr('xl/_rels/workbook.xml.rels','<Relationships><Relationship Id="r1" Target="worksheets/sheet1.xml"/></Relationships>')
            cells = []
            for index, row in enumerate(rows, 1):
                cells.append('<row>' + ''.join('<c r="'+col+str(index)+'" t="inlineStr"><is><t>'+escape(str(value))+'</t></is></c>' for col, value in row.items()) + '</row>')
            z.writestr('xl/worksheets/sheet1.xml','<worksheet xmlns="'+cli.NS['s']+'"><sheetData>'+''.join(cells)+'</sheetData></worksheet>')
        return stream.getvalue()


def regressions(cycle, at_row):
    from datetime import datetime
    epoch = datetime(1899, 12, 30)
    def serial(day):
        return str((datetime.fromisoformat(day) - epoch).days)
    body = synthetic_workbook([
        {'A': 'Date', 'B': 'Time', 'C': 'Wanted', 'D': 'Other'},
        {'A': serial('2016-01-01'), 'B': '00:00', 'C': '-', 'D': '7'},
        {'A': serial('2016-12-31'), 'B': '00:00', 'C': '12', 'D': '8'},
        {'A': serial('2017-01-15'), 'B': '00:00', 'C': '3', 'D': '4'},
    ])
    info = {}
    records = cli.parse_active(body, True, wanted_site='Wanted', nominal_year='2016', info=info)
    assert len(records) == 3 and records[0]['count'] is None
    assert records[2]['date_outside_file_year'] and records[2]['date'] == '2017-01-15'
    assert info['latest'] == '2016-12-31' and '1 placeholder' in info['warnings'][0]
    assert '2017-01-15' in info['warnings'][1]
    filtered = cli.parse_active(body, True, wanted_site='Wanted', start='2016-12-31', end='2016-12-31')
    assert len(filtered) == 1 and filtered[0]['count'] == 12
    sites = cli.parse_active(body, True, sites_only=True)
    assert len(sites) == 2 and next(r for r in sites if r['site_id'] == 'Wanted')['first_observed'] == '2016-12-31'
    for value in ['–', 'n/a', 'NA', '']:
        placeholder = synthetic_workbook([{'A': 'Date', 'B': 'Time', 'C': 'Wanted'}, {'A': serial('2016-01-01'), 'C': value}])
        assert cli.parse_active(placeholder, True)[0]['count'] is None
    invalid = synthetic_workbook([{'A': 'Date', 'B': 'Time', 'C': 'Wanted'}, {'A': serial('2016-01-01'), 'C': 'oops'}])
    try:
        cli.parse_active(invalid, True)
    except cli.SkillError as exc:
        assert exc.code == 6
    else:
        raise AssertionError('Unrecognised count must fail')
    date_cycle = synthetic_workbook([{'A': 'Date', 'B': 'Synthetic cyclist'}, {'A': serial('2024-07-01'), 'B': '61'}])
    assert cli.parse_active(date_cycle)[0]['count'] == 61
    text_cycle = synthetic_workbook([{'A': 'Date', 'B': 'Synthetic cyclist'}, {'A': 'Wednesday, 1 July 2020', 'B': '9'}])
    assert cli.parse_active(text_cycle)[0]['date'] == '2020-07-01'
    shifted_cycle = synthetic_workbook([
        {'A': 'Year', 'B': 'Month', 'C': 'Date', 'D': 'Date Check', 'E': 'Weekday', 'F': 'Weekend/Holiday', 'G': 'Date', 'H': 'Synthetic cyclist'},
        {'A': '2024', 'B': 'August', 'C': serial('2024-08-01'), 'D': 'OK', 'E': '1', 'F': '0', 'G': serial('2024-08-01'), 'H': '64'}])
    shifted = cli.parse_active(shifted_cycle)
    assert len(shifted) == 1 and shifted[0]['date'] == '2024-08-01' and shifted[0]['count'] == 64
    traffic = synthetic_workbook([
        {'B': 'Road Name', 'G': 'Count Start Date', 'H': '5 Day ADT', 'I': '7 Day ADT'},
        {'A': 'Synthetic area', 'B': 'Synthetic road', 'G': serial('2016-01-01'), 'H': '1.5', 'I': '2'},
        {'A': 'Synthetic area', 'B': 'Synthetic road', 'G': serial('2016-01-01'), 'H': '1.5', 'I': '2'},
    ], 'July 2012 synthetic')
    duplicate_info = {}
    duplicated = cli.parse_traffic(traffic, info=duplicate_info)
    assert len(duplicated) == 2 and all(r['duplicate_row'] for r in duplicated)
    assert duplicate_info['warnings'] and duplicated[0]['adt_5_day'] == 1.5
    unrelated = synthetic_workbook([{'A': 'Date', 'B': 'Wanted', 'C': 'Other'}, {'A': serial('2024-07-01'), 'B': '61', 'C': 'z'}])
    unrelated_info = {}
    assert cli.parse_active(unrelated, wanted_site='Wanted', info=unrelated_info)[0]['count'] == 61
    assert 'non-numeric cells' in unrelated_info['warnings'][0]
    for huge in ('1e300', 'inf'):
        try:
            cli.excel_date(huge, epoch)
        except cli.SkillError as exc:
            assert exc.code == 6
        else:
            raise AssertionError('Huge dates must become schema failures')
    print('[PASS] synthetic missing cells, nominal-year warnings and selective streaming parsers')

    links = (FIXTURES/'cycle-links.html').read_bytes()
    parser = cli.DownloadLinks(); parser.feed(links.decode())
    assert {cli.download_period(link) for link in parser.links} == {f'{year}-{m:02d}' for year in (2024, 2025) for m in range(1, 13)} | {'2026-05'}
    assert cli.download_period('/media/szypg1y3/daily-cycle-count-data-may-2026_auckland-transport.xlsx') == '2026-05'
    assert cli.download_period('/media/1982096/jan2020akldcyclecounterdata.xlsx') is None
    assert cli.download_period('/cycle-january-2024-2025.xlsx') is None
    assert cli.download_period('/january-2024/noncycle-may-sept-2025.xlsx') is None
    assert cli.download_period('/january-2024/cycle-feb-2025.xlsx') == '2025-02'
    assert cli.download_period('/cycle-2025/file-march-2025.xlsx') is None
    args = cli.build_parser().parse_args(['counts', '--source', 'at-cycle-monthly', '--site', 'Wanted', '--from', '2025-01-01', '--to', '2025-12-31'])
    with patch.object(cli, 'fetch', return_value=(links, '2026-10-08T00:00:00Z')):
        assert len(cli.workbook_urls(args)) == 12
    incomplete = links.decode().replace('cycle-movements-march-2025.xlsx', 'unsupported-march-2025.xlsx').encode()
    with patch.object(cli, 'fetch', return_value=(incomplete, '2026-10-08T00:00:00Z')):
        assert len(cli.workbook_urls(args)) == 11 and '2025-03' in args._warnings[0]
    latest_args = cli.build_parser().parse_args(['sites', '--source', 'at-cycle-daily'])
    with patch.object(cli, 'fetch', return_value=(links, '2026-10-08T00:00:00Z')):
        assert cli.download_period(cli.workbook_urls(latest_args)[0]) == '2026-05'
    hot_links = b'<a href="/files/All-pedestrian-2027-October.xlsx">new</a><a href="/files/All-pedestrian-2026.xlsx">old</a>'
    latest_args.source = 'hotcity'
    with patch.object(cli, 'fetch', return_value=(hot_links, '2026-10-08T00:00:00Z')):
        assert cli.download_period(cli.workbook_urls(latest_args)[0], True) == '2027'
    month_body = synthetic_workbook([{'A': 'Time', 'B': 'Wanted'},
        {'A': serial('2024-08-31'), 'B': '59'}, {'A': serial('2024-09-01'), 'B': '86'}])
    args = cli.build_parser().parse_args(['counts', '--source', 'at-cycle-monthly', '--site', 'Wanted', '--from', '2024-01-01', '--to', '2024-12-31'])
    with patch.object(cli, 'workbook_urls', return_value=[cli.CYCLE_PAGE + 'cycle-september-2024.xlsx']), patch.object(cli, 'fetch', return_value=(month_body, '2026-10-08T00:00:00Z')):
        monthly, _ = cli.get_counts(args)
    assert [r['date'] for r in monthly] == ['2024-08-01', '2024-09-01']
    assert monthly[0]['date_outside_file_month'] and '2024-08-31' in args._warnings[0]
    assert 'missing_days' not in monthly[0]
    print('[PASS] captured AT archive links, missing-month warnings and latest-download discovery')

    for source, expected in [('at-cycle-daily', '2025-06-01'), ('hotcity', '2025-01-01'), ('nzta-tms', '2025-05-31')]:
        args = cli.build_parser().parse_args(['counts', '--source', source, '--site', 'Wanted', '--to', '2025-06-30'])
        cli.resolve_dates(args)
        assert args.date_from == expected
    for argv in [
        ['counts', '--source', 'hotcity', '--json'],
        ['sites', '--source', 'hotcity', '--bbox', '174,-37,174,-36', '--json'],
        ['sites', '--source', 'hotcity', '--from', 'bad', '--json'],
        ['counts', '--source', 'hotcity', '--site', 'x', '--from', '2026-08-01', '--to', '2025-06-01', '--json'],
        ['sources', '--max-records', '50001', '--json'],
        ['sites', '--source', 'hotcity', '--bbox', '174,-37,175,-36', '--format', 'geojson'],
        ['sites', '--source', 'hotcity', '--bbox', 'bad', '--format=geojson'],
    ]:
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = cli.main(argv)
        error = json.loads(out.getvalue())
        assert code in (2, 7) and error['error']['code'] == code and error['error']['type']
        assert error['results'] == [] and error['meta']['source_url']
    assert 'licence' not in cli.source_provenance(cli.AT, 'Unknown publisher', licence=None)
    print('[PASS] one-sided date defaults, bounded arguments, JSON and GeoJSON error contracts')

    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        unrelated = root/'unrelated.bin'; unrelated.write_bytes(b'keep')
        own = root/'nz-traffic-counts-v1';own.mkdir()
        other = own/'unrelated.bin';other.write_bytes(b'keep')
        os.utime(unrelated, (0, 0));os.utime(other, (0, 0))
        args = argparse.Namespace(cache_dir=root, max_age=1)
        with patch.object(cli.nzfetch, 'fetch_bytes', return_value=(b'{}', 'application/json', cli.AT)):
            cli.fetch(cli.AT, args)
            assert unrelated.read_bytes() == other.read_bytes() == b'keep'
            with patch.object(Path, 'mkdir', side_effect=OSError('read only')):
                args.cache_dir = root/'new'
                assert cli.fetch(cli.AT, args)[0] == b'{}' and args._warnings
    print('[PASS] isolated cache pruning and successful downloads despite cache write failure')

    for upstream_code, expected in [(503, 5), (400, 6)]:
        args = argparse.Namespace(cache_dir=Path('.'), max_age=0)
        with patch.object(cli, 'fetch', return_value=(json.dumps({'error': {'code': upstream_code, 'message': 'test'}}).encode(), '2026-10-08T00:00:00Z')):
            try:
                cli.arc_query(cli.AT, args)
            except cli.SkillError as exc:
                assert exc.code == expected
            else:
                raise AssertionError('ArcGIS errors must fail')
    for source, site, counts in [('at-adt', '1:1', [0]), ('nzta-tms', 'ZZZ999', [0, 0]), ('nzta-tms', '00200444', [0, 1]), ('at-adt', '23788:522', [1])]:
        args = cli.build_parser().parse_args(['counts', '--source', source, '--site', site, '--from', '2018-01-01', '--to', '2018-01-01'])
        def count_query(base, a, **params):
            assert 'DATE' not in params['where'] and 'TIMESTAMP' not in params['where']
            return {'count': counts.pop(0)}, base, '2026-10-08T00:00:00Z'
        with patch.object(cli, 'arc_rows', return_value=([], [])), patch.object(cli, 'arc_query', side_effect=count_query):
            cli.resolve_dates(args)
            try:
                rows, warnings = cli.get_counts(args)
            except cli.SkillError as exc:
                assert exc.code == 2 and site in str(exc)
            else:
                assert not rows and warnings == ['Site exists but has no observations in the requested period']
    args = cli.build_parser().parse_args(['counts', '--source', 'at-adt', '--site', '23788:522', '--max-records', '1'])
    feature = json.loads((FIXTURES/'at-adt.json').read_text())['features'][0]
    def capped_query(base, args, **params):
        assert params['orderByFields'] == 'count_date,OBJECTID'
        return {'features': [feature], 'exceededTransferLimit': True}, cli.AT, '2026-10-08T00:00:00Z'
    with patch.object(cli, 'arc_query', side_effect=capped_query):
        _, warnings = cli.arc_rows(cli.AT, args)
    assert 'Returned period 2002-03-21..2002-03-21' in warnings[0]
    print('[PASS] transient ArcGIS errors and unknown versus inactive site distinction')

    # A fixture-backed direct envelope remains valid inside the canonical runner envelope.
    from result_contract import validate_result_envelope
    import importlib.util
    runner_path = Path(__file__).resolve().parents[3]/'scripts'/'run_skill.py'
    spec = importlib.util.spec_from_file_location('traffic_fixture_runner', runner_path)
    runner = importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
    args = cli.build_parser().parse_args(['counts', '--source', 'at-adt', '--site', '23788:522', '--json'])
    fixture_envelope = cli.envelope([at_row], args, [])
    fixture_process = subprocess.CompletedProcess([], 0, json.dumps(fixture_envelope), '')
    out = io.StringIO()
    with patch.object(sys, 'argv', [str(runner_path), 'nz-traffic-counts', 'counts', '--source', 'at-adt', '--site', '23788:522']), patch.object(runner.subprocess, 'run', return_value=fixture_process), redirect_stdout(out):
        assert runner.main() == 0
    wrapped = json.loads(out.getvalue())
    assert validate_result_envelope(wrapped) == [] and wrapped['ok'] and wrapped['data']['results'][0]['adt'] == 451
    p = subprocess.run([sys.executable, str(runner_path), 'nz-traffic-counts', 'sources'], capture_output=True, text=True, timeout=15)
    result = json.loads(p.stdout)
    assert p.returncode == 0 and result['ok'] and len(result['data']['results']) == len(cli.SOURCES)
    assert validate_result_envelope(result) == []
    print('[PASS] fixture result contract and network-free canonical sources command')


def re_review_regressions():
    """Synthetic workbook regressions for the second security/QA review."""
    stamp = '2026-10-08T00:00:00Z'
    july_url = 'https://at.govt.nz/media/synthetic/cycle-july-2024.xlsx'
    august_url = 'https://at.govt.nz/media/synthetic/cycle-august-2024.xlsx'
    september_url = 'https://at.govt.nz/media/synthetic/cycle-september-2024.xlsx'
    footer = synthetic_workbook([{'A': 'Date', 'B': 'Time', 'C': 'Wanted'},
        {'A': '2025-01-01', 'B': '00:00', 'C': '7'},
        {'A': 'PLEASE NOTE: ', 'C': 'Synthetic source notes, not an observation'}])
    assert len(cli.parse_active(footer, hotcity=True)) == 1
    body = synthetic_workbook([
        {'A': 'Date', 'B': 'Wanted', 'C': 'Other'},
        {'A': '2024-07-01', 'B': 'Pending', 'C': '7'},
        {'A': '2024-07-02', 'B': 'z', 'C': '8'},
        {'A': '2024-07-03', 'B': '9', 'C': '10'},
    ])
    args = cli.build_parser().parse_args(['counts', '--source', 'at-cycle-daily', '--site', 'Wanted'])
    with patch.object(cli, 'workbook_urls', return_value=[july_url]), patch.object(cli, 'fetch', return_value=(body, stamp)):
        daily, _ = cli.get_counts(args)
    assert [r['count'] for r in daily] == [None, None, 9]
    assert 'invalid_count_raw' not in daily[0] and daily[1]['invalid_count_raw'] == 'z'
    assert any('cycle-july-2024.xlsx: Wanted on 2024-07-02' in w for w in args._warnings)
    assert any('placeholder' in w for w in args._warnings)
    args.source = 'at-cycle-monthly'
    with patch.object(cli, 'workbook_urls', return_value=[july_url]), patch.object(cli, 'fetch', return_value=(body, stamp)):
        monthly, _ = cli.get_counts(args)
    assert monthly[0]['count'] == 9 and monthly[0]['missing_days'] == 30
    assert monthly[0]['invalid_count_days'] == [{'date': '2024-07-02', 'invalid_count_raw': 'z'}]
    print('[PASS] synthetic Pending/z counts, file/site/date warnings and monthly invalid-day provenance')

    august = synthetic_workbook([{'A': 'Date', 'B': 'Wanted', 'C': 'Empty'},
        {'A': '2024-08-01', 'B': '10'}, {'A': '2024-08-31', 'B': '59'}])
    september = synthetic_workbook([{'A': 'Date', 'B': 'Wanted', 'C': 'Empty'},
        {'A': '2024-09-02', 'B': '20'}, {'A': '2024-08-31', 'B': '59'}, {'A': '2024-09-01', 'B': '30'}])
    def fetch_workbook(url, args, **kwargs):
        return (august if url == august_url else september), stamp
    args = cli.build_parser().parse_args(['sites', '--source', 'at-cycle-daily'])
    with patch.object(cli, 'workbook_urls', return_value=[september_url, august_url]), patch.object(cli, 'fetch', side_effect=fetch_workbook):
        sites, _ = cli.get_sites(args)
    wanted = next(r for r in sites if r['site_id'] == 'Wanted')
    assert (wanted['first_observed'], wanted['last_observed'], wanted['date']) == ('2024-08-01', '2024-09-02', '2024-09-02')
    empty = next(r for r in sites if r['site_id'] == 'Empty')
    assert empty['first_observed'] is empty['last_observed'] is empty['date'] is None
    for order in ([august_url, september_url], [september_url, august_url]):
        args = cli.build_parser().parse_args(['counts', '--source', 'at-cycle-daily', '--site', 'Wanted'])
        with patch.object(cli, 'workbook_urls', return_value=order), patch.object(cli, 'fetch', side_effect=fetch_workbook):
            daily, _ = cli.get_counts(args)
        assert [r['date'] for r in daily] == ['2024-08-01', '2024-08-31', '2024-09-01', '2024-09-02']
        assert sum(r['count'] for r in daily) == 119 and not any(r.get('duplicate_row') for r in daily)
        assert any('1 equal outside-month' in w for w in args._warnings)
        args.source = 'at-cycle-monthly'
        with patch.object(cli, 'workbook_urls', return_value=order), patch.object(cli, 'fetch', side_effect=fetch_workbook):
            monthly, _ = cli.get_counts(args)
        assert [r['count'] for r in monthly] == [69, 50]
        assert not any(r.get('date_outside_file_month') for r in monthly)
    september = synthetic_workbook([{'A': 'Date', 'B': 'Wanted'},
        {'A': '2024-08-31', 'B': '60'}, {'A': '2024-09-01', 'B': '30'}])
    args.source = 'at-cycle-daily'
    with patch.object(cli, 'workbook_urls', return_value=[august_url, september_url]), patch.object(cli, 'fetch', side_effect=fetch_workbook):
        daily, _ = cli.get_counts(args)
    duplicates = [r for r in daily if r['date'] == '2024-08-31']
    assert len(duplicates) == 2 and all(r['duplicate_row'] for r in duplicates)
    assert any('Conflicting duplicate' in w for w in args._warnings)
    args.source = 'at-cycle-monthly'
    with patch.object(cli, 'workbook_urls', return_value=[august_url, september_url]), patch.object(cli, 'fetch', side_effect=fetch_workbook):
        monthly, _ = cli.get_counts(args)
    assert all(r['duplicate_row'] for r in monthly if r['date'] == '2024-08-01')
    assert 'missing_days' not in next(r for r in monthly if r.get('date_outside_file_month'))
    print('[PASS] synthetic multi-workbook site bounds, equal/conflicting spillovers and daily sorting')

    links = (FIXTURES / 'cycle-links.html').read_bytes()
    for bounds in (['--from', '2027-01-01'], ['--to', '2023-12-31']):
        args = cli.build_parser().parse_args(['counts', '--source', 'at-cycle-daily', '--site', 'Wanted', *bounds])
        cli.resolve_dates(args)
        with patch.object(cli, 'fetch', return_value=(links, stamp)):
            try:
                cli.workbook_urls(args)
            except cli.SkillError as exc:
                assert exc.code == 7 and 'latest published month is 2026-05' in str(exc)
                assert 'monthly XLSX coverage begins 2024-01' in str(exc)
            else:
                raise AssertionError('Unsupported dates must fail with coverage bounds')
    for broken in (synthetic_workbook([{'A': 'Changed header'}]),
                   synthetic_workbook([{'A': 'Date', 'B': 'Wanted'}, {'A': 'invalid date', 'B': '7'}]),
                   b'not a workbook'):
        output = io.StringIO()
        with patch.object(cli, 'workbook_urls', return_value=[july_url]), patch.object(cli, 'fetch', return_value=(broken, stamp)), redirect_stdout(output), redirect_stderr(io.StringIO()):
            code = cli.main(['counts', '--source', 'at-cycle-daily', '--site', 'Wanted', '--json'])
        result = json.loads(output.getvalue())
        assert code == 6 and result['error']['type'] == 'schema_failure'
        assert july_url in result['error']['message'] and 'cycle-july-2024.xlsx' in result['error']['message']
        assert result['meta']['source_url'] == july_url and result['meta']['retrieved_at'].endswith('Z')
    print('[PASS] synthetic archive coverage errors and workbook-specific schema error provenance')


if __name__ == '__main__':
    run()
