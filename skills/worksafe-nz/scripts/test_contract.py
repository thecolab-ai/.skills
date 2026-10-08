#!/usr/bin/env python3
"""Offline command, parser, provenance and bounded-cache checks."""
import contextlib
import io
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import cli

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / 'lib'))
from contract_test import audit_skill  # noqa: E402

FIXTURES = Path(__file__).resolve().parents[1] / 'tests/fixtures'
STAMP = '2026-10-01T01:02:03Z'


def fixture_checks():
    text = (FIXTURES / 'notifications.csv').read_text()
    fatal = (FIXTURES / 'fatalities.csv').read_text()
    page = (FIXTURES / 'source-page.html').read_text()
    rows = cli.parse_csv(text, 'incidents')
    assert len(rows) == 4 and sum(r['count'] for r in rows) == 13
    for dataset in ('concerns', 'injuries_serious_harm'):
        assert sum(r['count'] for r in cli.parse_csv(text, dataset)) == 13
    legacy = cli.parse_csv((FIXTURES / 'serious-harm.csv').read_text(), 'serious_harm')
    assert legacy[0]['industry_level2'] == 'Synthetic industry two' and legacy[0]['classification'] == ''
    assert cli.aggregate(rows, 'industry') == [{'industry': 'Construction', 'count': 11}, {'industry': 'Manufacturing', 'count': 2}]
    assert cli.aggregate(rows, 'year') == [{'year': 2024, 'count': 10}, {'year': 2025, 'count': 3}]
    assert sum(r['count'] for r in cli.filter_rows(rows, 'cOnStRuCtIoN', 'auck', '2024-02', '2025-01')) == 3
    assert cli.filter_rows(rows, 'CONSTRUCT') == []
    assert cli.filter_rows(rows, 'synthetic industry three') == []
    assert len(cli.filter_rows(rows, 'synthetic industry three', industry_match='any-level')) == 4
    assert sum(r['count'] for r in cli.filter_rows(rows, 'Construction')) == 11
    assert sum(r['count'] for r in cli.filter_rows(rows, 'CONSTRUCT', industry_match='any-level')) == 13
    assert cli.filter_rows(rows, region='operational') == []
    fatal_rows = cli.parse_csv(fatal, 'fatalities')
    grouped = cli.aggregate(fatal_rows, 'fatalities')
    assert sum(r['count'] for r in grouped) == 6 and len(grouped) == 5
    assert all(set(r) == {'year', 'industry', 'region', 'count'} for r in grouped)
    assert sum(r['count'] for r in cli.filter_rows(fatal_rows, 'Construction')) == 3
    assert sum(r['count'] for r in cli.filter_rows(fatal_rows, 'Construction', industry_match='any-level')) == 6
    print('[PASS] fixture CSV formats, weighted counts, filters and grouped fatalities')

    with patch.object(cli, 'fetch_cached', return_value=(page, STAMP)):
        discovered = cli.source('incidents', 86400)
        assert discovered['latest_data'] == '02 Feb 2025' and discovered['retrieved_at'] == STAMP
    source = cli.parse_source_page(page, 'incidents')
    assert source['page_updated'] == '02 Feb 2025'
    assert cli.parse_source_page(page, 'serious_harm')['source_url'].endswith('synthetic-legacy.csv')
    for bad in ('<html>changed schema</html>', page.replace('https://data-centre-public.s3.ap-southeast-2.amazonaws.com', 'https://example.invalid')):
        try:
            cli.parse_source_page(bad, 'incidents')
        except cli.SkillError as exc:
            assert exc.code == 6
        else:
            raise AssertionError('Invalid source metadata accepted')
    for bad in ('Year,Month\n2025,1\n', text.replace(',7\n', ',bad\n'), text.replace(',7\n', ',-1\n'), text.splitlines()[0]+'\n', fatal.replace('synthetic-1', 'synthetic-0')):
        try:
            cli.parse_csv(bad, 'fatalities' if 'FatalID' in bad else 'incidents')
        except cli.SkillError as exc:
            assert exc.code == 6
        else:
            raise AssertionError('Invalid CSV accepted')
    print('[PASS] fixture changed-schema, invalid-count and duplicate-fatality failures')

    def fake_fetch(url, max_age):
        return (page if '/graph/summary/' in url else fatal if url.endswith('/fatalities/synthetic.csv') else text), STAMP

    # Source fixtures are synthetic; adapt only the download path for each dataset.
    def fake_source(dataset, max_age):
        info = cli.parse_source_page(page, dataset)
        info['source_url'] = 'https://' + cli.S3_HOST + '/data-sets/' + dataset + '/synthetic.csv'
        info.update(cli.provenance(info['source_url'], cli.PUBLISHER, licence=cli.TERMS, retrieved_at=STAMP))
        return info

    cases = [(['sources'], 5), (['datasets'], 5), (['incidents', '--limit', '1'], 1),
             (['fatalities', '--year', '2024'], 1), (['summary', '--by', 'year'], 2),
             (['incidents', '--industry', 'absent'], 0)]
    with patch.object(cli, 'fetch_cached', side_effect=fake_fetch), patch.object(cli, 'source', side_effect=fake_source):
        for args, length in cases:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                assert cli.main([*args, '--json']) == 0
            payload = json.loads(out.getvalue())
            assert len(payload['results']) == length
            assert payload['meta']['publisher'] == cli.PUBLISHER and payload['meta']['retrieved_at'].endswith('Z')
            if args[0] not in ('sources', 'datasets'):
                assert payload['meta']['retrieved_at'] == STAMP and payload['meta']['latest_data'] == '2025-01'
            if args[0] == 'incidents' and length:
                assert payload['meta']['matched_count'] == 13 and payload['meta']['truncated']
            if args[0] == 'datasets':
                assert all(r['retrieved_at'] == STAMP and r['latest_data'] == '2025-01' for r in payload['results'])
        # Construction in a lower-level or AFF2017 group must not inflate sector totals.
        for command in (['incidents', '--limit', '0'], ['fatalities'],
                        ['summary', '--by', 'industry'], ['summary', '--dataset', 'fatalities', '--by', 'industry']):
            expected_exact = 3 if 'fatalities' in command else 11
            expected_broad = 6 if 'fatalities' in command else 13
            for mode, expected_count in (([], expected_exact), (['--industry-match', 'top-level'], expected_exact),
                                         (['--industry-match', 'any-level'], expected_broad)):
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    assert cli.main([*command, '--industry', 'cOnStRuCtIoN', *mode, '--json']) == 0
                payload = json.loads(out.getvalue())
                assert payload['meta']['matched_count'] == expected_count
                assert sum(r['count'] for r in payload['results']) == expected_count
                industries = {r['industry'] for r in payload['results']}
                assert industries == ({'Construction'} if expected_count == expected_exact else
                                      {'Construction', 'Manufacturing', 'Mining', 'Wholesale Trade'} if 'fatalities' in command else
                                      {'Construction', 'Manufacturing'})
    print('[PASS] exact top-level industry and opt-in any-level command counts')
    invalid = [['--bad-option'], ['summary', '--by', 'bad'], ['incidents', '--from', '2025-13'],
               ['incidents', '--from', '2025-02', '--to', '2024-01'], ['incidents', '--limit', '-1'],
               ['sources', '--max-age', 'nan'], ['fatalities', '--year', '0'],
               ['incidents', '--industry-match', 'invalid']]
    with patch.object(cli, 'fetch_cached', side_effect=AssertionError('Invalid input made a network call')):
        for args in invalid:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                assert cli.main([*args, '--json']) == 2
            payload = json.loads(out.getvalue())
            assert payload['error']['type'] == 'invalid_input' and payload['results'] == []
    with patch.object(cli, 'fetch_cached', side_effect=cli.SkillError('network error: rate-limited', 4, retry_after='60')):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            assert cli.main(['sources', '--json']) == 4
        assert json.loads(out.getvalue())['error']['retry_after'] == '60'
    print('[PASS] fixture all command envelopes, cache timestamps, truncation and JSON errors')

    with tempfile.TemporaryDirectory(dir=FIXTURES.parent) as directory:
        cache = Path(directory)
        url = 'https://' + cli.S3_HOST + '/synthetic.csv'
        with patch.object(cli.nzfetch, 'fetch_bytes', return_value=(b'synthetic response', 'text/csv', url)) as network:
            first = cli.fetch_cached(url, 86400, cache)
            network.assert_called_once_with(url, timeout=10, allowed_hosts=(cli.S3_HOST,))
            second = cli.fetch_cached(url, 86400, cache)
            assert first == second and network.call_count == 1
            cli.fetch_cached(url, 0, cache)
            assert network.call_count == 2
            next(cache.glob('*.json')).write_text('corrupt')
            cli.fetch_cached(url, 86400, cache)
            assert network.call_count == 3
        page_url = cli.ROOT_URL + 'graph/summary/incidents'
        with patch.object(cli.nzfetch, 'fetch_bytes', return_value=(b'synthetic page', 'text/html', page_url)) as network:
            cli.fetch_cached(page_url, 0, cache)
            network.assert_called_once_with(page_url, timeout=10, allowed_hosts=('data.worksafe.govt.nz',))
        with patch.object(cli.nzfetch, 'fetch_bytes', side_effect=cli.nzfetch.FetchError('synthetic outage')):
            try:
                cli.fetch_cached(url, 0, cache)
            except cli.SkillError as exc:
                assert exc.code == 5
            else:
                raise AssertionError('Expired cache served on outage')
    print('[PASS] fixture cache reuse, forced refresh, corruption, outage expiry and request host allowlists')


def main():
    result = audit_skill(Path(__file__).resolve().parents[1])
    if result['ok']:
        fixture_checks()
        result['checks'].extend(('source_parser', 'filters', 'provenance', 'json_errors', 'bounded_cache'))
    print(json.dumps(result, indent=2))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
