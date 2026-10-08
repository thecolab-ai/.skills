#!/usr/bin/env python3
"""Keyless NZ count downloads and ArcGIS queries; Python standard library only."""
from __future__ import annotations

import argparse
import calendar
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
import hashlib
from html.parser import HTMLParser
import io
import json
import math
from pathlib import Path
import posixpath
import re
import sys
import time
from urllib.parse import unquote, urlencode, urljoin, urlparse
import xml.etree.ElementTree as ET
import zipfile
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'lib'))
import nzfetch  # noqa: E402

AT = 'https://services2.arcgis.com/JkPEgZJGxhSjYOo0/arcgis/rest/services/TrafficService/FeatureServer/0'
TMS = 'https://services.arcgis.com/CXBb7LAjgIIdcsPt/arcgis/rest/services/TMS_Telemetry_Sites/FeatureServer/0'
TMS_SITES = 'https://services.arcgis.com/CXBb7LAjgIIdcsPt/arcgis/rest/services/Assets_SHTrafficMonitoringSites/FeatureServer/0'
TRAFFIC = 'https://at.govt.nz/media/afhnimq4/at-web-traffic-count-july-2012-to-june-2026.xlsx'
CYCLE_PAGE = 'https://at.govt.nz/cycling-walking/research-monitoring/monthly-cycle-monitoring/'
CYCLE = 'https://at.govt.nz/media/zj0lgcmg/at-daily-cycle-count-data-july-2026.xlsx'
HOT_PAGE = 'https://www.hotcity.co.nz/city-centre/results-and-statistics/pedestrian-counts'
HOT = 'https://www.hotcity.co.nz/sites/20180201.prod.hotcity.co.nz/files/2026-10/All%20pedestrian%20data%20day%20by%20hour%202026%20-%20September.xlsx'
ALLOWED = {'at.govt.nz', 'www.hotcity.co.nz', 'services.arcgis.com', 'services2.arcgis.com'}
SOURCES = {
    'at-traffic': dict(url=TRAFFIC, publisher='Auckland Transport', licence='AT terms: individual use; republication requires AT approval', latest_data='2026-06-30', spatial=False, granularity='survey ADT', catalogue_id='C0032'),
    'at-adt': dict(url=AT, publisher='Auckland Transport', licence='CC BY 4.0', latest_data='2026', spatial=True, granularity='survey ADT', catalogue_id='C0002'),
    'at-cycle-daily': dict(url=CYCLE, publisher='Auckland Transport', licence='CC BY 4.0', latest_data='2026-07-31', spatial=False, granularity='daily', catalogue_id='S0207'),
    'at-cycle-monthly': dict(url=CYCLE, publisher='Auckland Transport', licence='CC BY 4.0', latest_data='2026-07-31', spatial=False, granularity='monthly sum of published daily observations', catalogue_id='S0182'),
    'nzta-tms': dict(url=TMS, publisher='NZ Transport Agency Waka Kotahi', licence='CC BY 4.0', latest_data='2026', spatial=True, granularity='daily by lane/direction/vehicle class', catalogue_id='C0018'),
    'hotcity': dict(url=HOT, publisher='Heart of the City', licence=None, latest_data='2026-09-30', spatial=False, granularity='hourly camera series', catalogue_id='C0033'),
}
NS = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
NZ = ZoneInfo('Pacific/Auckland')


class SkillError(Exception):
    def __init__(self, message, code=6, retry_after=None):
        super().__init__(message)
        self.code, self.retry_after = code, retry_after


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')


def positive(raw):
    value = int(raw)
    if value <= 0:
        raise argparse.ArgumentTypeError('must be greater than zero')
    return value


def nonnegative(raw):
    value = float(raw)
    if not math.isfinite(value) or value < 0:
        raise argparse.ArgumentTypeError('must be a finite non-negative number')
    return value


def iso_date(raw):
    try:
        return date.fromisoformat(raw).isoformat()
    except ValueError as exc:
        raise argparse.ArgumentTypeError('use an ISO date: YYYY-MM-DD') from exc


