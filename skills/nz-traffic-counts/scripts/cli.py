#!/usr/bin/env python3
"""Keyless NZ count downloads and ArcGIS queries; Python standard library only."""
from __future__ import annotations

import argparse
import calendar
import csv
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
import tempfile
from urllib.parse import unquote, urlencode, urljoin, urlparse
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener
import xml.etree.ElementTree as ET
import zipfile
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'lib'))
import nzfetch  # noqa: E402
from provenance import provenance as source_provenance, result_envelope, error_envelope, geojson_envelope

AT = 'https://services2.arcgis.com/JkPEgZJGxhSjYOo0/arcgis/rest/services/TrafficService/FeatureServer/0'
TMS = 'https://services.arcgis.com/CXBb7LAjgIIdcsPt/arcgis/rest/services/TMS_Telemetry_Sites/FeatureServer/0'
TMS_SITES = 'https://services.arcgis.com/CXBb7LAjgIIdcsPt/arcgis/rest/services/Assets_SHTrafficMonitoringSites/FeatureServer/0'
TRAFFIC = 'https://at.govt.nz/media/afhnimq4/at-web-traffic-count-july-2012-to-june-2026.xlsx'
CYCLE_PAGE = 'https://at.govt.nz/cycling-walking/research-monitoring/monthly-cycle-monitoring/'
CYCLE = 'https://at.govt.nz/media/zj0lgcmg/at-daily-cycle-count-data-july-2026.xlsx'
HOT_PAGE = 'https://www.hotcity.co.nz/city-centre/results-and-statistics/pedestrian-counts'
HOT = 'https://www.hotcity.co.nz/sites/20180201.prod.hotcity.co.nz/files/2026-10/All%20pedestrian%20data%20day%20by%20hour%202026%20-%20September.xlsx'
HAMILTON = 'https://services1.arcgis.com/R6s0QqCMQdwKY6yp/arcgis/rest/services/Hamilton%20City%20Traffic%20Counts/FeatureServer/0'
TAURANGA = 'https://cemeteryaws.tauranga.govt.nz/server/rest/services/Mapi_Transportation/MapServer/17'
CHCH = 'https://smartview.ccc.govt.nz/app/router/map_features.php?feat=ecocounter'
WCC = 'https://gis.wcc.govt.nz/arcgis/rest/services/Transportation/Transport_Sensors/FeatureServer/0'
WCC_FILES = 'https://gis-snowflake-opendata-public-wcc-arcgis-prod.s3.ap-southeast-2.amazonaws.com/'
CITY_SOURCES = ('hamilton-traffic', 'tauranga-traffic', 'christchurch-cycle', 'wellington-sensors')
DATE_DERIVED_SOURCES = ('tauranga-traffic', 'wellington-sensors')
UNKNOWN_DATE_NOTE = 'No survey or observation dates are available in the returned rows; latest_data is unknown.'
ALLOWED = {'at.govt.nz', 'www.hotcity.co.nz', 'services.arcgis.com', 'services2.arcgis.com',
           'services1.arcgis.com', 'cemeteryaws.tauranga.govt.nz', 'smartview.ccc.govt.nz',
           'gis.wcc.govt.nz', urlparse(WCC_FILES).hostname}
SOURCES = {
    'at-traffic': dict(url=TRAFFIC, publisher='Auckland Transport', licence='AT terms: individual use; republication requires AT approval', latest_data='2026-06-30', spatial=False, granularity='survey ADT', catalogue_id='C0032'),
    'at-adt': dict(url=AT, publisher='Auckland Transport', licence='CC BY 4.0', latest_data='2026-06-23', spatial=True, granularity='survey ADT', catalogue_id='C0002'),
    'at-cycle-daily': dict(url=CYCLE, publisher='Auckland Transport', licence='CC BY 4.0', latest_data='2026-07-31', spatial=False, granularity='daily', catalogue_id='S0207'),
    'at-cycle-monthly': dict(url=CYCLE, publisher='Auckland Transport', licence='CC BY 4.0', latest_data='2026-07-31', spatial=False, granularity='monthly sum of published daily observations', catalogue_id='S0182'),
    'nzta-tms': dict(url=TMS, publisher='NZ Transport Agency Waka Kotahi', licence='CC BY 4.0', latest_data='2026', spatial=True, granularity='daily by lane/direction/vehicle class', catalogue_id='C0018'),
    'hotcity': dict(url=HOT, publisher='Heart of the City', licence='CC BY 4.0', latest_data='2026-09-30', spatial=False, granularity='hourly camera series', catalogue_id='C0033'),
    'hamilton-traffic': dict(url=HAMILTON, publisher='Hamilton City Council', licence='CC BY 4.0', latest_data='2023', spatial=True, granularity='published annual traffic values', catalogue_id='S1098'),
    'tauranga-traffic': dict(url=TAURANGA, publisher='Tauranga City Council and Bay of Plenty Regional Council', licence='Council copyright; no open reuse licence stated', latest_data=None, spatial=True, granularity='latest survey ADT', catalogue_id='S1373'),
    'christchurch-cycle': dict(url=CHCH, publisher='Christchurch City Council / Smart Christchurch', licence=None, latest_data=None, spatial=True, granularity='snapshot; observation period not supplied', catalogue_id='S2160'),
    'wellington-sensors': dict(url=WCC, publisher='Wellington City Council', licence='WCC terms: open urban mobility use; contact WCC for other purposes', latest_data=None, spatial=True, granularity='hourly by transport class and direction', catalogue_id='S1096;S2741'),
}
NS = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
NZ = ZoneInfo('Pacific/Auckland')


class SkillError(Exception):
    def __init__(self, message, code=6, retry_after=None, meta=None):
        super().__init__(message)
        self.code, self.retry_after = code, retry_after
        self.meta = meta


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
        if bbox and (vals[0] >= vals[2] or vals[1] >= vals[3]):
            raise ValueError()
        return vals
    except ValueError as exc:
        raise argparse.ArgumentTypeError('use minLon,minLat,maxLon,maxLat' if bbox else 'use lon,lat within WGS84 bounds') from exc


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise SkillError(message, 2)


def bounded_records(raw):
    value = positive(raw)
    if value > 50000:
        raise argparse.ArgumentTypeError('must be at most 50000')
    return value


