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
import time
from provenance import provenance as make_provenance, result_envelope, geojson_envelope, error_envelope, ERROR_TYPES
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = json.loads((ROOT / 'references/orgs.json').read_text())
CURATED = json.loads((ROOT / 'references/layers-auckland.json').read_text()) if (ROOT / 'references/layers-auckland.json').exists() else []
CATALOGUE = CURATED if isinstance(CURATED, dict) else {'layers': CURATED}
CURATED = CATALOGUE['layers']
NZ_CATALOGUE = json.loads((ROOT / 'references/layers-nz.json').read_text()) if (ROOT / 'references/layers-nz.json').exists() else {'layers': []}
NZ_CURATED = NZ_CATALOGUE['layers']
VERIFICATION = json.loads((ROOT / 'references/verification.json').read_text())
PUBLISHERS = 'New Zealand public-sector and utility ArcGIS publishers'
REPO_URL = 'https://github.com/thecolab-ai/.skills/blob/main/skills/nz-arcgis/references/'
TAGS = {'F1': 'flooding/flow paths', 'T1': 'congestion', 'T2': 'near-miss safety', 'T3': 'incidents/roadworks', 'W1': 'construction and demolition materials', 'W2': 'reuse/repair/recycling', 'W3': 'illegal dumping'}
ACTIVE_BUDGET = None
SERVER_TYPES = {'FeatureServer', 'MapServer', 'ImageServer'}
FIELD = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$')
UNKNOWN_LICENCE = re.compile(r'not stated|^not specified\b|does not state|no .*licen[cs]e', re.I)


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
    record = next((r for r in CURATED + NZ_CURATED if r['source_url'] == url), {})
    licence = record.get('licence') if record else info.get('licence')
    if licence and UNKNOWN_LICENCE.search(licence):
        licence = None
    result = make_provenance(url, info['publisher'], licence=licence)
    metadata = metadata or {}
    edited = (metadata.get('editingInfo') or {}).get('lastEditDate')
    if edited is not None:
        result['latest_data'] = timestamp(edited)
    for key in ('caveat', 'licence_note'):
        if record.get(key):
            result[key] = record[key]
    return result


def cached_meta(filename, retrieved_at):
    return make_provenance(REPO_URL + filename, 'TheColab', retrieved_at=retrieved_at)


def validate_url(url, kind='layer'):
    """Validate before connecting, including tenant, REST prefix and operation shape."""
    try:
        p = urllib.parse.urlsplit(url)
        invalid = p.scheme != 'https' or p.username is not None or p.password is not None or p.port is not None or p.query or p.fragment
    except ValueError:
        invalid = True
    if 'p' in locals() and (p.query or p.path.rstrip('/').endswith('/query')):
        raise ClientError('remove ?f=json / query suffix from the copied URL', 7, 'blocked_url')
    if invalid:
        raise ClientError('use an exact allowlisted HTTPS ArcGIS REST URL without query, fragment or credentials', 7, 'blocked_url')
    raw = p.path.removesuffix('/')
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
            if info.get('service_allowlist') and tail and tail[0] not in info['service_allowlist']:
                continue
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


class RequestBudget:
    """Per-command bounds, shared by metadata, discovery and feature requests."""
    def __init__(self, timeout=10):
        self.timeout = timeout
        self.deadline = time.monotonic() + 55
        self.bytes = 0

    def check(self):
        if time.monotonic() >= self.deadline:
            raise ClientError('command exceeded 55-second deadline', 6, 'resource_limit')
        if self.bytes >= 64 * 1024 * 1024:
            raise ClientError('command exceeded 64 MiB aggregate response bound', 6, 'resource_limit')


def upstream_code(code):
    return 2 if code in {400, 404} else 4 if code in {403, 406, 429, 451, 498, 499} else 5