def coordinates(raw, bbox=False):
    try:
        vals = tuple(float(v) for v in raw.split(','))
        if len(vals) != (4 if bbox else 2) or not all(math.isfinite(v) for v in vals):
            raise ValueError()
        pairs = [vals[:2], vals[2:]] if bbox else [vals]
        if any(not (-180 <= p[0] <= 180 and -90 <= p[1] <= 90) for p in pairs):
            raise ValueError()
        if bbox and (vals[0] > vals[2] or vals[1] > vals[3]):
            raise ValueError()
        return vals
    except ValueError as exc:
        raise argparse.ArgumentTypeError('use minLon,minLat,maxLon,maxLat' if bbox else 'use lon,lat within WGS84 bounds') from exc


def provenance(source, url=None, retrieved_at=None, latest=None):
    s = SOURCES[source]
    return dict(source_url=url or s['url'], publisher=s['publisher'], licence=s['licence'],
                retrieved_at=retrieved_at or utc_now(), latest_data=latest or s['latest_data'])


def fetch(url, args, binary=False):
    if urlparse(url).hostname not in ALLOWED:
        raise SkillError('source host is outside the declared allowlist', 7)
    root = args.cache_dir
    key = hashlib.sha256(url.encode()).hexdigest()
    path, meta = root / (key + '.bin'), root / (key + '.json')
    if args.max_age > 0 and path.is_file() and meta.is_file():
        try:
            info = json.loads(meta.read_text())
            age = time.time() - info['fetched_epoch']
            if 0 <= age <= args.max_age:
                return path.read_bytes(), info['retrieved_at']
        except (OSError, ValueError, KeyError, TypeError):
            pass
    try:
        body, _ct, _final = nzfetch.fetch_bytes(url, timeout=10, expect_json=not binary,
                                               max_bytes=32 * 1024 * 1024)
    except nzfetch.RateLimited as exc:
        raise SkillError('network error: rate_limited', 4, exc.retry_after) from exc
    except nzfetch.Blocked as exc:
        raise SkillError(f'network error: blocked: {exc}', 4) from exc
    except nzfetch.FetchError as exc:
        raise SkillError(f'network error: {exc}', 5) from exc
    stamp = utc_now()
    if args.max_age > 0:
        root.mkdir(parents=True, exist_ok=True)
        # Expired entries are pruned; URL-keyed cache retains original retrieval time.
        for old in root.glob('*.bin'):
            if time.time() - old.stat().st_mtime > args.max_age:
                old.unlink(missing_ok=True)
                old.with_suffix('.json').unlink(missing_ok=True)
        tmp = path.with_suffix('.tmp')
        tmp.write_bytes(body)
        tmp.replace(path)
        meta.write_text(json.dumps(dict(fetched_epoch=time.time(), retrieved_at=stamp)))
    return body, stamp


def arc_query(base, args, **params):
    url = base + '/query?' + urlencode(dict(f='json', **params))
    body, stamp = fetch(url, args)
    data = json.loads(body)
    if 'error' in data:
        raise SkillError(f"ArcGIS query failed: {data['error'].get('message', 'unknown error')}")
    if 'features' not in data:
        raise SkillError('ArcGIS response has no features array')
    return data, url, stamp


def arc_rows(base, args, where='1=1', bbox=None):
    rows, warnings = [], []
    params = dict(where=where, outFields='*', returnGeometry='true', outSR=4326,
                  orderByFields='OBJECTID', resultRecordCount=1000)
    if bbox:
        params.update(geometry=','.join(map(str, bbox)), geometryType='esriGeometryEnvelope',
                      inSR=4326, spatialRel='esriSpatialRelIntersects')
    for offset in range(0, args.max_records, 1000):
        params.update(resultOffset=offset, resultRecordCount=min(1000, args.max_records-offset))
        data, url, stamp = arc_query(base, args, **params)
        for feature in data['features']:
            if 'attributes' not in feature:
                raise SkillError('ArcGIS feature has no attributes')
            rows.append((feature, url, stamp))
        if not data.get('exceededTransferLimit'):
            break
        if not data['features']:
            raise SkillError('ArcGIS pagination stopped before completion')
    else:
        warnings.append(f'Result capped at {args.max_records} source records; narrow the date range or bbox, or increase --max-records.')
    return rows, warnings


