#!/usr/bin/env python3
"""Stream NZ GTFS static tables from bounded, cached public ZIP downloads."""
from __future__ import annotations

import argparse
import csv
import heapq
import hashlib
import http.client
import io
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit
import zipfile
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from provenance import provenance, result_envelope, error_envelope, geojson_envelope

TIMEOUT = 10
MAX_DOWNLOAD = 128 * 1024 * 1024
MAX_UNCOMPRESSED = 1024 * 1024 * 1024
DEFAULT_CACHE = Path(os.environ.get('GTFS_NZ_CACHE_DIR') or
                     Path(os.environ.get('XDG_CACHE_HOME') or Path.home() / '.cache') / 'thecolab-gtfs-nz')
REGISTRY_URL = 'https://gtfs.at.govt.nz/gtfs.zip'
REGISTRY_PUBLISHER = 'NZ public transport agencies'
ALLOWED_DOMAINS = frozenset(('gtfs.at.govt.nz', 'static.opendata.metlink.org.nz',
                            'wrcscheduledata.blob.core.windows.net', 'www.orc.govt.nz'))
FEEDS = {
    'at': {
        'name': 'Auckland Transport', 'publisher': 'Auckland Transport',
        'source_url': 'https://gtfs.at.govt.nz/gtfs.zip',
        'licence': 'CC BY 4.0',
    },
    'metlink': {
        'name': 'Metlink (Wellington)', 'publisher': 'Greater Wellington Regional Council',
        'source_url': 'https://static.opendata.metlink.org.nz/v1/gtfs/full.zip',
        'licence': 'Metlink GTFS Terms of Use',
    },
    'busit': {
        'name': 'BUSIT (Waikato)', 'publisher': 'Waikato Regional Council',
        'source_url': 'https://wrcscheduledata.blob.core.windows.net/wrcgtfs/busit-nz-public.zip',
        'licence': None,
    },
    'orbus': {
        'name': 'Orbus (Otago)', 'publisher': 'Otago Regional Council',
        'source_url': 'https://www.orc.govt.nz/transit/google_transit.zip',
        'licence': 'CC BY 4.0',
    },
}
# Fields consumed by this reader; all upstream columns are preserved on records.
FIELDS = {
    'agency.txt': ('agency_name', 'agency_timezone'),
    'stops.txt': ('stop_id', 'stop_name', 'stop_lat', 'stop_lon'),
    'routes.txt': ('route_id', 'route_type'),
    'trips.txt': ('route_id', 'service_id', 'trip_id'),
    'stop_times.txt': ('trip_id', 'stop_id', 'stop_sequence', 'departure_time'),
    'calendar.txt': ('service_id', 'start_date', 'end_date', 'monday', 'tuesday',
                     'wednesday', 'thursday', 'friday', 'saturday', 'sunday'),
    'calendar_dates.txt': ('service_id', 'date', 'exception_type'),
    'feed_info.txt': ('feed_publisher_name', 'feed_publisher_url', 'feed_lang'),
    'shapes.txt': ('shape_id', 'shape_pt_sequence', 'shape_pt_lon', 'shape_pt_lat'),
    'frequencies.txt': ('trip_id', 'start_time', 'end_time', 'headway_secs'),
}


class GTFSFailure(Exception):
    def __init__(self, message, code=6, retry_after=None):
        super().__init__(message)
        self.code = code
        self.retry_after = retry_after


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')


def gtfs_date(value):
    if not re.fullmatch(r'\d{8}', value):
        raise GTFSFailure(f'Invalid GTFS date: {value!r}')
    try:
        return datetime.strptime(value, '%Y%m%d').date()
    except ValueError as exc:
        raise GTFSFailure(f'Invalid GTFS date: {value!r}') from exc


def seconds(value):
    if not re.fullmatch(r'\d{1,3}:\d{2}(?::\d{2})?', value):
        raise ValueError('time must be HH:MM or HH:MM:SS (hours may exceed 24)')
    parts = [int(v) for v in value.split(':')]
    h, m, s = (*parts, 0) if len(parts) == 2 else parts
    if m > 59 or s > 59:
        raise ValueError('minutes and seconds must be between 00 and 59')
    return h * 3600 + m * 60 + s


