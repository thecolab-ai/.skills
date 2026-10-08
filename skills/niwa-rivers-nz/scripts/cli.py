#!/usr/bin/env python3
"""Keyless NIWA freshwater metadata and public WFS surveys (stdlib only)."""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import unicodedata
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlencode, urlparse

from provenance import (add_spatial_arguments, error_envelope, geojson_envelope,
                        provenance, result_envelope)

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'lib'))
import nzfetch  # noqa: E402

PUBLISHER = 'Earth Sciences New Zealand (NIWA)'
SOURCE_URL = 'https://data.niwa.co.nz/products/hydro-data-hourly'
FLOOD_URL = 'https://data.niwa.co.nz/products/100-year-flood-maps'
RIVERS_URL = 'https://shiny.niwa.co.nz/nzrivermaps/'
FILES_URL = 'https://d17fc0a885.execute-api.ap-southeast-2.amazonaws.com/dev/api/data-files'
WFS_URL = 'https://geoserver.niwa.co.nz/fpat/wfs'
REGIONS_URL = 'https://geoserver.niwa.co.nz/niwa/wfs'
ALLOWED_HOSTS = {'data.niwa.co.nz', 'shiny.niwa.co.nz', 'geoserver.niwa.co.nz',
                 'd17fc0a885.execute-api.ap-southeast-2.amazonaws.com'}
REGIONS = ('Northland', 'Auckland', 'Waikato', 'Bay of Plenty', 'Gisborne',
           "Hawke's Bay", 'Taranaki', 'Manawatu-Whanganui', 'Wellington',
           'Tasman', 'Nelson', 'Marlborough', 'West Coast', 'Canterbury',
           'Otago', 'Southland')
HOURLY_LICENCE = 'DataHub Non-commercial use; redistribution/rehosting restricted'
FLOOD_LICENCE = 'CC BY-NC 4.0 (non-commercial option); commercial restricted terms also offered'
RIVERS_LICENCE = 'Creative Commons Attribution 3.0 New Zealand (unless stated otherwise)'
FPAT_LICENCE = 'CC BY 4.0'


class Failure(Exception):
    def __init__(self, code, message, *, retry_after=None):
        super().__init__(message)
        self.code, self.retry_after = code, retry_after


class InputError(ValueError):
    pass


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise InputError(message)


def region_key(value):
    return re.sub(r'[^a-z]', '', unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode().lower())


def region_name(value):
    key = region_key(value)
    aliases = {'manawatuwanganui': 'Manawatu-Whanganui', 'nzauk': 'Auckland'}
    if key in aliases:
        return aliases[key]
    for name in REGIONS:
        if region_key(name) == key:
            return name
    raise argparse.ArgumentTypeError('--region must be one of: ' + ', '.join(REGIONS))


def point(value):
    try:
        coordinates = tuple(float(part) for part in value.split(','))
    except ValueError as exc:
        raise argparse.ArgumentTypeError('--near must be lon,lat in WGS84') from exc
    if (len(coordinates) != 2 or not all(math.isfinite(v) for v in coordinates)
            or not -180 <= coordinates[0] <= 180 or not -90 <= coordinates[1] <= 90):
        raise argparse.ArgumentTypeError('--near must be finite lon,lat within WGS84 bounds')
    return coordinates


def positive_limit(value):
    try:
        n = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError('--limit must be an integer from 1 to 1000') from exc
    if not 1 <= n <= 1000:
        raise argparse.ArgumentTypeError('--limit must be an integer from 1 to 1000')
    return n


def instant(value):
    try:
        date = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise argparse.ArgumentTypeError('dates must be ISO 8601 dates or timestamps with a timezone') from exc
    if len(value) == 10:
        date = date.replace(tzinfo=timezone.utc)
    elif date.tzinfo is None:
        raise argparse.ArgumentTypeError('timestamps require a timezone; plain dates use UTC')
    return date.astimezone(timezone.utc)