def numeric(value):
    if value in (None, ''):
        return None
    try:
        number = float(value)
    except (ValueError, TypeError) as exc:
        raise SkillError(f'Invalid count value: {value!r}') from exc
    if not math.isfinite(number):
        raise SkillError('Non-finite count value')
    return int(number) if number.is_integer() else number


def excel_date(value, epoch):
    if value in (None, ''):
        return None
    try:
        return (epoch + timedelta(days=float(value))).date().isoformat()
    except ValueError:
        for fmt in ('%d/%m/%Y', '%Y-%m-%d', '%d-%b-%Y', '%d/%m/%y'):
            try:
                return datetime.strptime(str(value), fmt).date().isoformat()
            except ValueError:
                pass
        raise SkillError(f'Unrecognised spreadsheet date: {value!r}')


def sheets(body):
    """Read sparse XLSX cells, rich shared strings and inline strings without openpyxl."""
    with zipfile.ZipFile(io.BytesIO(body)) as z:
        if sum(i.file_size for i in z.infolist()) > 256 * 1024 * 1024:
            raise SkillError('Workbook expanded size exceeds 256 MiB')
        shared = []
        if 'xl/sharedStrings.xml' in z.namelist():
            shared = [''.join(n.itertext()) for n in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('s:si', NS)]
        book = ET.fromstring(z.read('xl/workbook.xml'))
        props = book.find('s:workbookPr', NS)
        epoch = datetime(1904, 1, 1) if props is not None and props.get('date1904') in ('1', 'true') else datetime(1899, 12, 30)
        rels = {r.get('Id'): r.get('Target') for r in ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))}
        for sheet in book.findall('s:sheets/s:sheet', NS):
            target = rels[sheet.get('{' + REL + '}id')]
            path = target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/' + target)
            rows = []
            with z.open(path) as stream:
                for _, row in ET.iterparse(stream, events=('end',)):
                    if row.tag != '{' + NS['s'] + '}row':
                        continue
                    cells = {}
                    for c in row.findall('s:c', NS):
                        col = re.sub(r'\d', '', c.get('r', ''))
                        v = c.find('s:v', NS)
                        value = v.text if v is not None else ''
                        if c.get('t') == 's':
                            value = shared[int(value)]
                        elif c.get('t') == 'inlineStr':
                            value = ''.join(c.find('s:is', NS).itertext())
                        cells[col] = value
                    rows.append(cells)
                    row.clear()
            yield sheet.get('name'), rows, epoch


def site_hash(values):
    return hashlib.sha256(json.dumps(values, ensure_ascii=False).encode()).hexdigest()[:16]


def parse_traffic(body):
    records = []
    for name, rows, epoch in sheets(body):
        if not name.startswith('July 2012'):
            continue
        header = next((r for r in rows if r.get('G') == 'Count Start Date' and r.get('B') == 'Road Name'), None)
        if header is None:
            raise SkillError('AT traffic workbook header changed')
        for r in rows:
            if not r.get('B') or not re.fullmatch(r'\d+(?:\.\d+)?', r.get('G', '')):
                continue
            labels = [r.get(k, '').strip() for k in ('A', 'B', 'C', 'D', 'E', 'F')]
            records.append(dict(site_id=site_hash(labels), name=labels[1], area=labels[0],
                                location=labels[4], direction=labels[5], date=excel_date(r['G'], epoch),
                                adt_5_day=numeric(r.get('H')), adt_7_day=numeric(r.get('I')),
                                raw={v: r.get(k) for k, v in header.items() if v}))
    if not records:
        raise SkillError('No AT traffic survey rows parsed')
    return records