def coords(lon, lat):
    lon, lat = float(lon), float(lat)
    if not (math.isfinite(lon) and math.isfinite(lat) and -180 <= lon <= 180 and -90 <= lat <= 90):
        raise ValueError('coordinates must be finite WGS84 longitude,latitude')
    return lon, lat


def parse_near(value):
    try:
        lon, lat = value.split(',')
        return coords(lon, lat)
    except ValueError as exc:
        raise argparse.ArgumentTypeError('near must be lon,lat in WGS84') from exc


def parse_bbox(value):
    try:
        a, b, c, d = value.split(',')
        lo, la = coords(a, b)
        hi, ha = coords(c, d)
        if lo >= hi or la >= ha:
            raise ValueError('minimum must be smaller than maximum')
        return lo, la, hi, ha
    except ValueError as exc:
        raise argparse.ArgumentTypeError('bbox must be minLon,minLat,maxLon,maxLat with increasing bounds') from exc


def nonnegative(value):
    try:
        v = float(value)
        if not math.isfinite(v) or v < 0:
            raise ValueError()
        return v
    except ValueError as exc:
        raise argparse.ArgumentTypeError('value must be finite and non-negative') from exc


def limit_arg(value):
    try:
        n = int(value)
        if not 1 <= n <= 10000:
            raise ValueError()
        return n
    except ValueError as exc:
        raise argparse.ArgumentTypeError('limit must be between 1 and 10000') from exc


class Feed:
    def __init__(self, path, key, retrieved_at, cached=False):
        self.key = key
        self.retrieved_at = retrieved_at
        self.cached = cached
        self.z = zipfile.ZipFile(path)
        try:
            names = self.z.namelist()
            if len(names) != len(set(names)):
                raise GTFSFailure('GTFS ZIP contains duplicate table names')
            if sum(i.file_size for i in self.z.infolist()) > MAX_UNCOMPRESSED:
                raise GTFSFailure('GTFS ZIP exceeds 1 GiB uncompressed size limit')
            for name in ('agency.txt', 'stops.txt', 'routes.txt', 'trips.txt', 'stop_times.txt'):
                if name not in names:
                    raise GTFSFailure(f'GTFS ZIP is missing {name}')
                # Validate table headers and at least one row without loading the table.
                if next(self.rows(name), None) is None:
                    raise GTFSFailure(f'GTFS table is empty: {name}')
            if not {'calendar.txt', 'calendar_dates.txt'}.intersection(names):
                raise GTFSFailure('GTFS ZIP needs calendar.txt or calendar_dates.txt')
            self.info = list(self.rows('feed_info.txt', optional=True))
            if len(self.info) > 10:
                raise GTFSFailure('Unexpected number of feed_info records')
            self.agencies = list(self.rows('agency.txt'))
            zones = {r['agency_timezone'] for r in self.agencies}
            if zones != {'Pacific/Auckland'}:
                raise GTFSFailure(f'Unsupported agency timezone(s): {sorted(zones)}', 7)
        except Exception:
            self.z.close()
            raise

    def close(self):
        self.z.close()

    def rows(self, name, optional=False):
        if name not in self.z.namelist():
            if optional:
                return
            raise GTFSFailure(f'GTFS ZIP is missing {name}')
        with self.z.open(name) as raw, io.TextIOWrapper(raw, encoding='utf-8-sig', newline='') as stream:
            reader = csv.DictReader(stream)
            if not reader.fieldnames or not set(FIELDS[name]).issubset(reader.fieldnames):
                raise GTFSFailure(f'GTFS table {name} has missing required headers')
            for row in reader:
                if None in row or any(v is None for v in row.values()):
                    raise GTFSFailure(f'Malformed CSV row in {name}, line {reader.line_num}')
                yield row

    def provenance(self):
        source = FEEDS[self.key]
        meta = provenance(source['source_url'], source['publisher'],
                          licence=source.get('licence'), retrieved_at=self.retrieved_at)
        if self.info:
            meta['feed_info'] = self.info
            starts = [gtfs_date(r['feed_start_date']) for r in self.info if r.get('feed_start_date')]
            ends = [gtfs_date(r['feed_end_date']) for r in self.info if r.get('feed_end_date')]
            if starts and ends:
                meta['latest_data'] = f'{min(starts).isoformat()}/{max(ends).isoformat()}'
            elif starts or ends:
                meta['latest_data'] = (min(starts) if starts else max(ends)).isoformat()
        return meta

    def warnings(self):
        warnings = []
        if not self.info:
            warnings.append('Source has no feed_info.txt; latest_data is not stated.')
        if self.info and self.info[0].get('feed_end_date'):
            if gtfs_date(self.info[0]['feed_end_date']) < datetime.now(ZoneInfo('Pacific/Auckland')).date():
                warnings.append('Feed validity has ended; schedules may be stale.')
        return warnings

    def output(self, records, total, **extra):
        meta = {**self.provenance(), 'feed': self.key, 'cached': self.cached,
                'total': total, 'returned': len(records), 'truncated': total > len(records),
                'warnings': self.warnings(), **extra}
        return result_envelope(records, meta)


class SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        try:
            target = urlsplit(newurl)
            allowed = (target.scheme == 'https' and target.hostname in ALLOWED_DOMAINS and
                       target.port in (None, 443) and target.username is None)
        except ValueError:
            allowed = False
        if not allowed:
            raise GTFSFailure('Redirect target is outside the declared HTTPS host allowlist', 7)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


OPENER = urllib.request.build_opener(SafeRedirectHandler())


def error_meta(key=None):
    source = FEEDS.get(key)
    return provenance(source['source_url'] if source else REGISTRY_URL,
                      source['publisher'] if source else REGISTRY_PUBLISHER,
                      licence=source.get('licence') if source else None)


def fingerprint(stream):
    """Hash the opened archive, so a concurrent replacement cannot change its identity."""
    position = stream.tell()
    try:
        stream.seek(0)
        digest = hashlib.sha256()
        size = 0
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
            size += len(block)
        return {'size': size, 'sha256': digest.hexdigest()}
    finally:
        stream.seek(position)


def get_feed(key, cache_dir=DEFAULT_CACHE, max_age=86400, refresh=False):
    directory = Path(cache_dir)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / (key + '.zip')
    sidecar = directory / (key + '.json')
    if not refresh and target.is_file() and sidecar.is_file():
        cached = None
        try:
            meta = json.loads(sidecar.read_text(encoding='utf-8'))
            fetched = datetime.fromisoformat(meta['retrieved_at'].replace('Z', '+00:00')).timestamp()
            if meta['source_url'] == FEEDS[key]['source_url'] and 0 <= time.time() - fetched < max_age:
                cached = Feed(target, key, meta['retrieved_at'], cached=True)
                identity = fingerprint(cached.z.fp)
                if all(meta.get(k) == v for k, v in identity.items()):
                    return cached
        except (ValueError, TypeError, KeyError, GTFSFailure, zipfile.BadZipFile, csv.Error):
            pass  # Invalid or obsolete caches are downloaded again, never served silently.
        if cached is not None:
            cached.close()
    temporary = metadata_temp = None
    candidate = None
    try:
        # Cache creation/writes sit outside the network OSError classification.
        with tempfile.NamedTemporaryFile(dir=directory, suffix='.zip', delete=False) as destination:
            temporary = Path(destination.name)
            request = urllib.request.Request(FEEDS[key]['source_url'], headers={
                'User-Agent': 'TheColab-gtfs-nz/1.0', 'Accept': 'application/zip'})
            deadline = time.monotonic() + 50
            try:
                with OPENER.open(request, timeout=TIMEOUT) as response:
                    retrieved_at = utc_now()
                    size = 0
                    # Return after one buffered/socket read so a dripping response
                    # still lets the loop check the download deadline.
                    read_block = getattr(response, 'read1', response.read)
                    while True:
                        if time.monotonic() >= deadline:
                            raise GTFSFailure('network error: download exceeded 50 s', 5)
                        block = read_block(1024 * 1024)
                        if time.monotonic() >= deadline:
                            raise GTFSFailure('network error: download exceeded 50 s', 5)
                        if not block:
                            break
                        size += len(block)
                        if size > MAX_DOWNLOAD:
                            raise GTFSFailure('Download exceeds 128 MiB size limit')
                        try:
                            destination.write(block)
                        except OSError as exc:
                            raise GTFSFailure('Could not write GTFS cache; check cache permissions', 6) from exc
            except urllib.error.HTTPError as exc:
                code = 4 if exc.code in (401, 403, 406, 429, 451) else 5
                raise GTFSFailure(f'network error: HTTP {exc.code} downloading {key}', code,
                                  exc.headers.get('Retry-After')) from exc
            except (urllib.error.URLError, http.client.HTTPException, OSError) as exc:
                # Never echo exception URLs: a transport might contain proxy credentials.
                raise GTFSFailure(f'network error: could not download {key} (10 s socket timeout)', 5) from exc
        try:
            candidate = Feed(temporary, key, retrieved_at)
        except (UnicodeError, csv.Error) as exc:
            raise GTFSFailure('Could not parse GTFS tables; expected UTF-8 CSV', 6) from exc
        identity = fingerprint(candidate.z.fp)
        os.replace(temporary, target)
        temporary = None
        # Keep this opened ZIP paired with its own provenance during concurrent downloads.
        candidate.z.filename = str(target)
        with tempfile.NamedTemporaryFile(dir=directory, mode='w', encoding='utf-8', delete=False) as f:
            metadata_temp = Path(f.name)
            json.dump({'source_url': FEEDS[key]['source_url'], 'retrieved_at': retrieved_at, **identity}, f)
        os.replace(metadata_temp, sidecar)
        metadata_temp = None
        result = candidate
        candidate = None
        return result
    finally:
        if candidate is not None:
            candidate.close()
        for path in (temporary, metadata_temp):
            if path is not None:
                path.unlink(missing_ok=True)


