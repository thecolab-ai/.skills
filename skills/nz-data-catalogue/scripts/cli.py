#!/usr/bin/env python3
"""Search the bundled assessed catalogue; optionally probe a public endpoint."""
from __future__ import annotations
import argparse
import collections
import datetime as dt
import gzip
import ipaddress
import json
import math
import re
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_URL = 'https://github.com/thecolab-ai/.skills'
PROBLEMS = ('F1', 'T1', 'T2', 'T3', 'W1', 'W2', 'W3')
TIMEOUT = 10
SAMPLE_BYTES = 65536

class CatalogueError(Exception):
    def __init__(self, message, code=6):
        super().__init__(message)
        self.code = code

def utc_now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')

def load_catalogue(path=None):
    with gzip.open(path or ROOT / 'data/catalogue.json.gz', 'rt', encoding='utf-8') as handle:
        data = json.load(handle)
    if data.get('schema_version') != '1' or not isinstance(data.get('records'), list):
        raise CatalogueError('invalid bundled catalogue schema; rebuild the index')
    return data

def tokens(text):
    return re.findall(r'[^\W_]+', text.casefold(), re.UNICODE)

def ranked_search(records, query):
    """Weighted term frequency / inverse document frequency; all terms required."""
    terms = set(tokens(query))
    if not terms:
        raise CatalogueError('search text must contain a word or number', 2)
    documents, frequency = [], collections.Counter()
    for row in records:
        counts = collections.Counter()
        for field, weight in (('name', 5), ('why_useful', 2), ('owner', 2), ('category', 1)):
            for token in tokens(row.get(field) or ''):
                counts[token] += weight
        frequency.update(set(counts))
        documents.append((row, counts))
    results = []
    for row, counts in documents:
        if not terms.issubset(counts):
            continue
        relevance = sum((1 + math.log(counts[t])) * (1 + math.log((len(records) + 1) / (frequency[t] + 1))) for t in terms)
        if query.casefold() in row['name'].casefold():
            relevance += 5
        results.append(dict(row, relevance=round(relevance, 4)))
    return sorted(results, key=lambda r: (-r['relevance'], -r['score'], r['id']))

def filter_records(records, args):
    results = []
    for row in records:
        if getattr(args, 'problem', None) and args.problem not in row['problem_tags']:
            continue
        if getattr(args, 'grade', None) and row['grade'] not in args.grade:
            continue
        if getattr(args, 'auckland', None) and row['covers_auckland'] != args.auckland:
            continue
        if any(getattr(args, option, None) and getattr(args, option).casefold() not in (row.get(field) or '').casefold()
               for option, field in (('category', 'category'), ('scope', 'scope'), ('access', 'access'), ('type', 'data_type'), ('owner', 'owner'))):
            continue
        results.append(row)
    return results

def mapped_skills(row, skill_map):
    output = []
    for rule in skill_map['rules']:
        match = rule['match']
        # Host and path restrictions must match the same URL.
        if not any(url and (not match.get('hosts') or urllib.parse.urlsplit(url).hostname in match['hosts'])
                   and (not match.get('url_contains') or any(t.casefold() in url.casefold() for t in match['url_contains']))
                   for url in (row.get('direct_endpoint'), row.get('url'))):
            continue
        if match.get('name_contains') and not any(t.casefold() in row['name'].casefold() for t in match['name_contains']):
            continue
        if match.get('nz_only') and row['scope'] not in ('Auckland', 'NZ national', 'NZ other region'):
            continue
        result = {k: v for k, v in rule.items() if k != 'match'}
        if not any(r['skill'] == result['skill'] for r in output):
            output.append(result)
    return output

def enrich(row, skill_map, now):
    return dict(row, source_url=row.get('direct_endpoint') or row['url'], publisher=row['owner'],
                retrieved_at=now, retrieval_kind='bundled_catalogue', fetch_skills=mapped_skills(row, skill_map))

def validated_url(url, hosts):
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme not in ('http', 'https') or parsed.hostname not in hosts or parsed.username or parsed.password
            or parsed.port not in (None, 80, 443) or re.search(r'[\s{}<>]', url)):
        raise CatalogueError('endpoint is not a single public HTTP(S) URL, or needs template values', 7)
    addresses = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == 'https' else 80), type=socket.SOCK_STREAM)
    if any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise CatalogueError('endpoint resolves to a non-public address', 7)
    return url

class CheckedRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, hosts):
        self.hosts = hosts
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validated_url(newurl, self.hosts)
        return super().redirect_request(req, fp, code, msg, headers, newurl)