def parse_active(body, hotcity=False):
    records = []
    for _name, rows, epoch in sheets(body):
        marker = 'Date' if hotcity else 'Time'
        header_pos = next((i for i, r in enumerate(rows) if r.get('A') == marker), None)
        if header_pos is None:
            continue
        header = rows[header_pos]
        sites = {k: v.strip() for k, v in header.items() if v and k not in (('A', 'B') if hotcity else ('A',))}
        for r in rows[header_pos+1:]:
            if not r.get('A') or not re.fullmatch(r'\d+(?:\.\d+)?', r['A']):
                continue
            day = excel_date(r['A'], epoch)
            for col, name in sites.items():
                records.append(dict(site_id=name, name=name, date=day,
                                    interval=r.get('B') if hotcity else None, count=numeric(r.get(col)),
                                    granularity='hourly' if hotcity else 'daily'))
    if not records:
        raise SkillError('Active-mode workbook header changed or no observations parsed')
    return records


class DownloadLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            href = dict(attrs).get('href', '')
            if unquote(href).lower().endswith('.xlsx'):
                self.links.append(href)


def workbook_urls(args):
    source = args.source
    if source == 'at-traffic':
        return [TRAFFIC]
    if not args.date_from and not args.date_to:
        return [HOT if source == 'hotcity' else CYCLE]
    page = HOT_PAGE if source == 'hotcity' else CYCLE_PAGE
    body, _ = fetch(page, args, binary=True)
    parser = DownloadLinks()
    parser.feed(body.decode('utf-8'))
    start = args.date_from or ('2012-01-01' if source == 'hotcity' else '2026-01-01')
    end = args.date_to or SOURCES[source]['latest_data']
    urls = []
    months = {name.lower(): i for i, name in enumerate(calendar.month_name) if name}
    for link in parser.links:
        text = unquote(link).lower()
        url = urljoin(page, link)
        if source == 'hotcity':
            # Match the data year at the end of the filename, not its upload directory.
            years = re.findall(r'\b(?:19|20)\d{2}\b', text.rsplit('/', 1)[-1])
            if 'pedestrian' in text and years and start[:4] <= years[-1] <= end[:4]:
                urls.append(url)
        elif 'daily' in text and 'cycle' in text:
            year = re.search(r'20\d{2}', text.rsplit('/', 1)[-1])
            month = next((i for name, i in months.items() if name in text), None)
            if year and month:
                first = f'{year.group()}-{month:02d}-01'
                last = f'{year.group()}-{month:02d}-{calendar.monthrange(int(year.group()), month)[1]:02d}'
                if first <= end and last >= start:
                    urls.append(url)
    urls = list(dict.fromkeys(urls))
    if not urls:
        raise SkillError('No supported XLSX download found for the requested period; see source notes for archive limits', 7)
    if len(urls) > 24:
        raise SkillError('Request at most 24 workbooks at a time by narrowing --from/--to', 7)
    return urls


def workbook_records(args):
    records = []
    urls = workbook_urls(args)
    for url in urls:
        body, stamp = fetch(url, args, binary=True)
        parsed = parse_traffic(body) if args.source == 'at-traffic' else parse_active(body, args.source == 'hotcity')
        observed = [r['date'] for r in parsed if (r.get('count') is not None if args.source != 'at-traffic' else r.get('adt_5_day') is not None or r.get('adt_7_day') is not None)]
        if not observed:
            raise SkillError('Workbook contains no numeric count observations')
        latest = max(observed)
        parsed = [r for r in parsed if r['date'] <= latest]
        prov = provenance(args.source, url, stamp, latest)
        for row in parsed:
            row.update(prov)
        records.extend(parsed)
    return records


def local_day(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).astimezone(NZ).date().isoformat() if ms is not None else None


def at_site_id(a):
    return f"{a['carr_way_no']}:{a['location']}"