def active_services(feed, day):
    value = day.strftime('%Y%m%d')
    weekday = ('monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday')[day.weekday()]
    active = set()
    for row in feed.rows('calendar.txt', optional=True):
        if gtfs_date(row['start_date']) <= day <= gtfs_date(row['end_date']) and row[weekday] == '1':
            active.add(row['service_id'])
    for row in feed.rows('calendar_dates.txt', optional=True):
        if row['date'] == value:
            if row['exception_type'] == '1':
                active.add(row['service_id'])
            elif row['exception_type'] == '2':
                active.discard(row['service_id'])
            else:
                raise GTFSFailure('calendar_dates.txt has an invalid exception_type')
    return active


def route_rows(feed, selector=None):
    rows = list(feed.rows('routes.txt'))
    if selector is None:
        return rows
    exact = [r for r in rows if r['route_id'] == selector]
    matches = exact or [r for r in rows if r.get('route_short_name') == selector]
    if not matches:
        raise GTFSFailure(f'Unknown route {selector!r}; use routes to find a route_id', 2)
    if len(matches) > 1:
        ids = ', '.join(r['route_id'] for r in matches)
        raise GTFSFailure(f'Ambiguous route short name {selector!r}; choose route_id: {ids}', 2)
    return matches


def mode(route_type):
    n = int(route_type)
    if n == 3 or 700 <= n <= 799 or 200 <= n <= 299 or n == 11 or 800 <= n <= 899:
        return 'bus'
    if n in (1, 2, 12) or 100 <= n <= 199 or 300 <= n <= 499:
        return 'rail'
    if n == 4 or 1000 <= n <= 1099 or 1200 <= n <= 1299:
        return 'ferry'
    if n == 0 or 900 <= n <= 999:
        return 'tram'
    if n in (5, 6, 7) or 1300 <= n <= 1499:
        return 'cable'
    return 'other'


