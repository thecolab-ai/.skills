#!/usr/bin/env python3
"""Source parsers for AT XLSX and Metlink tidy CSV; standard library only."""
from __future__ import annotations

import csv
import io
import math
import posixpath
import re
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit
from zipfile import ZipFile

NS = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
REL = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'
MODES = {'bus', 'train', 'ferry'}


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            href = dict(attrs).get('href')
            if href:
                self.links.append(href)


def download_links(html, base, kind):
    parser = Links()
    parser.feed(html)
    patterns = {
        'daily': r'(?:bus-train(?:-and)?-ferry|bus-train-and-ferry)-boardings-by-day',
        'monthly': r'monthly-bus-train-ferry-boardings',
        'punctuality': r'monthly-punctuality-and-reliability',
        'metlink': r'metlink-daily-bus-performance',
    }
    suffix = '.csv' if kind == 'metlink' else '.xlsx'
    found = []
    for href in parser.links:
        url = urljoin(base, href)
        parts = urlsplit(url)
        if (parts.scheme == 'https' and parts.hostname == urlsplit(base).hostname
                and parts.path.lower().endswith(suffix)
                and re.search(patterns[kind], parts.path.lower()) and url not in found):
            found.append(url)
    if not found:
        raise ValueError(f'source page no longer links {kind} downloads')
    return found


def workbook(body):
    """Read sparse cells, shared/inline strings, cached formula values and date epoch."""
    with ZipFile(io.BytesIO(body)) as archive:
        if sum(item.file_size for item in archive.infolist()) > 64 * 1024 * 1024:
            raise ValueError('workbook expands beyond 64 MiB')
        root = ET.fromstring(archive.read('xl/workbook.xml'))
        props = root.find('s:workbookPr', NS)
        epoch = date(1904, 1, 1) if props is not None and props.get('date1904') in {'1', 'true'} else date(1899, 12, 30)
        strings = []
        if 'xl/sharedStrings.xml' in archive.namelist():
            strings = [''.join(t.text or '' for t in si.findall('.//s:t', NS))
                       for si in ET.fromstring(archive.read('xl/sharedStrings.xml'))]
        rels = {r.get('Id'): r.get('Target') for r in ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))
                if r.get('TargetMode') != 'External'}
        sheets = {}
        for sheet in root.findall('s:sheets/s:sheet', NS):
            target = rels.get(sheet.get(REL))
            if not target:
                raise ValueError('worksheet relationship missing')
            path = posixpath.normpath(target.lstrip('/') if target.startswith('/') else 'xl/' + target)
            if not path.startswith('xl/'):
                raise ValueError('worksheet path is outside the workbook')
            rows = []
            for row in ET.fromstring(archive.read(path)).findall('.//s:sheetData/s:row', NS):
                cells = {}
                for cell in row.findall('s:c', NS):
                    address = cell.get('r', '')
                    column = re.match(r'[A-Z]+', address)
                    if not column:
                        raise ValueError('worksheet cell address missing')
                    v = cell.find('s:v', NS)
                    value = v.text if v is not None else None
                    kind = cell.get('t')
                    if kind == 's' and value is not None:
                        value = strings[int(value)]
                    elif kind == 'inlineStr':
                        value = ''.join(t.text or '' for t in cell.findall('.//s:t', NS))
                    elif kind == 'e':
                        raise ValueError(f'Excel error at {sheet.get("name")}!{address}: {value}')
                    cells[column.group()] = value
                rows.append(cells)
            sheets[sheet.get('name')] = rows
        if not sheets:
            raise ValueError('workbook has no worksheets')
        return sheets, epoch


def number(value, *, integer=False, ratio=False):
    result = float(value)
    if not math.isfinite(result) or (integer and (result < 0 or not result.is_integer())) or (ratio and not 0 <= result <= 1):
        raise ValueError(f'invalid source numeric value: {value}')
    return int(result) if integer else result


def period(value, epoch, monthly=False):
    if value is None:
        raise ValueError('source reporting period missing')
    text = str(value)
    if re.fullmatch(r'\d{4}-\d{2}', text):
        date.fromisoformat(text + '-01')
        return text
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}', text):
        parsed = date.fromisoformat(text)
    else:
        parsed = epoch + timedelta(days=number(text, integer=True))
    return parsed.isoformat()[:7] if monthly else parsed.isoformat()


def table(rows, required):
    for index, row in enumerate(rows):
        headers = {v: c for c, v in row.items() if v is not None}
        if required <= headers.keys():
            return row, headers, rows[index + 1:]
    raise ValueError('source table headers missing: ' + ', '.join(sorted(required)))