def provenance(source, url=None, retrieved_at=None, latest=None):
    s = SOURCES[source]
    meta = source_provenance(url or s['url'], s['publisher'], licence=s['licence'],
                            retrieved_at=retrieved_at, latest_data=latest or s['latest_data'])
    if source in DATE_DERIVED_SOURCES and not latest:
        meta.update(latest_data=None, latest_data_note=UNKNOWN_DATE_NOTE)
    return meta


def note(args, message):
    if not hasattr(args, '_warnings'):
        args._warnings = []
    if message not in args._warnings:
        args._warnings.append(message)


def remember(args, meta):
    if not hasattr(args, '_provenances'):
        args._provenances = []
    args._provenances.append(meta)


def fetch_wcc_export(url):
    """Bounded S3 CSV read: the shared helper's 32 MiB wire cap is too small."""
    if not url.startswith(WCC_FILES+'transport_sensors/countline_mobility/csv/'):
        raise SkillError('Large CSV downloads are restricted to the WCC public export path', 7)

    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    try:
        request = Request(url, headers={'Accept': 'text/csv', 'Accept-Encoding': 'identity',
                                       'User-Agent': 'TheColab-nz-traffic-counts/1'})
        with build_opener(NoRedirect()).open(request, timeout=10) as response:
            if response.status != 200:
                raise SkillError('network error: unexpected WCC export status', 5)
            length = response.headers.get('Content-Length')
            expected = int(length) if length is not None else None
            if expected is not None and expected > 64 * 1024 * 1024:
                raise SkillError('network error: WCC monthly CSV exceeds the 64 MiB limit', 5)
            chunks, size = [], 0
            while chunk := response.read(65536):
                size += len(chunk)
                if size > 64 * 1024 * 1024:
                    raise SkillError('network error: WCC monthly CSV exceeds the 64 MiB limit', 5)
                chunks.append(chunk)
            if expected is not None and size != expected:
                raise SkillError('network error: WCC monthly CSV download was truncated', 5)
            return b''.join(chunks)
    except HTTPError as exc:
        raise SkillError(f'network error: WCC export HTTP {exc.code}',
                         4 if exc.code in (403, 429, 451) else 5,
                         exc.headers.get('Retry-After') if exc.code == 429 else None) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise SkillError('network error: WCC export unavailable: ' + str(exc), 5) from exc


def fetch(url, args, binary=False, max_bytes=32 * 1024 * 1024):
    if urlparse(url).hostname not in ALLOWED:
        raise SkillError('source host is outside the declared allowlist', 7)
    root = args.cache_dir / 'nz-traffic-counts-v1'
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
        if max_bytes > 32 * 1024 * 1024:
            body = fetch_wcc_export(url)
        else:
            body, _ct, _final = nzfetch.fetch_bytes(url, timeout=10, expect_json=not binary,
                                                   max_bytes=max_bytes, allowed_hosts=ALLOWED)
    except nzfetch.RateLimited as exc:
        raise SkillError('network error: rate_limited', 4, exc.retry_after) from exc
    except nzfetch.Blocked as exc:
        raise SkillError(f'network error: blocked: {exc}', 4) from exc
    except nzfetch.FetchError as exc:
        raise SkillError(f'network error: {exc}', 5) from exc
    stamp = utc_now()
    if args.max_age > 0:
        temporaries = []
        try:
            root.mkdir(parents=True, exist_ok=True)
            for old in root.glob('*.bin'):
                if re.fullmatch(r'[0-9a-f]{64}', old.stem) and time.time() - old.stat().st_mtime > args.max_age:
                    old.unlink(missing_ok=True)
                    old.with_suffix('.json').unlink(missing_ok=True)
            for destination, payload in ((path, body), (meta, json.dumps(dict(
                    fetched_epoch=time.time(), retrieved_at=stamp)).encode())):
                with tempfile.NamedTemporaryFile(dir=root, delete=False) as tmp:
                    temporaries.append(Path(tmp.name))
                    tmp.write(payload)
                Path(tmp.name).replace(destination)
        except OSError:
            note(args, 'Cache unavailable; downloaded data used without caching.')
        finally:
            for tmp in temporaries:
                try:
                    tmp.unlink(missing_ok=True)
                except OSError:
                    pass
    return body, stamp


def arc_query(base, args, **params):
    url = base + '/query?' + urlencode(dict(f='json', **params))
    body, stamp = fetch(url, args)
    data = json.loads(body)
    if 'error' in data:
        raise SkillError(f"ArcGIS query failed: {data['error'].get('message', 'unknown error')}",
                         5 if int(data['error'].get('code', 0)) >= 500 else 6)
    if not any(key in data for key in ('features', 'count')):
        raise SkillError('ArcGIS response has no features array')
    return data, url, stamp


def arc_rows(base, args, where='1=1', bbox=None):
    rows, warnings = [], []
    params = dict(where=where, outFields='*', returnGeometry='true', outSR=4326,
                  orderByFields=('startDate,OBJECTID' if base == TMS else 'count_date,OBJECTID' if base == AT else 'OBJECTID'), resultRecordCount=1000)
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
        dates = [local_day(f['attributes'].get('startDate' if base == TMS else 'count_date')) for f, _, _ in rows] if base in (AT, TMS) else []
        dates = [d for d in dates if d]
        period = f' Returned period {min(dates)}..{max(dates)} may be incomplete.' if dates else ''
        warnings.append(f'Result capped at {args.max_records} source records; narrow the date range or bbox, or increase --max-records.' + period)
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
    except OverflowError as exc:
        raise SkillError('Spreadsheet date is outside the supported range') from exc
    except ValueError:
        for fmt in ('%d/%m/%Y', '%Y-%m-%d', '%d-%b-%Y', '%d/%m/%y', '%A, %d %B %Y'):
            try:
                return datetime.strptime(str(value), fmt).date().isoformat()
            except ValueError:
                pass
        raise SkillError(f'Unrecognised spreadsheet date: {value!r}')