def in_bbox(point, bbox):
    return bbox is None or (bbox[0] <= point[0] <= bbox[2] and bbox[1] <= point[1] <= bbox[3])


def distance(a, b):
    lon1, lat1, lon2, lat2 = map(math.radians, (*a, *b))
    q = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371008.8 * 2 * math.asin(math.sqrt(min(1, q)))


def bounded(rows, limit, order=None):
    """Keep at most limit records while counting all matching rows."""
    kept, total = [], 0
    for row in rows:
        total += 1
        if order is None:
            if len(kept) < limit:
                kept.append(row)
        else:
            item = (-order(row), -total, row)
            if len(kept) < limit:
                heapq.heappush(kept, item)
            elif item[:2] > kept[0][:2]:
                heapq.heapreplace(kept, item)
    if order is not None:
        kept = [v[2] for v in sorted(kept, key=lambda v: (-v[0], -v[1]))]
    return kept, total


def stops(feed, args):
    def matching():
        for row in feed.rows('stops.txt'):
            # Coordinate-less entrances/stations are legal; retain them in non-spatial JSON.
            if row['stop_lon'] and row['stop_lat']:
                point = coords(row['stop_lon'], row['stop_lat'])
                row['stop_lon'], row['stop_lat'] = point
                if not in_bbox(point, args.bbox):
                    continue
                if args.near:
                    metres = distance(args.near, point)
                    if metres > args.radius:
                        continue
                    row['distance_m'] = round(metres, 2)
            elif args.bbox or args.near or args.format == 'geojson':
                continue
            yield row
    records, total = bounded(matching(), args.limit, (lambda r: r['distance_m']) if args.near else None)
    out = feed.output(records, total)
    if args.format == 'geojson':
        out = feature_collection(out, [feature(r, 'Point', [r['stop_lon'], r['stop_lat']]) for r in out['results']])
    return out


def routes(feed, args):
    rows = ({**r, 'mode': mode(r['route_type'])} for r in route_rows(feed))
    records, total = bounded((r for r in rows if not args.type or r['mode'] == args.type), args.limit)
    return feed.output(records, total)


def trips(feed, args):
    route = route_rows(feed, args.route)[0]
    records, total = bounded((r for r in feed.rows('trips.txt') if r['route_id'] == route['route_id']), args.limit)
    return feed.output(records, total, route_id=route['route_id'])


