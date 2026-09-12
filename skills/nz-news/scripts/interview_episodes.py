"""Bounded podcast episode metadata discovery; no audio or transcript downloads."""
from __future__ import annotations

import datetime as dt
from email.utils import parsedate_to_datetime
import hashlib
from http.client import HTTPException
import json
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'lib'))
from result_contract import result_envelope

VERSION = 'interview-feed-v1'
AGENT = 'ChatGPT-User'
CAP = 524288
PROGRAMMES = {
    'mike-hosking': {
        'title': 'The Mike Hosking Breakfast',
        'url': 'https://www.omnycontent.com/d/playlist/7784f840-c291-422a-924b-ad9000bbad71/532a8e5c-814a-498d-97aa-aed8016bec7e/4bd02e97-4e52-4b53-95cc-aed8016bec95/podcast.rss',
        'discovery_url': 'https://omny.fm/shows/the-mike-hosking-breakfast/playlists/podcast',
    },
    'rnz-morning-report': {
        'title': 'Morning Report',
        'url': 'https://www.rnz.co.nz/podcasts/morningreport.rss',
        'discovery_url': 'https://www.rnz.co.nz/programmes/morningreport',
    },
}
HOSTS = {urllib.parse.urlsplit(p['url']).hostname for p in PROGRAMMES.values()}
PODCAST = '{https://podcastindex.org/namespace/1.0}'


class FeedFailure(Exception):
    def __init__(self, status, message, code):
        super().__init__(message)
        self.status, self.code = status, code


def stamp():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')


def public_url(url, outbound=False):
    try:
        p = urllib.parse.urlsplit(url)
        if (p.scheme != 'https' or not p.hostname or p.username or p.password or p.port not in (None, 443)
                or any(c.isspace() for c in url) or (outbound and p.hostname not in HOSTS)):
            raise ValueError
    except ValueError:
        raise ValueError('Expected an approved public HTTPS URL without credentials') from None
    return url


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class FeedClient:
    """Two wire requests maximum: robots policy, then a bounded RSS prefix."""
    def __init__(self):
        self.ledger = []
        self.stopped = False
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def request(self, url, robots=False):
        public_url(url, outbound=True)
        if self.stopped or len(self.ledger) >= 2:
            raise FeedFailure('blocked', 'Source circuit breaker is open', 4)
        receipt = {'url': url, 'retrieved_at': stamp(), 'status': 'unavailable', 'http_status': None}
        self.ledger.append(receipt)
        cap = 65536 if robots else CAP
        try:
            request = urllib.request.Request(url, headers={'User-Agent': AGENT + ' (TheColab public episode metadata)', 'Accept-Encoding': 'identity'})
            with self.opener.open(request, timeout=10) as response:
                receipt['http_status'] = response.status
                body = response.read(cap + 1)
                content_type = response.headers.get('Content-Type', '')
        except urllib.error.HTTPError as exc:
            receipt['http_status'] = exc.code
            exc.close()
            if robots and exc.code in {404, 410}:
                receipt['reason'] = 'robots_not_published'
                return b'', receipt, True
            self.stopped = True
            status = 'blocked' if exc.code in {401, 403, 429} else 'unavailable'
            receipt['status'] = status
            raise FeedFailure(status, 'Source access denied' if status == 'blocked' else 'Source HTTP error or redirect', 4 if status == 'blocked' else 5) from None
        except (OSError, urllib.error.URLError, HTTPException):
            self.stopped = True
            raise FeedFailure('unavailable', 'Source connection unavailable', 5) from None
        complete = len(body) <= cap
        # Hash only the prefix passed to the parser, not the sentinel byte.
        body = body[:cap]
        receipt.update(bytes=len(body), sha256=hashlib.sha256(body).hexdigest(), response_complete=complete)
        if receipt['http_status'] != 200 or (robots and not complete):
            self.stopped = True
            raise FeedFailure('unavailable', 'Expected a complete robots policy or HTTP 200 feed', 5)
        lower = body[:100000].lower()
        if any(marker in lower for marker in (b'<title>just a moment', b'<title>access denied', b'cf-chl-', b'incapsula incident id')):
            self.stopped = True
            receipt['status'] = 'blocked'
            raise FeedFailure('blocked', 'Source returned an access challenge', 4)
        if robots and ('html' in content_type.lower() or b'<html' in lower):
            self.stopped = True
            raise FeedFailure('unavailable', 'Robots policy returned HTML', 5)
        receipt['status'] = 'ok' if complete else 'partial'
        return body, receipt, complete

    def feed(self, url):
        body, receipt, _ = self.request(urllib.parse.urljoin(url, '/robots.txt'), robots=True)
        delay = 1
        if body:
            try:
                rules = body.decode('utf-8-sig')
            except UnicodeDecodeError:
                self.stopped = True
                raise FeedFailure('unavailable', 'Robots policy decoding failed', 5) from None
            parser = urllib.robotparser.RobotFileParser()
            parser.parse(rules.splitlines())
            if not parser.can_fetch(AGENT, url) or re.search(r'(?:ai-input|search)\s*=\s*no', rules, re.I):
                self.stopped = True
                receipt['decision'] = 'disallowed'
                raise FeedFailure('blocked', 'Robots or content signals disallow this discovery', 4)
            delay = max(delay, parser.crawl_delay(AGENT) or 0)
            rate = parser.request_rate(AGENT)
            if rate and rate.requests:
                delay = max(delay, rate.seconds / rate.requests)
            if delay > 10:
                self.stopped = True
                raise FeedFailure('blocked', 'Crawl delay exceeds bounded probe budget', 4)
            receipt['decision'] = 'allowed'
        time.sleep(delay)
        return self.request(url)