def arc_normalise(feature, source, url, stamp, sites=False):
    a, geom = feature['attributes'], feature.get('geometry')
    if source == 'at-adt':
        required = {'carr_way_no', 'location', 'road_name', 'count_date', 'adt'}
        if not required <= a.keys():
            raise SkillError('AT ArcGIS fields changed')
        r = dict(site_id=at_site_id(a), name=a['road_name'], date=local_day(a['count_date']), adt=a['adt'], raw=a)
    elif sites:
        if not {'siteref', 'description'} <= a.keys():
            raise SkillError('NZTA site inventory fields changed')
        r = dict(site_id=a['siteref'], name=a['description'], region=a.get('region'), raw=a)
    else:
        if not {'SiteRef', 'startDate', 'trafficCount', 'classWeight', 'laneNumber', 'flowDirection'} <= a.keys():
            raise SkillError('NZTA daily-count fields changed')
        r = dict(site_id=a['SiteRef'], site_alias=a.get('siteID'), name=a.get('siteDescription'),
                 date=local_day(a['startDate']), start_time_utc=datetime.fromtimestamp(a['startDate']/1000, timezone.utc).isoformat().replace('+00:00', 'Z'),
                 count=a['trafficCount'], vehicle_class=a['classWeight'],
                 lane=a['laneNumber'], direction=a['flowDirection'], raw=a)
    if geom and geom.get('x') is not None and geom.get('y') is not None:
        x, y = geom['x'], geom['y']
        if -180 <= x <= 180 and -90 <= y <= 90:
            r.update(longitude=x, latitude=y)
    r.update(provenance(source, url, stamp, '2025' if source == 'nzta-tms' and sites else r.get('date')))
    return r


def get_sites(args, bbox=None):
    if args.source in ('at-adt', 'nzta-tms'):
        base = TMS_SITES if args.source == 'nzta-tms' else AT
        where = "latest='Yes'" if args.source == 'at-adt' else '1=1'
        if args.source == 'nzta-tms' and (args.date_from or args.date_to):
            raise SkillError('NZTA site inventory has no survey dates; apply --from/--to to counts', 7)
        if args.source == 'at-adt':
            if args.date_from:
                where += f" AND count_date>=DATE '{args.date_from} 00:00:00'"
            if args.date_to:
                end = (date.fromisoformat(args.date_to)+timedelta(days=1)).isoformat()
                where += f" AND count_date<DATE '{end} 00:00:00'"
        raw, warnings = arc_rows(base, args, where, bbox)
        rows = [arc_normalise(f, args.source, u, t, True) for f, u, t in raw]
    else:
        if bbox:
            raise SkillError('This workbook has no coordinates; --bbox is available for at-adt and nzta-tms', 7)
        rows, warnings = workbook_records(args), []
        rows = [r for r in rows if (not args.date_from or r['date'] >= args.date_from)
                and (not args.date_to or r['date'] <= args.date_to)]
    unique = {}
    for row in rows:
        key = row['site_id']
        if key not in unique or (row.get('date') or '') > (unique[key].get('date') or ''):
            unique[key] = {k: v for k, v in row.items() if k not in ('count', 'interval', 'granularity', 'adt_5_day', 'adt_7_day')}
    return list(unique.values()), warnings