def departures(feed, args):
    day = date.fromisoformat(args.date) if args.date else datetime.now(ZoneInfo('Pacific/Auckland')).date()
    threshold = seconds(args.time)
    all_stops = list(feed.rows('stops.txt'))
    matches = [s for s in all_stops if s['stop_id'] == args.stop]
    matches = matches or [s for s in all_stops if s.get('stop_code') == args.stop]
    if not matches:
        raise GTFSFailure(f'Unknown stop {args.stop!r}; use stops to find a stop_id', 2)
    if len(matches) > 1:
        raise GTFSFailure('Ambiguous stop code; supply an exact stop_id', 2)
    stop = matches[0]
    included = {stop['stop_id']}
    included.update(s['stop_id'] for s in all_stops if s.get('parent_station') == stop['stop_id'])
    services = active_services(feed, day)
    route_index = {r['route_id']: r for r in route_rows(feed)}
    trip_index = {r['trip_id']: {k: r.get(k, '') for k in
                  ('trip_id', 'route_id', 'service_id', 'trip_headsign', 'direction_id')}
                  for r in feed.rows('trips.txt') if r['service_id'] in services}
    frequency_ids = {r['trip_id'] for r in feed.rows('frequencies.txt', optional=True)}
    last_sequence = {}
    for row in feed.rows('stop_times.txt'):
        if row['trip_id'] not in trip_index:
            continue
        if row['trip_id'] in frequency_ids and row['stop_id'] in included:
            raise GTFSFailure('Frequency-based departures at this stop are unsupported', 7)
        sequence = int(row['stop_sequence'])
        last_sequence[row['trip_id']] = max(sequence, last_sequence.get(row['trip_id'], sequence))
    untimed = 0
    def matching():
        nonlocal untimed
        for row in feed.rows('stop_times.txt'):
            if row['stop_id'] not in included or row['trip_id'] not in trip_index:
                continue
            if row.get('pickup_type') == '1':
                continue  # No passenger boarding at this stop.
            if not row['departure_time']:
                untimed += 1
                continue  # No invented interpolation for intermediate stops.
            when = seconds(row['departure_time'])
            if when < threshold:
                continue
            trip = trip_index[row['trip_id']]
            route = route_index.get(trip['route_id'])
            if route is None:
                raise GTFSFailure('Trip refers to an unknown route_id')
            yield {**row, **trip, 'route_short_name': route.get('route_short_name', ''),
                   'route_type': route['route_type'], 'scheduled_seconds': when,
                   'service_date': day.isoformat(), 'timezone': 'Pacific/Auckland',
                   'scheduled': True, 'terminates': int(row['stop_sequence']) == last_sequence[row['trip_id']]}
    records, total = bounded(matching(), args.limit, lambda r: r['scheduled_seconds'])
    out = feed.output(records, total, service_date=day.isoformat(), time=args.time,
                      stop=stop, included_stop_ids=sorted(included),
                      active_service_count=len(services), untimed_stop_times=untimed)
    if feed.info:
        start = feed.info[0].get('feed_start_date')
        end = feed.info[0].get('feed_end_date')
        if (start and day < gtfs_date(start)) or (end and day > gtfs_date(end)):
            out['meta']['warnings'].append('Requested service date is outside the stated feed_info validity range.')
    if frequency_ids:
        out['meta']['warnings'].append('Feed has frequency-based trips elsewhere; no frequency expansion applied.')
    if untimed:
        out['meta']['warnings'].append(f'{untimed} stop_times have no departure_time; no interpolation applied.')
    return out