def fetch(url, *, as_json=True):
    if urlparse(url).scheme != 'https' or urlparse(url).hostname not in ALLOWED_HOSTS:
        raise Failure(2, 'source URL is outside the declared public host allowlist')
    try:
        return nzfetch.fetch_json(url, timeout=10, allowed_hosts=ALLOWED_HOSTS) if as_json else nzfetch.fetch_text(url, timeout=10, allowed_hosts=ALLOWED_HOSTS)
    except nzfetch.RateLimited as exc:
        raise Failure(4, 'network error: rate limited', retry_after=exc.retry_after) from exc
    except nzfetch.Blocked as exc:
        raise Failure(4, 'network error: access blocked by upstream') from exc
    except nzfetch.FetchError as exc:
        message = str(exc)
        if 'invalid JSON' in message or 'HTTP 400' in message:
            raise Failure(6, 'source schema failure: upstream rejected query or returned invalid JSON') from exc
        if 'HTTP 401' in message:
            raise Failure(4, 'access blocked: this source requires authentication') from exc
        raise Failure(5, 'network error: ' + message) from exc
    except (ValueError, TypeError) as exc:
        raise Failure(6, 'source schema failure: invalid JSON response') from exc


def decode_astro(value):
    """Decode observed Astro prop tags: 0=ordinary, 1=array, 3=Date."""
    if isinstance(value, list):
        if len(value) != 2 or value[0] not in (0, 1, 3):
            raise Failure(6, 'source schema failure: unsupported Astro prop encoding')
        tag, data = value
        if tag == 1:
            if not isinstance(data, list):
                raise Failure(6, 'source schema failure: Astro array is not a list')
            return [decode_astro(item) for item in data]
        return decode_astro(data) if isinstance(data, dict) else data
    if isinstance(value, dict):
        return {key: decode_astro(item) for key, item in value.items()}
    return value


class ProductPage(HTMLParser):
    """Read only the public product catalogue island; ignore account/settings props."""
    def __init__(self):
        super().__init__()
        self.catalogue = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'astro-island' and 'SubcategoriesMain.' in attrs.get('component-url', ''):
            try:
                props = json.loads(attrs['props'])
                self.catalogue = {key: decode_astro(props[key]) for key in ('products', 'total', 'page')}
            except (KeyError, ValueError) as exc:
                raise Failure(6, 'source schema failure: missing public product catalogue props') from exc


def parse_products(html):
    parser = ProductPage()
    parser.feed(html)
    page = parser.catalogue
    if (not isinstance(page, dict) or not isinstance(page.get('products'), list)
            or type(page.get('total')) is not int or type(page.get('page')) is not int
            or page['total'] < 0 or page['page'] < 1):
        raise Failure(6, 'source schema failure: DataHub page has no valid public product catalogue')
    for record in page['products']:
        if (not isinstance(record, dict) or not isinstance(record.get('id'), str)
                or not isinstance(record.get('metadata'), dict)
                or not isinstance(record['metadata'].get('title'), str)):
            raise Failure(6, 'source schema failure: malformed product metadata')
    return page


def product_listing(base, region=None):
    rows, seen, total = [], set(), None
    for page_number in range(1, 11):
        params = {'page': page_number}
        if region:
            params['region'] = region
        url = base + '?' + urlencode(params)
        data = parse_products(fetch(url, as_json=False))
        if data['page'] != page_number:
            raise Failure(6, 'source schema failure: DataHub ignored pagination')
        total = data['total']
        for row in data['products']:
            if row['id'] in seen:
                raise Failure(6, 'source schema failure: duplicate product across pages')
            seen.add(row['id'])
            rows.append({**row, 'source_url': url})
        if len(rows) >= total:
            if len(rows) != total:
                raise Failure(6, 'source schema failure: catalogue total differs from product count')
            return rows, total
        if not data['products']:
            raise Failure(6, 'source schema failure: catalogue pagination ended before total')
    raise Failure(7, 'catalogue exceeds the bounded 10-page limit; narrow the region')


