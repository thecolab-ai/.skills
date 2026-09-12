#!/usr/bin/env python3
"""Deterministic interview candidate discovery and bounded transport tests."""
import argparse
import contextlib
import datetime as dt
import hashlib
from http.client import IncompleteRead
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch
import urllib.error

from interview_episodes import CAP, FeedClient, FeedFailure, PROGRAMMES, bounded_limit, command, parse_feed

FIXTURE = Path(__file__).resolve().parents[1] / 'tests/fixtures/interviews.rss'
AS_OF = dt.datetime(2026, 9, 12, tzinfo=dt.timezone.utc)
PROGRAMME = PROGRAMMES['mike-hosking']


def receipt(body):
    return {'retrieved_at': AS_OF.isoformat(), 'sha256': hashlib.sha256(body).hexdigest()}


def response(body, content_type='application/rss+xml', status=200):
    r = Mock(status=status, headers={'Content-Type': content_type})
    r.read.return_value = body
    r.__enter__ = Mock(return_value=r)
    r.__exit__ = Mock(return_value=False)
    return r


class InterviewTests(unittest.TestCase):
    def parse(self, body=None, complete=True):
        body = FIXTURE.read_bytes() if body is None else body
        return parse_feed(body, PROGRAMME, receipt(body), complete, AS_OF)

    def test_window_provenance_and_rights(self):
        rows, coverage = self.parse()
        self.assertEqual(len(rows), 2)
        first = rows[0]
        self.assertEqual(first['speaker'], 'Example Speaker')
        self.assertEqual(first['speaker_basis'], 'publisher_title_prefix_unverified')
        self.assertEqual(first['publication_date'], '2026-09-10T22:00:00Z')
        self.assertIsNone(first['broadcast_date'])
        self.assertEqual(first['transcript_availability'], 'advertised')
        self.assertEqual(rows[1]['transcript_availability'], 'unknown')
        self.assertNotIn('description', json.dumps(rows))
        self.assertEqual(first['provenance']['guid'], 'synthetic-1')
        self.assertEqual(first['provenance']['hash_scope'], 'full_feed')
        self.assertEqual(coverage['excluded'], {'undated':1, 'outside_window':2, 'not_interview_candidate':1, 'duplicates':1})
        self.assertFalse(coverage['window_complete'])

    def test_prefix_only_complete_items(self):
        body = FIXTURE.read_bytes()
        prefix = body[:body.index(b'</item>')+7] + b'<item><title>part'
        rows, coverage = self.parse(prefix, complete=False)
        self.assertEqual(len(rows), 1)
        self.assertFalse(coverage['feed_complete'])
        self.assertEqual(coverage['items_scanned'], 1)
        self.assertEqual(rows[0]['provenance']['hash_scope'], 'bounded_feed_prefix')
        with self.assertRaises(FeedFailure):
            self.parse(prefix, complete=True)

    def test_empty_valid_feed(self):
        rows, coverage = self.parse(b'<rss><channel><title>The Mike Hosking Breakfast</title></channel></rss>')
        self.assertEqual(rows, [])
        self.assertEqual(coverage['items_scanned'], 0)

    def test_schema_failures(self):
        for body in (b'<html>Denied</html>', b'<rss><channel><title>Different programme</title></channel></rss>', b'<rss><unmatched></rss>', b'<!DOCTYPE rss><rss/>'):
            with self.subTest(body=body), self.assertRaises(FeedFailure) as e:
                self.parse(body)
            self.assertEqual(e.exception.code, 6)

    def test_missing_required_episode_and_bad_url(self):
        body = FIXTURE.read_bytes()
        for modified in (body.replace(b'<guid>synthetic-1</guid>', b''), body.replace(b'https://omny.fm/shows/example/one', b'javascript:alert(1)')):
            with self.assertRaises(FeedFailure) as e:
                self.parse(modified)
            self.assertEqual(e.exception.code, 6)

    def test_date_timezone_missing_is_excluded(self):
        body = FIXTURE.read_bytes().replace(b'Fri, 11 Sep 2026 10:00:00 +1200', b'Fri, 11 Sep 2026 10:00:00')
        rows, coverage = self.parse(body)
        self.assertEqual(len(rows), 1)
        self.assertEqual(coverage['excluded']['undated'], 3)

    def test_invalid_transcript_not_claimed_available(self):
        body = FIXTURE.read_bytes().replace(b'https://www.omnycontent.com/example/transcript.vtt', b'javascript:bad')
        rows, _ = self.parse(body)
        self.assertEqual(rows[0]['transcript_availability'], 'unknown')
        self.assertEqual(rows[0]['transcript_links'], [])

    def test_numeric_boundaries(self):
        for raw in ('0', '-1', '101', 'nan', 'inf', '9'*5000):
            with self.subTest(size=len(raw)), self.assertRaises(argparse.ArgumentTypeError):
                bounded_limit(raw)
        self.assertEqual(bounded_limit('100'), 100)

    def test_unsafe_url_before_request(self):
        c = FeedClient()
        c.opener = Mock()
        for url in ('https://' + '.'.join(['bad', 'invalid']), PROGRAMME['url'].replace('https:', 'http:'), PROGRAMME['url'].replace('www.', 'user:pass@www.')):
            with self.assertRaises(ValueError):
                c.request(url)
        c.opener.open.assert_not_called()

    @patch('interview_episodes.time.sleep')
    def test_robot_block_no_feed_request(self, sleep):
        c = FeedClient()
        c.opener.open = Mock(return_value=response(b'User-agent: ChatGPT-User\nDisallow: /\n\nUser-agent: *\nAllow: /', 'text/plain'))
        with self.assertRaises(FeedFailure) as e:
            c.feed(PROGRAMME['url'])
        self.assertEqual(e.exception.code, 4)
        self.assertEqual(c.opener.open.call_count, 1)
        self.assertEqual(c.ledger[0]['decision'], 'disallowed')
        sleep.assert_not_called()

    @patch('interview_episodes.time.sleep')
    def test_prefix_hash_and_budget(self, sleep):
        c = FeedClient()
        c.opener.open = Mock(side_effect=[response(b'User-agent: *\nAllow: /\nCrawl-delay: 2', 'text/plain'), response(b'a'*(CAP+1))])
        body, rec, complete = c.feed(PROGRAMME['url'])
        self.assertEqual(len(body), CAP)
        self.assertFalse(complete)
        self.assertEqual(rec['status'], 'partial')
        self.assertEqual(rec['sha256'], hashlib.sha256(body).hexdigest())
        sleep.assert_called_once_with(2)
        with self.assertRaises(FeedFailure):
            c.request(PROGRAMME['url'])
        self.assertEqual(c.opener.open.call_count, 2)

    def test_errors_stop_and_sanitise(self):
        for error, code in ((IncompleteRead(b'x',10),5), (OSError('private connection detail'),5), (urllib.error.HTTPError(PROGRAMME['url'],403,'private',{},io.BytesIO()),4)):
            c = FeedClient()
            c.opener.open = Mock(side_effect=error)
            with self.assertRaises(FeedFailure) as e:
                c.request(PROGRAMME['url'])
            self.assertEqual(e.exception.code, code)
            self.assertNotIn('private', str(e.exception))
            self.assertTrue(c.stopped)

    @patch('interview_episodes.FeedClient')
    def test_cli_error_json_and_exit(self, client):
        client.return_value.feed.side_effect = FeedFailure('blocked', 'Robots refused', 4)
        client.return_value.ledger = [{'status':'ok','decision':'disallowed'}]
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = command(argparse.Namespace(programme='mike-hosking', contains='', limit=2, json=True))
        data = json.loads(out.getvalue())
        self.assertEqual(code, 4)
        self.assertTrue(data['blocked'])
        self.assertFalse(data['ok'])
        self.assertEqual(data['query']['window'], 'last90days')

    def test_cli_invalid_input_json_flag(self):
        run = subprocess.run([sys.executable, str(Path(__file__).with_name('cli.py')), 'interviews', '--programme', 'mike-hosking', '--limit', '0', '--json'], capture_output=True, timeout=10)
        self.assertEqual(run.returncode, 2)
        self.assertNotIn(b'Traceback', run.stderr)


if __name__ == '__main__':
    unittest.main()