def get_counts(args):
    if args.source not in ('at-adt', 'nzta-tms'):
        rows = workbook_records(args)
        known = {r['site_id'] for r in rows}
        if args.site not in known:
            raise SkillError('Unknown site in selected workbooks; use sites --source with the same date range', 2)
        rows = [r for r in rows if r['site_id'] == args.site]
        warnings = []
        if args.source == 'at-cycle-monthly':
            groups = defaultdict(list)
            for row in rows:
                groups[(row['date'][:7], row['source_url'])].append(row)
            monthly = []
            for (month, _url), days in groups.items():
                values = [r['count'] for r in days if r['count'] is not None]
                monthly.append({**days[0], 'date': month + '-01', 'period_end': max(r['date'] for r in days),
                                'count': sum(values) if values else None, 'observed_days': len(values),
                                'published_days': len(days),
                                'missing_days': calendar.monthrange(int(month[:4]), int(month[5:]))[1]-len(values),
                                'granularity': 'monthly'})
            rows = monthly
            warnings.append('Monthly totals sum published daily observations; missing days are not zero-filled.')
        rows = [r for r in rows if (not args.date_from or (r.get('period_end') or r['date']) >= args.date_from)
                and (not args.date_to or r['date'] <= args.date_to)]
        return rows, warnings
    if args.source == 'at-adt':
        if not re.fullmatch(r'\d+:\d+', args.site):
            raise SkillError('AT ADT site must be carriageway:location from sites, e.g. 23788:522', 2)
        carriageway, location = args.site.split(':')
        where = f'carr_way_no={int(carriageway)} AND location={int(location)}'
        field = 'count_date'
        base = AT
    else:
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,40}', args.site):
            raise SkillError('NZTA site must be a SiteRef from sites, preserving leading zeros', 2)
        where = f"SiteRef='{args.site}'"
        field, base = 'startDate', TMS
    # TMS timestamps represent NZ local midnight. AT dates are stored as UTC dates.
    if args.source == 'nzta-tms':
        start = args.date_from or (date.today()-timedelta(days=30)).isoformat()
        end = args.date_to or date.today().isoformat()
        def utc_literal(day):
            return datetime.combine(date.fromisoformat(day), datetime.min.time(), NZ).astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        where += f" AND {field}>=TIMESTAMP '{utc_literal(start)}' AND {field}<TIMESTAMP '{utc_literal((date.fromisoformat(end)+timedelta(days=1)).isoformat())}'"
    else:
        if args.date_from:
            where += f" AND {field}>=DATE '{args.date_from} 00:00:00'"
        if args.date_to:
            end = (date.fromisoformat(args.date_to)+timedelta(days=1)).isoformat()
            where += f" AND {field}<DATE '{end} 00:00:00'"
    raw, warnings = arc_rows(base, args, where)
    rows = [arc_normalise(f, args.source, u, t) for f, u, t in raw]
    rows.sort(key=lambda r: (r.get('date') or '', str(r.get('lane') or ''), str(r.get('vehicle_class') or '')))
    if args.source == 'nzta-tms':
        groups = defaultdict(list)
        for row in rows:
            groups[(row['date'], row['lane'], row['direction'], row['vehicle_class'])].append(row)
        duplicates = [group for group in groups.values() if len(group) > 1]
        if duplicates:
            warnings.append('Repeated local-date/lane/direction/class keys occur in the source; raw rows and UTC timestamps are preserved. Review before summing.')
            for group in duplicates:
                for row in group:
                    row['duplicate_daily_key'] = True
    return rows, warnings


def distance(lon1, lat1, lon2, lat2):
    p1, p2 = map(math.radians, (lat1, lat2))
    dl = math.radians(lon2-lon1)
    dp = p2-p1
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 6371.0088 * 2 * math.asin(min(1, math.sqrt(a)))


def envelope(rows, args, warnings):
    # Individual observations always retain the exact query/download URL and cache time.
    prov = provenance(args.source) if getattr(args, 'source', None) else dict(
        source_url=CYCLE_PAGE, publisher='Auckland Transport; NZ Transport Agency Waka Kotahi; Heart of the City',
        licence=None, retrieved_at=utc_now(), latest_data='2026')
    if rows and getattr(args, 'source', None):
        prov = {k: rows[0][k] for k in prov}
        prov['latest_data'] = max(r['latest_data'] for r in rows)
        prov['retrieved_at'] = min(r['retrieved_at'] for r in rows)
    result = dict(schema_version='1', ok=True, source=dict(name=prov['publisher'], url=prov['source_url'],
                  retrieved_at=prov['retrieved_at']), query={k: v for k, v in vars(args).items() if k != 'cache_dir'},
                  records=rows[:args.limit], count=min(len(rows), args.limit), matched_count=len(rows),
                  warnings=warnings, blocked=False, **prov)
    if len(rows) > args.limit:
        result['warnings'].append(f'Output limited to {args.limit} of {len(rows)} matched records; increase --limit to return more.')
    if getattr(args, 'format', None) == 'geojson':
        result.update(type='FeatureCollection', features=[dict(type='Feature', geometry=(
            dict(type='Point', coordinates=[r['longitude'], r['latitude']]) if 'longitude' in r else None),
            properties=r) for r in result.pop('records')])
    return result


