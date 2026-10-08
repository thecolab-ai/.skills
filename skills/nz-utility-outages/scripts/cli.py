#!/usr/bin/env python3
"""Keyless, read-only NZ utility outage feeds and Auckland rail calendars."""
from __future__ import annotations

import argparse
import calendar
import json
import math
import pathlib
import re
import sys
import zlib
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from zoneinfo import ZoneInfo

from provenance import add_spatial_arguments, error_envelope, geojson_envelope, provenance, result_envelope
from rail_calendar import parse_pdf

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / 'lib'))
import nzfetch  # noqa: E402

SOURCES = {
    'watercare': {
        'publisher': 'Watercare Services Limited',
        'source_url': 'https://webapi.watercare.co.nz/faults-outages/content',
        'page_url': 'https://www.watercare.co.nz/home/faults-and-outages',
        'access': 'supported', 'coverage': 'Auckland', 'spatial': True,
        'note': 'Public JSON fault and planned shutdown list; point locations, no affected-property count.',
    },
    'vector': {
        'publisher': 'Vector Limited', 'source_url': 'https://help.vector.co.nz/',
        'access': 'unsupported', 'coverage': 'Auckland', 'spatial': False,
        'note': 'Verified public HTML is a client-rendered shell. No keyless outage feed verified; use the official map manually.',
    },
    'wellington': {
        'publisher': 'Wellington Electricity Lines Limited',
        'source_url': 'https://www.welectricity.co.nz/outages/getalloutages',
        'page_url': 'https://www.welectricity.co.nz/outages/',
        'access': 'supported', 'coverage': 'Wellington region', 'spatial': True,
        'note': 'Public JSON served as text/html; includes planned, cancelled and recently resolved outages.',
    },
    'kiwirail': {
        'publisher': 'KiwiRail',
        'source_url': 'https://www.kiwirail.co.nz/our-network/our-regions/amp/upcoming-work/',
        'access': 'supported', 'coverage': 'Auckland metro rail', 'spatial': False,
        'licence': 'Copyright KiwiRail; no dataset-specific reuse licence stated',
        'note': 'Published HTML work notices, not passenger service closures. No coordinates are supplied.',
    },
    'kiwirail-calendar': {
        'publisher': 'KiwiRail',
        'source_url': 'https://www.kiwirail.co.nz/assets/Uploads/Our-network/Our-regions/Auckland-Metro-Rail/BOL-Calendar-for-website_new.pdf',
        'access': 'supported', 'coverage': 'Auckland metro rail', 'spatial': False,
        'licence': 'Copyright KiwiRail; no PDF-specific reuse licence stated',
        'note': 'Colour-coded PDF: verified version covers January–May 2026 only, published 2 February 2026; schedules can change.',
    },
    'powernet': {
        'publisher': 'PowerNet', 'source_url': 'https://powernet.co.nz/wp-json/pnl/v2/future',
        'terms_url': 'https://powernet.co.nz/terms-of-use/',
        'access': 'permission_required', 'coverage': 'Lower South Island', 'spatial': False,
        'licence': 'PowerNet Terms of Use sections 2.2 and 3.2: written consent required except as permitted by law',
        'note': 'Keyless JSON verified, but automated content use disabled because published terms require consent.',
    },
    'counties': {
        'publisher': 'Counties Energy',
        'source_url': 'https://api.integration.countiesenergy.co.nz/user/v1.0/outages',
        'page_url': 'https://app.countiesenergy.co.nz/',
        'access': 'blocked', 'coverage': 'Southern Auckland and northern Waikato', 'spatial': False,
        'licence': 'Proprietary; catalogue notes written permission required to reproduce content',
        'note': 'Catalogue API probe was HTTP 403; this build also could not access app robots.txt. Fetching disabled.',
    },
}
SOURCE_URL = SOURCES['watercare']['source_url']
PUBLISHER = 'Watercare, Wellington Electricity and KiwiRail'
MAX_RECORDS = 10000


class InputError(ValueError):
    """Invalid command arguments."""


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise InputError(message)


class SourceError(Exception):
    def __init__(self, code, message, retry_after=None):
        super().__init__(message)
        self.code, self.retry_after = code, retry_after


def source_meta(utility):
    source = SOURCES[utility]
    return provenance(source['source_url'], source['publisher'], licence=source.get('licence'))