def fetch(url, params=None, kind='layer', query=False, timeout=None):
    _, url = validate_url(url, kind)
    budget = ACTIVE_BUDGET or RequestBudget(timeout or 10)
    budget.check()
    seconds = timeout or budget.timeout
    request_url = url + ('/query' if query else '') + '?' + urllib.parse.urlencode({'f': 'json', **(params or {})})
    if len(request_url.encode()) >= 8192:
        raise ClientError('query URL exceeds 8 KB; reduce fields or where expression')
    request = urllib.request.Request(request_url, headers={'User-Agent': 'TheColab-nz-arcgis/1.0', 'Accept': 'application/json'})
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=min(seconds, max(0.1, budget.deadline-time.monotonic()))) as response:
            chunks, size = [], 0
            while True:
                budget.check()
                chunk = response.read1(min(65536, 32 * 1024 * 1024 + 1 - size))
                budget.bytes += len(chunk)
                size += len(chunk)
                if size > 32 * 1024 * 1024:
                    raise ClientError('source response exceeds 32 MiB', 6, 'resource_limit')
                budget.check()
                if not chunk:
                    break
                chunks.append(chunk)
            body = b''.join(chunks)
    except urllib.error.HTTPError as exc:
        raise ClientError(f'network error: HTTP {exc.code}', upstream_code(exc.code), 'upstream_http_failure', retry_after=exc.headers.get('Retry-After')) from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        budget.check()
        reason = exc.reason if isinstance(exc, urllib.error.URLError) else exc
        hint = 'narrow --bbox/--where or raise --timeout' if query else 'raise --timeout or retry later' if kind == 'layer' else 'retry later'
        message = f'upstream timed out after {seconds}s; {hint}' if isinstance(reason, TimeoutError) else f'network error: upstream unavailable ({type(reason).__name__})'
        raise ClientError(message, 5, 'upstream_http_failure') from None
    try:
        data = json.loads(body)
    except (ValueError, UnicodeError):
        raise ClientError('source schema failure: expected ArcGIS JSON', 6, 'malformed_response') from None
    if not isinstance(data, dict):
        raise ClientError('source schema failure: expected an object', 6, 'malformed_response')
    if data.get('error'):
        error = data['error']
        if not isinstance(error, dict):
            raise ClientError('source schema failure: invalid ArcGIS error', 6)
        details = error.get('details', [])
        parts = [str(error.get('message') or '')]
        if isinstance(details, list):
            parts.extend(d for d in details if isinstance(d, str))
        message = '; '.join(dict.fromkeys(p.strip() for p in parts if p.strip())) or 'unknown failure'
        raise ClientError('ArcGIS error: ' + message[:300], upstream_code(error.get('code')), 'upstream_arcgis_failure')
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


def query_fields(org, value):
    allowed = REGISTRY[org].get('field_allowlist')
    if not allowed:
        return value if value is not None else '*'
    if value is None:
        return ','.join(allowed)
    selected = [s.strip().lower() for s in value.split(',')]
    if any(s not in allowed for s in selected):
        raise ClientError(f"{org} privacy restriction: --fields must use only {','.join(allowed)}; * and other fields are refused")
    return ','.join(selected)


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


def failure(url, exc):
    return dict(source_url=url, type=ERROR_TYPES[exc.code], message=str(exc))


def tolerable_discovery_error(exc):
    return (exc.code in {4, 5, 6}
            or (exc.code == 2 and exc.category in {'upstream_http_failure', 'upstream_arcgis_failure'})
            or exc.category == 'blocked_redirect')


