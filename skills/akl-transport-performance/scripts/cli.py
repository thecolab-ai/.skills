#!/usr/bin/env python3
"""Keyless AT patronage/performance downloads and Metlink daily bus measures."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from zipfile import BadZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'lib'))
import nzfetch  # noqa: E402
from provenance import add_spatial_arguments, error_envelope, geojson_envelope, provenance, result_envelope  # noqa: E402
from transport import download_links, parse_inventory, parse_metlink, parse_patronage, parse_punctuality  # noqa: E402

AT_PAGE = 'https://at.govt.nz/about-us/reports-publications/at-metro-patronage-report/'
METLINK_PAGE = 'https://www.metlink.org.nz/about-us/performance-of-our-network'
CITY_URL = 'https://at.govt.nz/umbraco/surface/parkingavailabilitysurface/ParkingAvailabilityResult?carparkIds=civic%2C+victoria+st&categories=short-term'
ROBOTS_URL = 'https://at.govt.nz/robots.txt'
INVENTORY_URL = 'https://services2.arcgis.com/JkPEgZJGxhSjYOo0/arcgis/rest/services/ParkingService/FeatureServer/1/query?where=1%3D1&outFields=*&returnGeometry=true&outSR=4326&f=json'
HOSTS = {'at.govt.nz', 'www.metlink.org.nz', 'services2.arcgis.com'}
AT_TERMS = 'AT website copyright terms (personal, non-commercial download; attributed, accurate reproduction)'
PUBLISHERS = {'at': 'Auckland Transport', 'metlink': 'Greater Wellington Regional Council / Metlink'}
CACHE = Path(__file__).resolve().parents[1] / '.cache'


class InputError(ValueError):
    """Invalid command arguments."""


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise InputError(message)


class AccessRestricted(Exception):
    pass


def get_bytes(url, max_age=86400):
    """Bounded local cache, no stale fallback; original retrieval timestamps retained."""
    path = CACHE / (hashlib.sha256(url.encode()).hexdigest() + '.json')
    now = datetime.now(timezone.utc)
    if max_age:
        try:
            cached = json.loads(path.read_text())
            stamp = datetime.fromisoformat(cached['retrieved_at'].replace('Z', '+00:00'))
            if cached['source_url'] == url and 0 <= (now - stamp).total_seconds() <= max_age:
                return base64.b64decode(cached['body'], validate=True), cached['retrieved_at']
        except (OSError, ValueError, KeyError, TypeError):
            pass
    body, _, _ = nzfetch.fetch_bytes(url, timeout=10, allowed_hosts=HOSTS, expect_json=False)
    stamp = datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')
    if max_age:
        CACHE.mkdir(exist_ok=True)
        with NamedTemporaryFile(mode='w', dir=CACHE, suffix='.part', delete=False) as handle:
            temporary = Path(handle.name)
            json.dump({'source_url': url, 'retrieved_at': stamp,
                       'body': base64.b64encode(body).decode('ascii')}, handle)
        temporary.replace(path)
        for old in sorted(CACHE.glob('*.json'), key=lambda f: f.stat().st_mtime, reverse=True)[16:]:
            old.unlink()
    return body, stamp


def meta_for(url, owner='at', stamp=None, latest=None):
    return provenance(url, PUBLISHERS[owner], retrieved_at=stamp, latest_data=latest,
                      licence=AT_TERMS if owner == 'at' and url.startswith('https://at.govt.nz/') else None)


def bounds(value, end=False):
    if not value:
        return None
    try:
        if len(value) == 7:
            first = date.fromisoformat(value + '-01')
            if end:
                return date(first.year + (first.month == 12), first.month % 12 + 1, 1) - timedelta(days=1)
            return first
        if len(value) != 10:
            raise ValueError()
        return date.fromisoformat(value)
    except ValueError as exc:
        raise InputError('dates must be YYYY-MM or YYYY-MM-DD') from exc


def matches(record, route):
    return route is None or record.get('route', '').casefold() == route.casefold()


def in_bounds(record, start, end):
    value = record['period']
    low = bounds(value)
    high = bounds(value, True)
    return (start is None or high >= start) and (end is None or low <= end)


def load_download(kind, max_age, archive=False):
    page = METLINK_PAGE if kind == 'metlink' else AT_PAGE
    html, _ = get_bytes(page, max_age)
    links = download_links(html.decode('utf-8'), page, kind)
    # Pages publish newest first. Historical AT files are available only when requested.
    if kind == 'metlink' or not archive:
        links = links[:1]
    elif kind == 'daily':
        # One hidden legacy partial-year link duplicates the full 2024/25 report.
        links = [u for u in links if 'to-20-july-2025' not in u][:4]
    else:
        links = links[:4]
    for url in links:
        body, stamp = get_bytes(url, max_age)
        yield body, meta_for(url, 'metlink' if kind == 'metlink' else 'at', stamp)


def records_with_meta(records, meta, period_key):
    latest = max(row[period_key] for row in records)
    meta['latest_data'] = latest
    meta['coverage_from'] = min(row[period_key] for row in records)
    for row in records:
        row.update(meta)
    return records


def sources():
    records = []
    for kind in ('daily', 'monthly', 'punctuality', 'metlink'):
        current_url = METLINK_PAGE if kind == 'metlink' else AT_PAGE
        owner = 'metlink' if kind == 'metlink' else 'at'
        try:
            body, meta = next(load_download(kind, 0))
            current_url = meta['source_url']
            if kind == 'daily':
                rows = parse_patronage(body, 'daily')
                key = 'period'
            elif kind == 'monthly':
                rows = parse_patronage(body, 'monthly', True)
                key = 'period'
            elif kind == 'punctuality':
                rows = parse_punctuality(body)
                key = 'month'
            else:
                rows = parse_metlink(body)
                key = 'day'
            records_with_meta(rows, meta, key)
            records.append({'source': kind, 'status': 'healthy', 'records': len(rows), **meta})
        except (nzfetch.FetchError, ValueError, BadZipFile, ET.ParseError, KeyError, IndexError, TypeError, UnicodeError) as exc:
            record = {'source': kind, 'status': 'degraded', 'message': str(exc), **meta_for(current_url, owner)}
            if isinstance(exc, nzfetch.RateLimited):
                record['retry_after'] = exc.retry_after
            records.append(record)
    try:
        robots, stamp = get_bytes(ROBOTS_URL, 0)
        disallowed = b'Disallow: /umbraco/' in robots
        records.append({'source': 'city_carparks', 'status': 'blocked',
                        'message': 'City vacancy fragment is not queried: /umbraco/ is disallowed by AT robots.txt.' if disallowed
                                   else 'City vacancy fragment requires a fresh access and parser review before enabling.',
                        'robots_url': ROBOTS_URL, **meta_for(CITY_URL, stamp=stamp)})
    except nzfetch.FetchError as exc:
        records.append({'source': 'city_carparks', 'status': 'blocked', 'message': str(exc), **meta_for(CITY_URL)})
    try:
        body, stamp = get_bytes(INVENTORY_URL, 0)
        rows = parse_inventory(json.loads(body))
        records.append({'source': 'parking_inventory', 'status': 'healthy', 'records': len(rows),
                        'undated_availability_records': sum(r['available_spaces'] is not None for r in rows),
                        **meta_for(INVENTORY_URL, stamp=stamp)})
    except (nzfetch.FetchError, ValueError, KeyError, TypeError) as exc:
        records.append({'source': 'parking_inventory', 'status': 'degraded', 'message': str(exc), **meta_for(INVENTORY_URL)})
    return result_envelope(records, meta_for(AT_PAGE))


def build_parser():
    parser = Parser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('sources', 'patronage', 'punctuality', 'carparks', 'metlink'):
        child = commands.add_parser(name)
        child.add_argument('--json', action='store_true', help='emit provenance and results as JSON')
        if name in {'patronage', 'punctuality', 'metlink'}:
            child.add_argument('--route', help='exact route identifier, case-insensitive')
            child.add_argument('--max-age', type=int, default=86400, help='download cache max age in seconds, 0–86400; 0 refreshes')
        if name == 'patronage':
            child.add_argument('--mode', required=True, choices=('bus', 'train', 'ferry'))
            child.add_argument('--from', dest='from_date', help='inclusive YYYY-MM or YYYY-MM-DD')
            child.add_argument('--to', dest='to_date', help='inclusive YYYY-MM or YYYY-MM-DD')
            child.add_argument('--frequency', choices=('daily', 'monthly'), help='default daily for mode totals, monthly with --route')
        elif name == 'punctuality':
            child.add_argument('--month', help='YYYY-MM; searches published AT archives when supplied')
        elif name == 'metlink':
            child.add_argument('--date', help='exact YYYY-MM-DD')
        elif name == 'carparks':
            child.add_argument('--inventory', action='store_true', help='use the public facility inventory; undated values are not live city vacancies')
            add_spatial_arguments(child)
    return parser


def execute(args):
    if args.command == 'sources':
        return sources()
    if args.command == 'carparks':
        if not args.inventory:
            raise AccessRestricted('City car park endpoint is under /umbraco/, disallowed by https://at.govt.nz/robots.txt; use --inventory for facilities with undated availability fields.')
        body, stamp = get_bytes(INVENTORY_URL, 0)
        rows = parse_inventory(json.loads(body))
        if args.bbox:
            west, south, east, north = args.bbox
            rows = [r for r in rows if west <= r['longitude'] <= east and south <= r['latitude'] <= north]
        meta = meta_for(INVENTORY_URL, stamp=stamp)
        meta['caveat'] = 'Facility inventory; available_spaces has no observation timestamp and is not established as live short-term availability.'
        if args.format == 'geojson':
            return geojson_envelope([{'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [r['longitude'], r['latitude']]},
                                     'properties': r} for r in rows], meta)
        return result_envelope(rows, meta)
    if not 0 <= args.max_age <= 86400:
        raise InputError('--max-age must be between 0 and 86400 seconds')
    if args.route is not None and not args.route.strip():
        raise InputError('--route must not be empty')
    start = end = None
    if args.command == 'patronage':
        start, end = bounds(args.from_date), bounds(args.to_date, True)
        if start and end and start > end:
            raise InputError('--from must not be after --to')
        frequency = args.frequency or ('monthly' if args.route else 'daily')
        if args.route and frequency == 'daily':
            raise InputError('AT route patronage is monthly; use --frequency monthly')
        kind = frequency
        archive = bool(start or end)
        key = 'period'
    elif args.command == 'punctuality':
        if args.month and len(args.month) != 7:
            raise InputError('--month must be YYYY-MM')
        bounds(args.month)
        kind, archive, key = 'punctuality', bool(args.month), 'month'
    else:
        if args.date and len(args.date) != 10:
            raise InputError('--date must be YYYY-MM-DD')
        bounds(args.date)
        kind, archive, key = 'metlink', False, 'day'
    results = []
    metas = []
    seen = set()
    for body, meta in load_download(kind, args.max_age, archive):
        if args.command == 'patronage':
            rows = parse_patronage(body, frequency, args.route is not None)
        elif args.command == 'punctuality':
            rows = parse_punctuality(body)
        else:
            rows = parse_metlink(body)
        records_with_meta(rows, meta, key)
        metas.append(meta)
        for row in rows:
            if not matches(row, args.route):
                continue
            if args.command == 'patronage' and (row['mode'] != args.mode or not in_bounds(row, start, end)):
                continue
            if args.command == 'punctuality' and args.month and row['month'] != args.month:
                continue
            if args.command == 'metlink' and args.date and row['day'] != args.date:
                continue
            identity = (row.get('mode'), row.get('route'), row[key])
            if identity not in seen:
                seen.add(identity)
                results.append(row)
        # Do not download older fiscal years if the query is covered already.
        if archive:
            earliest = bounds(meta['coverage_from'])
            target = (start or end) if args.command == 'patronage' else bounds(args.month)
            if earliest <= target:
                break
    meta = dict(metas[0])
    meta['coverage_from'] = min(m['coverage_from'] for m in metas)
    meta['queried_sources'] = [m['source_url'] for m in metas]
    meta['matched_records'] = len(results)
    return result_envelope(sorted(results, key=lambda r: (r[key], r.get('mode', ''), r.get('route', ''))), meta)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    machine = '--json' in argv or ('--format' in argv and 'geojson' in argv) or '--format=geojson' in argv
    url, owner = AT_PAGE, 'at'
    if argv and argv[0] == 'metlink':
        url, owner = METLINK_PAGE, 'metlink'
    elif argv and argv[0] == 'carparks':
        url = INVENTORY_URL if '--inventory' in argv else CITY_URL
    try:
        args = build_parser().parse_args(argv)
        output = execute(args)
        if machine:
            print(json.dumps(output, indent=2, ensure_ascii=False, allow_nan=False))
        else:
            print(f"{len(output['results'])} records — {output['meta']['publisher']}")
            if output['meta'].get('caveat'):
                print(output['meta']['caveat'])
            for row in output['results']:
                fields = {k: v for k, v in row.items() if k not in {'publisher', 'source_url', 'licence', 'retrieved_at', 'queried_sources'}}
                print(' | '.join(f'{k}: {v}' for k, v in fields.items()))
        return 0
    except InputError as exc:
        code, message = 2, str(exc)
    except AccessRestricted as exc:
        code, message = 4, str(exc)
    except nzfetch.RateLimited as exc:
        output = error_envelope(4, 'network error: ' + str(exc), meta_for(url, owner), retry_after=exc.retry_after)
        if machine:
            print(json.dumps(output, indent=2))
        else:
            print(output['error']['message'], file=sys.stderr)
        return 4
    except nzfetch.Blocked as exc:
        code, message = 4, 'network error: ' + str(exc)
    except nzfetch.FetchError as exc:
        code, message = 5, 'network error: ' + str(exc)
    except (ValueError, KeyError, TypeError, IndexError, BadZipFile, ET.ParseError, UnicodeError) as exc:
        code, message = 6, 'source schema error: ' + str(exc)
    except OSError as exc:
        code, message = 5, 'local cache error: ' + str(exc)
    if machine:
        print(json.dumps(error_envelope(code, message, meta_for(url, owner)), indent=2))
    else:
        print(message, file=sys.stderr)
    return code


if __name__ == '__main__':
    raise SystemExit(main())