def fetch(utility, *, binary=False):
    url = SOURCES[utility]['source_url']
    try:
        if binary:
            return nzfetch.fetch_bytes(url, timeout=10)[0]
        # Wellington declares text/html despite returning valid JSON.
        if utility == 'wellington':
            return json.loads(nzfetch.fetch_text(url, timeout=10))
        if utility == 'kiwirail':
            return nzfetch.fetch_text(url, timeout=10)
        body, _, _ = nzfetch.fetch_bytes(url, timeout=10, expect_json=True, accept='application/json,*/*')
        return json.loads(body)
    except nzfetch.RateLimited as exc:
        raise SourceError(4, f'network error: rate limited by {utility}', exc.retry_after) from exc
    except nzfetch.Blocked as exc:
        raise SourceError(4, f'network error: {utility} blocked this request') from exc
    except nzfetch.FetchError as exc:
        # Keep messages bounded and avoid returning proxy/configuration details.
        raise SourceError(5, f'network error: {utility} source unavailable ({type(exc).__name__})') from exc


def require_row(row, fields):
    if not isinstance(row, dict) or not set(fields) <= row.keys():
        raise ValueError('source record is missing required fields: ' + ', '.join(fields))


def require_list(value):
    if not isinstance(value, list) or len(value) > MAX_RECORDS:
        raise ValueError('source must return a bounded record array')
    return value


def iso_time(value, *, local=False):
    if value is None or value == '':
        return None
    if not isinstance(value, str):
        raise ValueError('source timestamp must be a string')
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        if not local:
            raise ValueError('source UTC timestamp has no timezone')
        result = result.replace(tzinfo=ZoneInfo('Pacific/Auckland'))
    return result.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def point(location):
    if location is None:
        return None
    require_row(location, ('lat', 'lng'))
    lat, lon = location['lat'], location['lng']
    if lat is None or lon is None:
        return None
    if isinstance(lat, bool) or isinstance(lon, bool):
        raise ValueError('source coordinates must be numeric')
    lat, lon = float(lat), float(lon)
    if not (math.isfinite(lon) and math.isfinite(lat) and -180 <= lon <= 180 and -90 <= lat <= 90):
        raise ValueError('source coordinates are outside WGS84')
    return {'type': 'Point', 'coordinates': [lon, lat]}


def count(value):
    if value is None or value == '':
        return None
    number = int(value)
    if isinstance(value, bool) or number < 0 or float(value) != number:
        raise ValueError('source affected count must be a non-negative integer')
    return number


def record(utility, meta, *, identifier, kind, status, start=None, end=None, area=None,
           geometry=None, affected_count=None, description=None, **extras):
    if identifier is None or not isinstance(identifier, (str, int)) or isinstance(identifier, bool):
        raise ValueError('source record identifier must be a string or integer')
    if area is not None and not isinstance(area, str):
        raise ValueError('source area must be text or null')
    if description is not None and not isinstance(description, str):
        raise ValueError('source description must be text or null')
    return {
        'utility': utility, 'id': str(identifier), 'kind': kind, 'status': status,
        'start': start, 'end': end, 'area': area, 'geometry': geometry,
        'affected_count': affected_count, 'description': description, **extras, **meta,
    }


def window_status(start, end, now):
    if start and datetime.fromisoformat(start.replace('Z', '+00:00')) > now:
        return 'planned'
    if start and end and datetime.fromisoformat(end.replace('Z', '+00:00')) >= now:
        return 'current'
    return 'unknown'  # An estimated end is not evidence of restoration.


def parse_watercare(payload, meta, now):
    rows = []
    for row in require_list(payload):
        require_row(row, ('id', 'name', 'type', 'start_time', 'estimated_resolution_time', 'location', 'updatedAt'))
        if row['type'] not in ('planned', 'unplanned'):
            raise ValueError('unrecognised Watercare outage type')
        location = row['location']
        if location is not None:
            require_row(location, ('coordinates',))
        start, end = iso_time(row['start_time']), iso_time(row['estimated_resolution_time'])
        status = 'current' if row['type'] == 'unplanned' else window_status(start, end, now)
        item = record('watercare', meta, identifier=row['id'], kind='water_outage', status=status,
                      start=start, end=end, area=row.get('address') or row['name'],
                      geometry=point(location['coordinates']) if location else None,
                      description=row.get('description'), source_status=row['type'], end_is_estimate=True)
        if row['updatedAt']:
            iso_time(row['updatedAt'])
            item['latest_data'] = row['updatedAt']
        rows.append(item)
    return rows