def bounded_limit(raw):
    import argparse
    try:
        value = int(raw)
        if not 1 <= value <= 100:
            raise ValueError
        return value
    except ValueError:
        raise argparse.ArgumentTypeError('Expected an integer from 1 to 100') from None


def parse_feed(body, programme, receipt, complete, as_of):
    """Only completed RSS items count; a capped tail is intentionally unparsed."""
    if b'<!DOCTYPE' in body.upper() or b'<!ENTITY' in body.upper():
        raise FeedFailure('schema_error', 'DTD/entity declarations are unsupported', 6)
    parser = ET.XMLPullParser(events=('start', 'end'))
    try:
        parser.feed(body)
        events = list(parser.read_events())
        if complete:
            parser.close()
    except ET.ParseError:
        raise FeedFailure('schema_error', 'Malformed RSS source', 6) from None
    roots = [element for event, element in events if event == 'start']
    if not roots or roots[0].tag != 'rss':
        raise FeedFailure('schema_error', 'Expected RSS 2.0 source', 6)
    channel = next((element for event, element in events if event == 'start' and element.tag == 'channel'), None)
    if channel is None or channel.findtext('title', '').strip() != programme['title']:
        raise FeedFailure('schema_error', 'Unexpected programme title in feed', 6)
    items = [element for event, element in events if event == 'end' and element.tag == 'item']
    if not items and not complete:
        raise FeedFailure('unavailable', 'Feed prefix contains no complete episodes', 5)
    cutoff = as_of - dt.timedelta(days=90)
    rows, dates, seen = [], [], set()
    counts = {'undated': 0, 'outside_window': 0, 'not_interview_candidate': 0, 'duplicates': 0}
    for ordinal, item in enumerate(items, 1):
        title, url = item.findtext('title', '').strip(), item.findtext('link', '').strip()
        guid, raw_date = item.findtext('guid', '').strip(), item.findtext('pubDate', '').strip()
        if not title or not url or not guid:
            raise FeedFailure('schema_error', 'Episode is missing title, link or GUID', 6)
        try:
            public_url(url)
        except ValueError:
            raise FeedFailure('schema_error', 'Episode contains an unsafe source URL', 6) from None
        try:
            published = parsedate_to_datetime(raw_date)
            if published.tzinfo is None:
                raise ValueError
            published = published.astimezone(dt.timezone.utc)
        except (TypeError, ValueError, OverflowError):
            counts['undated'] += 1
            continue
        dates.append(published)
        if not cutoff <= published <= as_of:
            counts['outside_window'] += 1
            continue
        if guid in seen:
            counts['duplicates'] += 1
            continue
        seen.add(guid)
        # A candidate, not verified identity or proof of an utterance. No role inference.
        prefix, separator, detail = title.partition(':')
        name_words = prefix.split()
        name_like = 2 <= len(name_words) <= 5 and all(word[0].isupper() for word in name_words)
        if not separator or not name_like or ' on ' not in (' ' + detail.lower() + ' ') or prefix in {'Full Show Podcast', 'Politics Friday', 'Commentary Box', 'Sportstalk', 'The Panel'}:
            counts['not_interview_candidate'] += 1
            continue
        transcript_links = []
        for transcript in item.findall(PODCAST + 'transcript'):
            target = transcript.get('url', '')
            try:
                public_url(target)
            except ValueError:
                continue
            transcript_links.append({'url': target, 'type': transcript.get('type'), 'language': transcript.get('language')})
        rows.append({'title': title, 'source_url': url, 'programme': programme['title'],
                     'speaker': prefix, 'speaker_basis': 'publisher_title_prefix_unverified',
                     'interview_status': 'title_pattern_candidate',
                     'publication_date': published.isoformat().replace('+00:00', 'Z'), 'broadcast_date': None,
                     'transcript_availability': 'advertised' if transcript_links else 'unknown',
                     'transcript_links': transcript_links,
                     'provenance': {'source_url': programme['url'], 'discovery_url': programme['discovery_url'],
                                    'retrieved_at': receipt['retrieved_at'], 'response_sha256': receipt['sha256'],
                                    'hash_scope': 'full_feed' if complete else 'bounded_feed_prefix',
                                    'bytes_hashed': len(body), 'parser_version': VERSION,
                                    'item_ordinal': ordinal, 'guid': guid,
                                    'title_field': 'rss/channel/item/title', 'speaker_title_start': 0,
                                    'speaker_title_end': len(prefix), 'date_field': 'rss/channel/item/pubDate',
                                    'publication_date_raw': raw_date,
                                    'transcript_field': 'rss/channel/item/podcast:transcript/@url'}})
    rows.sort(key=lambda row: row['publication_date'], reverse=True)
    coverage = {'feed_complete': complete, 'items_scanned': len(items), 'byte_cap': CAP,
                'oldest_scanned_date': min(dates).isoformat() if dates else None,
                'newest_scanned_date': max(dates).isoformat() if dates else None,
                'window_complete': False, 'excluded': counts}
    return rows, coverage


