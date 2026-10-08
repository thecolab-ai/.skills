#!/usr/bin/env python3
"""Bounded, keyless Port of Auckland and Tauranga freight snapshots."""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
import re
import sys
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'lib'))
import nzfetch  # noqa: E402
from provenance import error_envelope, provenance, result_envelope  # noqa: E402

NZ = ZoneInfo('Pacific/Auckland')
CACHE_DIR = Path(__file__).resolve().parents[1] / '.cache'
REGISTRY = Path(__file__).resolve().parents[1] / 'references' / 'sources.json'
ALLOWED_HOSTS = {'poal.co.nz', 'www.poal.co.nz', 'www.port-tauranga.co.nz'}
USER_AGENT = 'TheColab-port-of-auckland/1.0'
FEEDS = {
    ('auckland', 'arrivals'): ('https://poal.co.nz/operations/schedules/arrivals/download', 'Port of Auckland Ltd'),
    ('auckland', 'truck-turns'): ('https://www.poal.co.nz/customer-centre/truck-turn-times', 'Port of Auckland Ltd'),
    ('tauranga', 'arrivals'): ('https://www.port-tauranga.co.nz/operations/shipping-schedules/', 'Port of Tauranga Limited'),
    ('tauranga', 'truck-turns'): ('https://www.port-tauranga.co.nz/truck-turn-time/', 'Port of Tauranga Limited'),
}
CSV_FIELDS = ['Vessel', 'Agent', 'Wharf', 'Vessel Ref', "Lloyd's No", 'Voyage In', 'Voyage Out',
              'Receivals start', 'Receivals stop', 'Arrival', 'Departs', 'Previous Port', 'Next Port']
TAURANGA_FIELDS = ['Vessel Name', 'IMO', 'Arrives', 'Departs', 'Berth', 'Agent', 'Cargo', 'Last Port', 'Next Port']


class SkillError(Exception):
    def __init__(self, message, code=6, retry_after=None):
        super().__init__(message)
        self.code, self.retry_after = code, retry_after


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise SkillError(message, 2)


def local_time(raw, fmt):
    try:
        precision = 'seconds' if '%S' in fmt else 'minutes'
        return datetime.strptime(raw, fmt).replace(tzinfo=NZ).isoformat(timespec=precision)
    except ValueError as exc:
        raise SkillError(f'Source schema error: unrecognised date {raw!r}') from exc


def parse_arrivals(text):
    reader = csv.DictReader(io.StringIO(text.lstrip('\ufeff')))
    if reader.fieldnames != CSV_FIELDS:
        raise SkillError('Source schema error: expected the 13-column Auckland arrivals CSV')
    records = []
    for row in reader:
        if None in row or any(value is None for value in row.values()) or not row['Vessel'].strip():
            raise SkillError('Source schema error: malformed Auckland vessel row')
        records.append({
            'vessel': row['Vessel'], 'agent': row['Agent'], 'wharf': row['Wharf'],
            'vessel_ref': row['Vessel Ref'], 'imo': row["Lloyd's No"],
            'voyage_in': row['Voyage In'], 'voyage_out': row['Voyage Out'],
            'receivals_start': row['Receivals start'], 'receivals_stop': row['Receivals stop'],
            'arrival': local_time(row['Arrival'], '%d %b %Y %H:%M') if row['Arrival'] else None,
            'departs': local_time(row['Departs'], '%d %b %Y %H:%M') if row['Departs'] else None,
            'previous_port': row['Previous Port'], 'next_port': row['Next Port'],
            'port': 'auckland', 'status': 'expected',
        })
    return records, None