def parse_patronage(body, frequency, by_route=False):
    sheets, epoch = workbook(body)
    results = []
    if by_route:
        if frequency != 'monthly':
            raise ValueError('route patronage is published monthly')
        rows = sheets.get('Monthly by Route')
        if rows is None:
            raise ValueError('Monthly by Route worksheet missing')
        header, columns, data = table(rows, {'Mode', 'Route Num', 'Route Name'})
        months = {c: period(v, epoch, True) for c, v in header.items()
                  if v is not None and re.fullmatch(r'\d+(?:\.0)?|\d{4}-\d{2}', v)}
        if not months:
            raise ValueError('route month columns missing')
        for row in data:
            mode = str(row.get(columns['Mode'], '')).lower()
            if mode not in MODES:  # published subtotals are deliberately excluded
                continue
            route = row.get(columns['Route Num'])
            if route is None:
                raise ValueError('route number missing')
            for column, month in months.items():
                if row.get(column) is not None:
                    results.append({'mode': mode, 'route': str(route), 'route_name': row.get(columns['Route Name']),
                                    'period': month, 'frequency': 'monthly', 'boardings': number(row[column], integer=True)})
    else:
        rows = sheets.get('Data' if frequency == 'daily' else 'Monthly by Mode')
        if rows is None:
            raise ValueError('mode patronage worksheet missing')
        key = 'Date' if frequency == 'daily' else 'Month'
        _, columns, data = table(rows, {key, 'Bus', 'Train', 'Ferry'})
        for row in data:
            if row.get(columns[key]) is None:
                continue
            reporting_period = period(row[columns[key]], epoch, frequency == 'monthly')
            for mode in sorted(MODES):
                value = row.get(columns[mode.title()])
                if value is not None:
                    results.append({'mode': mode, 'period': reporting_period, 'frequency': frequency,
                                    'boardings': number(value, integer=True)})
    if not results:
        raise ValueError('patronage workbook contains no observations')
    return results


def parse_punctuality(body):
    sheets, epoch = workbook(body)
    results = {}
    for sheet, field in [('Punctuality', 'punctuality'), ('Reliability', 'reliability')]:
        if sheet not in sheets:
            raise ValueError(f'{sheet} worksheet missing')
        header, columns, data = table(sheets[sheet], {'Mode', 'Route No', 'Route Name'})
        months = {c: period(v, epoch, True) for c, v in header.items()
                  if v is not None and re.fullmatch(r'\d+(?:\.0)?|\d{4}-\d{2}', v)}
        if not months:
            raise ValueError('performance month columns missing')
        observed = 0
        for row in data:
            mode = str(row.get(columns['Mode'], '')).lower()
            if mode not in MODES:
                continue
            route = row.get(columns['Route No'])
            if route is None:
                raise ValueError('route number missing')
            for column, month in months.items():
                value = row.get(column)
                if value is None:
                    continue
                key = (mode, str(route), month)
                record = results.setdefault(key, {'mode': mode, 'route': str(route), 'route_name': row.get(columns['Route Name']),
                                                  'month': month, 'punctuality': None, 'reliability': None})
                if record[field] is not None:
                    raise ValueError('duplicate route performance observation')
                record[field] = number(value, ratio=True)
                observed += 1
        if not observed:
            raise ValueError(f'{sheet} contains no observations')
    return list(results.values())


METLINK_COLUMNS = ('day,route,scheduled_trips,reliability_numerator,reliability_denominator,reliability,'
    'punctuality_numerator,punctuality_denominator,punctuality,punctuality_contributing_percent,'
    'mean_departure_time_variance,cancellations,cancellations_rate,seated_capacity,license_capacity,'
    'trips_with_some_standing,trips_with_some_standing_rate,peak_scheduled_trips,peak_reliability_numerator,'
    'peak_reliability_denominator,peak_reliability,peak_punctuality_numerator,peak_punctuality_denominator,'
    'peak_punctuality,peak_punctuality_contributing_percent,peak_mean_departure_time_variance,peak_cancellations,'
    'peak_cancellations_rate,peak_seated_capacity,peak_license_capacity,peak_trips_with_some_standing,'
    'peak_trips_with_some_standing_rate,patronage,peak_patronage,offpeak_patronage,offpeak_patronage_percent').split(',')


def parse_metlink(body):
    reader = csv.DictReader(io.StringIO(body.decode('utf-8-sig')))
    if reader.fieldnames != METLINK_COLUMNS:
        raise ValueError('Metlink CSV column schema has changed')
    results = []
    for row in reader:
        if None in row or any(v is None for v in row.values()):
            raise ValueError('Metlink CSV row has the wrong number of fields')
        record = {'day': date.fromisoformat(row['day']).isoformat(), 'route': row['route']}
        if not record['route']:
            raise ValueError('Metlink route missing')
        for key in METLINK_COLUMNS[2:]:
            value = row[key]
            ratio = key.endswith(('_rate', '_percent')) or key in {'reliability', 'punctuality', 'peak_reliability', 'peak_punctuality'}
            floating = ratio or key.endswith('time_variance')
            record[key] = None if value == '' else number(value, integer=not floating, ratio=ratio)
        results.append(record)
    if not results:
        raise ValueError('Metlink CSV contains no observations')
    return results


def parse_inventory(payload):
    if 'error' in payload or not isinstance(payload.get('features'), list) or payload.get('exceededTransferLimit'):
        raise ValueError('parking inventory returned an error or incomplete features')
    records = []
    for feature in payload['features']:
        a = feature['attributes']
        if not {'OBJECTID', 'SHORTDESCRIPTION', 'AVAILABLESPACES', 'TOTALSPACES'} <= a.keys():
            raise ValueError('parking inventory fields have changed')
        geom = feature.get('geometry') or {}
        lon, lat = geom.get('x'), geom.get('y')
        if lon is None or lat is None or not (-180 <= lon <= 180 and -90 <= lat <= 90):
            raise ValueError('parking inventory WGS84 point missing or invalid')
        records.append({'id': a['OBJECTID'], 'name': a['SHORTDESCRIPTION'], 'suburb': a.get('SUBURB'),
                        'total_spaces': a['TOTALSPACES'], 'available_spaces': a['AVAILABLESPACES'],
                        'longitude': lon, 'latitude': lat,
                        'availability_status': 'undated_inventory_field' if a['AVAILABLESPACES'] is not None else 'not_reported'})
    if not records:
        raise ValueError('parking inventory has no features')
    return records