def positions(geometry):
    if not isinstance(geometry, dict):
        raise Failure(6, 'source schema failure: missing spatial geometry')
    def walk(values):
        if not isinstance(values, list) or not values:
            raise Failure(6, 'source schema failure: malformed spatial coordinates')
        if isinstance(values[0], (float, int)):
            if (len(values) < 2 or not all(type(v) in (float, int) and math.isfinite(v) for v in values)
                    or not -180 <= values[0] <= 180 or not -90 <= values[1] <= 90):
                raise Failure(6, 'source schema failure: coordinates are not WGS84 lon,lat')
            yield values[:2]
        else:
            for item in values:
                yield from walk(item)
    return list(walk(geometry.get('coordinates')))


def intersects_bbox(geometry, bbox):
    coordinates = positions(geometry)
    xs, ys = zip(*coordinates)
    return max(xs) >= bbox[0] and min(xs) <= bbox[2] and max(ys) >= bbox[1] and min(ys) <= bbox[3]


def in_ring(lon, lat, ring):
    inside = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        if (y1 > lat) != (y2 > lat) and lon < (x2-x1)*(lat-y1)/(y2-y1)+x1:
            inside = not inside
    return inside


def in_region(coordinates, geometry):
    polygons = [geometry['coordinates']] if geometry['type'] == 'Polygon' else geometry['coordinates']
    lon, lat = coordinates[:2]
    return any(in_ring(lon, lat, polygon[0]) and not any(in_ring(lon, lat, hole) for hole in polygon[1:])
               for polygon in polygons)


def wfs_query(base, typename, *, count=1000, bbox=None, start=0):
    params = {'service': 'WFS', 'version': '2.0.0', 'request': 'GetFeature',
              'typeNames': typename, 'outputFormat': 'application/json',
              'srsName': 'urn:ogc:def:crs:OGC:1.3:CRS84', 'count': count, 'startIndex': start}
    if typename == 'fpat:fpat_surveys':
        params['sortBy'] = 'id'  # WFS paging requires an explicit sort for this view
    if bbox:
        params['bbox'] = ','.join(str(v) for v in bbox) + ',urn:ogc:def:crs:OGC:1.3:CRS84'
    return base + '?' + urlencode(params)


def parse_features(data):
    if not isinstance(data, dict) or data.get('type') != 'FeatureCollection' or not isinstance(data.get('features'), list):
        raise Failure(6, 'source schema failure: WFS did not return a FeatureCollection')
    for feature in data['features']:
        if not isinstance(feature, dict) or feature.get('type') != 'Feature' or not isinstance(feature.get('properties'), dict):
            raise Failure(6, 'source schema failure: malformed WFS feature')
        positions(feature.get('geometry'))
    total = data.get('numberMatched', data.get('totalFeatures'))
    if type(total) is not int or total < len(data['features']):
        raise Failure(6, 'source schema failure: missing or invalid WFS numberMatched')
    return data['features'], total


def region_geometry(region):
    url = wfs_query(REGIONS_URL, 'niwa:regional_council_gen', count=20)
    features, total = parse_features(fetch(url))
    if total > len(features):
        raise Failure(6, 'source schema failure: regional boundary response is incomplete')
    for feature in features:
        council = feature['properties'].get('regc2013_n')
        if isinstance(council, str):
            council = council.removesuffix(' Region')
        if isinstance(council, str) and region_key(council.replace('Wanganui', 'Whanganui')) == region_key(region):
            if feature['geometry']['type'] not in ('Polygon', 'MultiPolygon'):
                raise Failure(6, 'source schema failure: region is not a polygon')
            return feature['geometry'], url
    raise Failure(6, 'source schema failure: requested council missing from boundary layer')


def record_meta(url, licence=None, latest=None):
    return provenance(url, PUBLISHER, licence=licence, latest_data=latest)