def sheets(body, streaming=False):
    """Read sparse XLSX rows; parsers stream rows instead of retaining whole sheets."""
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
        def read_rows(path):
            with z.open(path) as stream:
                parents = []
                for event, element in ET.iterparse(stream, events=('start', 'end')):
                    if event == 'start':
                        parents.append(element)
                        continue
                    if element.tag == '{' + NS['s'] + '}row':
                        cells = {}
                        for c in element.findall('s:c', NS):
                            col = re.sub(r'\d', '', c.get('r', ''))
                            v = c.find('s:v', NS)
                            value = v.text if v is not None else ''
                            if c.get('t') == 's':
                                value = shared[int(value)]
                            elif c.get('t') == 'inlineStr':
                                value = ''.join(c.find('s:is', NS).itertext())
                            cells[col] = value
                        yield cells
                        parents[-2].remove(element)
                        element.clear()
                    parents.pop()
        for sheet in book.findall('s:sheets/s:sheet', NS):
            target = rels[sheet.get('{' + REL + '}id')]
            path = target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/' + target)
            rows = read_rows(path)
            yield sheet.get('name'), rows if streaming else list(rows), epoch


def site_hash(values):
    return hashlib.sha256(json.dumps(values, ensure_ascii=False).encode()).hexdigest()[:16]


def in_range(day, start, end):
    return (not start or day >= start) and (not end or day <= end)


def add_site(sites, row):
    key = row['site_id']
    if key not in sites or sites[key].get('first_observed') is None:
        sites[key] = {**row, 'first_observed': row['date'], 'last_observed': row['date']}
    else:
        sites[key]['first_observed'] = min(sites[key]['first_observed'], row['date'])
        sites[key]['last_observed'] = max(sites[key]['last_observed'], row['date'])
        sites[key]['date'] = sites[key]['last_observed']


def parse_traffic(body, wanted_site=None, start=None, end=None, sites_only=False, info=None):
    info = info if info is not None else {}
    records, sites, known, latest = [], {}, set(), None
    found = False
    for name, rows, epoch in sheets(body, streaming=True):
        if not name.startswith('July 2012'):
            continue
        header = None
        for r in rows:
            if r.get('G') == 'Count Start Date' and r.get('B') == 'Road Name':
                header = r
                continue
            if header is None or not r.get('B') or not re.fullmatch(r'\d+(?:\.\d+)?', r.get('G', '')):
                continue
            found = True
            labels = [r.get(k, '').strip() for k in ('A', 'B', 'C', 'D', 'E', 'F')]
            key, day = site_hash(labels), excel_date(r['G'], epoch)
            known.add(key)
            if r.get('H') or r.get('I'):
                latest = max(latest or day, day)
            if (wanted_site and key != wanted_site) or not in_range(day, start, end):
                continue
            row = dict(site_id=key, name=labels[1], area=labels[0], location=labels[4], direction=labels[5], date=day)
            if sites_only:
                add_site(sites, row)
            else:
                records.append(dict(row, adt_5_day=numeric(r.get('H')), adt_7_day=numeric(r.get('I')),
                                    raw={v: r.get(k) for k, v in header.items() if v}))
        if header is None:
            raise SkillError('AT traffic workbook header changed')
    if not found:
        raise SkillError('No AT traffic survey rows parsed')
    info.update(known=known, latest=latest)
    groups = defaultdict(list)
    for row in records:
        groups[json.dumps(row, sort_keys=True)].append(row)
    duplicated = [r for group in groups.values() if len(group) > 1 for r in group]
    for row in duplicated:
        row['duplicate_row'] = True
    info['warnings'] = [f'{len(duplicated)} AT traffic rows are exact duplicates; preserved and flagged.'] if duplicated else []
    return list(sites.values()) if sites_only else records


def parse_active(body, hotcity=False, wanted_site=None, start=None, end=None,
                 sites_only=False, nominal_year=None, info=None):
    info = info if info is not None else {}
    records, summaries, known, latest = [], {}, set(), None
    placeholders, outside, found, unrelated_invalid = 0, defaultdict(int), False, 0
    invalid_warnings = []
    for _name, rows, epoch in sheets(body, streaming=True):
        header, date_col = None, 'A'
        for r in rows:
            shifted_cycle = not hotcity and r.get('A') == 'Year' and r.get('G') == 'Date'
            if r.get('A') in (('Date',) if hotcity else ('Time', 'Date')) or shifted_cycle:
                date_col = 'G' if shifted_cycle else 'A'
                excluded = ('A', 'B', 'C', 'D', 'E', 'F', 'G') if shifted_cycle else ('A', 'B') if hotcity else ('A',)
                header = {k: v.strip() for k, v in r.items() if v and k not in excluded}
                known.update(header.values())
                if sites_only:
                    for name in header.values():
                        summaries.setdefault(name, dict(site_id=name, name=name, date=None,
                                                        first_observed=None, last_observed=None))
                continue
            if header is None or not r.get(date_col):
                continue
            if re.fullmatch(r'\d+(?:\.\d+)?', r[date_col]):
                day = excel_date(r[date_col], epoch)
            else:
                try:
                    day = excel_date(r[date_col], epoch)
                except SkillError:
                    # Footer labels are not observation rows.
                    continue
            found = True
            wrong_year = bool(nominal_year and day[:4] != str(nominal_year))
            if wrong_year:
                outside[day] += 1
            selected = in_range(day, start, end)
            for col, name in header.items():
                value = r.get(col)
                invalid_raw = None
                if isinstance(value, str) and value.strip().lower() in ('-', '–', 'n/a', 'na', '', 'pending'):
                    placeholders += 1
                    count = None
                else:
                    try:
                        count = numeric(value)
                    except SkillError:
                        if selected and not sites_only and (not wanted_site or name == wanted_site):
                            if hotcity:
                                raise
                            invalid_raw = str(value)
                            invalid_warnings.append(f'{name} on {day}: invalid count {value!r} treated as missing')
                        else:
                            # Currency scans and header listings must not retain unrelated series.
                            unrelated_invalid += 1
                        count = None
                if count is not None and not wrong_year:
                    latest = max(latest or day, day)
                if not selected or (wanted_site and name != wanted_site):
                    continue
                row = dict(site_id=name, name=name, date=day)
                if sites_only:
                    if count is not None:
                        add_site(summaries, row)
                else:
                    row.update(interval=r.get('B') if hotcity else None, count=count,
                               granularity='hourly' if hotcity else 'daily')
                    if wrong_year:
                        row['date_outside_file_year'] = True
                    if invalid_raw is not None:
                        row['invalid_count_raw'] = invalid_raw
                    records.append(row)
    if not found:
        raise SkillError('Active-mode workbook header changed or no observations parsed')
    warnings = invalid_warnings
    if placeholders:
        warnings.append(f'{placeholders} placeholder cells treated as missing')
    if unrelated_invalid:
        warnings.append(f'{unrelated_invalid} non-numeric cells outside requested counts omitted from source-currency/site-date calculation.')
    if outside:
        warnings.append(f'{sum(outside.values())} date rows outside file year {nominal_year}: ' + ', '.join(sorted(outside)) + '; source dates preserved.')
    info.update(known=known, latest=latest, warnings=warnings)
    return list(summaries.values()) if sites_only else records


class DownloadLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            href = dict(attrs).get('href', '')
            if unquote(href).lower().endswith('.xlsx'):
                self.links.append(href)


def download_period(link, hotcity=False):
    filename = unquote(urlparse(link).path.rsplit('/', 1)[-1]).lower()
    if not filename.endswith('.xlsx') or ('pedestrian' if hotcity else 'cycle') not in filename:
        return None
    years = re.findall(r'(?<!\d)(?:19|20)\d{2}(?!\d)', filename)
    if not years:
        return None
    if hotcity:
        return years[-1]
    tokens = set(re.split(r'[^a-z0-9]+', filename))
    names = {name.lower(): i for i, name in enumerate(calendar.month_name) if name}
    names.update({name.lower(): i for i, name in enumerate(calendar.month_abbr) if name})
    names['sept'] = 9
    months = {i for name, i in names.items() if name in tokens}
    # Multi-month / annual layouts are outside this monthly parser's coverage.
    if len(months) != 1 or len(years) != 1:
        return None
    return f'{years[-1]}-{months.pop():02d}'


def workbook_urls(args):
    if args.source == 'at-traffic':
        return [TRAFFIC]
    hotcity = args.source == 'hotcity'
    page = HOT_PAGE if hotcity else CYCLE_PAGE
    body, _ = fetch(page, args, binary=True)
    parser = DownloadLinks()
    parser.feed(body.decode('utf-8'))
    periods = {}
    for link in parser.links:
        period = download_period(link, hotcity)
        if period:
            periods[period] = urljoin(page, link)
    if not periods:
        raise SkillError('No supported XLSX downloads discovered', 7)
    if not args.date_from and not args.date_to:
        selected = [max(periods)]
    elif hotcity:
        selected = sorted(p for p in periods if args.date_from[:4] <= p <= args.date_to[:4])
    else:
        coverage_start = min(periods)
        start = max(args.date_from[:7], coverage_start)
        end = min(args.date_to[:7], max(max(periods), SOURCES[args.source]['latest_data'][:7]))
        expected = []
        year, month = map(int, start.split('-'))
        while f'{year}-{month:02d}' <= end:
            expected.append(f'{year}-{month:02d}')
            year, month = (year+1, 1) if month == 12 else (year, month+1)
        missing = [p for p in expected if p not in periods]
        if missing:
            note(args, 'No supported download for ' + ', '.join(missing))
        if args.date_from[:7] < coverage_start:
            note(args, f'Monthly XLSX coverage begins {coverage_start}; earlier annual/CSV layouts are unsupported.')
        selected = sorted(p for p in expected if p in periods)
    if not selected:
        coverage = (f'latest published year is {max(periods)}; annual XLSX coverage begins {min(periods)}'
                    if hotcity else f'latest published month is {max(periods)}; monthly XLSX coverage begins {min(periods)}')
        raise SkillError('No supported XLSX download found for the requested period; ' + coverage + '; see source notes for archive limits', 7)
    if len(selected) > 24:
        raise SkillError('Request at most 24 workbooks at a time by narrowing --from/--to', 7)
    return [periods[p] for p in selected]


def workbook_records(args):
    records, known = [], set()
    urls = workbook_urls(args)
    monthly = args.source == 'at-cycle-monthly'
    start, end = args.date_from, args.date_to
    if monthly:
        start = start[:7] + '-01' if start else None
        end = (end[:7] + f'-{calendar.monthrange(int(end[:4]), int(end[5:7]))[1]:02d}') if end else None
    for url in urls:
        info = {}
        options = dict(wanted_site=getattr(args, 'site', None), start=start, end=end,
                       sites_only=args.command == 'sites', info=info)
        try:
            body, stamp = fetch(url, args, binary=True)
            if args.source == 'at-traffic':
                parsed = parse_traffic(body, **options)
                if start and start < '2012-07-01':
                    note(args, 'Prior to July 2012 worksheet is unsupported and omitted; only the recent worksheet is parsed.')
            else:
                hotcity = args.source == 'hotcity'
                parsed = parse_active(body, hotcity, nominal_year=download_period(url, True) if hotcity else None, **options)
            if not info['latest']:
                raise SkillError('Workbook contains no numeric count observations within its nominal year')
        except (SkillError, OSError, OverflowError, ValueError, KeyError, IndexError, TypeError,
                ET.ParseError, zipfile.BadZipFile) as exc:
            meta = source_provenance(url, SOURCES[args.source]['publisher'],
                                     licence=SOURCES[args.source]['licence'])
            raise SkillError(f'{unquote(url.rsplit("/", 1)[-1])} ({url}): {exc}',
                             getattr(exc, 'code', 6), getattr(exc, 'retry_after', None), meta) from exc
        if args.source in ('at-cycle-daily', 'at-cycle-monthly'):
            nominal_month = download_period(url)
            outside_month = [r for r in parsed if r['date'] and r['date'][:7] != nominal_month]
            for row in outside_month:
                row['date_outside_file_month'] = True
            if outside_month:
                note(args, f'{len(outside_month)} observations outside file month {nominal_month}: ' +
                     ', '.join(sorted({r['date'] for r in outside_month})) + '; source dates preserved.')
        known.update(info['known'])
        latest = info['latest']
        for message in info['warnings']:
            note(args, unquote(url.rsplit('/', 1)[-1]) + ': ' + message)
        remember(args, provenance(args.source, url, stamp, latest))
        for row in parsed:
            if row['date'] is None or row['date'] <= latest or row.get('date_outside_file_year'):
                # Reference the workbook once; detailed provenance is in meta.downloads.
                row['source_url'] = url
                records.append(row)
    if args.source in ('at-cycle-daily', 'at-cycle-monthly') and args.command == 'counts':
        nominal = defaultdict(list)
        for row in records:
            if not row.get('date_outside_file_month'):
                nominal[(row['site_id'], row['date'])].append(row)
        retained, dropped = [], 0
        for row in records:
            originals = nominal.get((row['site_id'], row['date']), [])
            if row.get('date_outside_file_month') and originals:
                if all((r['count'], r.get('invalid_count_raw')) ==
                       (row['count'], row.get('invalid_count_raw')) for r in originals):
                    dropped += 1
                    continue
                for duplicate in [row, *originals]:
                    duplicate['duplicate_row'] = True
                note(args, f'Conflicting duplicate cycle observations for {row["site_id"]} on {row["date"]}: ' +
                     ', '.join(r['source_url'] for r in [row, *originals]) + '; preserved and flagged.')
            retained.append(row)
        if dropped:
            note(args, f'{dropped} equal outside-month cycle observations omitted; supplied by their nominal-month workbook.')
        records = retained
    if args.command == 'counts' and args.site not in known:
        raise SkillError('Unknown site in selected workbooks; use sites --source with the same date range', 2)
    if args.command == 'counts' and not records:
        note(args, 'Site exists but has no observations in the requested period')
    return records


