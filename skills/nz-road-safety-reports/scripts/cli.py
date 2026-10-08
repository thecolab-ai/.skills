#!/usr/bin/env python3
"""Read-only, keyless road safety evidence with explicit source failures."""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import re
import sys
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlencode, urljoin, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'lib'))
import nzfetch  # noqa: E402
from provenance import (add_spatial_arguments, error_envelope, geojson_envelope,
                        parse_bbox, provenance, result_envelope)

AUCKLAND = (174.4, -37.2, 175.2, -36.4)
BIKE = 'https://bikemaps.org/'
CAMERAS = 'https://nzta.govt.nz/travelling-on-our-roads/safety-cameras/about-safety-cameras/fixed-safety-camera-locations'
RELEASE = 'https://www.nzta.govt.nz/about-us/our-data-and-official-information/official-information-act/proactive-releases'
POLICE = 'https://www.police.govt.nz/rss/alerts'
ZONES = 'https://raw.githubusercontent.com/PaulAtKeyboard/OpenCCTV/47788874df0dac6e56f0f5f3aba55ad54b0ae293/data-speed-cameras-auckland.csv'
NZTA = 'NZ Transport Agency Waka Kotahi'
SOURCES = {
    'bikemaps-nearmiss': (BIKE + 'nearmiss.json', 'BikeMaps.org', 'GeoJSON', 'Self-reported; sparse and biased; reuse licence unknown.'),
    'bikemaps-collision': (BIKE + 'collisions.json', 'BikeMaps.org', 'GeoJSON', 'Self-reported collisions; use nzta-crash-data-nz for CAS.'),
    'nzta-cameras': (CAMERAS, NZTA, 'HTML table', 'Access depends on the requesting host; parser uses published table columns.'),
    'nzta-infringements': (RELEASE, NZTA, 'XLSX release listing', 'Discovers the latest dated release; workbook schema unverified. Filtering is gated.'),
    'police-alerts': (POLICE, 'New Zealand Police', 'RSS 2.0', 'Recent national alerts only; no coordinates; cannot spatially filter.'),
    'at-camera-zones': (ZONES, 'Auckland Transport; PaulAtKeyboard/OpenCCTV mirror', 'CSV', 'Historical 2014–2018 camera zones; not current fixed camera locations; licence unknown.'),
}


class SourceError(Exception):
    def __init__(self, code, message, meta, retry_after=None):
        super().__init__(message)
        self.code, self.meta, self.retry_after = code, meta, retry_after


def fetch(url, publisher, *, as_json=False):
    meta = provenance(url, publisher)
    try:
        payload = (nzfetch.fetch_json if as_json else nzfetch.fetch_text)(url, timeout=10)
        meta['retrieved_at'] = provenance(url, publisher)['retrieved_at']
        return payload, meta
    except nzfetch.RateLimited as exc:
        raise SourceError(4, 'network error: rate limited', meta, exc.retry_after) from exc
    except nzfetch.Blocked as exc:
        raise SourceError(4, 'network error: public source blocked this request', meta) from exc
    except nzfetch.FetchError as exc:
        if isinstance(exc.__cause__, json.JSONDecodeError):
            raise SourceError(6, 'Source response is not valid JSON', meta) from exc
        # Avoid echoing helper exception text that can contain network configuration.
        raise SourceError(5, 'network error: public source unavailable', meta) from exc


def fail_schema(message, meta):
    raise SourceError(6, message, meta)


def valid_point(coords):
    if not isinstance(coords, (list, tuple)) or len(coords) < 2:
        return False
    return (all(isinstance(v, (int, float)) and math.isfinite(v) for v in coords[:2])
            and -180 <= coords[0] <= 180 and -90 <= coords[1] <= 90)


def feature(geometry, properties, meta):
    return {'type': 'Feature', 'geometry': geometry, 'properties': {**properties, **meta}}


def in_box(point, bbox):
    return bbox is None or (bbox[0] <= point[0] <= bbox[2] and bbox[1] <= point[1] <= bbox[3])


