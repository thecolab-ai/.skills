#!/usr/bin/env python3
"""Discover public NZ datasets through OGC Records and CKAN catalogues."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from html.parser import HTMLParser
import json
import math
from pathlib import Path
import re
import sys
from urllib.error import HTTPError
from urllib.parse import quote, urlencode, urlsplit, urlunsplit

from provenance import ERROR_TYPES, provenance as build_provenance, result_envelope, error_envelope, geojson_envelope

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'lib'))
import nzfetch  # noqa: E402

CATALOGUES = {
    'auckland-council': {
        'publisher': 'Auckland Council', 'kind': 'ogc-records',
        'source_url': 'https://data-aucklandcouncil.opendata.arcgis.com/api/search/v1/collections/dataset/items',
    },
    'auckland-transport': {
        'publisher': 'Auckland Transport', 'kind': 'ogc-records',
        'source_url': 'https://data-atgis.opendata.arcgis.com/api/search/v1/collections/dataset/items',
    },
    'waka-kotahi': {
        'publisher': 'NZ Transport Agency Waka Kotahi', 'kind': 'ogc-records',
        'source_url': 'https://opendata-nzta.opendata.arcgis.com/api/search/v1/collections/dataset/items',
    },
    'niwa': {
        'publisher': 'Earth Sciences New Zealand (NIWA)', 'kind': 'ogc-records',
        'source_url': 'https://data-niwa.opendata.arcgis.com/api/search/v1/collections/dataset/items',
    },
    'data-govt-nz': {
        'publisher': 'data.govt.nz', 'kind': 'ckan',
        'source_url': 'https://catalogue.data.govt.nz/api/3/action/',
    },
}
ALLOWED_HOSTS = {urlsplit(c['source_url']).hostname for c in CATALOGUES.values()}


class SourceError(Exception):
    def __init__(self, message, code=6, category='schema_failure', retry_after=None):
        super().__init__(message)
        self.code = code
        self.category = ERROR_TYPES[code]
        self.retry_after = retry_after


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')


def provenance(url, publisher, retrieved_at, licence=None, latest_data=None):
    return build_provenance(url, publisher, retrieved_at=retrieved_at, licence=licence, latest_data=latest_data)


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def text(value):
    if not value:
        return None
    parser = PlainText()
    parser.feed(str(value))
    return ' '.join(' '.join(parser.parts).split())


def iso_date(value):
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return datetime.fromtimestamp(value / 1000, timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')
        except (ValueError, OverflowError, OSError) as exc:
            raise SourceError('Invalid catalogue modification timestamp') from exc
    if isinstance(value, str):
        try:
            date = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if date.tzinfo is None:
                date = date.replace(tzinfo=timezone.utc)
            return date.astimezone(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')
        except ValueError as exc:
            raise SourceError('Invalid catalogue modification timestamp') from exc
    raise SourceError('Unexpected catalogue date format')


def fetch_json(url, *, record_catalogue=None):
    try:
        data = nzfetch.fetch_json(url, timeout=10, allowed_hosts=ALLOWED_HOSTS,
                                  max_bytes=8_000_000)
    except nzfetch.RateLimited as exc:
        raise SourceError('network error: rate limited', 4, 'rate_limited', exc.retry_after) from exc
    except nzfetch.Blocked as exc:
        raise SourceError('network error: public endpoint blocked this request', 4, 'blocked') from exc
    except nzfetch.FetchError as exc:
        if record_catalogue and isinstance(exc.__cause__, HTTPError) and exc.__cause__.code in (404, 410):
            raise SourceError('record not found in ' + record_catalogue, 2, 'invalid_input') from exc
        if isinstance(exc.__cause__, json.JSONDecodeError):
            raise SourceError('Source did not return valid JSON') from exc
        # Do not print proxy details or unexpected upstream bodies.
        raise SourceError('network error: upstream unavailable', 5, 'upstream_unavailable') from exc
    except ValueError as exc:
        raise SourceError('Source did not return valid JSON') from exc
    if not isinstance(data, dict):
        raise SourceError('Expected a JSON object from the catalogue')
    if 'error' in data:
        raise SourceError('Catalogue returned an API error', 5, 'upstream_error')
    return data


def query_url(cat, query=None, bbox=None, limit=1, record_id=None, start=None):
    c = CATALOGUES[cat]
    if c['kind'] == 'ckan':
        if record_id is not None:
            return c['source_url'] + 'package_show?' + urlencode({'id': record_id})
        params = {'q': query or '*:*', 'rows': limit}
        if bbox is not None:
            params['ext_bbox'] = ','.join(str(n) for n in bbox)
        if start is not None:
            params['start'] = start
        return c['source_url'] + 'package_search?' + urlencode(params)
    if record_id is not None:
        return c['source_url'] + '/' + quote(record_id, safe='')
    params = {'limit': limit}
    if query is not None:
        params['q'] = query
    if bbox is not None:
        params['bbox'] = ','.join(str(n) for n in bbox)
    return c['source_url'] + '?' + urlencode(params)


def ogc_page(data):
    if (data.get('type') != 'FeatureCollection' or not isinstance(data.get('features'), list)
            or not isinstance(data.get('numberMatched'), int) or data['numberMatched'] < 0):
        raise SourceError('Expected OGC FeatureCollection, features and numberMatched')
    for f in data['features']:
        if not isinstance(f, dict) or f.get('type') != 'Feature' or not isinstance(f.get('properties'), dict):
            raise SourceError('Malformed OGC catalogue record')
    links = data.get('links') or []
    if not isinstance(links, list):
        raise SourceError('Malformed catalogue pagination links')
    return data['features'], data['numberMatched'], [l['href'] for l in links
            if isinstance(l, dict) and l.get('rel') == 'next' and isinstance(l.get('href'), str)]


def ckan_result(data, detail=False):
    result = data.get('result')
    if data.get('success') is not True or not isinstance(result, dict):
        raise SourceError('Expected a successful CKAN result')
    if detail:
        return result
    if not isinstance(result.get('results'), list) or not isinstance(result.get('count'), int):
        raise SourceError('Expected CKAN results and count')
    return result['results'], result['count'], []


def public_url(value):
    if not isinstance(value, str):
        return None
    try:
        u = urlsplit(value)
        if u.scheme in ('http', 'https') and u.hostname and not u.username and not u.password:
            return value
    except ValueError:
        pass
    return None


def normalise_ogc(feature, cat, request_url, retrieved_at):
    if (not isinstance(feature, dict) or feature.get('type') != 'Feature'
            or not isinstance(feature.get('properties'), dict) or not feature.get('id')):
        raise SourceError('Expected an OGC record with id and properties')
    p = feature['properties']
    if not isinstance(p.get('title'), str):
        raise SourceError('Catalogue record has no title')
    for key in ('type', 'source', 'license', 'licenseInfo', 'url', 'name', 'accessInformation'):
        if p.get(key) is not None and not isinstance(p[key], str):
            raise SourceError('Unexpected catalogue property type: ' + key)
    geometry = feature.get('geometry')
    if geometry is not None and (not isinstance(geometry, dict) or not isinstance(geometry.get('type'), str)):
        raise SourceError('Malformed catalogue coverage geometry')
    links = feature.get('links') or []
    if not isinstance(links, list):
        raise SourceError('Catalogue record links are malformed')
    links = [{k: l[k] for k in ('href', 'rel', 'type', 'title') if k in l}
             for l in links if isinstance(l, dict) and public_url(l.get('href'))]
    formats = [p['type']] if p.get('type') else []
    settings = p.get('properties') or {}
    download_settings = settings.get('downloads') if isinstance(settings, dict) else None
    downloads = download_settings.get('formats', []) if isinstance(download_settings, dict) else []
    if isinstance(downloads, list):
        formats.extend(d['key'] for d in downloads if isinstance(d, dict) and isinstance(d.get('key'), str) and not d.get('hidden'))
    distributions = []
    if public_url(p.get('url')):
        distributions.append({'url': p['url'], 'format': p.get('type'), 'rel': 'data'})
    for l in links:
        if l.get('rel') in ('enclosure', 'data', 'download', 'item', 'service'):
            distributions.append({'url': l['href'], 'format': l.get('type'), 'rel': l['rel']})
    # Hub file records lack a download link. This ArcGIS endpoint was verified
    # with HEAD for real Council File Geodatabase and Waka Kotahi CSV ZIP items.
    item_id = str(p.get('id') or feature['id']).split('_')[0]
    if (not distributions and re.fullmatch('[a-fA-F0-9]{32}', item_id)
            and str(p.get('name') or '').lower().endswith('.zip')
            and p.get('type') in ('File Geodatabase', 'CSV Collection', 'Shapefile')):
        # Construct a returned distribution link; this host is never fetched.
        download_url = urlunsplit(('https', 'www.arcgis.com', '/sharing/rest/content/items/' + item_id + '/data', '', ''))
        distributions.append({'url': download_url,
                              'format': p['type'], 'rel': 'download', 'derived': True})
    licence = p.get('license')
    if not licence or licence.lower() in ('none', 'custom'):
        licence = (text(p.get('licenseInfo')) or '')[:300] or None
    # ArcGIS `modified` describes the catalogue item, not the data vintage.
    prov = provenance(request_url, p.get('source') or CATALOGUES[cat]['publisher'],
                      retrieved_at, licence, p.get('latest_data'))
    distributions = [dict(prov, **d) for d in distributions]
    return dict(prov, catalogue=cat, id=str(feature['id']), title=p['title'],
                description=text(p.get('description') or p.get('snippet')),
                access=p.get('access'), updated_at=iso_date(p.get('updated') or p.get('modified')),
                temporal_extent=feature.get('time'), licence_info=text(p.get('licenseInfo')),
                attribution=text(p.get('accessInformation')), geometry=feature.get('geometry'),
                formats=list(dict.fromkeys(formats)), links=links, distributions=distributions,
                distribution_urls=list(dict.fromkeys(d['url'] for d in distributions)))


def normalise_ckan(pkg, cat, request_url, retrieved_at):
    if not isinstance(pkg, dict) or not pkg.get('id') or not isinstance(pkg.get('title'), str):
        raise SourceError('Expected a CKAN dataset with id and title')
    org = pkg.get('organization') or {}
    if not isinstance(org, dict):
        raise SourceError('CKAN organisation is malformed')
    publisher = org.get('title') or org.get('name')
    resources = pkg.get('resources') or []
    if not isinstance(resources, list):
        raise SourceError('CKAN resources are malformed')
    for resource in resources:
        if not isinstance(resource, dict):
            raise SourceError('CKAN resource is malformed')
        for key in ('url', 'format', 'mimetype', 'name', 'last_modified'):
            if resource.get(key) is not None and not isinstance(resource[key], str):
                raise SourceError('Unexpected CKAN resource property type: ' + key)
    distributions = [{'url': r['url'], 'format': r.get('format') or r.get('mimetype'),
                      'title': r.get('name'), 'updated_at': iso_date(r.get('last_modified'))}
                     for r in resources if isinstance(r, dict) and public_url(r.get('url'))]
    geometry = pkg.get('spatial')
    if isinstance(geometry, str):
        try:
            geometry = json.loads(geometry)
        except ValueError as exc:
            raise SourceError('Malformed CKAN coverage geometry') from exc
    if geometry is not None and (not isinstance(geometry, dict) or not isinstance(geometry.get('type'), str)):
        raise SourceError('Malformed CKAN coverage geometry')
    prov = provenance(request_url, publisher or CATALOGUES[cat]['publisher'], retrieved_at,
                      pkg.get('license_title') or pkg.get('license_id'), pkg.get('latest_data'))
    distributions = [dict(prov, **d) for d in distributions]
    return dict(prov, catalogue=cat, id=pkg['id'], name=pkg.get('name'), title=pkg['title'],
                description=text(pkg.get('notes')), updated_at=iso_date(pkg.get('metadata_modified')),
                geometry=geometry, formats=list(dict.fromkeys(d['format'] for d in distributions if d['format'])),
                links=[], distributions=distributions, distribution_urls=[d['url'] for d in distributions])


def catalogue_request(cat, query=None, bbox=None, limit=1, probe=False):
    url = query_url(cat, query, bbox, limit)
    stamp = now()
    status = dict(provenance(url, CATALOGUES[cat]['publisher'], stamp),
                  catalogue=cat, kind=CATALOGUES[cat]['kind'])
    try:
        data = fetch_json(url)
        features, count, next_urls = ogc_page(data) if CATALOGUES[cat]['kind'] == 'ogc-records' else ckan_result(data)
        if CATALOGUES[cat]['kind'] == 'ckan' and count > limit:
            next_urls = [query_url(cat, query, bbox, limit, start=limit)]
        normaliser = normalise_ogc if CATALOGUES[cat]['kind'] == 'ogc-records' else normalise_ckan
        records = [normaliser(f, cat, url, stamp) for f in features[:limit]]
        return dict(status, available=True, status='available', number_matched=count,
                    returned=0 if probe else len(records), next_urls=next_urls), [] if probe else records
    except SourceError as exc:
        return dict(status, available=False, status='unavailable', error=str(exc),
                    error_category=exc.category, error_code=exc.code, retry_after=exc.retry_after), []


def aggregate(kind, catalogues):
    return dict(provenance(CATALOGUES[catalogues[0]]['source_url'], '; '.join(CATALOGUES[c]['publisher'] for c in catalogues), now()),
                kind=kind, source_urls=[CATALOGUES[c]['source_url'] for c in catalogues])


def make_geojson(result):
    return geojson_envelope([
        {'type': 'Feature', 'id': r['catalogue'] + ':' + r['id'], 'geometry': r.get('geometry'),
         'properties': {k: v for k, v in r.items() if k != 'geometry'}} for r in result['results']], result['meta'])


def output(result, as_json=False, geojson=False):
    if as_json or geojson:
        print(json.dumps(make_geojson(result) if geojson and 'error' not in result else result,
                         ensure_ascii=False, indent=2, allow_nan=False))
        return
    for c in result['meta'].get('catalogues', []):
        if c['available']:
            print(f"{c['catalogue']}: available; {c['number_matched']} matched")
        else:
            print(f"{c['catalogue']}: {c['status']}; {c['error']}")
    if 'error' in result:
        print('nz-ogc-records: ' + result['error']['message'], file=sys.stderr)
    for r in result['results']:
        print(f"- {r['title']} [{r['catalogue']} / {r['id']}]")
        print(f"  licence: {r.get('licence') or 'unknown'} | catalogue updated: {r.get('updated_at') or 'unknown'}")
        for d in r['distributions']:
            print(f"  {d.get('format') or 'data'}: {d['url']}")


def parse_bbox(value):
    try:
        b = [float(v) for v in value.split(',')]
        if (len(b) != 4 or not all(math.isfinite(n) for n in b)
                or not -180 <= b[0] < b[2] <= 180 or not -90 <= b[1] < b[3] <= 90):
            raise ValueError
        return b
    except ValueError as exc:
        raise argparse.ArgumentTypeError('bbox must be minLon,minLat,maxLon,maxLat in WGS84 with increasing bounds') from exc


def parse_limit(value):
    try:
        n = int(value)
        if 1 <= n <= 100:
            return n
    except ValueError:
        pass
    raise argparse.ArgumentTypeError('limit must be an integer from 1 to 100')


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='command', required=True)
    subs.add_parser('catalogues', help='List catalogues and probe live keyless access')
    search = subs.add_parser('search', help='Search dataset metadata (limit per catalogue)')
    search.add_argument('text')
    search.add_argument('--catalogue', choices=list(CATALOGUES), action='append', help='Repeat to choose multiple catalogues; default all')
    search.add_argument('--bbox', type=parse_bbox, help='WGS84 minLon,minLat,maxLon,maxLat')
    search.add_argument('--limit', type=parse_limit, default=10, help='Maximum records per catalogue, 1–100 (default 10)')
    get = subs.add_parser('get', help='Get a dataset record and distribution links')
    get.add_argument('catalogue', choices=list(CATALOGUES))
    get.add_argument('record_id')
    for sub in subs.choices.values():
        sub.add_argument('--json', action='store_true', help='Emit JSON with provenance')
    for sub in (search, get):
        sub.add_argument('--format', choices=['json', 'geojson'], default=None, help='GeoJSON geometries describe catalogue coverage')
    args = parser.parse_args(argv)
    if args.command == 'search' and not args.text.strip():
        parser.error('search text must not be empty')
    if args.command == 'get' and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,199}', args.record_id):
        parser.error('record-id must be a catalogue identifier, not a URL or path')
    return args


def main(argv=None):
    args = parse_args(argv)
    as_json = args.json or getattr(args, 'format', None) == 'json'
    geojson = getattr(args, 'format', None) == 'geojson'
    try:
        if args.command == 'get':
            url = query_url(args.catalogue, record_id=args.record_id)
            stamp = now()
            data = fetch_json(url, record_catalogue=args.catalogue)
            normaliser = normalise_ogc
            if CATALOGUES[args.catalogue]['kind'] == 'ckan':
                data = ckan_result(data, detail=True)
                normaliser = normalise_ckan
            record = normaliser(data, args.catalogue, url, stamp)
            meta = provenance(url, record['publisher'], stamp, record.get('licence'), record.get('latest_data'))
            result = result_envelope([record], meta)
        else:
            cats = list(dict.fromkeys(args.catalogue)) if args.command == 'search' and args.catalogue else list(CATALOGUES)
            def request(cat):
                if args.command == 'catalogues':
                    return catalogue_request(cat, probe=True)
                return catalogue_request(cat, args.text, args.bbox, args.limit)
            with ThreadPoolExecutor(max_workers=len(cats)) as pool:
                replies = list(pool.map(request, cats))
            meta = aggregate(args.command, cats)
            meta['catalogues'] = [r[0] for r in replies]
            failures = [c for c in meta['catalogues'] if not c['available']]
            meta['warnings'] = [c['catalogue'] + ': ' + c['error'] for c in failures]
            meta['partial'] = bool(failures)
            records = []
            if args.command == 'search':
                records = [rec for _, rows in replies for rec in rows]
                meta.update(query=args.text, bbox=args.bbox, limit_per_catalogue=args.limit, returned=len(records))
            if len(failures) == len(cats):
                codes = {c['error_code'] for c in failures}
                code = next(c for c in (6, 4, 5, 7, 2) if c in codes)
                retry_after = next((c['retry_after'] for c in failures
                                    if c['error_code'] == code and c.get('retry_after') is not None), None)
                result = error_envelope(code, 'No catalogue could complete this ' + args.command,
                                        meta, retry_after=retry_after)
                output(result, as_json, geojson)
                return code
            result = result_envelope(records, meta)
        output(result, as_json, geojson)
        return 0
    except SourceError as exc:
        url = query_url(args.catalogue, record_id=args.record_id)
        result = error_envelope(exc.code, str(exc), provenance(url, CATALOGUES[args.catalogue]['publisher'], now()),
                                retry_after=exc.retry_after)
        output(result, as_json, geojson)
        return exc.code


if __name__ == '__main__':
    raise SystemExit(main())