def product_record(row, kind):
    data = row['metadata']
    for field in ('description', 'region', 'dateMin', 'dateMax', 'updatedAt'):
        if data.get(field) is not None and not isinstance(data[field], str):
            raise Failure(6, 'source schema failure: product metadata field is not text: ' + field)
    geometry = data.get('geojson')
    if geometry is not None:
        positions(geometry)
    latest = data.get('dateMax') if kind == 'hourly_series_metadata' else data.get('updatedAt')
    result = {'product_id': row['id'], 'title': data['title'], 'description': data.get('description'),
              'region': data.get('region'), 'geometry': geometry, 'data_kind': kind,
              'from': data.get('dateMin'), 'to': data.get('dateMax'), 'catalogue_updated_at': data.get('updatedAt'),
              **record_meta(row['source_url'], HOURLY_LICENCE if kind == 'hourly_series_metadata' else FLOOD_LICENCE, latest)}
    if kind == 'hourly_series_metadata':
        title = re.fullmatch(r'Station: (.+), parameter: (.+)', data['title'])
        station = re.search(r'station-id:\s*(\d+)', data.get('description') or '')
        if not title or not station or geometry is None or geometry.get('type') != 'Point':
            raise Failure(6, 'source schema failure: hourly listing has no station/parameter/point')
        result.update(station=station.group(1), name=title.group(1), parameter=title.group(2),
                      geometry_role='station_location', observations_available=False)
    else:
        if geometry is None or geometry.get('type') != 'Polygon':
            raise Failure(6, 'source schema failure: flood listing has no coverage polygon')
        result.update(geometry_role='product_coverage_bbox', hazard_values_available=False,
                      warning='Coverage footprint only: not an inundation extent or flood depth polygon.')
    return result


def spatial_output(rows, meta, args):
    if args.format == 'geojson':
        features = [{'type': 'Feature', 'id': row.get('product_id', row.get('id', row.get('nzsegment'))),
                     'geometry': row['geometry'], 'properties': {k: v for k, v in row.items() if k != 'geometry'}}
                    for row in rows]
        return geojson_envelope(features, meta)
    return result_envelope(rows, meta)


def cmd_stations(args):
    rows, total = product_listing(SOURCE_URL)
    records = [product_record(row, 'hourly_series_metadata') for row in rows]
    meta = record_meta(SOURCE_URL, HOURLY_LICENCE)
    meta.update(data_kind='hourly_series_metadata', source_total=total,
                warning='Station/parameter catalogue only. Hourly observations require a DataHub account.')
    dates = [row['latest_data'] for row in records if row.get('latest_data')]
    if dates:
        meta['latest_data'] = max(dates)
        meta['latest_data_meaning'] = 'Newest stated series end across the source catalogue, not retrieval time'
    if args.bbox:
        records = [row for row in records if intersects_bbox(row['geometry'], args.bbox)]
    if args.region:
        boundary, url = region_geometry(args.region)
        records = [row for row in records if in_region(row['geometry']['coordinates'], boundary)]
        meta['region_boundary_source_url'] = url
        meta['region_filter'] = args.region
    meta.update(returned=len(records), unique_stations=len({row['station'] for row in records}), truncated=False)
    return spatial_output(records, meta, args)


def cmd_flow(args):
    if not re.fullmatch(r'\d+', args.station):
        raise Failure(2, '--station must be the numeric station ID from stations')
    if args.date_from and args.date_to and args.date_from > args.date_to:
        raise Failure(2, '--from must be before or equal to --to')
    raise Failure(4, 'Hourly river observations are account-gated. DataHub requires X-Customer-ID and Authorization; '
                  'the keyless endpoint returned HTTP 401 on 2026-10-08. Use stations for series metadata; '
                  'use lawa-nz or gwrc-hilltop-nz for their supported observations. No credentials are accepted.')