def parse_bike(payload, kind, meta, bbox):
    if not isinstance(payload, dict) or payload.get('type') != 'FeatureCollection' or not isinstance(payload.get('features'), list):
        fail_schema('BikeMaps response is not a GeoJSON FeatureCollection', meta)
    results = []
    # Deliberately exclude narratives, identifiers and demographic fields.
    fields = ('i_type', 'incident_with', 'date', 'report_date', 'p_type',
              'personal_involvement', 'witness_vehicle', 'injury', 'bicycle_type',
              'trip_purpose', 'road_conditions', 'sightlines', 'direction', 'turning')
    dates = []
    for f in payload['features']:
        if not isinstance(f, dict):
            fail_schema('BikeMaps feature is not an object', meta)
        g, p = f.get('geometry'), f.get('properties')
        if (not isinstance(g, dict) or g.get('type') != 'Point' or not valid_point(g.get('coordinates'))
                or not isinstance(p, dict) or not isinstance(p.get('date'), str)):
            fail_schema('BikeMaps report has invalid point geometry or event date', meta)
        if not in_box(g['coordinates'], bbox):
            continue
        dates.append(p['date'])
        results.append(feature(g, {'source': 'bikemaps', 'kind': kind,
                                 **{k: p[k] for k in fields if k in p}}, meta))
    if dates:
        meta['latest_data'] = max(dates)  # Latest event in this response, not a feed update time.
        for f in results:
            f['properties']['latest_data'] = meta['latest_data']
    return results


def incidents(kind, bbox):
    endpoint = SOURCES['bikemaps-' + kind][0] + '?' + urlencode({'bbox': ','.join(map(str, bbox))})
    payload, meta = fetch(endpoint, 'BikeMaps.org', as_json=True)
    return parse_bike(payload, kind, meta, bbox), meta