class Page(HTMLParser):
    """Extract only published headings, relevant div text and shipping tables."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.fields = []
        self.headings = []
        self.tables = {}
        self.table = None
        self.cell = None
        self.row = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ('div', 'h3'):
            self.stack.append([tag, attrs.get('class', ''), []])
        if tag == 'table':
            self.table = attrs.get('id')
            self.tables[self.table] = []
        if self.table and tag == 'tr':
            self.row = []
        if self.table and tag in ('td', 'th'):
            self.cell = []

    def handle_data(self, text):
        for item in self.stack:
            item[2].append(text)
        if self.cell is not None:
            self.cell.append(text)

    def handle_endtag(self, tag):
        if tag in ('div', 'h3') and self.stack and self.stack[-1][0] == tag:
            _, classes, parts = self.stack.pop()
            text = ' '.join(''.join(parts).split())
            if tag == 'h3':
                self.headings.append(text)
            if classes.startswith('truck-turnaround--'):
                self.fields.append((classes, text))
        if self.table and tag in ('td', 'th') and self.cell is not None:
            self.row.append(' '.join(''.join(self.cell).split()))
            self.cell = None
        if self.table and tag == 'tr':
            self.tables[self.table].append(self.row)
        if tag == 'table':
            self.table = None


def parse_trucks(text):
    page = Page(); page.feed(text)
    records = []
    requested = None
    for classes, value in page.fields:
        if classes == 'truck-turnaround--request-time':
            requested = local_time(value, '%d/%m/%Y %H:%M:%S')
        elif classes == 'truck-turnaround--item--detail':
            match = re.fullmatch(r'At (\d{2}:\d{2}) Truck Turnaround for (.+) for the last (\d+) min is (\d+) min (\d+) sec', value)
            if not match or not requested:
                raise SkillError('Source schema error: unrecognised Auckland truck turnaround block')
            clock, location, window, minutes, seconds = match.groups()
            if int(seconds) >= 60 or int(window) <= 0:
                raise SkillError('Source schema error: invalid turnaround duration')
            request_dt = datetime.fromisoformat(requested)
            hour, minute = map(int, clock.split(':'))
            if hour > 23 or minute > 59:
                raise SkillError('Source schema error: invalid observation time')
            observed = request_dt.replace(hour=hour, minute=minute, second=0)
            if observed > request_dt:
                observed -= timedelta(days=1)
            records.append({'port': 'auckland', 'metric': 'truck_turnaround', 'location': location,
                            'turn_seconds': int(minutes)*60+int(seconds), 'window_minutes': int(window),
                            'observed_at': observed.isoformat(timespec='minutes'), 'request_time': requested,
                            'latest_data': observed.isoformat(timespec='minutes')})
    if not records:
        raise SkillError('Source schema error: no Auckland turnaround blocks found')
    return records, max(r['latest_data'] for r in records)


def parse_tauranga_arrivals(text):
    page = Page(); page.feed(text)
    table = page.tables.get('pot-data-table-2')
    if not table or table[0] != TAURANGA_FIELDS:
        raise SkillError('Source schema error: Tauranga Expected Arrivals table missing or changed')
    heading = next((h for h in page.headings if h.startswith('Expected Arrivals (')), '')
    match = re.search(r'\(([^)]+)\)', heading)
    if not match:
        raise SkillError('Source schema error: Tauranga schedule timestamp missing')
    latest = local_time(match[1], '%A %d %B %Y %H:%M')
    records = []
    for values in table[1:]:
        if len(values) == 1 and re.search(r'no (?:vessels|records|data)', values[0], re.I):
            continue
        if len(values) != len(TAURANGA_FIELDS) or not values[0]:
            raise SkillError('Source schema error: malformed Tauranga vessel row')
        row = dict(zip(TAURANGA_FIELDS, values))
        records.append({'vessel': row['Vessel Name'], 'imo': row['IMO'], 'wharf': row['Berth'],
                        'agent': row['Agent'], 'cargo': row['Cargo'], 'previous_port': row['Last Port'],
                        'next_port': row['Next Port'], 'port': 'tauranga', 'status': 'expected',
                        'arrival': local_time(row['Arrives'], '%d/%m/%Y %H:%M') if row['Arrives'] else None,
                        'departs': local_time(row['Departs'], '%d/%m/%Y %H:%M') if row['Departs'] else None})
    return records, latest


def parse_tauranga_queue(text):
    page = Page(); page.feed(text)
    heading = next((h for h in page.headings if h.startswith('Truck Turn Data - Last ')), '')
    match = re.fullmatch(r'Truck Turn Data - Last (\d+) Minutes \(([^)]+)\)', heading)
    queue = re.search(r'Current road queue is:\s*(\d+) trucks', text)
    if not match or not queue:
        raise SkillError('Source schema error: Tauranga queue count or timestamp missing')
    latest = local_time(match[2], '%A %d %B %Y %H:%M')
    return [{'port': 'tauranga', 'metric': 'road_queue', 'queue_trucks': int(queue[1]),
             'window_minutes': int(match[1]), 'observed_at': latest,
             'caveat': 'Page exposes a queue count, not a numeric truck turn time series.'}], latest


PARSERS = {('auckland', 'arrivals'): parse_arrivals, ('auckland', 'truck-turns'): parse_trucks,
           ('tauranga', 'arrivals'): parse_tauranga_arrivals, ('tauranga', 'truck-turns'): parse_tauranga_queue}


def fetch_text(url, *, allow_missing=False):
    try:
        return nzfetch.fetch_text(url, timeout=10, max_bytes=4_000_000, allowed_hosts=ALLOWED_HOSTS,
                                  headers={'User-Agent': USER_AGENT}, browser_headers=False)
    except nzfetch.RateLimited as exc:
        raise SkillError('network error: source rate-limited', 4, exc.retry_after) from exc
    except nzfetch.Blocked as exc:
        raise SkillError('network error: public source blocked access', 4) from exc
    except nzfetch.FetchError as exc:
        if allow_missing and isinstance(exc.__cause__, HTTPError) and exc.__cause__.code == 404:
            return ''  # A missing robots.txt imposes no restrictions.
        raise SkillError('network error: public source unavailable', 5) from exc


def read_cache(path, max_age):
    if max_age == 0:
        return None
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
        meta = payload['meta']
        retrieved = datetime.fromisoformat(meta['retrieved_at'].replace('Z', '+00:00'))
        age = (datetime.now(timezone.utc) - retrieved).total_seconds()
        if (isinstance(meta, dict) and 0 <= age <= max_age and isinstance(payload['results'], list)
                and meta.get('source_url') and meta.get('publisher')):
            return payload
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def write_cache(path, payload):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Each writer has a separate temporary file; replacement is atomic.
        temporary = path.with_suffix(f'.{os.getpid()}.tmp')
        temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
        temporary.replace(path)
    except OSError:
        pass  # A read still works when the cache directory is read-only.


def check_robots(url):
    origin = urlsplit(url)
    robots_url = f'{origin.scheme}://{origin.netloc}/robots.txt'
    path = CACHE_DIR / (origin.netloc + '-robots.json')
    cached = read_cache(path, 86400)
    if (cached and cached['meta']['source_url'] == robots_url
            and len(cached['results']) == 1 and isinstance(cached['results'][0], str)):
        text = cached['results'][0]
    else:
        text = fetch_text(robots_url, allow_missing=True)
        if '<html' in text.lower():
            raise SkillError('network error: robots.txt returned HTML; access policy could not be checked', 5)
        write_cache(path, result_envelope([text], provenance(robots_url, origin.netloc)))
    robots = RobotFileParser(); robots.parse(text.splitlines())
    if not robots.can_fetch(USER_AGENT, url):
        raise SkillError('Public source robots.txt disallows this path', 4)


def load_feed(port, command, max_age):
    url, publisher = FEEDS[port, command]
    path = CACHE_DIR / f'{port}-{command}.json'
    cached = read_cache(path, max_age)
    if cached and cached['meta']['source_url'] == url and cached['meta']['publisher'] == publisher:
        return cached
    try:
        check_robots(url)
        text = fetch_text(url)
        retrieved = provenance(url, publisher)['retrieved_at']
        records, latest = PARSERS[port, command](text)
    except SkillError as exc:
        exc.source_url, exc.publisher = url, publisher
        raise
    payload = result_envelope(records, provenance(url, publisher, retrieved_at=retrieved, latest_data=latest))
    write_cache(path, payload)
    return payload


def date_arg(value):
    try:
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
            raise ValueError
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError('Use a valid date in YYYY-MM-DD format') from exc


def max_age_arg(value):
    try:
        age = int(value)
        if not 0 <= age <= 3600:
            raise ValueError
        return age
    except ValueError as exc:
        raise argparse.ArgumentTypeError('--max-age must be an integer from 0 to 3600 seconds') from exc


def filter_records(records, args, field):
    result = []
    for record in records:
        if getattr(args, 'vessel', None) and args.vessel.casefold() not in record['vessel'].casefold():
            continue
        if args.start or args.end:
            if not record.get(field):
                continue
            try:
                day = datetime.fromisoformat(record[field]).astimezone(NZ).date()
            except ValueError as exc:
                raise SkillError(f'Cache schema error: unrecognised {field} date {record[field]!r}') from exc
            if (args.start and day < args.start) or (args.end and day > args.end):
                continue
        result.append(record)
    return result


def build_parser():
    parser = Parser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True, parser_class=Parser)
    for command in ('sources', 'arrivals', 'truck-turns', 'summary'):
        p = sub.add_parser(command)
        p.add_argument('--json', action='store_true', help='emit the provenance/results envelope')
        if command != 'sources':
            p.add_argument('--port', choices=('auckland', 'tauranga'), default='auckland')
            p.add_argument('--max-age', type=max_age_arg, default=300, help='maximum cache age in seconds (0 refreshes; default 300; maximum 3600)')
        if command in ('arrivals', 'truck-turns'):
            p.add_argument('--from', dest='start', type=date_arg, help='inclusive NZ calendar date YYYY-MM-DD')
            p.add_argument('--to', dest='end', type=date_arg, help='inclusive NZ calendar date YYYY-MM-DD')
        if command == 'arrivals':
            p.add_argument('--vessel', help='case-insensitive vessel name substring')
    return parser


def execute(args):
    if getattr(args, 'start', None) and getattr(args, 'end', None) and args.start > args.end:
        raise SkillError('--from must be on or before --to', 2)
    if args.command == 'sources':
        records = json.loads(REGISTRY.read_text(encoding='utf-8'))
        for record in records:
            record.update(provenance(record['source_url'], record['publisher']))
        return result_envelope(records, provenance(FEEDS['auckland', 'arrivals'][0], 'Port of Auckland Ltd'))
    if args.command in ('arrivals', 'truck-turns'):
        payload = load_feed(args.port, args.command, args.max_age)
        field = 'arrival' if args.command == 'arrivals' else 'observed_at'
        return result_envelope(filter_records(payload['results'], args, field), payload['meta'])
    arrivals = load_feed(args.port, 'arrivals', args.max_age)
    trucks = load_feed(args.port, 'truck-turns', args.max_age)
    counts = Counter(r['arrival'][:10] for r in arrivals['results'] if r.get('arrival'))
    vessel_count = len({r['vessel'] for r in arrivals['results']})
    return result_envelope([
        {'kind': 'expected_arrivals', 'port': args.port, 'vessel_calls': len(arrivals['results']),
         'distinct_vessels': vessel_count, 'calls_by_nz_date': dict(sorted(counts.items())),
         'caveat': 'Vessel calls are schedule entries, including berth shifts; they do not measure truck demand.',
         **arrivals['meta']},
        {'kind': 'truck_snapshot', 'port': args.port, 'observations': trucks['results'], **trucks['meta']},
    ], arrivals['meta'])


def print_record(record):
    if 'fetch_command' in record:
        command = record['fetch_command'] or 'discovery link only'
        print(f"{record['id']} {record['name']} ({command})\n  {record['source_url']}")
    elif 'vessel' in record:
        print(f"{record['vessel']}: arrives {record['arrival'] or 'unknown'}; wharf {record['wharf']}; departs {record['departs'] or 'unknown'}")
    elif record.get('metric') == 'truck_turnaround':
        minutes, seconds = divmod(record['turn_seconds'], 60)
        print(f"{record['location']}: {minutes} min {seconds} sec for the last {record['window_minutes']} min; observed {record['observed_at']}")
    elif record.get('metric') == 'road_queue':
        print(f"Tauranga road queue: {record['queue_trucks']} trucks; observed {record['observed_at']}")
    elif record.get('kind') == 'expected_arrivals':
        print(f"{record['port'].title()}: {record['vessel_calls']} expected vessel calls, {record['distinct_vessels']} distinct vessel names")
    elif record.get('kind') == 'truck_snapshot':
        for observation in record['observations']:
            print_record(observation)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    args = None
    try:
        args = build_parser().parse_args(argv)
        payload = execute(args)
    except SkillError as exc:
        port = getattr(args, 'port', 'auckland')
        command = getattr(args, 'command', 'arrivals')
        url, publisher = FEEDS.get((port, command), FEEDS[port, 'arrivals'])
        url = getattr(exc, 'source_url', url)
        publisher = getattr(exc, 'publisher', publisher)
        if '--json' in argv:
            print(json.dumps(error_envelope(exc.code, str(exc), provenance(url, publisher), retry_after=exc.retry_after)))
        else:
            print(f'port-of-auckland: {exc}', file=sys.stderr)
        return exc.code
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False))
    else:
        print(f"{len(payload['results'])} result(s); retrieved {payload['meta']['retrieved_at']}")
        for record in payload['results']:
            print_record(record)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