def local_day(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).astimezone(NZ).date().isoformat() if ms is not None else None


def at_site_id(a):
    return f"{a['carr_way_no']}:{a['location']}"


def city_spatial(row, geometry):
    """Keep WCC countlines intact; nearest uses their vertex-mean centre."""
    if not geometry:
        return row
    if 'paths' in geometry:
        paths = geometry['paths']
        points = [p for path in paths for p in path]
        if not points or any(len(path) < 2 for path in paths):
            raise SkillError('Empty or incomplete countline geometry')
        if any(len(p) != 2 or not all(math.isfinite(v) for v in p)
               or not (-180 <= p[0] <= 180 and -90 <= p[1] <= 90) for p in points):
            raise SkillError('Countline vertices are outside WGS84 bounds')
        row['geometry'] = dict(type='MultiLineString', coordinates=paths)
        x, y = (sum(p[i] for p in points)/len(points) for i in (0, 1))
    else:
        x, y = geometry['x'], geometry['y']
    if not all(math.isfinite(v) for v in (x, y)) or not (-180 <= x <= 180 and -90 <= y <= 90):
        raise SkillError('Source geometry is outside WGS84 bounds')
    row.update(longitude=x, latitude=y)
    return row


def parse_city_arc(feature, source, url, stamp):
    a = feature['attributes']
    if source == 'hamilton-traffic':
        if not {'OBJECTID', 'Site_Number', 'Site_Name', 'Year2023'} <= a.keys():
            raise SkillError('Hamilton annual traffic fields changed')
        row = dict(site_id=str(a['OBJECTID']), site_number=a['Site_Number'], name=a['Site_Name'],
                   direction=a.get('Direction'), raw=a)
    elif source == 'tauranga-traffic':
        if not {'id', 'road_id', 'count_date', 'ADT'} <= a.keys():
            raise SkillError('Tauranga traffic fields changed')
        try:
            day = date.fromisoformat(a['count_date'][:10]).isoformat() if a['count_date'] else None
        except ValueError as exc:
            raise SkillError('Invalid Tauranga count_date') from exc
        row = dict(site_id=a['id'], name=a['road_id'], date=day, adt=numeric(a['ADT']),
                   direction=a.get('direction'), heavy_vehicle_percent=numeric(a.get('PcHeavy')), raw=a)
    else:
        if not {'COUNTLINE_ID', 'Status'} <= a.keys():
            raise SkillError('Wellington countline fields changed')
        row = dict(site_id=str(a['COUNTLINE_ID']), name='Countline ' + str(a['COUNTLINE_ID']),
                   status=a['Status'], raw=a)
    return city_spatial(dict(row, **provenance(source, url, stamp, row.get('date'))), feature.get('geometry'))


def hamilton_years(row, args):
    years = sorted((k[4:], v) for k, v in row['raw'].items() if re.fullmatch(r'Year\d{4}', k))
    return [dict(row, date=year, period_start=year+'-01-01', period_end=year+'-12-31',
                 count=numeric(value), granularity='annual source value') for year, value in years
            if (not args.date_from or year+'-12-31' >= args.date_from)
            and (not args.date_to or year+'-01-01' <= args.date_to)]


def parse_chch(data, url, stamp):
    if data.get('type') != 'FeatureCollection' or not isinstance(data.get('features'), list):
        raise SkillError('Christchurch response is not a GeoJSON FeatureCollection')
    rows = []
    for feature in data['features']:
        a, g = feature['properties'], feature.get('geometry')
        if a.get('total') is True and a.get('oid') == 'total':
            continue  # The source's network total has a display coordinate, not a counter site.
        if not {'oid', 'name', 'count', 'direction'} <= a.keys() or not g or g.get('type') != 'Point':
            raise SkillError('Christchurch counter fields or point geometry changed')
        row = dict(site_id=str(a['oid']), name=a['name'], count=numeric(a['count']),
                   direction=a['direction'], installed_on=a.get('installed_on'), raw=a,
                   **provenance('christchurch-cycle', url, stamp))
        rows.append(city_spatial(row, dict(zip(('x', 'y'), g['coordinates']))))
    return rows