def build_parser():
    parser = argparse.ArgumentParser(description='Query NZ traffic and active-mode counts (keyless).')
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('sources', 'sites', 'counts', 'nearest'):
        p = sub.add_parser(name)
        p.add_argument('--json', action='store_true')
        p.add_argument('--limit', type=positive, default=100)
        p.add_argument('--max-records', type=positive, default=10000, help='maximum ArcGIS rows queried')
        p.add_argument('--max-age', type=nonnegative, default=86400, help='cache max age in seconds; 0 bypasses cache')
        p.add_argument('--cache-dir', type=Path, default=Path(__file__).resolve().parents[1]/'.cache')
        if name != 'sources':
            p.add_argument('--source', choices=tuple(SOURCES), required=True)
            p.add_argument('--from', dest='date_from', type=iso_date)
            p.add_argument('--to', dest='date_to', type=iso_date)
        if name in ('sites', 'nearest'):
            p.add_argument('--bbox', type=lambda s: coordinates(s, True))
            p.add_argument('--format', choices=('json', 'geojson'), default='json')
        if name == 'counts':
            p.add_argument('--site', required=True)
        if name == 'nearest':
            p.add_argument('--near', type=coordinates, required=True)
            p.add_argument('--radius-km', type=nonnegative, default=10, help='bounded search radius (default 10 km)')
    return parser


def execute(args):
    if getattr(args, 'date_from', None) and getattr(args, 'date_to', None) and args.date_from > args.date_to:
        raise SkillError('--from must be on or before --to', 2)
    warnings = []
    if args.command == 'sources':
        rows = [dict(source_id=k, **{**{x: v for x, v in s.items() if x != 'url'}, **provenance(k)},
                     sites_url=TMS_SITES if k == 'nzta-tms' else s['url']) for k, s in SOURCES.items()]
        warnings.append('Sources is the verified catalogue, not a live health probe. Workbook defaults are pinned snapshots; use date filters for archive discovery.')
    elif args.command == 'counts':
        rows, warnings = get_counts(args)
    elif args.command == 'sites':
        rows, warnings = get_sites(args, args.bbox)
    else:
        if not SOURCES[args.source]['spatial']:
            raise SkillError('This workbook has no coordinates; nearest supports at-adt and nzta-tms', 7)
        lon, lat = args.near
        dy = args.radius_km/110.0
        dx = min(180.0, dy/max(0.01, math.cos(math.radians(lat))))
        bounds = args.bbox or (max(-180, lon-dx), max(-90, lat-dy), min(180, lon+dx), min(90, lat+dy))
        rows, warnings = get_sites(args, bounds)
        if warnings:
            raise SkillError('Nearest query exceeded --max-records; narrow --radius-km or increase --max-records', 7)
        rows = [dict(r, distance_km=round(distance(lon, lat, r['longitude'], r['latitude']), 6))
                for r in rows if 'longitude' in r]
        rows = sorted((r for r in rows if r['distance_km'] <= args.radius_km), key=lambda r: r['distance_km'])
        warnings.append(f'Nearest sites within {args.radius_km:g} km; distance is straight-line, not road distance.')
    return envelope(rows, args, warnings)


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        result = execute(args)
        if args.json or getattr(args, 'format', None) == 'geojson':
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"{result['count']} records ({result['matched_count']} matched)")
            for r in result['records']:
                label = r.get('site_id', r.get('source_id'))
                value = r.get('count', r.get('adt_7_day', r.get('adt')))
                print(f"{label}: {r.get('name', r.get('granularity', ''))} {r.get('date', '')} {'' if value is None else value}")
            print('Source: ' + result['source_url'])
            for warning in result['warnings']:
                print('Note: ' + warning)
    except (SkillError, OSError, ValueError, KeyError, IndexError, TypeError, ET.ParseError, zipfile.BadZipFile) as exc:
        code = exc.code if isinstance(exc, SkillError) else 6
        if args.json:
            prov = provenance(args.source) if getattr(args, 'source', None) else dict(
                source_url=CYCLE_PAGE, publisher='Auckland Transport', licence=None, retrieved_at=utc_now(), latest_data='2026')
            print(json.dumps(dict(schema_version='1', ok=False, error=dict(code=code, message=str(exc),
                             retry_after=getattr(exc, 'retry_after', None)), blocked=code == 4, **prov)))
        print(f'nz-traffic-counts: {exc}', file=sys.stderr)
        return code
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