def inspect_sample(body, content_type):
    text = body.decode('utf-8', errors='replace')
    if any(marker in text.lower() for marker in ('_incapsula_resource', 'cf-chl-', 'awswaf', 'goku_props', '<title>just a moment', 'checking your browser')):
        return 'blocked', 'network error: browser challenge returned instead of data'
    try:
        parsed = json.loads(text)
    except ValueError:
        parsed = None
    if isinstance(parsed, dict) and parsed.get('error'):
        return 'api_error', 'endpoint returned an API error in its response body'
    return 'reachable', None

def check_endpoint(row, hosts):
    url = row.get('direct_endpoint') or row['url']
    start = time.monotonic()
    result = dict(source_url=url, publisher=row['owner'], licence=row['licence'], latest_data=row['latest_data'],
                  retrieved_at=utc_now(), retrieval_kind='live_get', id=row['id'], name=row['name'],
                  http_status=None, status='unavailable', timeout_seconds=TIMEOUT)
    try:
        validated_url(url, hosts)
        request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (TheColab public catalogue check)', 'Accept': '*/*', 'Accept-Encoding': 'identity'}, method='GET')
        opener = urllib.request.build_opener(CheckedRedirect(hosts))
        with opener.open(request, timeout=TIMEOUT) as response:
            body = response.read(SAMPLE_BYTES)
            result.update(http_status=response.status, final_url=response.geturl(), content_type=response.headers.get('Content-Type'),
                          sample_bytes=len(body), sample_limit_bytes=SAMPLE_BYTES, sample_may_be_truncated=len(body) == SAMPLE_BYTES)
        status, error = inspect_sample(body, result['content_type'])
        result['status'] = status
        if error:
            result['error'] = error
        code = 4 if status == 'blocked' else 6 if status == 'api_error' else 0
    except urllib.error.HTTPError as exc:
        result.update(http_status=exc.code, status='blocked' if exc.code in (401, 403, 406, 429, 451) else 'http_error', error=f'network error: HTTP {exc.code}')
        if exc.code == 429:
            result['retry_after'] = exc.headers.get('Retry-After')
        exc.close()
        code = 4 if result['status'] == 'blocked' else 5
    except CatalogueError as exc:
        result.update(status='unsupported', error=str(exc))
        code = exc.code
    except (urllib.error.URLError, OSError, TimeoutError, ValueError) as exc:
        # Lower-level exception messages can expose proxy credentials; use the type only.
        result['error'] = f'network error: endpoint unavailable ({type(exc).__name__})'
        code = 5
    result['elapsed_seconds'] = round(time.monotonic() - start, 3)
    return result, code

def positive_int(value):
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError('must be a whole number')
    if not 1 <= number <= 500:
        raise argparse.ArgumentTypeError('must be between 1 and 500')
    return number

def result_envelope(payload, code, argv):
    """Retain provenance and place command results in the repo's common envelope."""
    result = dict(payload)
    result['source'] = {'name': payload['publisher'] or 'Unknown publisher',
                        'url': payload['source_url'], 'retrieved_at': payload['retrieved_at']}
    result['query'] = {'argv': list(argv)}
    result['data'] = {key: result.pop(key) for key in ('command', 'records', 'total', 'returned', 'truncated', 'stats', 'check') if key in result}
    result.setdefault('warnings', [])
    result['blocked'] = code == 4
    if code:
        result['error'] = {'code': code, 'message': str(payload['error'])}
    return result

class CatalogueParser(argparse.ArgumentParser):
    def error(self, message):
        if '--json' in sys.argv[1:]:
            payload = dict(schema_version='1', ok=False, exit_code=2, error=message,
                                  source_url=SOURCE_URL, publisher='TheColab', licence=None,
                                  retrieved_at=utc_now(), latest_data=None, retrieval_kind='bundled_catalogue')
            print(json.dumps(result_envelope(payload, 2, sys.argv[1:])))
            raise SystemExit(2)
        super().error(message)

def parser():
    root = CatalogueParser(description=__doc__)
    sub = root.add_subparsers(dest='command', required=True)
    for command in ('search', 'filter', 'get', 'stats', 'top', 'check'):
        p = sub.add_parser(command)
        p.add_argument('--json', action='store_true', help='emit JSON with provenance')
        if command == 'search':
            p.add_argument('text')
        if command in ('get', 'check'):
            p.add_argument('id')
        if command in ('search', 'filter'):
            p.add_argument('--limit', type=positive_int, default=20)
        if command in ('filter', 'top'):
            p.add_argument('--problem', type=str.upper, choices=PROBLEMS, required=command == 'top')
        if command == 'filter':
            for name in ('category', 'scope', 'access', 'type', 'owner'):
                p.add_argument('--' + name, help='case-insensitive substring')
            p.add_argument('--grade', type=str.upper, choices=list('ABCDE'), action='append')
            p.add_argument('--auckland', nargs='?', const='yes', choices=('yes', 'no', 'partial', 'unknown'))
        if command == 'top':
            p.add_argument('--n', type=positive_int, default=10)
    return root

def human_output(payload):
    if 'records' in payload:
        print(f"{payload['total']} matching sources; {payload['returned']} shown")
        for row in payload['records']:
            routes = ', '.join(f"{s['skill']} ({s['status']}; {s['relationship']}; auth: {s['auth']})" for s in row['fetch_skills']) or 'no mapped skill'
            flag = ' [NOT DATA]' if row['not_data'] else ''
            if row['credential_redacted']:
                flag += ' [CREDENTIAL PLACEHOLDER]'
            print(f"{row['id']} [{row['grade']} {row['score']:.2f}] {row['name']}{flag}")
            print(f"  {row['scope']} | {row['access']} | {row['agent_check']} | {routes}")
            print(f"  {row['source_url']}")
            if payload['command'] == 'get':
                for field in ('why_useful', 'latest_data', 'licence', 'caveat', 'records_size'):
                    print(f"  {field}: {row.get(field)}")
    elif 'check' in payload:
        result = payload['check']
        print(f"{result['id']}: {result['status']} (HTTP {result['http_status']}) — {result['source_url']}")
        if result.get('error'):
            print(result['error'])
    elif 'stats' in payload:
        print(json.dumps(payload['stats'], indent=2, ensure_ascii=False))
    else:
        print(payload['error'], file=sys.stderr)

def main(argv=None):
    args = parser().parse_args(argv)
    now = utc_now()
    payload = dict(schema_version='1', ok=True, command=args.command, source_url=SOURCE_URL, publisher='TheColab',
                   licence=None, latest_data=None, retrieved_at=now, retrieval_kind='bundled_catalogue', warnings=[])
    code = 0
    try:
        catalogue = load_catalogue()
        records = catalogue['records']
        skill_map = json.loads((ROOT / 'references/skill-map.json').read_text(encoding='utf-8'))
        payload['catalogue'] = {k: v for k, v in catalogue['metadata'].items() if k != 'allowed_domains'}
        if args.command in ('get', 'check'):
            selected = [r for r in records if r['id'].casefold() == args.id.casefold()]
            if not selected:
                raise CatalogueError(f'unknown catalogue id: {args.id}', 2)
            if args.command == 'check':
                result, code = check_endpoint(selected[0], set(catalogue['metadata']['allowed_domains']))
                payload.update({k: result[k] for k in ('source_url', 'publisher', 'licence', 'latest_data', 'retrieved_at', 'retrieval_kind')})
                payload['check'] = dict(result, fetch_skills=mapped_skills(selected[0], skill_map))
                payload['warnings'].append('GET reachability and a bounded sample do not verify dataset completeness, correctness or freshness.')
                if code:
                    payload['error'] = result['error']
        elif args.command == 'stats':
            stats = dict(total=len(records), not_data=sum(r['not_data'] for r in records))
            for field in ('grade', 'agent_check', 'category', 'scope', 'access', 'data_type', 'covers_auckland'):
                stats[field] = dict(sorted(collections.Counter(r[field] or 'unknown' for r in records).items()))
            stats['problem_tags'] = {p: sum(p in r['problem_tags'] for r in records) for p in PROBLEMS}
            stats['with_mapped_skill'] = sum(bool(mapped_skills(r, skill_map)) for r in records)
            payload['stats'] = stats
        elif args.command == 'search':
            selected = ranked_search(records, args.text)
        else:
            selected = filter_records(records, args)
            if args.command == 'top':
                selected = [r for r in selected if not r['not_data']]
                payload['warnings'].append('Top excludes Not data rows; scores are the supplied hackathon assessments, not new live verification.')
            selected.sort(key=lambda r: (-r['score'], r['id']))
        if args.command not in ('stats', 'check'):
            limit = getattr(args, 'limit', getattr(args, 'n', 1))
            payload.update(total=len(selected), returned=min(len(selected), limit), truncated=len(selected) > limit,
                           records=[enrich(r, skill_map, now) for r in selected[:limit]])
    except CatalogueError as exc:
        code = exc.code
        payload['error'] = str(exc)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        code = 6
        payload['error'] = f'catalogue read/schema error ({type(exc).__name__}); rebuild the index'
    payload['ok'] = code == 0
    if code:
        payload['exit_code'] = code
    if args.json:
        print(json.dumps(result_envelope(payload, code, argv if argv is not None else sys.argv[1:]), ensure_ascii=False, indent=2, allow_nan=False))
    else:
        human_output(payload)
    return code

if __name__ == '__main__':
    raise SystemExit(main())