def city_sites(args, bbox=None, site=None):
    source = args.source
    if source == 'christchurch-cycle':
        if args.date_from or args.date_to:
            raise SkillError('Christchurch snapshot supplies no observation date or period; date filters are unsupported', 7)
        body, stamp = fetch(CHCH, args)
        rows = parse_chch(json.loads(body), CHCH, stamp)
        if len(rows) > args.max_records:
            raise SkillError('Christchurch inventory exceeds --max-records; increase the bound', 7)
        if bbox:
            rows = [r for r in rows if bbox[0] <= r['longitude'] <= bbox[2] and bbox[1] <= r['latitude'] <= bbox[3]]
        if site is not None:
            rows = [r for r in rows if r['site_id'] == site]
        remember(args, provenance(source, CHCH, stamp))
        return rows, ['Christchurch snapshot has no observation timestamp or count period; do not interpret it as a daily count.']
    base = SOURCES[source]['url']
    where = '1=1'
    if site is not None:
        if source == 'tauranga-traffic':
            if not re.fullmatch(r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}', site):
                raise SkillError('Tauranga site must be the UUID from sites', 2)
            where = f"id='{site}'"
        else:
            if not re.fullmatch(r'\d{1,12}', site):
                raise SkillError('Site must be the numeric identifier from sites', 2)
            field = 'OBJECTID' if source == 'hamilton-traffic' else 'COUNTLINE_ID'
            where = f'{field}={int(site)}'
    if source == 'wellington-sensors' and (args.date_from or args.date_to) and args.command != 'counts':
        raise SkillError('Wellington inventory has no observation dates; apply date filters to counts', 7)
    raw, warnings = arc_rows(base, args, where, bbox)
    rows = [parse_city_arc(f, source, u, t) for f, u, t in raw]
    latest = max((r['date'] for r in rows if r.get('date')), default=None)
    remember(args, provenance(source, base, min((t for _, _, t in raw), default=utc_now()), latest))
    if source == 'tauranga-traffic' and site is None:
        rows = [r for r in rows if (r['date'] is not None or not (args.date_from or args.date_to))
                and in_range(r['date'], args.date_from, args.date_to)]
    if source == 'hamilton-traffic' and site is None:
        for row in rows:
            observed = [r for r in hamilton_years(row, args) if r['count'] is not None]
            row['date'] = observed[-1]['date'] if observed else None
        if args.date_from or args.date_to:
            rows = [r for r in rows if r['date']]
    return rows, warnings


def wcc_months(body):
    root = ET.fromstring(body)
    if root.tag.rsplit('}', 1)[-1] != 'ListBucketResult':
        raise SkillError('Wellington file listing schema changed')
    if any(e.text == 'true' for e in root.iter() if e.tag.rsplit('}', 1)[-1] == 'IsTruncated'):
        raise SkillError('Wellington file listing is truncated; archive discovery is incomplete', 7)
    months = {}
    for element in root.iter():
        if element.tag.rsplit('}', 1)[-1] != 'Key':
            continue
        match = re.fullmatch(r'transport_sensors/countline_mobility/csv/(\d{4})/(\d{2})/countline_mobility_\1_\2.csv', element.text or '')
        if match:
            months[match[1]+'-'+match[2]] = WCC_FILES + element.text
    if not months:
        raise SkillError('No Wellington monthly CSV exports found')
    return months


def parse_wcc_csv(body, wanted_site, start=None, end=None):
    reader = csv.DictReader(io.TextIOWrapper(io.BytesIO(body), encoding='utf-8-sig', newline=''))
    fields = {'COUNTLINE_ID', 'COUNTLINE_DATE', 'COUNTLINE_HOUR', 'DIRECTION_COUNT', 'COUNTLINE_TRANSPORT_CLASS', 'DIRECTION'}
    if not reader.fieldnames or not fields <= set(reader.fieldnames):
        raise SkillError('Wellington CSV fields changed')
    rows, latest, seen = [], None, False
    for a in reader:
        try:
            day = date.fromisoformat(a['COUNTLINE_DATE']).isoformat()
        except (TypeError, ValueError) as exc:
            raise SkillError('Invalid Wellington observation date') from exc
        latest = max(latest or day, day)
        if a['COUNTLINE_ID'] != wanted_site:
            continue
        seen = True
        if not in_range(day, start, end):
            continue
        hour = int(a['COUNTLINE_HOUR'])
        if not 0 <= hour <= 23:
            raise SkillError('Wellington observation hour is outside 0..23')
        rows.append(dict(site_id=wanted_site, date=day, hour=hour, count=numeric(a['DIRECTION_COUNT']),
                         transport_class=a['COUNTLINE_TRANSPORT_CLASS'], direction=a['DIRECTION'],
                         granularity='hourly', raw=a))
    if latest is None:
        raise SkillError('Wellington monthly CSV has no observations')
    return rows, latest, seen


def city_counts(args):
    # Validate the site independently of spatial/date filtering, so no matches is meaningful.
    sites, warnings = city_sites(args, site=args.site)
    if not sites and args.source != 'wellington-sensors':
        raise SkillError(f'Unknown site {args.site}; use sites --source to find an identifier', 2)
    if args.source == 'hamilton-traffic':
        rows = [r for site in sites for r in hamilton_years(site, args)]
        warnings.append('Annual source values retain their year precision; null annual values are not zero-filled.')
    elif args.source == 'tauranga-traffic':
        rows = [r for r in sites if (r['date'] is not None or not (args.date_from or args.date_to))
                and in_range(r['date'], args.date_from, args.date_to)]
    elif args.source == 'christchurch-cycle':
        rows = sites
    else:
        inventory_meta = args._provenances.pop()
        listing = WCC_FILES + '?' + urlencode({'list-type': '2', 'prefix': 'transport_sensors/countline_mobility/csv/'})
        body, _ = fetch(listing, args, binary=True)
        months = wcc_months(body)
        start = args.date_from[:7] if args.date_from else (args.date_to[:7] if args.date_to else max(months))
        end = args.date_to[:7] if args.date_to else (datetime.now(NZ).date().isoformat()[:7] if args.date_from else start)
        expected = []
        current = date.fromisoformat(start+'-01')
        while current.isoformat()[:7] <= end:
            expected.append(current.isoformat()[:7])
            if len(expected) > 3:
                raise SkillError('Wellington counts allow at most three monthly CSV downloads; narrow the dates', 7)
            current = (current.replace(day=28)+timedelta(days=4)).replace(day=1)
        missing = [m for m in expected if m not in months]
        if missing:
            raise SkillError('No Wellington monthly export for: ' + ', '.join(missing), 7)
        rows, seen = [], False
        for month in expected:
            url = months[month]
            try:
                body, stamp = fetch(url, args, binary=True, max_bytes=64 * 1024 * 1024)
                parsed, latest, found = parse_wcc_csv(body, args.site, args.date_from, args.date_to)
            except SkillError as exc:
                exc.meta = provenance(args.source, url)
                raise
            meta = provenance(args.source, url, stamp, latest)
            remember(args, meta)
            rows.extend(dict(r, **provenance(args.source, url, stamp, r['date'])) for r in parsed)
            seen = seen or found
        remember(args, inventory_meta)
        if not sites and not seen:
            raise SkillError('Site is absent from the Wellington inventory and selected monthly exports', 2)
        if sites:
            geometry = {k: sites[0][k] for k in ('geometry', 'longitude', 'latitude') if k in sites[0]}
            rows = [dict(r, **geometry, geometry_source_url=sites[0]['source_url']) for r in rows]
        warnings.append('Wellington classes and directions remain separate; gaps are not zero-filled. Nearest measures countline centres.')
    bbox = getattr(args, 'bbox', None)
    if bbox:
        candidates, extra = city_sites(args, bbox=bbox)
        allowed = {r['site_id'] for r in candidates}
        rows = [r for r in rows if r['site_id'] in allowed]
        warnings.extend(extra)
    return rows, warnings


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
    r['source_url'] = url
    return r