def cmd_rivers(args):
    import rivermaps
    lon, lat = args.near
    delta_y = args.radius_km / 111.32
    scale = math.cos(math.radians(lat))
    if abs(scale) < 0.001:
        raise Failure(2, '--near must be away from the poles')
    delta_x = delta_y / scale
    bbox = args.bbox or (lon-delta_x, lat-delta_y, lon+delta_x, lat+delta_y)
    if not (-180 <= bbox[0] < bbox[2] <= 180 and -90 <= bbox[1] < bbox[3] <= 90):
        raise Failure(2, 'search box crosses WGS84 bounds; supply --bbox')
    try:
        rows, description, visibility = rivermaps.query(bbox, args.metric)
    except rivermaps.RiverMapsError as exc:
        raise Failure(exc.code, str(exc), retry_after=exc.retry_after) from exc
    records = [row for row in rows if intersects_bbox(row['geometry'], bbox)]
    for row in records:
        row['distance_km'] = round(rivermaps.distance_km(args.near, row['geometry']), 4)
        row['data_kind'] = 'static_modelled_river_metric'
    records.sort(key=lambda row: (row['distance_km'], row['nzsegment']))
    meta = record_meta(RIVERS_URL, RIVERS_LICENCE)
    meta.update(data_kind='static_modelled_river_metric', near=list(args.near), search_bbox=list(bbox),
                metric=args.metric, metric_description=description, visibility=visibility,
                matched_in_box=len(records), returned=min(len(records), args.limit),
                truncated=len(records) > args.limit,
                warning='Static national model estimates at displayed precision, not observations or flood forecasts.')
    return spatial_output(records[:args.limit], meta, args)


def cmd_flood(args):
    rows, total = product_listing(FLOOD_URL, args.region)
    records = [product_record(row, 'flood_product_metadata') for row in rows]
    if any(row['region'] != args.region for row in records):
        raise Failure(6, 'source schema failure: DataHub did not apply the requested region')
    if args.bbox:
        records = [row for row in records if intersects_bbox(row['geometry'], args.bbox)]
    meta = record_meta(FLOOD_URL + '?' + urlencode({'region': args.region}), FLOOD_LICENCE)
    dates = [row['latest_data'] for row in records if row.get('latest_data')]
    if dates:
        meta['latest_data'] = max(dates)
    meta.update(data_kind='flood_product_metadata', source_total=total, returned=len(records), truncated=False,
                warning='Product coverage footprints only. Hazard rasters require an account/licence; no hazard values returned.',
                latest_data_meaning='Catalogue metadata update, not modelled flood event date')
    return spatial_output(records, meta, args)


def cmd_fish(args):
    url = wfs_query(WFS_URL, 'fpat:fpat_surveys', count=args.limit, bbox=args.bbox, start=args.offset)
    features, total = parse_features(fetch(url))
    meta = record_meta(url, FPAT_LICENCE)
    meta.update(data_kind='fish_passage_surveys', number_matched=total, returned=len(features), offset=args.offset,
                truncated=total > args.offset + len(features),
                warning='Survey coverage is uneven; fish passage risk is not flood conveyance capacity.')
    # timeStamp is the response time, not a latest observation date.
    for feature in features:
        properties = feature['properties']
        if not isinstance(properties.get('structure_type'), str) or 'recorded_date' not in properties:
            raise Failure(6, 'source schema failure: survey lacks structure_type or recorded_date')
        if feature['geometry'].get('type') != 'Point':
            raise Failure(6, 'source schema failure: survey geometry is not a point')
    if args.format == 'geojson':
        return geojson_envelope(features, meta)
    return result_envelope(features, meta)


def cmd_sources(args):
    # A maintained source directory: retrieved_at refers to the directory read, not a live observation.
    descriptors = [
        ('hourly', SOURCE_URL, HOURLY_LICENCE, 'public_metadata_account_gated_download', 'stations',
         'Public series listings; hourly data-file API requires an account. New Zealand coverage is sparse.'),
        ('river-maps', RIVERS_URL, RIVERS_LICENCE, 'keyless_shiny_query', 'rivers',
         'Static hydrology metrics at displayed precision via the public Shiny interface.'),
        ('flood-hazard', FLOOD_URL, FLOOD_LICENCE, 'public_metadata_account_gated_download', 'flood-hazard',
         'Regional ZIP listings and coverage footprints; actual 4 m hazard rasters are account-gated.'),
        ('fish-passage', WFS_URL, FPAT_LICENCE, 'keyless_wfs', 'fish-passage',
         'Public instream structure surveys; not a complete structure inventory.'),
    ]
    rows = [{'id': name, 'access': access, 'command': command, 'caveat': caveat,
             'verified_on': '2026-10-08', **record_meta(url, licence)}
            for name, url, licence, access, command, caveat in descriptors]
    return result_envelope(rows, {**record_meta(SOURCE_URL), 'data_kind': 'maintained_source_directory'})