class Page(HTMLParser):
    """Extract text, table rows, region headings and public download links."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows, self.links, self.text = [], [], []
        self.region = ''
        self.heading = None
        self.row = None
        self.cell = None
        self.anchor = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'h3': self.heading = []
        if tag == 'tr': self.row = []
        if tag in ('td', 'th') and self.row is not None: self.cell = []
        if tag == 'a': self.anchor = [attrs.get('href', ''), []]

    def handle_data(self, data):
        self.text.append(data)
        if self.heading is not None: self.heading.append(data)
        if self.cell is not None: self.cell.append(data)
        if self.anchor is not None: self.anchor[1].append(data)

    def handle_endtag(self, tag):
        if tag == 'h3' and self.heading is not None:
            self.region = ' '.join(''.join(self.heading).split()); self.heading = None
        if tag in ('td', 'th') and self.cell is not None:
            self.row.append(' '.join(''.join(self.cell).split())); self.cell = None
        if tag == 'tr' and self.row is not None:
            self.rows.append((self.region, self.row)); self.row = None
        if tag == 'a' and self.anchor is not None:
            self.links.append((self.anchor[0], ' '.join(''.join(self.anchor[1]).split()))); self.anchor = None


def parse_cameras(html, meta, bbox=None):
    page = Page(); page.feed(html)
    headers = [r for _, r in page.rows if r[:3] == ['Suburb', 'Location', 'Camera type']]
    if not headers:
        fail_schema('NZTA camera table columns missing', meta)
    update = re.search(r'Last update:\s*(\d{1,2}\s+\w+\s+\d{4})', ' '.join(page.text))
    if update:
        try: meta['latest_data'] = datetime.strptime(update.group(1), '%d %B %Y').date().isoformat()
        except ValueError: fail_schema('NZTA camera update date invalid', meta)
    results = []
    for region, row in page.rows:
        if not row or row[0] in ('Suburb', 'Latitude', 'Longitude'): continue
        if len(row) != 5:
            fail_schema('NZTA camera row does not have five published columns', meta)
        try:
            point = [float(row[4].strip(' ,')), float(row[3].strip(' ,'))]
        except ValueError:
            fail_schema('NZTA camera coordinates are not numeric', meta)
        if not valid_point(point): fail_schema('NZTA camera coordinates are outside WGS84', meta)
        if in_box(point, bbox):
            results.append(feature({'type': 'Point', 'coordinates': point},
                                  {'source': 'nzta-cameras', 'region': region, 'suburb': row[0],
                                   'location': row[1], 'camera_type': row[2]}, meta))
    if not page.rows or not any(len(r) == 5 and r[0] != 'Suburb' for _, r in page.rows):
        fail_schema('NZTA camera table contains no data rows', meta)
    return results


def cameras(bbox):
    html, meta = fetch(CAMERAS, NZTA)
    return parse_cameras(html, meta, bbox), meta


def line_hits_box(points, bbox):
    if bbox is None: return True
    # Liang–Barsky segment clipping; detects intersections with neither end inside.
    a, b = points
    dx, dy = b[0] - a[0], b[1] - a[1]
    lo, hi = 0.0, 1.0
    for p, q in ((-dx, a[0]-bbox[0]), (dx, bbox[2]-a[0]), (-dy, a[1]-bbox[1]), (dy, bbox[3]-a[1])):
        if p == 0:
            if q < 0: return False
        elif p < 0: lo = max(lo, q/p)
        else: hi = min(hi, q/p)
        if lo > hi: return False
    return True


def parse_zones(text, meta, bbox=None):
    reader = csv.DictReader(io.StringIO(text))
    expected = ['Street', 'Locality (* indicates existing sites)', 'Start of camera zone', 'End of camera zone', 'Go-live Date']
    if reader.fieldnames != expected: fail_schema('Historical camera-zone CSV columns changed', meta)
    records = []
    latest = None
    for row in reader:
        try:
            points = [[float(v.strip()) for v in row[k].split(',')][::-1]
                      for k in expected[2:4]]
            from datetime import datetime
            go_live = datetime.strptime(row['Go-live Date'], '%B %Y').strftime('%Y-%m')
        except (ValueError, TypeError, KeyError): fail_schema('Invalid historical camera-zone row', meta)
        if not all(valid_point(p) for p in points): fail_schema('Invalid historical zone coordinates', meta)
        latest = max(latest or go_live, go_live)
        if line_hits_box(points, bbox):
            records.append(feature({'type': 'LineString', 'coordinates': points},
                                   {'source': 'at-camera-zones', 'street': row['Street'],
                                    'locality': row[expected[1]], 'go_live': go_live, 'historical': True}, meta))
    if not latest: fail_schema('Historical camera-zone CSV has no rows', meta)
    meta['latest_data'] = latest
    for f in records: f['properties']['latest_data'] = latest
    return records


def zones(bbox):
    text, meta = fetch(ZONES, SOURCES['at-camera-zones'][1])
    return parse_zones(text, meta, bbox), meta


def parse_alerts(text, meta):
    try: root = ET.fromstring(text)
    except ET.ParseError: fail_schema('Police RSS is not valid XML', meta)
    if root.tag != 'rss' or root.find('channel') is None: fail_schema('Police response is not RSS', meta)
    records = []
    for item in root.findall('./channel/item'):
        title, link, published = (item.findtext(k) for k in ('title', 'link', 'pubDate'))
        if not title or not link or not published: fail_schema('Police alert is missing RSS fields', meta)
        from email.utils import parsedate_to_datetime
        try:
            from datetime import timezone
            observed = parsedate_to_datetime(published)
            if observed.tzinfo is None: raise ValueError('RSS date needs timezone')
            published_utc = observed.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')
        except (ValueError, TypeError, OverflowError): fail_schema('Police RSS date invalid', meta)
        page = Page(); page.feed(item.findtext('description') or '')
        record = {'source': 'police-alerts', 'title': title, 'url': link, 'published_at': published_utc,
                  'description': ' '.join(' '.join(page.text).split()), 'spatial_status': 'unlocated', **meta}
        records.append(record)
    if records:
        meta['latest_data'] = max(r['published_at'] for r in records)
        for r in records: r['latest_data'] = meta['latest_data']
    return records


def alerts():
    text, meta = fetch(POLICE, 'New Zealand Police')
    return parse_alerts(text, meta), meta


def infringement_link(html, meta):
    page = Page(); page.feed(html)
    matches = []
    for href, label in page.links:
        match = re.search(r'\bsafety camera infringement data to\s+(\d{1,2}\s+[A-Za-z]+\s+\d{4})\b', label, re.I)
        if not match or not urlparse(href).path.lower().endswith('.xlsx'): continue
        try: released_to = datetime.strptime(match.group(1), '%d %B %Y').date()
        except ValueError: fail_schema('Infringement release date invalid', meta)
        matches.append((released_to, urljoin(RELEASE, href)))
    if not matches: fail_schema('Dated infringement workbook link missing', meta)
    latest = max(released_to for released_to, _ in matches)
    urls = {url for released_to, url in matches if released_to == latest}
    if len(urls) != 1: fail_schema('Latest infringement workbook link ambiguous', meta)
    url = urls.pop()
    parsed = urlparse(url)
    if parsed.scheme != 'https' or parsed.hostname not in ('nzta.govt.nz', 'www.nzta.govt.nz') or parsed.username or parsed.password:
        fail_schema('Infringement download is outside the declared NZTA hosts', meta)
    meta['latest_data'] = latest.isoformat()
    return url


def infringements():
    html, meta = fetch(RELEASE, NZTA)
    url = infringement_link(html, meta)
    # No invented workbook schema or counts: enable only after a real workbook inspection.
    raise SourceError(7, 'Infringement workbook schema has not been verified; camera/date filtering unavailable. Official download: ' + url, meta)


def near(value):
    try: point = tuple(float(v) for v in value.split(','))
    except ValueError: point = ()
    if len(point) != 2 or not valid_point(point) or abs(point[1]) > 85:
        raise argparse.ArgumentTypeError('--near must be finite lon,lat; latitude must be within ±85 degrees')
    return point


def radius(value):
    try: val = float(value)
    except ValueError: val = float('nan')
    if not math.isfinite(val) or not 0 < val <= 20000:
        raise argparse.ArgumentTypeError('--radius must be greater than 0 and at most 20000 metres')
    return val


def iso_date(value):
    try: return date.fromisoformat(value)
    except ValueError as exc: raise argparse.ArgumentTypeError('date must be YYYY-MM-DD') from exc


def distance(geometry, centre):
    """Local tangent-plane distance to points or straight zone segments (<=20 km)."""
    def xy(p):
        return ((p[0]-centre[0])*111195*math.cos(math.radians(centre[1])), (p[1]-centre[1])*111195)
    if geometry['type'] == 'Point': return math.hypot(*xy(geometry['coordinates']))
    a, b = map(xy, geometry['coordinates']); dx, dy = b[0]-a[0], b[1]-a[1]
    fraction = max(0, min(1, -(a[0]*dx+a[1]*dy)/(dx*dx+dy*dy))) if dx or dy else 0
    return math.hypot(a[0]+fraction*dx, a[1]+fraction*dy)


def corridor(centre, metres):
    dy = metres/111195; dx = dy/math.cos(math.radians(centre[1]))
    try:
        bbox = parse_bbox(','.join(map(str, (centre[0]-dx, centre[1]-dy, centre[0]+dx, centre[1]+dy))))
    except argparse.ArgumentTypeError as exc:
        raise SourceError(2, 'Corridor crosses the antimeridian or WGS84 bounds; choose a smaller radius', provenance(BIKE, 'Multiple road safety publishers')) from exc
    jobs = [('bikemaps-nearmiss', lambda: incidents('nearmiss', bbox)),
            ('bikemaps-collision', lambda: incidents('collision', bbox)),
            ('nzta-cameras', lambda: cameras(bbox)), ('at-camera-zones', lambda: zones(bbox)),
            ('nzta-infringements', infringements)]
    records, statuses = [], []
    def run(job):
        name, fn = job
        try: return name, fn(), None
        except SourceError as exc: return name, None, exc
    with ThreadPoolExecutor(max_workers=5) as pool:
        for name, response, error in pool.map(run, jobs):
            if error:
                if error.code == 6 and name != 'nzta-infringements': raise error
                status = {**error.meta, 'source': name, 'status': 'unavailable',
                          'error': error_envelope(error.code, str(error), error.meta, retry_after=error.retry_after)['error']}
            else:
                features, meta = response
                count = 0
                for f in features:
                    d = distance(f['geometry'], centre)
                    if d <= metres:
                        f['properties']['distance_m'] = round(d, 1); records.append(f); count += 1
                status = {**meta, 'source': name, 'status': 'available', 'count': count}
            statuses.append(status)
    if not any(s['status'] == 'available' for s in statuses):
        raise SourceError(5, 'network error: no spatial corridor source available', provenance(BIKE, 'Multiple road safety publishers'))
    statuses.append({**provenance(POLICE, 'New Zealand Police'), 'source': 'police-alerts',
                     'status': 'not_spatial', 'reason': 'RSS has no coordinates; use alerts for national context.'})
    return records, statuses


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise SourceError(2, message, provenance(BIKE, 'Multiple road safety publishers'))


def build_parser():
    parser = Parser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('sources', 'incidents', 'cameras', 'infringements', 'corridor', 'alerts', 'camera-zones'):
        p = commands.add_parser(name)
        p.add_argument('--json', action='store_true', help='return machine-readable output with provenance')
        if name in ('incidents', 'cameras', 'camera-zones', 'corridor'):
            if name == 'corridor': p.add_argument('--format', choices=('json', 'geojson'), default='json')
            else: add_spatial_arguments(p)
        if name == 'incidents':
            p.add_argument('--source', choices=('bikemaps',), default='bikemaps')
            p.add_argument('--kind', choices=('nearmiss', 'collision'), default='nearmiss')
        if name == 'infringements':
            p.add_argument('--camera', help='camera filter (gated until workbook schema is verified)')
            p.add_argument('--from', dest='date_from', type=iso_date)
            p.add_argument('--to', dest='date_to', type=iso_date)
        if name == 'corridor':
            p.add_argument('--near', type=near, required=True, metavar='lon,lat')
            p.add_argument('--radius', type=radius, default=500, metavar='m')
    return parser


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    machine = '--json' in argv or any(v == 'geojson' or v == '--format=geojson' for v in argv)
    try:
        args = build_parser().parse_args(argv)
        extras = {}
        if args.command == 'sources':
            meta = provenance(BIKE, 'Multiple road safety publishers')
            records = [{'id': k, 'format': v[2], 'caveat': v[3], **provenance(v[0], v[1])} for k, v in SOURCES.items()]
            records[3]['status'] = 'gated'
        elif args.command == 'incidents': records, meta = incidents(args.kind, args.bbox or AUCKLAND)
        elif args.command == 'cameras': records, meta = cameras(args.bbox)
        elif args.command == 'camera-zones': records, meta = zones(args.bbox)
        elif args.command == 'alerts': records, meta = alerts()
        elif args.command == 'infringements':
            if args.date_from and args.date_to and args.date_from > args.date_to:
                raise SourceError(2, '--from must be on or before --to', provenance(RELEASE, NZTA))
            records, meta = infringements()
        else:
            records, statuses = corridor(args.near, args.radius)
            meta = provenance(BIKE, 'Multiple road safety publishers')
            extras = {'source_status': statuses, 'complete': False,
                      'warnings': ['Partial spatial evidence: Police alerts lack coordinates; infringement schema unverified; consult source_status.']}
        spatial = getattr(args, 'format', 'json') == 'geojson'
        result = geojson_envelope(records, meta) if spatial else result_envelope(records, meta)
        result.update(extras)
        if machine: print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        else:
            print(f'{len(records)} records from {meta["publisher"]}')
            for r in records: print(json.dumps(r.get('properties', r), ensure_ascii=False))
            for warning in extras.get('warnings', []): print('Warning: ' + warning)
        return 0
    except SourceError as exc:
        if machine: print(json.dumps(error_envelope(exc.code, str(exc), exc.meta, retry_after=exc.retry_after)))
        else: print('Error: ' + str(exc), file=sys.stderr)
        return exc.code
    except (ValueError, TypeError, KeyError) as exc:
        meta = provenance(BIKE, 'Multiple road safety publishers')
        message = 'Source schema or parser failure: ' + type(exc).__name__
        if machine: print(json.dumps(error_envelope(6, message, meta)))
        else: print('Error: ' + message, file=sys.stderr)
        return 6


if __name__ == '__main__':
    raise SystemExit(main())