def get_sites(args, bbox=None):
    if args.source in CITY_SOURCES:
        return city_sites(args, bbox)
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
        remember(args, provenance(args.source, base, min((t for _, _, t in raw), default=utc_now()),
                                  '2025' if args.source == 'nzta-tms' else None))
    else:
        if bbox:
            raise SkillError('This workbook has no coordinates; choose a spatial source from sources', 7)
        rows, warnings = workbook_records(args), []
    unique = {}
    for row in rows:
        key = row['site_id']
        previous = unique.get(key)
        if key not in unique or (row.get('date') or '') > (unique[key].get('date') or ''):
            unique[key] = {k: v for k, v in row.items() if k not in ('count', 'interval', 'granularity', 'adt_5_day', 'adt_7_day')}
        if 'first_observed' in row:
            for field, merge in (('first_observed', min), ('last_observed', max)):
                dates = [r.get(field) for r in (row, previous or {}) if r.get(field) is not None]
                unique[key][field] = merge(dates) if dates else None
            unique[key]['date'] = unique[key]['last_observed']
    return list(unique.values()), warnings


def get_counts(args):
    if args.source in CITY_SOURCES:
        return city_counts(args)
    if getattr(args, 'bbox', None) or getattr(args, 'format', 'json') == 'geojson':
        raise SkillError('Spatial counts output is available for the city sources; use sites for existing sources', 7)
    if args.source not in ('at-adt', 'nzta-tms'):
        rows = workbook_records(args)
        rows = [r for r in rows if r['site_id'] == args.site]
        warnings = []
        if args.source == 'at-cycle-monthly':
            groups = defaultdict(list)
            for row in rows:
                groups[(row['date'][:7], row['source_url'])].append(row)
            monthly = []
            for (month, _url), days in groups.items():
                values = [r['count'] for r in days if r['count'] is not None]
                summary = {**days[0], 'date': month + '-01', 'period_end': max(r['date'] for r in days),
                                'count': sum(values) if values else None, 'observed_days': len(values),
                                'published_days': len(days),
                                'granularity': 'monthly'}
                for flag in ('duplicate_row', 'date_outside_file_month'):
                    if any(r.get(flag) for r in days):
                        summary[flag] = True
                if not summary.get('date_outside_file_month'):
                    summary['missing_days'] = calendar.monthrange(int(month[:4]), int(month[5:]))[1]-len(values)
                invalid_days = [{'date': r['date'], 'invalid_count_raw': r['invalid_count_raw']}
                                for r in days if 'invalid_count_raw' in r]
                summary.pop('invalid_count_raw', None)
                if invalid_days:
                    summary['invalid_count_days'] = invalid_days
                monthly.append(summary)
            rows = sorted(monthly, key=lambda r: (r['date'], r['source_url']))
            warnings.append('Monthly totals sum published daily observations; missing days are not zero-filled.')
        rows = [r for r in rows if (not args.date_from or (r.get('period_end') or r['date']) >= args.date_from)
                and (not args.date_to or r['date'] <= args.date_to)]
        if args.source == 'at-cycle-daily':
            rows.sort(key=lambda r: (r['date'], r['source_url']))
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
    site_where = where
    # TMS timestamps represent NZ local midnight. AT dates are stored as UTC dates.
    if args.source == 'nzta-tms':
        start, end = args.date_from, args.date_to
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
    remember(args, provenance(args.source, base, min((t for _, _, t in raw), default=utc_now())))
    if not rows:
        data, _, _ = arc_query(base, args, where=site_where, returnCountOnly='true')
        exists = data['count'] > 0
        if not exists and args.source == 'nzta-tms':
            data, _, _ = arc_query(TMS_SITES, args, where=f"siteref='{args.site}'", returnCountOnly='true')
            exists = data['count'] > 0
        if not exists:
            raise SkillError(f'Unknown site {args.site}; use sites --source to find an identifier', 2)
        warnings.append('Site exists but has no observations in the requested period')
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
    meta = provenance(args.source) if getattr(args, 'source', None) else source_provenance(
        CYCLE_PAGE, 'Auckland Transport; NZ Transport Agency Waka Kotahi; Heart of the City')
    downloads = getattr(args, '_provenances', [])
    if downloads:
        meta.update(downloads[0])
        latest = [p['latest_data'] for p in downloads if p.get('latest_data')]
        if latest:
            meta['latest_data'] = max(latest)
        meta['retrieved_at'] = min(p['retrieved_at'] for p in downloads)
        meta['downloads'] = downloads
    warnings = list(dict.fromkeys(warnings + getattr(args, '_warnings', [])))
    if getattr(args, 'source', None) in DATE_DERIVED_SOURCES:
        meta['latest_data'] = max((r['date'] for r in rows[:args.limit] if r.get('date')), default=None)
        if meta['latest_data'] is None:
            meta['latest_data_note'] = UNKNOWN_DATE_NOTE
            warnings.append(UNKNOWN_DATE_NOTE)
        else:
            meta.pop('latest_data_note', None)
    if len(rows) > args.limit:
        warnings.append(f'Output limited to {args.limit} of {len(rows)} matched records; increase --limit to return more.')
    meta.update(query={k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()
                       if k != 'cache_dir' and not k.startswith('_')}, warnings=warnings,
                count=min(len(rows), args.limit), matched_count=len(rows))
    if getattr(args, 'format', None) == 'geojson':
        features = [dict(type='Feature', geometry=r.get('geometry', (dict(type='Point', coordinates=[r['longitude'], r['latitude']])
                    if 'longitude' in r else None)), properties=r) for r in rows[:args.limit]]
        return geojson_envelope(features, meta)
    return result_envelope(rows[:args.limit], meta)