def parse_wellington(payload, meta, now):
    require_row(payload, ('plannedOutages', 'unplannedOutages'))
    rows = []
    for category in ('plannedOutages', 'unplannedOutages'):
        for row in require_list(payload[category]):
            require_row(row, ('id', 'type', 'status', 'timeBasedStatus', 'location', 'suburbsText'))
            planned = category == 'plannedOutages'
            if row['type'] != ('planned' if planned else 'unplanned'):
                raise ValueError('Wellington outage type disagrees with its array')
            if planned:
                require_row(row, ('outageStartDateTime', 'outageEndDateTime', 'customersAffected', 'useAlternateDate'))
                alternate = row['useAlternateDate']
                if alternate not in (0, 1, False, True):
                    raise ValueError('Wellington alternate-date flag is unsupported')
                if alternate:
                    require_row(row, ('alternateStartDateTime', 'alternateEndDateTime'))
                start = iso_time(row['alternateStartDateTime'] if alternate else row['outageStartDateTime'], local=True)
                end = iso_time(row['alternateEndDateTime'] if alternate else row['outageEndDateTime'], local=True)
                affected = count(row['customersAffected'])
                description = row.get('reasonForOutage')
                status = window_status(start, end, now)
            else:
                require_row(row, ('timeOfFault', 'lastUpdatedEta', 'lastUpdatedCustomersAffected', 'lastUpdatedTime'))
                start, end = iso_time(row['timeOfFault'], local=True), iso_time(row['lastUpdatedEta'], local=True)
                affected = count(row['lastUpdatedCustomersAffected'])
                description = row.get('lastUpdatedComments')
                status = 'current' if str(row['timeBasedStatus']).lower() in ('current', 'active') else 'unknown'
            state = str(row['status']).lower()
            if state in ('cancelled', 'canceled'):
                status = 'cancelled'
            elif state in ('closed', 'completed', 'restored'):
                status = 'resolved'
            item = record('wellington', meta, identifier=row['id'], kind='power_outage', status=status,
                          start=start, end=end, area=row['suburbsText'], geometry=point(row['location']),
                          affected_count=affected, description=description, source_status=row['status'],
                          source_time_status=row['timeBasedStatus'], end_is_estimate=not planned,
                          alternate_date_used=bool(row.get('useAlternateDate', False)))
            if row.get('lastUpdatedTime'):
                iso_time(row['lastUpdatedTime'], local=True)
                item['latest_data'] = row['lastUpdatedTime']
            rows.append(item)
    return rows