def build_parser():
    parser = ArgumentParser(description='Keyless NIWA river catalogue, flood product coverage and Fish Passage surveys')
    sub = parser.add_subparsers(dest='command', required=True)
    sources = sub.add_parser('sources', help='list verified freshwater sources and access limits')
    sources.set_defaults(func=cmd_sources)
    stations = sub.add_parser('stations', help='hourly station/parameter metadata, without observations')
    stations.add_argument('--region', type=region_name)
    add_spatial_arguments(stations)
    stations.set_defaults(func=cmd_stations)
    flow = sub.add_parser('flow', help='report account gate for hourly observations (exit 4)')
    flow.add_argument('--station', required=True)
    flow.add_argument('--from', dest='date_from', type=instant)
    flow.add_argument('--to', dest='date_to', type=instant)
    flow.set_defaults(func=cmd_flow)
    rivers = sub.add_parser('rivers', help='query static River Maps hydrology metrics near a point')
    rivers.add_argument('--near', required=True, type=point)
    add_spatial_arguments(rivers)
    import rivermaps
    rivers.add_argument('--metric', choices=rivermaps.METRICS, default='Mean Flow')
    rivers.add_argument('--limit', type=positive_limit, default=5)
    rivers.add_argument('--radius-km', type=float, default=5, help='half-size of default search box (0.1–10 km)')
    rivers.set_defaults(func=cmd_rivers)
    flood = sub.add_parser('flood-hazard', help='regional flood product metadata and coverage footprints')
    flood.add_argument('--region', required=True, type=region_name)
    add_spatial_arguments(flood)
    flood.set_defaults(func=cmd_flood)
    fish = sub.add_parser('fish-passage', help='query public instream structure assessments')
    add_spatial_arguments(fish)
    fish.add_argument('--limit', type=positive_limit, default=100)
    fish.add_argument('--offset', type=int, default=0)
    fish.set_defaults(func=cmd_fish)
    for command in (sources, stations, flow, rivers, flood, fish):
        command.add_argument('--json', action='store_true', help='emit provenance and machine-readable JSON')
    return parser


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    machine = '--json' in argv or '--format=geojson' in argv or any(
        argv[i:i+2] == ['--format', 'geojson'] for i in range(len(argv)))
    licence = {'flow': HOURLY_LICENCE, 'rivers': RIVERS_LICENCE, 'flood-hazard': FLOOD_LICENCE,
               'fish-passage': FPAT_LICENCE, 'stations': HOURLY_LICENCE}.get(argv[0] if argv else '')
    source = {'flow': FILES_URL, 'rivers': RIVERS_URL, 'flood-hazard': FLOOD_URL,
              'fish-passage': WFS_URL}.get(argv[0] if argv else '', SOURCE_URL)
    try:
        args = build_parser().parse_args(argv)
        if args.command == 'rivers' and (not math.isfinite(args.radius_km) or not 0.1 <= args.radius_km <= 10):
            raise Failure(2, '--radius-km must be finite and from 0.1 to 10')
        if getattr(args, 'offset', 0) < 0:
            raise Failure(2, '--offset must be non-negative')
        payload = args.func(args)
    except (InputError, Failure) as exc:
        code = exc.code if isinstance(exc, Failure) else 2
        if machine:
            print(json.dumps(error_envelope(code, str(exc), record_meta(source, licence),
                                           retry_after=getattr(exc, 'retry_after', None)), ensure_ascii=False))
        else:
            print('niwa-rivers-nz: ' + str(exc), file=sys.stderr)
        return code
    if machine:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        if payload['meta'].get('warning'):
            print(payload['meta']['warning'])
        rows = payload.get('results', payload.get('features', []))
        print(f'{len(rows)} record(s) from {payload["meta"]["source_url"]}')
        for row in rows:
            values = row.get('properties', row)
            print(' | '.join(str(values[key]) for key in ('id', 'station', 'title', 'structure_type', 'recorded_date', 'access') if key in values))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