def intersects(points, bbox):
    if bbox is None or any(in_bbox(p, bbox) for p in points):
        return True
    # Liang-Barsky segment clipping tests; return full geometry when it intersects.
    for a, b in zip(points, points[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        lower, upper = 0.0, 1.0
        for p, q in zip((-dx, dx, -dy, dy), (a[0]-bbox[0], bbox[2]-a[0], a[1]-bbox[1], bbox[3]-a[1])):
            if p == 0:
                if q < 0:
                    break
            elif p < 0:
                lower = max(lower, q / p)
            else:
                upper = min(upper, q / p)
            if lower > upper:
                break
        else:
            return True
    return False


def feature(record, kind, coordinates):
    return {'type': 'Feature', 'properties': record,
            'geometry': {'type': kind, 'coordinates': coordinates}}


def feature_collection(out, features):
    return geojson_envelope(features, out['meta'])


def shapes(feed, args):
    route = route_rows(feed, args.route)[0]
    ids = {r['shape_id'] for r in feed.rows('trips.txt')
           if r['route_id'] == route['route_id'] and r.get('shape_id')}
    if not ids or 'shapes.txt' not in feed.z.namelist():
        raise GTFSFailure('This route has no published shapes', 7)
    # Route-only geometry is held; never build an index of all feed shapes.
    points = {key: [] for key in ids}
    for r in feed.rows('shapes.txt'):
        if r['shape_id'] in ids:
            point = coords(r['shape_pt_lon'], r['shape_pt_lat'])
            points[r['shape_id']].append((int(r['shape_pt_sequence']), point))
    features = []
    total = 0
    for key in sorted(ids):
        line = [list(p) for _, p in sorted(points[key])]
        if len(line) < 2:
            raise GTFSFailure(f'Shape {key!r} has fewer than two points')
        if not intersects(line, args.bbox):
            continue
        total += 1
        if len(features) < args.limit:
            features.append(feature({'shape_id': key, 'route_id': route['route_id']}, 'LineString', line))
    out = feed.output([], total, route_id=route['route_id'])
    out['meta'].update(returned=len(features), truncated=total > len(features))
    return feature_collection(out, features)


def feed_status(args):
    records = []
    for key in ([args.feed] if args.feed else FEEDS):
        meta = {'feed': key, 'name': FEEDS[key]['name'], **error_meta(key)}
        try:
            feed = get_feed(key, args.cache_dir, args.max_age, refresh=args.refresh)
            try:
                meta.update(feed.provenance(), status='available', cached=feed.cached,
                            zip_bytes=os.fstat(feed.z.fp.fileno()).st_size,
                            tables=feed.z.namelist(), warnings=feed.warnings())
            finally:
                feed.close()
        except (GTFSFailure, zipfile.BadZipFile, UnicodeError, csv.Error, ValueError, OSError, EOFError) as exc:
            code = exc.code if isinstance(exc, GTFSFailure) else 6
            message = str(exc) if isinstance(exc, GTFSFailure) else 'Invalid GTFS archive or cache'
            meta.update(status='blocked' if code == 4 else 'unavailable' if code == 5 else 'invalid',
                        error=error_envelope(code, message, {},
                              retry_after=exc.retry_after if isinstance(exc, GTFSFailure) else None)['error'])
        records.append(meta)
    failures = [r for r in records if r['status'] != 'available']
    if len(failures) == len(records):
        codes = [r['error']['code'] for r in failures]
        code = codes[0] if len(codes) == 1 else 4 if 4 in codes else 5 if all(c == 5 for c in codes) else 6
        message = '; '.join(f"{r['feed']} (code {r['error']['code']}): {r['error']['message']}" for r in failures)
        retry_after = next((r['error']['retry_after'] for r in failures if 'retry_after' in r['error']), None)
        raise GTFSFailure(message, code, retry_after)
    meta = {**provenance(REGISTRY_URL, REGISTRY_PUBLISHER), 'total': len(records),
            'returned': len(records), 'truncated': False,
            'warnings': [f"{r['feed']}: {r['status']} ({r['error']['message']})" for r in failures]}
    return result_envelope(records, meta)


class JSONArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        argv = getattr(self, 'input_argv', sys.argv[1:])
        machine = '--json' in argv or 'shapes' in argv or '--format=geojson' in argv or any(
            a == '--format' and i + 1 < len(argv) and argv[i + 1] == 'geojson' for i, a in enumerate(argv))
        if machine:
            key = next((a.split('=', 1)[1] for a in argv if a.startswith('--feed=')), None)
            if '--feed' in argv and argv.index('--feed') + 1 < len(argv):
                key = argv[argv.index('--feed') + 1]
            print(json.dumps(error_envelope(2, message, error_meta(key)), ensure_ascii=False))
            self.exit(2)
        super().error(message)


def parser(argv=None):
    p = JSONArgumentParser(description=__doc__)
    p.input_argv = list(argv) if argv is not None else sys.argv[1:]
    sub = p.add_subparsers(dest='command', required=True)
    for name, help_text in (
        ('feeds', 'list verified feed registry and live ZIP/feed_info status'),
        ('stops', 'list or spatially filter stops'), ('routes', 'list routes by transport type'),
        ('trips', 'list trips for a route'), ('departures', 'scheduled departures on a GTFS service date'),
        ('shapes', 'route shape LineStrings as GeoJSON')):
        s = sub.add_parser(name, help=help_text)
        s.input_argv = p.input_argv
        s.add_argument('--json', action='store_true', help='emit machine-readable JSON')
        s.add_argument('--feed', choices=FEEDS, required=name != 'feeds', help='registered feed identifier')
        s.add_argument('--cache-dir', type=Path, default=DEFAULT_CACHE, help='ZIP cache directory')
        s.add_argument('--max-age', type=nonnegative, default=86400, metavar='SECONDS', help='cache maximum age (default 86400 seconds)')
        s.add_argument('--refresh', action='store_true', help='download a fresh ZIP')
        if name != 'feeds':
            s.add_argument('--limit', type=limit_arg, default=100, help='maximum records or shapes (default 100)')
        if name in ('stops', 'shapes'):
            s.add_argument('--bbox', type=parse_bbox, help='minLon,minLat,maxLon,maxLat')
            s.add_argument('--format', choices=('json', 'geojson') if name == 'stops' else ('geojson',),
                           default='json' if name == 'stops' else 'geojson')
        if name == 'stops':
            s.add_argument('--near', type=parse_near, help='lon,lat in WGS84')
            s.add_argument('--radius', type=nonnegative, default=500, metavar='METRES')
        if name == 'routes':
            s.add_argument('--type', choices=('bus', 'rail', 'ferry', 'tram', 'cable', 'other'))
        if name in ('trips', 'shapes'):
            s.add_argument('--route', required=True, help='exact route_id or unambiguous route_short_name')
        if name == 'departures':
            s.add_argument('--stop', required=True, help='exact stop_id or unambiguous stop_code; stations include child stops')
            s.add_argument('--date', help='GTFS service date YYYY-MM-DD (default today in NZ)')
            s.add_argument('--time', default='00:00', help='inclusive minimum GTFS time HH:MM[:SS]; supports 24+ hours')
    return p


def human(out):
    if out.get('type') == 'FeatureCollection':
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return
    meta = out['meta']
    print(f"Returned {meta['returned']} of {meta['total']} records")
    for row in out['results']:
        if 'status' in row:
            print(f"{row['feed']}: {row['name']} — {row['status']}; {json.dumps(row.get('latest_data', {}))}")
        elif 'departure_time' in row:
            terminal = ' (terminal arrival)' if row['terminates'] else ''
            print(f"{row['departure_time']}  {row['route_short_name']}  {row['trip_headsign']}  stop={row['stop_id']}{terminal}")
        elif 'stop_name' in row:
            print(f"{row['stop_id']}  {row['stop_name']}  {row['stop_lon']},{row['stop_lat']}")
        elif 'route_type' in row:
            print(f"{row['route_id']}  {row.get('route_short_name', '')}  {row.get('route_long_name', '')}  {row['mode']}")
        else:
            print(f"{row['trip_id']}  {row['service_id']}  {row.get('trip_headsign', '')}")
    print('Source: ' + str(meta['source_url']))
    for warning in meta.get('warnings', []):
        print('Warning: ' + warning)


def main(argv=None):
    args = parser(argv).parse_args(argv)
    machine = args.json or getattr(args, 'format', None) == 'geojson'
    feed = None
    try:
        # Reject invalid dates/times before a network request.
        if args.command == 'departures':
            try:
                if args.date:
                    date.fromisoformat(args.date)
                seconds(args.time)
            except ValueError as exc:
                raise GTFSFailure('Invalid service date or time: ' + str(exc), 2) from exc
        if args.command == 'feeds':
            out = feed_status(args)
        else:
            feed = get_feed(args.feed, args.cache_dir, args.max_age, args.refresh)
            out = {'stops': stops, 'routes': routes, 'trips': trips,
                   'departures': departures, 'shapes': shapes}[args.command](feed, args)
        if machine:
            print(json.dumps(out, indent=2, ensure_ascii=False, allow_nan=False))
        else:
            human(out)
        return 0
    except (GTFSFailure, zipfile.BadZipFile, UnicodeError, csv.Error, ValueError, OSError, EOFError) as exc:
        if isinstance(exc, GTFSFailure):
            code, message = exc.code, str(exc)
        else:
            code, message = 6, 'Could not parse GTFS archive or access cache; check source tables and cache permissions'
        meta = error_meta(args.feed)
        error = error_envelope(code, message, meta,
                               retry_after=exc.retry_after if isinstance(exc, GTFSFailure) else None)
        if machine:
            print(json.dumps(error, ensure_ascii=False))
        else:
            print('Error: ' + message, file=sys.stderr)
        return code
    finally:
        if feed is not None:
            feed.close()


if __name__ == '__main__':
    raise SystemExit(main())
