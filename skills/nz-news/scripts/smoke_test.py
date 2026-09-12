#!/usr/bin/env python3
"""Deterministic news/interview fixtures, then two bounded public feed probes."""
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import cli
from test_interviews import InterviewTests

SKILL_DIR = Path(__file__).resolve().parents[1]
CLI = SKILL_DIR / 'scripts/cli.py'


class NewsFixtures(unittest.TestCase):
    def test_rss_and_search_fixture(self):
        feed = {'id':'synthetic', 'name':'Synthetic News'}
        xml = '''<rss><channel><item><title><![CDATA[<b>Synthetic cyclone headline</b>]]></title>
        <link>https://www.rnz.co.nz/news/1</link><pubDate>Sun, 19 Jul 2026 09:30:00 +1200</pubDate>
        <description><![CDATA[<p>Synthetic summary.</p>]]></description></item></channel></rss>'''
        rows = cli.parse_rss_items(xml, feed)
        self.assertEqual(rows[0]['title'], 'Synthetic cyclone headline')
        self.assertEqual(rows[0]['sourceId'], 'synthetic')
        self.assertEqual(rows[0]['published'].isoformat(), '2026-07-19T09:30:00+12:00')
        self.assertEqual(len(cli.apply_search_filters(rows, keyword='cyclone')), 1)
        self.assertEqual(cli.apply_search_filters(rows, keyword='unmatched-928374'), [])

    def test_legacy_command_dispatch(self):
        for name, argv in (('cmd_summary',['summary','--json']), ('cmd_headlines',['headlines','--limit','2','--json']), ('cmd_search',['search','cyclone','--json'])):
            with self.subTest(command=name), patch.object(cli, name) as fn:
                fn.return_value = None
                self.assertEqual(cli.main(argv), 0)
                fn.assert_called_once()


def main():
    suite = unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromTestCase(NewsFixtures), unittest.defaultTestLoader.loadTestsFromTestCase(InterviewTests)])
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    if not result.wasSuccessful():
        return 1
    print(f'[PASS] fixture suite: {result.testsRun} news/interview tests')
    run = subprocess.run([sys.executable, str(CLI), '--help'], capture_output=True, timeout=10)
    assert run.returncode == 0 and b'interviews' in run.stdout
    for extra in ([], ['--contains', 'zz-no-interview-match-928374']):
        try:
            run = subprocess.run([sys.executable, str(CLI), 'interviews', '--programme', 'mike-hosking', '--limit', '2', '--json', *extra], capture_output=True, text=True, timeout=35)
        except subprocess.TimeoutExpired:
            print('[SKIP] live episode probe exceeded process deadline')
            return 0
        payload = json.loads(run.stdout)
        if run.returncode in {4, 5}:
            assert not payload['ok'] and payload['status'] in {'blocked','unavailable'}
            print(f"[SKIP] live episode source {payload['status']}")
            return 0
        assert run.returncode == 0, payload.get('error')
        assert payload['ok'] and payload['source_ledger']
        if extra:
            assert payload['status'] == 'empty' and payload['data'] == []
            print('[PASS] live no-match JSON is explicitly empty within scanned coverage')
        else:
            assert payload['data'] and payload['status'] == 'ok'
            assert payload['query']['window'] == 'last90days'
            assert all(row['provenance']['guid'] and row['provenance']['publication_date_raw'] for row in payload['data'])
            assert all(payload['query']['since'] <= row['publication_date'].replace('Z','+00:00') <= payload['query']['as_of'] for row in payload['data'])
            print('[PASS] live episode metadata, date window and provenance')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