def add_parser(subparsers):
    parser = subparsers.add_parser('interviews', help='Discover last90days interview candidates from one public programme feed')
    parser.add_argument('--programme', choices=sorted(PROGRAMMES), required=True)
    parser.add_argument('--contains', default='', help='Case-insensitive title filter; does not search transcript text')
    parser.add_argument('--limit', type=bounded_limit, default=10)
    parser.add_argument('--json', action='store_true')
    parser.set_defaults(func=command)


def command(args):
    programme = PROGRAMMES[args.programme]
    as_of = dt.datetime.now(dt.timezone.utc)
    query = {'command': 'interviews', 'programme': args.programme, 'contains': args.contains, 'limit': args.limit,
             'window': 'last90days', 'as_of': as_of.isoformat(), 'since': (as_of-dt.timedelta(days=90)).isoformat()}
    client = FeedClient()
    warnings = ['Only title-pattern interview candidates in the scanned feed prefix; no complete 90-day coverage claim.',
                'Speaker is an unverified publisher title prefix; broadcast date is unknown. Transcript links are advertised, never fetched.']
    code = 0
    try:
        body, receipt, complete = client.feed(programme['url'])
        rows, coverage = parse_feed(body, programme, receipt, complete, as_of)
        matches = [row for row in rows if args.contains.casefold() in row['title'].casefold()]
        payload = result_envelope(ok=True, source_name=programme['title'], source_url=programme['url'], query=query,
                                  data=matches[:args.limit], warnings=warnings, retrieved_at=receipt['retrieved_at'])
        payload.update(status='ok' if matches else 'empty', coverage=coverage, total_matching=len(matches),
                       truncated=len(matches) > args.limit)
    except FeedFailure as exc:
        code = exc.code
        payload = result_envelope(ok=False, source_name=programme['title'], source_url=programme['url'], query=query,
                                  data=[], warnings=warnings, blocked=code == 4, error={'type': exc.status, 'message': str(exc)})
        payload['status'] = exc.status
    payload['source_ledger'] = client.ledger
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"{programme['title']}: {payload['status']} (last90days, scanned prefix only)")
        for row in payload['data']:
            print(f"{row['publication_date']} | {row['title']}\n  {row['source_url']}")
        if not payload['ok']:
            print(payload['error']['message'], file=sys.stderr)
        for warning in warnings:
            print(f'Note: {warning}')
    return code