def discover(org, budget, root_index=None):
    roots = REGISTRY[org]['roots']
    if root_index is not None:
        if root_index >= len(roots):
            raise ClientError('root index is outside this organisation registry')
        roots = [roots[root_index]]
    pending = [(r, r, 0) for r in roots]
    rows, seen, requests, failed, root_failures = [], set(), 0, [], []
    while pending and requests < budget:
        url, root, depth = pending.pop(0)
        if url in seen:
            continue
        seen.add(url)
        requests += 1
        try:
            data = fetch(url, kind='directory')
            collected = []
            for row in list_value(data, 'services'):
                if row.get('type') not in SERVER_TYPES:
                    continue
                name = row.get('name')
                if not isinstance(name, str) or not name:
                    raise ClientError('source schema failure: invalid service name', 6)
                path = name if depth == 0 or '/' in name else urllib.parse.unquote(url[len(root)+1:]) + '/' + name
                if REGISTRY[org].get('service_allowlist') and path not in REGISTRY[org]['service_allowlist']:
                    continue
                service_url = root + '/' + '/'.join(urllib.parse.quote(s, safe='-_.()') for s in path.split('/')) + '/' + row['type']
                owner, service_url = validate_url(service_url, 'service')
                if owner != org:
                    raise ClientError('source schema failure: service changed organisation', 6)
                collected.append(dict(name=name, type=row['type'], **provenance(service_url, org)))
            folders = data.get('folders', [])
            if not isinstance(folders, list) or not all(isinstance(f, str) for f in folders):
                raise ClientError('source schema failure: invalid folders', 6)
            children = []
            for folder in folders:
                child = root + '/' + '/'.join(urllib.parse.quote(s, safe='-_.()') for s in folder.split('/'))
                validate_url(child, 'directory')
                if depth < 2 and child not in seen:
                    children.append((child, root, depth+1))
            rows.extend(collected)
            pending.extend(children)
        except ClientError as exc:
            if not tolerable_discovery_error(exc):
                raise
            failed.append(failure(url, exc))
            if depth == 0:
                root_failures.append(exc)
            if exc.category == 'resource_limit':
                break
    if len(root_failures) == len(roots):
        raise root_failures[0]
    return dict(services=rows, requests=requests, truncated=bool(pending or failed), pending_directories=[u for u, _, _ in pending], failed_directories=failed)