def build_parser():
    parser = ArgumentParser(description='Query NZ traffic and active-mode counts (keyless).')
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('sources', 'sites', 'counts', 'nearest'):
        p = sub.add_parser(name)
        p.add_argument('--json', action='store_true')
        p.add_argument('--limit', type=positive, default=100)
        p.add_argument('--max-records', type=bounded_records, default=10000, help='maximum ArcGIS rows queried')
        p.add_argument('--max-age', type=nonnegative, default=86400, help='cache max age in seconds; 0 bypasses cache')
        p.add_argument('--cache-dir', type=Path, default=Path(__file__).resolve().parents[1]/'.cache')
        p.add_argument('--source', choices=tuple(SOURCES), required=name != 'sources')
        if name != 'sources':
            p.add_argument('--from', dest='date_from', type=iso_date)
            p.add_argument('--to', dest='date_to', type=iso_date)
        if name in ('sites', 'nearest', 'counts'):
            p.add_argument('--bbox', type=lambda s: coordinates(s, True))
            p.add_argument('--format', choices=('json', 'geojson'), default='json')
        if name == 'counts':
            p.add_argument('--site', required=True)
        if name == 'nearest':
            p.add_argument('--near', type=coordinates, required=True)
            p.add_argument('--radius-km', type=nonnegative, default=10, help='bounded search radius (default 10 km)')
    return parser


def execute(args):
    resolve_dates(args)
    if getattr(args, 'date_from', None) and getattr(args, 'date_to', None) and args.date_from > args.date_to:
        raise SkillError('--from must be on or before --to', 2)
    warnings = []
    if args.command == 'sources':
        rows = [dict(source_id=k, **{**{x: v for x, v in s.items() if x != 'url' and v is not None}, **provenance(k)},
                     sites_url=TMS_SITES if k == 'nzta-tms' else s['url']) for k, s in SOURCES.items()
                if not args.source or k == args.source]
        warnings.append('Sources is the verified catalogue, not a live health probe. Active-mode defaults discover the latest workbook; date filters select archives.')
    elif args.command == 'counts':
        rows, warnings = get_counts(args)
    elif args.command == 'sites':
        rows, warnings = get_sites(args, args.bbox)
    else:
        if not SOURCES[args.source]['spatial']:
            raise SkillError('This workbook has no coordinates; choose a spatial source from sources', 7)
        lon, lat = args.near
        dy = args.radius_km/110.0
        dx = min(180.0, dy/max(0.01, math.cos(math.radians(lat))))
        bounds = args.bbox or (max(-180, lon-dx), max(-90, lat-dy), min(180, lon+dx), min(90, lat+dy))
        rows, warnings = get_sites(args, bounds)
        if any(w.startswith('Result capped') for w in warnings):
            raise SkillError('Nearest query exceeded --max-records; narrow --radius-km or increase --max-records', 7)
        rows = [dict(r, distance_km=round(distance(lon, lat, r['longitude'], r['latitude']), 6))
                for r in rows if 'longitude' in r]
        rows = sorted((r for r in rows if r['distance_km'] <= args.radius_km), key=lambda r: r['distance_km'])
        warnings.append(f'Nearest sites within {args.radius_km:g} km; distance is straight-line, not road distance.')
    return envelope(rows, args, warnings)


def resolve_dates(args):
    if args.command == 'sources':
        return
    today = datetime.now(NZ).date()
    start, end = args.date_from, args.date_to
    if args.source == 'nzta-tms' and args.command == 'counts':
        end = end or today.isoformat()
        start = start or (date.fromisoformat(end)-timedelta(days=30)).isoformat()
    elif args.source == 'wellington-sensors' and args.command == 'counts' and (start or end):
        end = end or today.isoformat()
        start = start or end[:7]+'-01'
    elif args.source in ('hotcity', 'at-cycle-daily', 'at-cycle-monthly') and (start or end):
        end = end or today.isoformat()
        start = start or (end[:4] + '-01-01' if args.source == 'hotcity' else end[:7] + '-01')
    args.date_from, args.date_to = start, end


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    machine = '--json' in argv or '--format=geojson' in argv or any(
        argv[i:i+2] == ['--format', 'geojson'] for i in range(len(argv)))
    args = None
    try:
        args = build_parser().parse_args(argv)
        result = execute(args)
        if machine:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            meta = result['meta']
            print(f"{meta['count']} records ({meta['matched_count']} matched)")
            for r in result['results']:
                label = r.get('site_id', r.get('source_id'))
                value = r.get('count', r.get('adt_7_day', r.get('adt')))
                print(f"{label}: {r.get('name', r.get('granularity', ''))} {r.get('date', '')} {'' if value is None else value}")
            print('Source: ' + meta['source_url'])
            for warning in meta['warnings']:
                print('Note: ' + warning)
    except (SkillError, OSError, OverflowError, ValueError, KeyError, IndexError, TypeError,
            ET.ParseError, zipfile.BadZipFile) as exc:
        code = exc.code if isinstance(exc, SkillError) else 6
        if machine:
            meta = getattr(exc, 'meta', None) or (provenance(args.source) if args and getattr(args, 'source', None) else source_provenance(CYCLE_PAGE, 'Auckland Transport'))
            print(json.dumps(error_envelope(code, str(exc), meta, retry_after=getattr(exc, 'retry_after', None))))
        print(f'nz-traffic-counts: {exc}', file=sys.stderr)
        return code
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
