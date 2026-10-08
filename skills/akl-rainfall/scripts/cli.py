#!/usr/bin/env python3
"""Read Auckland Council's anonymous AQUARIUS JSON exports (stdlib only)."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
import sys
import urllib.parse

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'lib'))
import nzfetch  # noqa: E402
from provenance import result_envelope, error_envelope, geojson_envelope

BASE = 'https://environmentauckland.org.nz'
PUBLISHER = 'Auckland Council'
LICENCE = 'Auckland Council copyright; sole use of recipient; attribution required; no redistribution without agreement'
MAX_RAW_POINTS = 5000
NZST = timezone(timedelta(hours=12))
# IDs and parameter names confirmed against Data_List on 2026-10-08.
PARAMETERS = {'rainfall': (78, 'Rainfall', 'mm', 332),
              'level': (40, 'River Water Level', 'm', 282),
              'flow': (82, 'River Discharge', 'm^3/s', 306)}
QUALITY = {'GradeCode': 'grade_code', 'GradeName': 'grade_name',
           'ApprovalLevel': 'approval_level', 'ApprovalName': 'approval_name',
           'Qualifiers': 'qualifiers', 'InterpolationType': 'interpolation_type',
           'InterpolationName': 'interpolation_name', 'Notes': 'notes'}


class SkillError(Exception):
    def __init__(self, message, code=6, retry_after=None):
        super().__init__(message)
        self.code = code
        self.retry_after = retry_after


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')


def provenance(url, retrieved_at, latest_data=None):
    result = {'source_url': url, 'publisher': PUBLISHER, 'licence': LICENCE,
              'retrieved_at': retrieved_at}
    if latest_data is not None:
        result['latest_data'] = latest_data
    return result


def timestamp(raw):
    """Naive portal metadata and CLI dates are fixed NZST, including summer."""
    try:
        value = datetime.fromisoformat(raw.replace('Z', '+00:00'))
    except (ValueError, AttributeError, TypeError):
        raise SkillError(f'invalid ISO date/time: {raw!r}', 2)
    return value.replace(tzinfo=NZST) if value.tzinfo is None else value.astimezone(NZST)


def source_time(raw):
    try:
        return timestamp(raw).isoformat()
    except SkillError:
        raise SkillError('source schema failure: invalid observation or record timestamp')


def bbox_type(raw):
    try:
        values = tuple(float(v) for v in raw.split(','))
        if len(values) != 4 or not all(math.isfinite(v) for v in values):
            raise ValueError
        west, south, east, north = values
        if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
            raise ValueError
        return values
    except ValueError:
        raise argparse.ArgumentTypeError('--bbox requires minLon,minLat,maxLon,maxLat in WGS84, ordered and finite')


def raw_point_limit(raw):
    try:
        limit = int(raw)
    except ValueError:
        raise argparse.ArgumentTypeError(f'--max-points must be an integer from 1 to {MAX_RAW_POINTS}')
    if not 1 <= limit <= MAX_RAW_POINTS:
        raise argparse.ArgumentTypeError(f'--max-points must be an integer from 1 to {MAX_RAW_POINTS}')
    return limit


def in_bbox(row, bbox):
    if bbox is None:
        return True
    lon, lat = row['longitude'], row['latitude']
    return lon is not None and lat is not None and bbox[0] <= lon <= bbox[2] and bbox[1] <= lat <= bbox[3]


def request_json(path, params, post=False):
    query = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    url = BASE + path if post else BASE + path + '?' + query
    try:
        result = nzfetch.fetch_json(BASE + path if post else url, timeout=10, allowed_hosts=['environmentauckland.org.nz'],
                                    method='POST' if post else 'GET',
                                    data=query.encode() if post else None,
                                    headers={'Content-Type': 'application/x-www-form-urlencoded'} if post else None)
    except nzfetch.RateLimited as exc:
        raise SkillError('network error: rate_limited', 4, exc.retry_after)
    except nzfetch.Blocked as exc:
        raise SkillError(f'network error: {exc}', 4)
    except nzfetch.FetchError as exc:
        if 'invalid JSON' in str(exc):
            raise SkillError('source schema failure: expected a non-empty JSON response')
        raise SkillError(f'upstream unavailable: {exc}', 5)
    return result, url


def parse_catalogue(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get('Data'), list) or type(payload.get('Total')) is not int:
        raise SkillError('source schema failure: expected Data_List Data array and integer Total')
    rows = []
    for item in payload['Data']:
        required = ('LocationIdentifier', 'Location', 'LocationId', 'DatasetId', 'DatasetIdentifier', 'EndOfRecord', 'StartOfRecord')
        if not isinstance(item, dict) or any(item.get(k) is None for k in required) or not isinstance(item.get('DatasetIdentifier'), str) or not isinstance(item.get('Location'), str):
            raise SkillError('source schema failure: incomplete monitoring dataset metadata')
        name = item['DatasetIdentifier'].split('.', 1)[0]
        parameter = next((k for k, v in PARAMETERS.items() if v[1] == name), None)
        if parameter is None:
            raise SkillError('source schema failure: unexpected parameter in monitoring catalogue')
        coords = []
        for field, limit in [('LocX', 180), ('LocY', 90)]:
            value = item.get(field)
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or abs(value) > limit):
                raise SkillError('source schema failure: invalid WGS84 monitoring coordinates')
            coords.append(value)
        end = source_time(item['EndOfRecord'])
        rows.append({'site': str(item['LocationIdentifier']), 'name': item['Location'],
                     'location_id': item['LocationId'], 'dataset_id': item['DatasetId'],
                     'dataset': item['DatasetIdentifier'], 'parameter': parameter,
                     'longitude': coords[0], 'latitude': coords[1],
                     'start_of_record': source_time(item['StartOfRecord']),
                     'end_of_record': end})
    return rows


def catalogue(parameter):
    keys = [parameter] if parameter else list(PARAMETERS)
    rows = []
    requests = []
    for page in range(1, 21):
        q = {'page': page, 'pageSize': 1000}
        q.update({f'parameters[{i}]': PARAMETERS[k][0] for i, k in enumerate(keys)})
        payload, url = request_json('/Data/Data_List', q, post=True)
        parsed = parse_catalogue(payload)
        rows.extend(parsed)
        requests.append({'source_url': url, 'method': 'POST', 'form': q})
        if len(rows) == payload['Total']:
            return rows, requests
        if not parsed or len(rows) > payload['Total']:
            raise SkillError('source schema failure: inconsistent catalogue pagination')
    raise SkillError('source catalogue exceeds bounded 20-page limit', 7)


def select_site(rows, site):
    matches = [r for r in rows if r['site'] == site or r['name'].casefold() == site.casefold()]
    if not matches:
        raise SkillError('unknown site or unavailable parameter; use sites to find its identifier', 2)
    if len({r['site'] for r in matches}) != 1:
        raise SkillError('ambiguous site name; use the site identifier from sites', 2)
    # Preserve the actual identifier, including the portal's one "Continous" label.
    return max(matches, key=lambda r: timestamp(r['end_of_record']))


def export_params(rows, start, end, interval=None):
    q = {'DateRange': 'Custom', 'StartTime': start.astimezone(NZST).strftime('%Y-%m-%d %H:%M'),
         'EndTime': end.astimezone(NZST).strftime('%Y-%m-%d %H:%M'), 'TimeZone': 12,
         'Calendar': 'CALENDARYEAR', 'Interval': {None: 'PointsAsRecorded', 'hour': 'Hourly', 'day': 'Daily'}[interval],
         'Step': 1, 'ExportFormat': 'json', 'TimeAligned': 'True', 'RoundData': 'False',
         'IncludeGradeCodes': 'True', 'IncludeApprovalLevels': 'True', 'IncludeQualifiers': 'True',
         'IncludeInterpolationTypes': 'True', 'IncludeNotes': 'False'}
    for i, row in enumerate(rows):
        q.update({f'Datasets[{i}].DatasetName': row['dataset'],
                  f'Datasets[{i}].Calculation': 'Aggregate' if interval else 'Instantaneous',
                  f'Datasets[{i}].UnitId': PARAMETERS[row['parameter']][3]})
    return q


def parse_export(payload, expected):
    if not isinstance(payload, dict) or not isinstance(payload.get('Datasets'), list) or not isinstance(payload.get('Rows'), list):
        raise SkillError('source schema failure: expected AQUARIUS Datasets and Rows arrays')
    if type(payload.get('NumRows')) is not int or payload['NumRows'] != len(payload['Rows']):
        raise SkillError('source schema failure: export row count differs from NumRows')
    metadata = {}
    for dataset in payload['Datasets']:
        if not isinstance(dataset, dict) or not isinstance(dataset.get('Identifier'), str):
            raise SkillError('source schema failure: incomplete exported dataset')
        key = dataset['Identifier']
        if key not in expected or key in metadata:
            raise SkillError('source schema failure: unexpected or duplicate exported dataset')
        parameter = expected[key]['parameter']
        if dataset.get('Parameter') != PARAMETERS[parameter][1] or dataset.get('Unit') != PARAMETERS[parameter][2] or str(dataset.get('LocationIdentifier')) != expected[key]['site']:
            raise SkillError('source schema failure: exported parameter, site or unit differs from request')
        metadata[key] = dataset
    if set(metadata) != set(expected):
        raise SkillError('source schema failure: requested dataset absent from export')
    result = {key: [] for key in metadata}
    for row in payload['Rows']:
        if not isinstance(row, dict) or not isinstance(row.get('Points'), list):
            raise SkillError('source schema failure: invalid export row')
        when = source_time(row.get('Timestamp'))
        seen = set()
        for point in row['Points']:
            if not isinstance(point, dict) or point.get('Dataset') not in metadata or point['Dataset'] in seen or 'Value' not in point:
                raise SkillError('source schema failure: invalid or duplicate observation dataset')
            key = point['Dataset']
            seen.add(key)
            value = point['Value']
            # AQUARIUS represents missing aggregate boundary values as the JSON
            # string "NaN". Keep its meaning as null, never zero or JSON NaN.
            missing_marker = value == 'NaN'
            if missing_marker:
                value = None
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)):
                raise SkillError('source schema failure: observation value must be finite or null')
            result[key].append({'time': when, 'value': value, 'units': metadata[key]['Unit'],
                                'missing': value is None, 'source_missing_marker': 'NaN' if missing_marker else None,
                                **{v: point.get(k) for k, v in QUALITY.items()}})
    for points in result.values():
        points.sort(key=lambda r: timestamp(r['time']))
        if len({r['time'] for r in points}) != len(points):
            raise SkillError('source schema failure: duplicate observation timestamps')
    return result


def export(rows, start, end, interval):
    q = export_params(rows, start, end, interval)
    # This public endpoint supports read-only POST for bulk requests, without cookies.
    payload, url = request_json('/Export/BulkExportJsonFile', q, post=len(rows) > 1)
    points = parse_export(payload, {r['dataset']: r for r in rows})
    # Aquarius includes boundary/preceding points; honour the requested inclusive window.
    points = {key: [p for p in values if start <= timestamp(p['time']) <= end] for key, values in points.items()}
    if interval:
        duration = timedelta(hours=1) if interval == 'hour' else timedelta(days=1)
        for values in points.values():
            for point in values:
                point['period_end'] = point['time']
                point['period_start'] = (timestamp(point['time']) - duration).isoformat()
    return points, url


def group_sites(rows):
    sites = {}
    for row in rows:
        if row['site'] not in sites:
            sites[row['site']] = {k: row[k] for k in ['site', 'name', 'longitude', 'latitude', 'end_of_record']}
            sites[row['site']]['datasets'] = []
        sites[row['site']]['datasets'].append(row)
        sites[row['site']]['end_of_record'] = max(sites[row['site']]['end_of_record'], row['end_of_record'])
    return sorted(sites.values(), key=lambda r: (r['name'].casefold(), r['site']))


def as_geojson(payload):
    return geojson_envelope([
        {'type': 'Feature', 'id': row['site'],
         'geometry': {'type': 'Point', 'coordinates': [row['longitude'], row['latitude']]} if row['longitude'] is not None and row['latitude'] is not None else None,
         'properties': row} for row in payload['results']], payload['meta'])


def command(args):
    retrieved_at = utc_now()
    if args.command == 'series':
        start, end = timestamp(args.start), timestamp(args.end)
        if start >= end or end - start > timedelta(days=31):
            raise SkillError('--from must precede --to; request at most 31 days', 2)
        if start.second or start.microsecond or end.second or end.microsecond:
            raise SkillError('date/time boundaries must have minute precision (zero seconds)', 2)
    rows, requests = catalogue(args.parameter)
    sources = [request['source_url'] for request in requests]
    warnings = ['Council data is provisional; retain quality fields and attribute Auckland Council.']
    if args.command == 'sites':
        selected = [r for r in rows if in_bbox(r, args.bbox)]
        records = group_sites(selected)
        payload = {'kind': 'sites', 'parameter': args.parameter, 'count': len(records),
                   'dataset_count': len(selected), 'source_urls': sources,
                   'request': {k: v for k, v in requests[0].items() if k != 'source_url'},
                   'catalogue_requests': requests,
                   **provenance(sources[0], retrieved_at, max((r['end_of_record'] for r in selected), default=None))}
    elif args.command == 'series':
        row = select_site(rows, args.site)
        points, url = export([row], start, end, args.interval)
        records = points[row['dataset']]
        if not args.interval and len(records) > args.max_points:
            raise SkillError(f'raw series exceeds {args.max_points} points; use --interval hour|day or a shorter window', 2)
        if end < timestamp(row['start_of_record']) or start > timestamp(row['end_of_record']):
            warnings.append(f"requested window is outside this dataset's record ({row['start_of_record']}..{row['end_of_record']})")
        payload = {'kind': 'series', 'site': row['site'], 'name': row['name'], 'dataset': row['dataset'],
                   'parameter': args.parameter, 'from': start.isoformat(), 'to': end.isoformat(),
                   'interval': args.interval or 'points_as_recorded',
                   'aggregation': ('preceding interval total' if args.parameter == 'rainfall' else 'preceding interval average') if args.interval else 'as recorded',
                   'count': len(records), 'source_urls': [*sources, url],
                   'catalogue_requests': requests,
                   **provenance(url, retrieved_at, row['end_of_record'])}
    else:
        end = datetime.now(NZST).replace(second=0, microsecond=0)
        start = end - timedelta(hours=72)
        spatial = [r for r in rows if in_bbox(r, args.bbox)]
        active = [r for r in spatial if timestamp(r['end_of_record']) >= start]
        # Recorded rainfall cadences differ (e.g. hourly versus five-minute).
        # The portal returns empty bodies for mixed-cadence time-aligned exports;
        # request each exact recorded series independently to retain its meaning.
        batches = [[row] for row in active]
        records = []
        # Four bounded read requests at a time; a failed batch fails the whole command.
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda batch: export(batch, start, end, None), batches))
        for batch, (points, url) in zip(batches, results):
            sources.append(url)
            for row in batch:
                valid = [p for p in points[row['dataset']] if p['value'] is not None]
                if not valid:
                    continue
                latest = valid[-1]
                age = round((end - timestamp(latest['time'])).total_seconds() / 3600, 2)
                records.append({**row, **latest, 'source_url': url, 'age_hours': age, 'stale': age > 24})
        records.sort(key=lambda r: (r['name'].casefold(), r['site']))
        payload = {'kind': 'latest', 'parameter': 'rainfall', 'count': len(records),
                   'lookback_hours': 72, 'matching_sites': len(spatial),
                   'outside_lookback_sites': len(spatial) - len(active),
                   'sites_without_values': len(active) - len(records), 'source_urls': sources,
                   'catalogue_requests': requests,
                   'meaning': 'Latest non-null recorded rainfall increment per gauge; not a 24-hour total',
                   **provenance(BASE + '/Export/BulkExportJsonFile', retrieved_at,
                                max((r['time'] for r in records), default=None))}
    payload['timezone'] = 'NZ Standard Time (UTC+12), fixed year-round'
    payload['warnings'] = warnings
    payload = result_envelope(records, payload)
    if args.command in ('sites', 'latest') and args.format == 'geojson':
        payload = as_geojson(payload)
    return payload


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise SkillError(message, 2)


def build_parser():
    parser = Parser(description='Query Auckland Council rainfall and river monitoring JSON exports')
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ['sites', 'series', 'latest']:
        p = sub.add_parser(name)
        p.add_argument('--json', action='store_true', help='emit JSON with provenance and quality fields')
        if name == 'sites':
            p.add_argument('--parameter', choices=PARAMETERS, help='filter parameter; default all three')
        else:
            p.add_argument('--parameter', required=True, choices=['rainfall'] if name == 'latest' else PARAMETERS)
        if name in ('sites', 'latest'):
            p.add_argument('--bbox', type=bbox_type, help='WGS84 minLon,minLat,maxLon,maxLat')
            p.add_argument('--format', choices=['json', 'geojson'], default=None, help='explicit format implies machine-readable output')
        else:
            p.add_argument('--site', required=True, help='site identifier or exact name from sites')
            p.add_argument('--from', dest='start', required=True, help='ISO date/time; naive values use fixed UTC+12')
            p.add_argument('--to', dest='end', required=True, help='inclusive ISO end date/time; at most 31 days')
            p.add_argument('--interval', choices=['hour', 'day'], help='Council totals for rainfall; averages for level/flow')
            p.add_argument('--max-points', type=raw_point_limit, default=MAX_RAW_POINTS, help=f'raw output limit, 1–{MAX_RAW_POINTS}; default {MAX_RAW_POINTS}')
    return parser


def machine_mode(argv):
    return ('--json' in argv or any(arg in ('--format=json', '--format=geojson') for arg in argv)
            or any(arg == '--format' and argv[i + 1] in ('json', 'geojson')
                   for i, arg in enumerate(argv[:-1])))


def main():
    machine = machine_mode(sys.argv[1:])
    try:
        args = build_parser().parse_args()
        payload = command(args)
        if machine:
            print(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False))
        else:
            meta = payload['meta']
            print(f"{PUBLISHER} {meta['kind']}: {meta['count']} records (NZST, UTC+12)")
            for row in payload['results']:
                if meta['kind'] == 'sites':
                    print(f"{row['site']}  {row['name']}  ({row['longitude']}, {row['latitude']})")
                else:
                    print(f"{row.get('site', meta.get('site', ''))}  {row['time']}  {row['value']} {row['units']}  {row.get('grade_name') or ''}")
        return 0
    except SkillError as exc:
        if machine:
            payload = error_envelope(exc.code, str(exc), provenance(BASE, utc_now()), retry_after=exc.retry_after)
            print(json.dumps(payload, ensure_ascii=False))
        print(f'akl-rainfall: {exc}', file=sys.stderr)
        return exc.code


if __name__ == '__main__':
    raise SystemExit(main())
