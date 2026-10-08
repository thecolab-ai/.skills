#!/usr/bin/env python3
"""Keyless, read-only ArcGIS REST client with exact publisher route restrictions."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import io
import json
import math
from pathlib import Path
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = json.loads((ROOT / 'references/orgs.json').read_text())
CURATED = json.loads((ROOT / 'references/layers-auckland.json').read_text()) if (ROOT / 'references/layers-auckland.json').exists() else []
SERVER_TYPES = {'FeatureServer', 'MapServer', 'ImageServer'}
FIELD = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$')


class ClientError(Exception):
    def __init__(self, message, code=2, category='invalid_input', **details):
        super().__init__(message)
        self.code, self.category, self.details = code, category, details


def timestamp(value=None):
    if value is None:
        return datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')
    try:
        return datetime.fromtimestamp(float(value) / 1000, timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')
    except (TypeError, ValueError, OverflowError, OSError):
        raise ClientError('source schema failure: invalid lastEditDate', 6, 'malformed_response')


def provenance(url, org, metadata=None):
    info = REGISTRY[org]
    licence = next((r['licence'] for r in CURATED if r['source_url'] == url), None)
    result = dict(source_url=url, publisher=info['publisher'], licence=licence or info['licence'], retrieved_at=timestamp())
    metadata = metadata or {}
    edited = metadata.get('editingInfo', {}).get('lastEditDate')
    if edited is not None:
        result['latest_data'] = timestamp(edited)
    return result


def validate_url(url, kind='layer'):
    """Validate before connecting, including tenant, REST prefix and operation shape."""
    try:
        p = urllib.parse.urlsplit(url)
        invalid = p.scheme != 'https' or p.username is not None or p.password is not None or p.port is not None or p.query or p.fragment
    except ValueError:
        invalid = True
    if invalid:
        raise ClientError('use an exact allowlisted HTTPS ArcGIS REST URL without query, fragment or credentials', 7, 'blocked_url')
    raw = p.path
    parts = [urllib.parse.unquote(s) for s in raw.split('/')[1:]]
    if not raw.startswith('/') or any(not s or s in {'.', '..'} or any(c in s for c in '/\\%?#') or any(ord(c) < 32 or ord(c) == 127 for c in s) for s in parts):
        raise ClientError('unsafe ArcGIS path', 7, 'blocked_url')
    for org, info in REGISTRY.items():
        for base in info['roots']:
            bp = urllib.parse.urlsplit(base)
            prefix = bp.path.strip('/').split('/')
            if p.hostname != bp.hostname or [s.lower() for s in parts[:len(prefix)]] != [s.lower() for s in prefix]:
                continue
            tail = parts[len(prefix):]
            valid = False
            if kind == 'directory':
                valid = len(tail) <= 2 and not any(s in SERVER_TYPES for s in tail)
            elif kind == 'service':
                valid = 2 <= len(tail) <= 4 and tail[-1] in SERVER_TYPES and not any(s in SERVER_TYPES for s in tail[:-1])
            elif kind == 'layer':
                valid = 3 <= len(tail) <= 5 and tail[-2] in {'FeatureServer', 'MapServer'} and tail[-1].isdigit() and not any(s in SERVER_TYPES for s in tail[:-2])
            if valid:
                canonical = base + ('/' + '/'.join(urllib.parse.quote(s, safe='-_.()') for s in tail) if tail else '')
                return org, canonical
    raise ClientError('URL is outside the verified organisation/service allowlist', 7, 'blocked_url')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Refuse before following: a same-host redirect could change the tenant.
        raise ClientError('upstream redirect refused; use the verified canonical route', 7, 'blocked_redirect')


def fetch(url, params=None, kind='layer', query=False):
    _, url = validate_url(url, kind)
    request_url = url + ('/query' if query else '') + '?' + urllib.parse.urlencode({'f': 'json', **(params or {})})
    request = urllib.request.Request(request_url, headers={'User-Agent': 'TheColab-nz-arcgis/1.0', 'Accept': 'application/json'})
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=10) as response:
            body = response.read(32 * 1024 * 1024 + 1)
            if len(body) > 32 * 1024 * 1024:
                raise ClientError('source response exceeds 32 MiB', 6, 'malformed_response')
    except urllib.error.HTTPError as exc:
        code = 4 if exc.code in {403, 406, 429, 451} else 5
        raise ClientError(f'network error: HTTP {exc.code}', code, 'rate_limited' if exc.code == 429 else 'upstream_http_failure', retry_after=exc.headers.get('Retry-After')) from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ClientError(f'network error: upstream unavailable ({exc.reason if isinstance(exc, urllib.error.URLError) else type(exc).__name__})', 5, 'upstream_http_failure') from None
    try:
        data = json.loads(body)
    except (ValueError, UnicodeError):
        raise ClientError('source schema failure: expected ArcGIS JSON', 6, 'malformed_response') from None
    if not isinstance(data, dict):
        raise ClientError('source schema failure: expected an object', 6, 'malformed_response')
    if data.get('error'):
        error = data['error']
        category = 'access_blocked' if error.get('code') in {403, 498, 499} else 'upstream_arcgis_failure'
        raise ClientError('ArcGIS error: ' + str(error.get('message', 'unknown failure')), 4 if category == 'access_blocked' else 5, category)
    return data


def list_value(data, key):
    value = data.get(key)
    if not isinstance(value, list) or not all(isinstance(r, dict) for r in value):
        raise ClientError(f'source schema failure: missing or invalid {key}', 6, 'malformed_response')
    return value


def bbox(value):
    try:
        values = [float(v) for v in value.split(',')]
        a, b, c, d = values
        if not all(math.isfinite(v) for v in values) or not (-180 <= a < c <= 180 and -90 <= b < d <= 90):
            raise ValueError
    except ValueError:
        raise argparse.ArgumentTypeError('bbox must be minLon,minLat,maxLon,maxLat in WGS84, finite and ordered') from None
    return ','.join(str(v) for v in values)


def bounded(maximum):
    def parse(value):
        try:
            n = int(value)
            if not 1 <= n <= maximum:
                raise ValueError
        except ValueError:
            raise argparse.ArgumentTypeError(f'must be between 1 and {maximum}') from None
        return n
    return parse


def fields(value):
    if value != '*' and not all(FIELD.fullmatch(s.strip()) for s in value.split(',')):
        raise argparse.ArgumentTypeError('fields must be * or comma-separated field identifiers')
    return value


def filter_params(args):
    result = {'where': args.where}
    if args.bbox:
        result.update(geometry=args.bbox, geometryType='esriGeometryEnvelope', inSR=4326, spatialRel='esriSpatialRelIntersects')
    return result


def record_count(url, params=None):
    data = fetch(url, {**(params or {'where': '1=1'}), 'returnCountOnly': 'true'}, query=True)
    count = data.get('count')
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise ClientError('source schema failure: missing non-negative count', 6, 'malformed_response')
    return count


def service_layers(url):
    org, url = validate_url(url, 'service')
    data = fetch(url, kind='service')
    rows = []
    if url.endswith('/ImageServer'):
        return [dict(name=data.get('name'), kind='image', **provenance(url, org, data))]
    for key, kind in [('layers', 'layer'), ('tables', 'table')]:
        for row in list_value(data, key) if key in data else []:
            if not isinstance(row.get('id'), int) or row['id'] < 0:
                raise ClientError('source schema failure: invalid layer id', 6, 'malformed_response')
            layer_url = url + '/' + str(row['id'])
            rows.append(dict(row, kind=kind, **provenance(layer_url, org)))
    if 'layers' not in data and 'tables' not in data:
        raise ClientError('source schema failure: service has no layers or tables', 6, 'malformed_response')
    return rows


def discover(org, budget, root_index=None):
    roots = REGISTRY[org]['roots']
    if root_index is not None:
        if root_index >= len(roots):
            raise ClientError('root index is outside this organisation registry')
        roots = [roots[root_index]]
    pending = [(r, r, 0) for r in roots]
    rows, seen, requests, inaccessible = [], set(), 0, []
    while pending and requests < budget:
        url, root, depth = pending.pop(0)
        if url in seen:
            continue
        seen.add(url)
        requests += 1
        try:
            data = fetch(url, kind='directory')
        except ClientError as exc:
            if depth == 0 or exc.category != 'access_blocked':
                raise
            inaccessible.append(dict(error=str(exc), **provenance(url, org)))
            continue
        for row in list_value(data, 'services'):
            if row.get('type') not in SERVER_TYPES:
                continue
            name = row.get('name')
            if not isinstance(name, str) or not name:
                raise ClientError('source schema failure: invalid service name', 6, 'malformed_response')
            # Enterprise listings usually include the folder in name; AGOL may not.
            path = name if depth == 0 or '/' in name else urllib.parse.unquote(url[len(root)+1:]) + '/' + name
            service_url = root + '/' + '/'.join(urllib.parse.quote(s, safe='-_.()') for s in path.split('/')) + '/' + row['type']
            owner, service_url = validate_url(service_url, 'service')
            if owner != org:
                raise ClientError('source schema failure: service changed organisation', 6, 'malformed_response')
            rows.append(dict(name=name, type=row['type'], **provenance(service_url, org)))
        folders = data.get('folders', [])
        if not isinstance(folders, list) or not all(isinstance(f, str) for f in folders):
            raise ClientError('source schema failure: invalid folders', 6, 'malformed_response')
        for folder in folders:
            child = root + '/' + '/'.join(urllib.parse.quote(s, safe='-_.()') for s in folder.split('/'))
            validate_url(child, 'directory')
            if depth < 2 and child not in seen:
                pending.append((child, root, depth+1))
    return dict(services=rows, requests=requests, truncated=bool(pending or inaccessible), pending_directories=[u for u, _, _ in pending], inaccessible_directories=inaccessible)


def query_layer(args, url, metadata):
    params = {**filter_params(args), 'outFields': args.fields, 'returnGeometry': 'true', 'outSR': 4326}
    oid = metadata.get('objectIdField') or metadata.get('objectIdFieldName')
    if oid and FIELD.fullmatch(oid):
        params['orderByFields'] = oid + ' ASC'
        if args.fields != '*' and oid.lower() not in {s.strip().lower() for s in args.fields.split(',')}:
            params['outFields'] += ',' + oid
    supports = metadata.get('advancedQueryCapabilities', {}).get('supportsPagination', False)
    page_size = min(1000, metadata.get('maxRecordCount') or 1000, args.limit)
    if not isinstance(page_size, int) or page_size < 1:
        raise ClientError('source schema failure: invalid record limit', 6, 'malformed_response')
    features, offsets, truncated, seen = [], [], False, set()
    for _ in range(20):
        offset = len(features)
        wanted = min(page_size, args.limit - offset)
        fmt = 'geojson' if args.format == 'geojson' else 'json'
        page = fetch(url, dict(params, f=fmt, resultOffset=offset, resultRecordCount=wanted), query=True)
        if fmt == 'geojson' and page.get('type') != 'FeatureCollection':
            raise ClientError('source schema failure: expected a GeoJSON FeatureCollection', 6, 'malformed_response')
        batch = list_value(page, 'features')
        offsets.append(offset)
        if len(batch) > wanted:
            truncated = True
            batch = batch[:wanted]
        for feature in batch:
            attributes = feature.get('properties' if fmt == 'geojson' else 'attributes')
            if not isinstance(attributes, dict):
                raise ClientError('source schema failure: feature has no attributes/properties', 6, 'malformed_response')
            identity = feature.get('id') if fmt == 'geojson' else attributes.get(oid) if oid else None
            if identity is not None and identity in seen:
                raise ClientError('source paging repeated an object ID; refusing a misleading extract', 6, 'paging_failure')
            if identity is not None:
                seen.add(identity)
        features.extend(batch)
        more = bool(page.get('exceededTransferLimit') or page.get('properties', {}).get('exceededTransferLimit')) or len(batch) == wanted
        if not more:
            break
        if len(features) >= args.limit or not supports or not batch:
            truncated = True
            break
    else:
        truncated = True
    return dict(features=features, spatial_reference={'wkid': 4326}, geometry_type=metadata.get('geometryType'), feature_count=len(features), truncated=truncated, result_offsets=offsets, limit=args.limit,
                **({'type': 'FeatureCollection'} if args.format == 'geojson' else {}))


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ClientError(message)


def parser():
    p = Parser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    for command in ['orgs', 'services', 'layers', 'describe', 'query', 'count', 'search']:
        q = sub.add_parser(command)
        q.add_argument('--json', action='store_true', help='emit machine-readable JSON with provenance')
        if command in {'services', 'layers'}:
            q.add_argument('org', nargs='?' if command == 'layers' else None, choices=sorted(REGISTRY))
        if command in {'services', 'search'}:
            q.add_argument('--max-requests', type=bounded(50), default=40, help='directory request cap (default 40, maximum 50)')
            q.add_argument('--root', type=int, choices=range(20), help='select a registry root by its zero-based index')
        if command == 'layers':
            q.add_argument('service', nargs='?', help='service name including FeatureServer/MapServer/ImageServer, or allowlisted service URL')
            q.add_argument('--curated', choices=['akl'])
            q.add_argument('--problem', choices=['F1', 'T1', 'T2', 'T3', 'W1', 'W2', 'W3'])
        if command in {'describe', 'query', 'count'}:
            q.add_argument('layer_url')
        if command in {'query', 'count'}:
            q.add_argument('--where', default='1=1', help='ArcGIS read-only SQL attribute filter')
            q.add_argument('--bbox', type=bbox, help='minLon,minLat,maxLon,maxLat (WGS84)')
        if command == 'query':
            q.add_argument('--fields', type=fields, default='*')
            q.add_argument('--limit', type=bounded(10000), default=100)
            q.add_argument('--format', choices=['json', 'geojson', 'csv'], default='json')
        if command == 'search':
            q.add_argument('text')
            q.add_argument('--org', required=True, choices=sorted(REGISTRY), help='search only this organisation')
            q.add_argument('--max-services', type=bounded(50), default=20, help='layer listing request cap; results state incomplete coverage')
    return p


def execute(args):
    command = args.command
    if command == 'orgs':
        records = [dict(org=k, roots=v['roots'], **provenance(v['roots'][0], k)) for k, v in REGISTRY.items()]
        return dict(dict(orgs=records, **provenance(REGISTRY['akl']['roots'][0], 'akl')), publisher='New Zealand public-sector ArcGIS publishers')
    if command == 'layers' and args.curated:
        if args.org or args.service:
            raise ClientError('use layers --curated akl without organisation or service arguments')
        rows = [dict(r, retrieved_at=timestamp()) for r in CURATED if not args.problem or args.problem in r['problem_tags']]
        return dict(dict(layers=rows, curated='akl', problem=args.problem, **provenance(REGISTRY['akl']['roots'][0], 'akl')), publisher='New Zealand public-sector ArcGIS publishers')
    if command in {'services', 'search'}:
        result = discover(args.org, args.max_requests, args.root)
        if command == 'search':
            text = args.text.casefold()
            matches = [dict(r, kind='service') for r in result['services'] if text in r['name'].casefold()]
            examined, inaccessible = 0, []
            ordered = sorted(result['services'], key=lambda r: text not in r['name'].casefold())
            for row in ordered[:args.max_services]:
                examined += 1
                try:
                    layers = service_layers(row['source_url'])
                except ClientError as exc:
                    if exc.category != 'access_blocked':
                        raise
                    inaccessible.append(dict(error=str(exc), **provenance(row['source_url'], args.org)))
                    continue
                for layer in layers:
                    if text in str(layer.get('name', '')).casefold():
                        matches.append(layer)
            result = dict(matches=matches, scanned_services=examined, total_discovered_services=len(ordered), directory_requests=result['requests'], truncated=result['truncated'] or examined < len(ordered) or bool(inaccessible), pending_directories=result['pending_directories'], inaccessible_directories=result['inaccessible_directories'], inaccessible_services=inaccessible)
        return dict(result, **provenance(REGISTRY[args.org]['roots'][0], args.org))
    if command == 'layers':
        if args.problem:
            raise ClientError('--problem requires --curated akl')
        if not args.org or not args.service:
            raise ClientError('layers requires an organisation and service, or --curated akl')
        url = args.service if args.service.startswith('https://') else REGISTRY[args.org]['roots'][0] + '/' + '/'.join(urllib.parse.quote(s, safe='-_.()') for s in args.service.split('/'))
        org, url = validate_url(url, 'service')
        if org != args.org:
            raise ClientError('service does not belong to the selected organisation', 7, 'blocked_organisation')
        return dict(layers=service_layers(url), **provenance(url, org))
    org, url = validate_url(args.layer_url)
    metadata = fetch(url)
    source = provenance(url, org, metadata)
    if command == 'describe':
        return dict(name=metadata.get('name'), fields=list_value(metadata, 'fields'), geometry_type=metadata.get('geometryType'), object_id_field=metadata.get('objectIdField'), record_count=record_count(url), editingInfo=metadata.get('editingInfo'), max_record_count=metadata.get('maxRecordCount'), supports_pagination=metadata.get('advancedQueryCapabilities', {}).get('supportsPagination', False), **source)
    if command == 'count':
        return dict(count=record_count(url, filter_params(args)), **source)
    return dict(query_layer(args, url, metadata), **source)


def csv_output(result):
    rows = [f['attributes'] for f in result['features']]
    keys = list(dict.fromkeys(k for row in rows for k in row))
    provenance_keys = [k for k in ['source_url', 'publisher', 'licence', 'retrieved_at', 'latest_data'] if k in result]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=keys + ['provenance_' + k for k in provenance_keys])
    writer.writeheader()
    for row in rows:
        writer.writerow({**row, **{'provenance_' + k: result[k] for k in provenance_keys}})
    return output.getvalue()



def human_output(command, result):
    if command == 'orgs':
        for row in result['orgs']:
            print(f"{row['org']}: {row['publisher']}")
            for i, root in enumerate(row['roots']):
                print(f"  [{i}] {root}")
    elif command in {'services', 'layers', 'search'}:
        rows = result.get('services', result.get('layers', result.get('matches', [])))
        for row in rows:
            print(f"{row.get('name', '')} ({row.get('kind', row.get('type', 'layer'))})")
            print(f"  {row['source_url']}")
            if row.get('caveat'):
                print(f"  Caveat: {row['caveat']}")
        print(f"Returned {len(rows)} records.")
        if result.get('truncated'):
            print('Coverage is incomplete; inspect --json for unvisited or inaccessible entries.')
    elif command == 'describe':
        print(f"{result['name']}: {result['geometry_type'] or 'table'}; {result['record_count']} records")
        if result.get('latest_data'):
            print(f"Latest published edit: {result['latest_data']}")
        for field in result['fields']:
            print(f"  {field['name']}: {field['type']} ({field.get('alias', '')})")
    elif command == 'count':
        print(f"Count: {result['count']}")
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    if command != 'query':
        print(f"Source: {result['publisher']} — {result['source_url']}")


def main(argv=None):
    try:
        args = parser().parse_args(argv)
        result = execute(args)
        if args.command == 'query' and args.format == 'csv':
            rendered = csv_output(result)
            if args.json:
                print(json.dumps({k: v for k, v in result.items() if k != 'features'} | {'format': 'csv', 'csv': rendered}, ensure_ascii=False))
            else:
                print(rendered, end='')
                print(f"Returned {result['feature_count']} rows; truncated={result['truncated']}", file=sys.stderr)
        elif args.json or (args.command == 'query' and args.format == 'geojson'):
            print(json.dumps(result, ensure_ascii=False))
        else:
            human_output(args.command, result)
        return 0
    except ClientError as exc:
        print(json.dumps(dict(ok=False, source_url=None, publisher=None, licence=None, retrieved_at=timestamp(), error=dict(category=exc.category, code=exc.code, message=str(exc), **exc.details))), file=sys.stderr)
        return exc.code
    except (KeyError, TypeError, AttributeError, ValueError) as exc:
        print(json.dumps(dict(ok=False, source_url=None, publisher=None, licence=None, retrieved_at=timestamp(), error=dict(category='malformed_response', code=6, message='source schema failure: ' + str(exc)))), file=sys.stderr)
        return 6


if __name__ == '__main__':
    raise SystemExit(main())