class WorkHTML(HTMLParser):
    """Read heading/paragraph blocks only within the page's main element."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_main = False
        self.tag = None
        self.parts, self.links, self.blocks = [], [], []
        self.strong = False
        self.title_parts = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'main':
            self.in_main = True
        if self.in_main and tag in ('h1', 'h2', 'h3', 'p'):
            self.tag, self.parts, self.links = tag, [], []
            self.title_parts = []
        elif self.tag and tag == 'strong':
            self.strong = True
        elif self.tag and tag == 'a' and attrs.get('href'):
            self.links.append(attrs['href'])

    def handle_data(self, value):
        if self.tag:
            self.parts.append(value)
            if self.strong:
                self.title_parts.append(value)

    def handle_endtag(self, tag):
        if tag == self.tag:
            self.blocks.append((tag, re.sub(r'\s+', ' ', ''.join(self.parts)).strip(), self.links,
                                ''.join(self.title_parts).strip()))
            self.tag = None
        if tag == 'strong':
            self.strong = False
        if tag == 'main':
            self.in_main = False


def parse_works(body, meta):
    parser = WorkHTML()
    parser.feed(body)
    rows, section, area, grouped = [], None, None, []
    found_sections = set()
    for tag, text, links, title in parser.blocks:
        if tag == 'h2':
            section = 'short' if 'short term upgrade works' in text.lower() else 'ongoing' if 'ongoing upgrade works' in text.lower() else None
            if section:
                found_sections.add(section)
        elif section and tag == 'h3':
            area = text
        elif section and tag == 'p' and text:
            if not title and grouped and grouped[-1][0] == section and grouped[-1][1] == area:
                grouped[-1][3] += ' ' + text
                grouped[-1][4].extend(links)
            else:
                grouped.append([section, area, title, text, list(links)])
    if found_sections != {'short', 'ongoing'} or not grouped:
        raise ValueError('KiwiRail work notice headings changed')
    for index, (section, area, title, text, links) in enumerate(grouped):
        # Site notices may omit a year in prose but include it in their linked notice filename.
        years = set(re.findall(r'\b(20\d{2})\b', text + ' ' + ' '.join(links)))
        dates = re.findall(r'\b(\d{1,2})\s+(' + '|'.join(calendar.month_name[1:]) + r')\b', text)
        start = end = None
        if len(years) == 1 and len(dates) == 2:
            year = int(next(iter(years)))
            start, end = [date(year, list(calendar.month_name).index(month), int(day)).isoformat() for day, month in dates]
            if start > end:
                raise ValueError('KiwiRail notice date range is reversed')
        # Preserve paragraphs even when dates are unavailable. No geocoding or inferred year.
        notice_only = bool(title and 'noise' in title.lower() and 'work' not in title.lower())
        rows.append(record('kiwirail', meta, identifier=f'notice-{index + 1}', kind='rail_notice' if notice_only else 'rail_work',
                           status='unknown' if notice_only else 'planned' if section == 'short' else 'current', start=start, end=end,
                           area=title or area or text.split(' - ', 1)[0], description=text,
                           date_precision='day' if start else None, notice_links=links,
                           passenger_closure_confirmed=False))
    return rows


def parse_calendar(body, meta):
    calendar_data = parse_pdf(body)
    meta.update({key: calendar_data[key] for key in ('latest_data', 'coverage_start', 'coverage_end')})
    meta['note'] = 'Calendar coverage only; empty results outside coverage do not mean no closures. Dates are inclusive NZ calendar days, not exact operating hours.'
    return [record('kiwirail', meta, identifier='calendar-' + item['date'], kind=item['kind'],
                   status='planned', start=item['date'], end=item['date'], area='Auckland metro rail',
                   date_precision='day', source_status='published_schedule') for item in calendar_data['closures']]


def load(utility):
    source = SOURCES[utility]
    if source['access'] != 'supported':
        code = 4 if source['access'] == 'blocked' else 7
        raise SourceError(code, source['note'])
    meta = source_meta(utility)
    payload = fetch(utility, binary=utility == 'kiwirail-calendar')
    now = datetime.now(timezone.utc)
    if utility == 'watercare':
        rows = parse_watercare(payload, meta, now)
    elif utility == 'wellington':
        rows = parse_wellington(payload, meta, now)
    elif utility == 'kiwirail':
        rows = parse_works(payload, meta)
    else:
        rows = parse_calendar(payload, meta)
    return rows, meta


def near_point(value):
    try:
        lon, lat = map(float, value.split(','))
    except ValueError as exc:
        raise argparse.ArgumentTypeError('--near must be lon,lat in WGS84') from exc
    if not (math.isfinite(lon) and math.isfinite(lat) and -180 <= lon <= 180 and -90 <= lat <= 90):
        raise argparse.ArgumentTypeError('--near must contain finite WGS84 coordinates')
    return lon, lat


def radius(value):
    try:
        distance = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError('--radius must be a positive distance in km') from exc
    if not math.isfinite(distance) or not 0 < distance <= 20000:
        raise argparse.ArgumentTypeError('--radius must be greater than 0 and at most 20000 km')
    return distance


def iso_date(value):
    try:
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
            raise ValueError()
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise argparse.ArgumentTypeError('dates must be YYYY-MM-DD') from exc


def distance_km(first, second):
    lon1, lat1, lon2, lat2 = map(math.radians, (*first, *second))
    value = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371.0088 * 2 * math.asin(math.sqrt(min(1, max(0, value))))


def filter_rows(rows, args, meta):
    if getattr(args, 'status', None):
        rows = [row for row in rows if row['status'] == args.status]
    if getattr(args, 'bbox', None) or args.command == 'near':
        meta['excluded_unlocated'] = sum(row['geometry'] is None for row in rows)
        rows = [row for row in rows if row['geometry'] is not None]
    if getattr(args, 'bbox', None):
        left, bottom, right, top = args.bbox
        rows = [row for row in rows if left <= row['geometry']['coordinates'][0] <= right and bottom <= row['geometry']['coordinates'][1] <= top]
    if args.command == 'near':
        for row in rows:
            row['distance_km'] = round(distance_km(args.near, row['geometry']['coordinates']), 3)
        rows = [row for row in rows if distance_km(args.near, row['geometry']['coordinates']) <= args.radius]
        rows.sort(key=lambda row: row['distance_km'])
    if args.command == 'rail-closures':
        rows = [row for row in rows if (not args.from_date or row['end'] >= args.from_date) and (not args.to_date or row['start'] <= args.to_date)]
    return rows


def build_parser():
    parser = ArgumentParser(description='NZ utility outages, Auckland rail works and closure calendars')
    sub = parser.add_subparsers(dest='command', required=True)
    sources = sub.add_parser('sources', help='list verified source coverage, access and limits (no network calls)')
    sources.add_argument('--json', action='store_true', help='emit JSON with provenance')
    outages = sub.add_parser('outages', help='fetch an operator outage feed or KiwiRail work notices')
    outages.add_argument('--utility', required=True, choices=[key for key in SOURCES if key != 'kiwirail-calendar'])
    outages.add_argument('--status', choices=('current', 'planned'), help='filter normalised status')
    outages.add_argument('--json', action='store_true', help='emit JSON with provenance')
    add_spatial_arguments(outages)
    rail = sub.add_parser('rail-closures', help='extract closure days from the published KiwiRail PDF calendar')
    rail.add_argument('--from', dest='from_date', type=iso_date, help='inclusive first date, YYYY-MM-DD')
    rail.add_argument('--to', dest='to_date', type=iso_date, help='inclusive last date, YYYY-MM-DD')
    rail.add_argument('--json', action='store_true', help='emit JSON with calendar coverage and provenance')
    nearby = sub.add_parser('near', help='match published point locations within a radius; no geocoding')
    nearby.add_argument('--near', required=True, type=near_point, metavar='lon,lat')
    nearby.add_argument('--radius', type=radius, default=5.0, help='radius in km (default 5)')
    nearby.add_argument('--utility', choices=('watercare', 'wellington', 'all'), default='watercare', help='default Watercare; all combines the supported spatial feeds')
    nearby.add_argument('--status', choices=('current', 'planned'))
    nearby.add_argument('--json', action='store_true', help='emit JSON with provenance')
    add_spatial_arguments(nearby)
    return parser


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    parser = build_parser()
    as_json = '--json' in argv or '--format=geojson' in argv or ('--format' in argv and 'geojson' in argv)
    meta = source_meta('watercare')
    try:
        args = parser.parse_args(argv)
        if args.command == 'sources':
            meta = provenance(SOURCE_URL, PUBLISHER)
            meta['retrieval_kind'] = 'verified_source_registry'
            rows = [{'utility': key, **value, **source_meta(key), 'verified_on': '2026-10-08'} for key, value in SOURCES.items()]
        else:
            utility = 'kiwirail-calendar' if args.command == 'rail-closures' else args.utility
            if utility != 'all':
                meta = source_meta(utility)
            if args.command == 'rail-closures' and args.from_date and args.to_date and args.from_date > args.to_date:
                raise InputError('--from must be on or before --to')
            if args.command == 'outages' and args.bbox and not SOURCES[utility]['spatial'] and SOURCES[utility]['access'] == 'supported':
                raise SourceError(7, 'KiwiRail publishes no coordinates; --bbox cannot filter its work notices')
            if utility == 'all':
                rows = []
                meta = provenance(SOURCE_URL, 'Watercare and Wellington Electricity')
                for key in ('watercare', 'wellington'):
                    # Attribute a possible error to the feed that failed; no partial success.
                    meta = source_meta(key)
                    source_rows, _ = load(key)
                    rows.extend(source_rows)
                meta = provenance(SOURCE_URL, 'Watercare and Wellington Electricity')
            else:
                rows, meta = load(utility)
            rows = filter_rows(rows, args, meta)
        if getattr(args, 'format', 'json') == 'geojson':
            features = [{'type': 'Feature', 'id': row['utility'] + ':' + row['id'], 'geometry': row['geometry'], 'properties': {key: value for key, value in row.items() if key != 'geometry'}} for row in rows]
            payload = geojson_envelope(features, meta)
        else:
            payload = result_envelope(rows, meta)
        if as_json:
            print(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False))
        else:
            print(f'{len(rows)} records; {meta["publisher"]}')
            for row in rows:
                if args.command == 'sources':
                    print(f'{row["utility"]}: {row["access"]} — {row["note"]}')
                else:
                    print(f'{row["utility"]} {row["id"]}: {row["status"]} {row["kind"]}; {row["start"] or "time unknown"} to {row["end"] or "unknown"}; {row["area"] or "area unknown"}')
            if meta.get('coverage_end'):
                print(f'Calendar coverage: {meta["coverage_start"]} to {meta["coverage_end"]}. {meta["note"]}')
            if meta.get('excluded_unlocated'):
                print(f'Excluded {meta["excluded_unlocated"]} records without published coordinates.')
            print(f'Source: {meta["source_url"]}; retrieved {meta["retrieved_at"]}')
        return 0
    except (InputError, SourceError, ValueError, TypeError, KeyError, OverflowError, zlib.error) as exc:
        code = 2 if isinstance(exc, InputError) else exc.code if isinstance(exc, SourceError) else 6
        message = str(exc) if isinstance(exc, (InputError, SourceError)) else f'source schema failure: {exc}'
        if as_json:
            print(json.dumps(error_envelope(code, message, meta, retry_after=getattr(exc, 'retry_after', None)), indent=2))
        else:
            print(f'nz-utility-outages: {message}', file=sys.stderr)
        return code


if __name__ == '__main__':
    raise SystemExit(main())