def query_layer(args, url, metadata):
    org, url = validate_url(url)
    args.fields = query_fields(org, args.fields)
    allowed = REGISTRY[org].get('field_allowlist')
    params = {**filter_params(args), 'outFields': args.fields, 'returnGeometry': 'false' if args.format == 'csv' else 'true', 'outSR': 4326}
    oid = metadata.get('objectIdField') or metadata.get('objectIdFieldName')
    if not oid:
        oid = next((f['name'] for f in metadata.get('fields', []) if f.get('type') == 'esriFieldTypeOID'), None)
    if oid and not FIELD.fullmatch(oid):
        raise ClientError('source schema failure: invalid object ID field', 6)
    if allowed and oid and oid.lower() not in allowed:
        raise ClientError('source schema failure: object ID field is outside the organisation field allowlist', 6, 'malformed_response')
    if oid and args.fields != '*' and oid.lower() not in {s.strip().lower() for s in args.fields.split(',')}:
        params['outFields'] += ',' + oid
    output_fields = {s.strip().lower() for s in params['outFields'].split(',')} if allowed else None
    page_size = metadata.get('maxRecordCount') or 1000
    if isinstance(page_size, bool) or not isinstance(page_size, int) or page_size < 1:
        raise ClientError('source schema failure: invalid record limit', 6)
    page_size = min(200, page_size, args.limit)
    fmt = 'geojson' if args.format == 'geojson' else 'json'
    features, offsets, seen, reasons = [], [], set(), []
    missing = 0
    expected = None
    total = None
    truncated = False
    incomplete = False
    def add_page(page, requested=None):
        if fmt == 'geojson' and page.get('type') != 'FeatureCollection':
            raise ClientError('source schema failure: expected a GeoJSON FeatureCollection', 6)
        batch = list_value(page, 'features')
        for feature in batch:
            attributes = feature.get('properties' if fmt == 'geojson' else 'attributes')
            if not isinstance(attributes, dict):
                raise ClientError('source schema failure: feature has no attributes/properties', 6)
            if output_fields is not None:
                # Do not expose extra attributes even if upstream ignores outFields.
                attributes = {k: v for k, v in attributes.items() if k.lower() in output_fields}
                feature['properties' if fmt == 'geojson' else 'attributes'] = attributes
            identity = attributes.get(oid, feature.get('id')) if oid else None
            if oid and (type(identity) is not int or identity in seen or (requested is not None and identity not in requested)):
                raise ClientError('source paging repeated, omitted or returned an unexpected object ID', 6, 'paging_failure')
            if identity is not None:
                seen.add(identity)
        if len(features) + len(batch) > args.limit:
            raise ClientError('source paging exceeded requested feature limit', 6, 'paging_failure')
        features.extend(batch)
        return batch
    try:
        if oid:
            # No outSR on the ID selection: reprojection must not remove IDs.
            data = fetch(url, {**filter_params(args), 'returnIdsOnly': 'true', 'returnGeometry': 'false'}, query=True)
            ids = data.get('objectIds')
            if ids is None and data.get('objectIdFieldName'):
                ids = []
            if not isinstance(ids, list):
                raise ClientError('source schema failure: invalid objectIds', 6)
            if any(type(i) is not int for i in ids) or len(set(ids)) != len(ids):
                raise ClientError('source schema failure: invalid objectIds', 6)
            if data.get('exceededTransferLimit'):
                incomplete = True
                reasons.append('server truncated object ID selection')
            total = len(ids)
            expected = sorted(ids)[:args.limit]
            truncated = incomplete or total > args.limit
            index = 0
            while index < len(expected):
                wanted = expected[index:index+page_size]
                # Keep even large 64-bit ID batches below the 8 KB URL bound.
                while len((url + '/query?' + urllib.parse.urlencode(dict(params, f=fmt, objectIds=','.join(map(str, wanted))))).encode()) >= 8192 and len(wanted) > 1:
                    wanted = wanted[:len(wanted)//2]
                offsets.append(index)
                page = fetch(url, dict(params, f=fmt, objectIds=','.join(map(str, wanted))), query=True)
                add_page(page, set(wanted))
                index += len(wanted)
            missing = len(set(expected) - seen)
            if missing:
                incomplete = truncated = True
                reasons.append('server omitted requested object IDs (possibly during reprojection)')
        else:
            supports = metadata.get('advancedQueryCapabilities', {}).get('supportsPagination', False)
            for _ in range(50):
                offset = len(features)
                wanted = min(page_size, args.limit-offset)
                if wanted <= 0:
                    break
                offsets.append(offset)
                page = fetch(url, dict(params, f=fmt, resultOffset=offset, resultRecordCount=wanted), query=True)
                batch = add_page(page)
                more = bool(page.get('exceededTransferLimit') or (page.get('properties') or {}).get('exceededTransferLimit')) or len(batch) == wanted
                if not more or not supports or not batch:
                    break
            total = record_count(url, filter_params(args))
            if len(features) < min(total, args.limit):
                incomplete = True
                reasons.append('returned fewer features than the count selection')
            truncated = incomplete or total > len(features)
    except ClientError as exc:
        if exc.category != 'resource_limit':
            raise
        incomplete = truncated = True
        reasons.append(str(exc))
        if expected is not None:
            missing = len(set(expected)-seen)
    if oid:
        key = 'properties' if fmt == 'geojson' else 'attributes'
        features.sort(key=lambda f: f[key].get(oid, f.get('id')))
    result = dict(features=features, spatial_reference={'wkid': 4326}, geometry_type=metadata.get('geometryType'), feature_count=len(features), truncated=truncated, incomplete=incomplete, result_offsets=offsets, limit=args.limit, ordering='object_id' if oid else 'unordered')
    if total is not None:
        result['matched_count'] = total
    if oid:
        result['missing_object_ids_count'] = missing
    else:
        result['warnings'] = ['No object ID field; ordering and duplicate detection are unavailable.']
    if reasons:
        result['truncation_reasons'] = reasons
    return result


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
            q.add_argument('--curated', choices=['akl', 'nz'])
            q.add_argument('--publisher', choices=sorted(REGISTRY), help='filter a curated selection by organisation code')
            q.add_argument('--problem', choices=list(TAGS), help='; '.join(k + ': ' + v for k, v in TAGS.items()))
        if command in {'describe', 'query', 'count'}:
            q.add_argument('layer_url')
            q.add_argument('--timeout', type=bounded(60), default=10, metavar='SECONDS', help='request timeout 1–60 seconds (default 10)')
        if command in {'query', 'count'}:
            q.add_argument('--where', default='1=1', help='ArcGIS read-only SQL attribute filter')
            q.add_argument('--bbox', type=bbox, help='minLon,minLat,maxLon,maxLat (WGS84)')
        if command == 'query':
            q.add_argument('--fields', type=fields, help='comma-separated fields (default *; restricted organisations use their field allowlist)')
            q.add_argument('--limit', type=bounded(10000), default=100)
            q.add_argument('--format', choices=['json', 'geojson', 'csv'], default='json')
        if command == 'search':
            q.add_argument('text')
            q.add_argument('--org', required=True, choices=sorted(REGISTRY), help='search only this organisation')
            q.add_argument('--max-services', type=bounded(50), default=20, help='layer listing request cap; results state incomplete coverage')
    return p


def execute(args):
    global ACTIVE_BUDGET
    ACTIVE_BUDGET = RequestBudget(getattr(args, 'timeout', 10))
    command = args.command
    if command == 'orgs':
        verified = max(r['verified_at'] for r in VERIFICATION if r['org'] in REGISTRY and r.get('ok'))
        records = [dict(org=k, roots=v['roots'], publisher=v['publisher']) for k, v in REGISTRY.items()]
        return result_envelope(records, cached_meta('orgs.json', verified))
    if command == 'layers' and args.curated:
        if args.org or args.service:
            raise ClientError('use layers --curated akl without organisation or service arguments')
        selected = CURATED if args.curated == 'akl' else CURATED + NZ_CURATED
        rows = [dict(r) for r in selected if (not args.problem or args.problem in r['problem_tags']) and (not args.publisher or args.publisher == r['org'])]
        meta = cached_meta('layers-auckland.json', max(r['verified_at'] for r in selected))
        if args.curated == 'nz':
            meta['source_urls'] = [REPO_URL + filename for filename in ('layers-auckland.json', 'layers-nz.json')]
        return dict(result_envelope(rows, meta), curated=args.curated, problem=args.problem, tags=TAGS)
    if command in {'services', 'search'}:
        result = discover(args.org, args.max_requests, args.root)
        rows = result.pop('services')
        if command == 'search':
            text = args.text.casefold()
            matches = [dict(r, kind='service') for r in rows if text in r['name'].casefold()]
            examined, failed = 0, []
            ordered = sorted(rows, key=lambda r: text not in r['name'].casefold())
            for row in ordered[:args.max_services]:
                examined += 1
                try:
                    layers = service_layers(row['source_url'])
                except ClientError as exc:
                    if not tolerable_discovery_error(exc):
                        raise
                    failed.append(failure(row['source_url'], exc))
                    if exc.category == 'resource_limit':
                        break
                    continue
                for layer in layers:
                    if text in str(layer.get('name', '')).casefold():
                        matches.append(layer)
            result.update(scanned_services=examined, total_discovered_services=len(ordered), failed_services=failed, truncated=result['truncated'] or examined < len(ordered) or bool(failed))
            rows = matches
        root = REGISTRY[args.org]['roots'][args.root or 0]
        return dict(result_envelope(rows, provenance(root, args.org)), **result)
    if command == 'layers':
        if args.problem or args.publisher:
            raise ClientError('--problem and --publisher require --curated akl or nz')
        if not args.org or not args.service:
            raise ClientError('layers requires an organisation and service, or --curated akl')
        url = args.service if args.service.startswith('https://') else REGISTRY[args.org]['roots'][0] + '/' + '/'.join(urllib.parse.quote(s, safe='-_.()') for s in args.service.split('/'))
        org, url = validate_url(url, 'service')
        if org != args.org:
            raise ClientError('service does not belong to the selected organisation', 7, 'blocked_organisation')
        return result_envelope(service_layers(url), provenance(url, org))
    if command == 'describe' and args.layer_url.rstrip('/').rsplit('/', 1)[-1] in SERVER_TYPES:
        org, url = validate_url(args.layer_url, 'service')
        if urllib.parse.urlsplit(url).hostname == 'tiledimageservices1.arcgis.com':
            raise ClientError('service describe refused: tiledimageservices1.arcgis.com robots.txt disallows all automated paths', 7, 'robots_disallowed')
        metadata = fetch(url, kind='service')
        if not any(k in metadata for k in ('layers', 'bandCount')):
            raise ClientError('source schema failure: service has no layers or image bands', 6)
        row = dict(name=metadata.get('name') or url.split('/')[-2], kind='service', server_type=url.rsplit('/', 1)[-1], capabilities=metadata.get('capabilities'), extent=metadata.get('fullExtent') or metadata.get('extent'), spatial_reference=metadata.get('spatialReference'), service_item_id=metadata.get('serviceItemId'), tile_only='TilesOnly' in (metadata.get('capabilities') or '').split(','))
        for key in ('layers', 'tables', 'bandCount', 'pixelType', 'pixelSizeX', 'pixelSizeY', 'minValues', 'maxValues'):
            if key in metadata:
                if key in {'layers', 'tables'}:
                    list_value(metadata, key)
                row[key] = metadata[key]
        return result_envelope([row], provenance(url, org, metadata))
    org, url = validate_url(args.layer_url)
    if command == 'query':
        args.fields = query_fields(org, args.fields)
    metadata = fetch(url)
    if metadata.get('type') not in {'Feature Layer', 'Table'}:
        raise ClientError(f"not a queryable feature layer (type {metadata.get('type')})", 7)
    if getattr(args, 'bbox', None) and (metadata.get('type') == 'Table' or not metadata.get('geometryType')):
        raise ClientError('bbox not supported on tables; use --where')
    source = provenance(url, org, metadata)
    if command == 'describe':
        oid = metadata.get('objectIdField') or metadata.get('objectIdFieldName')
        described_fields = list_value(metadata, 'fields')
        allowed = REGISTRY[org].get('field_allowlist')
        if allowed:
            described_fields = [f for f in described_fields if f.get('name', '').lower() in allowed]
            if oid and oid.lower() not in allowed:
                raise ClientError('source schema failure: object ID field is outside the organisation field allowlist', 6, 'malformed_response')
        row = dict(name=metadata.get('name'), fields=described_fields, geometry_type=metadata.get('geometryType'), object_id_field=oid, record_count=record_count(url), editingInfo=metadata.get('editingInfo'), max_record_count=metadata.get('maxRecordCount'), supports_pagination=metadata.get('advancedQueryCapabilities', {}).get('supportsPagination', False))
        result = result_envelope([row], source)
        if not oid:
            result.update(ordering='unordered', warnings=['No object ID field; ordering and duplicate detection are unavailable.'])
        return result
    if command == 'count':
        return result_envelope([dict(count=record_count(url, filter_params(args)))], source)
    data = query_layer(args, url, metadata)
    features = data.pop('features')
    envelope = geojson_envelope(features, source) if args.format == 'geojson' else result_envelope(features, source)
    return dict(envelope, **data)


def safe_cell(value):
    return "'" + value if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@')) else value


def csv_output(result):
    rows = [f['attributes'] for f in result['results']]
    keys = list(dict.fromkeys(k for row in rows for k in row))
    meta = result['meta']
    provenance_keys = [k for k in ['source_url', 'publisher', 'licence', 'retrieved_at', 'latest_data'] if k in meta]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=[safe_cell(k) for k in keys] + ['provenance_' + k for k in provenance_keys])
    writer.writeheader()
    for row in rows:
        values = {**{safe_cell(k): v for k, v in row.items()}, **{'provenance_' + k: meta[k] for k in provenance_keys}}
        writer.writerow({k: safe_cell(v) for k, v in values.items()})
    return output.getvalue()


