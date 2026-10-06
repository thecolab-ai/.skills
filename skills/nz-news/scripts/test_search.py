#!/usr/bin/env python3
"""Deterministic keyword matcher tests for search/topic."""
import argparse
import contextlib
import datetime as dt
import io
import json
import unittest
from unittest.mock import patch

import cli

PUBLISHED = dt.datetime(2026, 10, 6, 9, 0, tzinfo=dt.timezone.utc)


def story(title, summary=None):
    return {'title': title, 'url': 'https://www.rnz.co.nz/news/1', 'published': PUBLISHED,
            'source': 'Synthetic News', 'sourceId': 'synthetic', 'summary': summary}


def hits(keyword, *titles, **kw):
    rows = [story(t) for t in titles]
    return [r['title'] for r in cli.apply_search_filters(rows, keyword=keyword, **kw)]


class SearchMatcherTests(unittest.TestCase):
    def test_short_term_is_whole_word(self):
        titles = ('IOC confirms India, Qatar among 7 bidders', 'Luxon faces Hipkins in first debate',
                  'Campaigners rally against the bill', 'Government sets new AI rules',
                  'AI-driven tools reach classrooms', 'The A.I. boom', 'Ai Weiwei opens Auckland show',
                  "AI's energy bill", 'Firm hires (AI) lead')
        self.assertEqual(hits('AI', *titles), [
            'Government sets new AI rules', 'AI-driven tools reach classrooms', 'The A.I. boom',
            'Ai Weiwei opens Auckland show', "AI's energy bill", 'Firm hires (AI) lead'])
        self.assertEqual(hits('A.I.', *titles), hits('ai', *titles))

    def test_summary_is_searched_and_html_is_ignored(self):
        rows = [story('Budget day', '<p>Treasury flags <b>AI</b> savings.</p>'),
                story('Budget day two', '<a href="https://example.test/ai">link</a> no match')]
        self.assertEqual([r['title'] for r in cli.apply_search_filters(rows, keyword='ai')], ['Budget day'])

    def test_multi_word_phrase_default(self):
        titles = ('Housing market cools again', 'Market for housing stays flat', 'Housing-market slump deepens',
                  'Rehousing marketplace launches')
        self.assertEqual(hits('housing market', *titles), ['Housing market cools again', 'Housing-market slump deepens'])

    def test_contains_all_any_order_whole_words(self):
        titles = ('Housing market cools again', 'Market for housing stays flat', 'Rehousing marketplace launches',
                  'Housing stays flat')
        self.assertEqual(hits('housing market', *titles, contains_all=True),
                         ['Housing market cools again', 'Market for housing stays flat'])

    def test_exact_phrase(self):
        titles = ('Coalition talks resume', 'Coalitions form in Europe', 'The coalition: talks resume',
                  'Talks resume on coalition')
        self.assertEqual(hits('coalition talks', *titles, exact=True),
                         ['Coalition talks resume', 'The coalition: talks resume'])
        self.assertEqual(hits('coalition', *titles, exact=True),
                         ['Coalition talks resume', 'The coalition: talks resume', 'Talks resume on coalition'])

    def test_exclude_is_whole_word(self):
        titles = ('Sport funding cut', 'Transport plan released', 'Sports minister speaks', 'AI in sport')
        self.assertEqual(hits('plan', 'Transport plan released', exclude=['sport']), ['Transport plan released'])
        self.assertEqual(hits('ai', *titles, exclude=['sport']), [])
        self.assertEqual(hits('funding', *titles, exclude=['sport funding']), [])
        self.assertEqual(hits('minister', *titles, exclude=['sport']), ['Sports minister speaks'])
        self.assertEqual(hits('plan', *titles, exclude=['-', '']), ['Transport plan released'])

    def test_macrons_and_hyphens(self):
        titles = ('Māori wards vote passes', 'Maori health plan', 'Te Ao Māori news', 'Co-op dairy payout lifts',
                  'Co op shop opens', 'Coop chickens escape', 'Tamaki Makaurau', 'Tāmaki Makaurau traffic')
        self.assertEqual(hits('Māori', *titles), ['Māori wards vote passes', 'Maori health plan', 'Te Ao Māori news'])
        self.assertEqual(hits('maori', *titles), hits('Māori', *titles))
        self.assertEqual(hits('co-op', *titles), ['Co-op dairy payout lifts', 'Co op shop opens'])
        self.assertEqual(hits('Tāmaki', *titles, exact=True), ['Tamaki Makaurau', 'Tāmaki Makaurau traffic'])
        self.assertEqual(hits('ā', *titles), [])

    def test_unicode_words_and_case(self):
        self.assertEqual(hits('STRASSE', 'Die Straße ist zu', 'Strassen'), ['Die Straße ist zu'])
        self.assertEqual(hits('café', 'Cafe owners rally', 'Cafés close'), ['Cafe owners rally'])
        self.assertEqual(hits('2026', 'Election 2026 live', 'Ticket 20261'), ['Election 2026 live'])

    def test_entities_and_other_scripts(self):
        self.assertEqual(cli.word_tokens('a &lt; b and c &gt; d'), ['a', 'b', 'and', 'c', 'd'])
        self.assertEqual(cli.word_tokens('<p>Here&#8217;s AI</p>'), ['here', 's', 'ai'])
        self.assertEqual(hits('हिंदी', 'हिंदी समाचार', 'हदी'), ['हिंदी समाचार'])

    def test_empty_keyword_keeps_items(self):
        self.assertEqual(hits('!!!', 'Any story'), ['Any story'])

    def test_substring_restores_legacy_behaviour(self):
        titles = ('Campaigners rally against the bill', 'Government sets new AI rules', 'Sports minister speaks',
                  'IOC confirms India, Qatar among 7 bidders')
        self.assertEqual(hits('AI', *titles, substring=True), list(titles[:2]))
        self.assertEqual(hits('minister', *titles, substring=True, exclude=['sport']), [])
        self.assertEqual(hits('ai rules', *titles, substring=True, contains_all=True), ['Government sets new AI rules'])
        self.assertEqual(hits('AI', *titles, substring=True, exact=True), ['Government sets new AI rules'])

    @patch.object(cli, 'fetch_feeds')
    def test_json_match_mode(self, fetch):
        fetch.return_value = [{'feed': cli.FEED_BY_ID['rnz'], 'ok': True, 'error': None, 'durationMs': 1,
                               'items': [story('Rally against bid'), story('New AI rules')]}]
        for argv, mode, word, count in ((['search', 'AI'], 'phrase', True, 1),
                                        (['search', 'AI', '--substring'], 'substring', False, 2),
                                        (['search', 'AI', '--exact'], 'exact', True, 1),
                                        (['topic', 'AI', 'rules', '--contains-all', '--substring'], 'contains-all', False, 1)):
            out = io.StringIO()
            with self.subTest(argv=argv), contextlib.redirect_stdout(out):
                self.assertEqual(cli.main([*argv, '--json']), 0)
                data = json.loads(out.getvalue())
                self.assertEqual((data['matchMode'], data['wordMatch'], data['totalMatching']), (mode, word, count))

    def test_substring_and_exact_conflict(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as e:
            cli.cmd_search(argparse.Namespace(keyword_parts=['ai'], keyword=None, exact=True, substring=True,
                                              contains_all=False, since_hours=None, since_date=None))
        self.assertEqual(e.exception.code, 1)
        self.assertIn('--substring', err.getvalue())


if __name__ == '__main__':
    unittest.main()