def print_terms(record):
    print(f"  Licence: {record.get('licence', 'unknown')}")
    if record.get('licence_note'):
        print(f"  Licence note: {record['licence_note']}")
    if record.get('caveat'):
        print(f"  Caveat: {record['caveat']}")


def human_output(command, result):
    rows = result['results']
    meta = result['meta']
    if command == 'orgs':
        for row in rows:
            print(f"{row['org']}: {row['publisher']}")
            for i, root in enumerate(row['roots']):
                print(f"  [{i}] {root}")
    elif command in {'services', 'layers', 'search'}:
        for row in rows:
            print(f"{row.get('name', '')} ({row.get('kind', row.get('type', 'layer'))})")
            print(f"  {row['source_url']}")
            print_terms(row)
        print(f"Returned {len(rows)} records.")
        if result.get('truncated'):
            print('Coverage is incomplete; inspect --json for failed or unvisited entries.')
    elif command == 'describe':
        row = rows[0]
        if row.get('kind') == 'service':
            print(f"{row['name']}: {row['server_type']}; capabilities={row['capabilities']}")
            print_terms(meta)
            for layer in row.get('layers', []):
                print(f"  {layer['id']}: {layer['name']}")
            print(f"Source: {meta['publisher']} — {meta['source_url']}")
            return
        print(f"{row['name']}: {row['geometry_type'] or 'table'}; {row['record_count']} records")
        print_terms(meta)
        for field in row['fields']:
            print(f"  {field['name']}: {field['type']} ({field.get('alias', '')})")
    elif command == 'count':
        print(f"Count: {rows[0]['count']}")
    else:
        print(f"Returned {len(rows)} features; truncated={result['truncated']}; incomplete={result['incomplete']}")
        print_terms(meta)
        for row in rows[:5]:
            print('  ' + json.dumps(row['attributes'], ensure_ascii=False))
    print(f"Source: {meta['publisher']} — {meta['source_url']}")


def error_meta(args):
    if args and getattr(args, 'layer_url', None):
        try:
            kind = 'service' if args.command == 'describe' and args.layer_url.rstrip('/').rsplit('/', 1)[-1] in SERVER_TYPES else 'layer'
            org, url = validate_url(args.layer_url, kind)
            return provenance(url, org)
        except ClientError:
            pass
    if args and getattr(args, 'org', None) in REGISTRY:
        org = args.org
        root = REGISTRY[org]['roots'][getattr(args, 'root', None) or 0] if (getattr(args, 'root', None) or 0) < len(REGISTRY[org]['roots']) else REGISTRY[org]['roots'][0]
        service = getattr(args, 'service', None)
        if service:
            try:
                url = service if service.startswith('https://') else root + '/' + service
                owner, url = validate_url(url, 'service')
                if owner == org:
                    return provenance(url, org)
            except ClientError:
                pass
        return provenance(root, org)
    return make_provenance(REPO_URL + 'orgs.json', PUBLISHERS)


def main(argv=None):
    args = None
    raw = list(sys.argv[1:] if argv is None else argv)
    machine = '--json' in raw or '--format=geojson' in raw or any(
        raw[i:i+2] == ['--format', 'geojson'] for i in range(len(raw))
    )
    try:
        args = parser().parse_args(raw)
        result = execute(args)
        if args.command == 'query' and args.format == 'csv':
            rendered = csv_output(result)
            if args.json:
                print(json.dumps({k: v for k, v in result.items() if k != 'results'} | {'results': [{'format': 'csv', 'csv': rendered}]}, ensure_ascii=False))
            else:
                print(rendered, end='')
                print(f"Returned {result['feature_count']} rows; truncated={result['truncated']}", file=sys.stderr)
        elif machine:
            print(json.dumps(result, ensure_ascii=False))
        else:
            human_output(args.command, result)
        return 0
    except (ClientError, KeyError, TypeError, AttributeError, ValueError) as exc:
        if not isinstance(exc, ClientError):
            exc = ClientError('source schema failure: ' + str(exc), 6)
        if machine:
            error = error_envelope(exc.code, str(exc), error_meta(args), retry_after=exc.details.get('retry_after'))
            error['error']['reason'] = exc.category
            print(json.dumps(error))
        else:
            print(str(exc).replace('\n', ' '), file=sys.stderr)
        return exc.code


if __name__ == '__main__':
    raise SystemExit(main())
